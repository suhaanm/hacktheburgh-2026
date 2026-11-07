"""Gemini provider (REQ-5 phase C): a real ModelPort next to OpenAI, plus the pointing, glance and screen-check capabilities.

Flag-gated: nothing imports this on the default path (`UNDERSTUDY_X_GEMINI` off). Model ids come only from the environment
(`GEMINI_MODEL_FAST`, `GEMINI_MODEL_ACCURATE`; `GEMINI_MODEL_LIVE` is only checked at boot). The key is read by `GeminiClient`
alone. Two tiers: `fast` (flash-lite class) and `accurate` (flash class); the router (routing.py) decides which to use, by code.

ModelPort:  plan (accurate), read / check / vision (fast), computer_step (not supported here: raises). `vision(image_bytes, prompt,
schema)` is what the privacy track's `egress.send_image` calls (the frame has already passed its gate, size and format checks);
`model_for(method)` names the model id for the ledger.
Direct capabilities for sandbox screenshots (the bake-off; real-screen frames go through `egress.send_image` and the router):
    point(image, description)      -> PointResult   {found, box_2d [ymin,xmin,ymax,xmax] 0..1000, confidence}
    glance(image)                  -> GlanceResult  {app_kind, task_phase, blocker enums, confidence, box_2d}
    verify_screen(image, question) -> {verdict: yes|no|unsure, confidence}
`image` is PNG or JPEG bytes. Response schemas are the privacy track's closed ones (schemas.py).

After every call `self.last_call = {input_tokens, output_tokens, cost_estimate_usd}` (output is billed output: visible plus thinking
tokens; `None` when unknown). It is thread-local, so concurrent callers each see their own call.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..security.sanitize import is_wrapped, sanitize_untrusted, wrap_untrusted
from . import coverage, prompts
from .config import GeminiModelIds
from .errors import ProviderError, SchemaViolation
from .gemini_http import GeminiClient, GeminiHTTPError, GeminiReply, Part
from .port import Action, Done, SafetyStop
from .prices import cost_estimate
from .schemas import (GLANCE_SCHEMA, POINT_SCHEMA, VERIFY_SCHEMA, GlanceResult, PointResult, parse_glance, parse_point,
                      parse_verify)
from .strict import validate_output

MAX_UNTRUSTED_CHARS = 60_000
DEFAULT_THINKING = {"fast": "low", "accurate": "low"}   # `minimal` is rejected by some flash models; `low` works on both classes
ENV_THINKING = {"fast": "GEMINI_THINKING_FAST", "accurate": "GEMINI_THINKING_ACCURATE"}


def _thinking_for(tier: str) -> str | None:
    v = os.environ.get(ENV_THINKING.get(tier, ""), "").strip() or DEFAULT_THINKING.get(tier, "low")
    return None if v.lower() == "unset" else v


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The caller's closed JSON schema in the shape the Gemini API takes: enum-only nodes get an explicit type."""
    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        out = {k: walk(v) for k, v in node.items()}
        if "enum" in out and "type" not in out and out["enum"]:
            kinds = {type(v).__name__ for v in out["enum"] if v is not None}
            out["type"] = {"str": "string", "bool": "boolean", "int": "integer", "float": "number"}.get(
                next(iter(kinds)), "string") if len(kinds) == 1 else "string"
        return out

    return walk(schema)


def _flatten(messages: list[dict[str, Any]]) -> tuple[str | None, str]:
    """ModelPort messages -> (system text, one user text). Text only; roles are kept as plain labels."""
    system: list[str] = []
    turns: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        c = m.get("content", "")
        if isinstance(c, list):
            c = "\n".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in c)
        if role in ("system", "developer"):
            system.append(str(c))
        elif role in ("user", "assistant"):
            turns.append(f"{role.upper()}: {c}" if len(messages) > 1 else str(c))
        else:
            raise ProviderError(f"unsupported message role: {role!r}")
    return ("\n".join(system) or None), "\n".join(turns)


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, client: GeminiClient | Any | None = None, models: GeminiModelIds | None = None,
                 timeout_s: float = 30.0, max_output_tokens: int = 1024) -> None:
        self.models = models or GeminiModelIds.from_env()
        self.client = client if client is not None else GeminiClient(timeout_s=timeout_s)
        self.max_output_tokens = max_output_tokens
        self._lock = threading.Lock()
        self._tls = threading.local()
        self.stats: dict[str, Any] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "by_role": {}}
        coverage.register(self)

    # ------------------------------------------------------------------ plumbing
    @property
    def last_call(self) -> dict[str, Any] | None:
        return getattr(self._tls, "last", None)

    @property
    def api(self) -> str:
        return str(getattr(self.client, "api", "unknown"))

    def model_for(self, key: str = "vision") -> str:
        """The model id for a tier (`fast`, `accurate`) or a port method (`vision`, `read`, `check`, `point`, `glance`,
        `verify_screen` use the fast tier; `plan` the accurate one)."""
        tier = {"plan": "accurate", "planner": "accurate"}.get(key, key)
        if tier in ("fast", "accurate"):
            return self.models.fast if tier == "fast" else self.models.accurate
        if tier in ("vision", "read", "check", "point", "glance", "verify_screen", "reader"):
            return self.models.fast
        raise ProviderError(f"unknown Gemini tier or method {key!r}")

    def _note(self, role: str, tier: str, reply: GeminiReply) -> None:
        out = reply.billed_output_tokens
        cost = cost_estimate("gemini", tier, reply.input_tokens, out)
        self._tls.last = {"input_tokens": reply.input_tokens, "output_tokens": out, "cost_estimate_usd": cost,
                          "thought_tokens": reply.thought_tokens, "latency_ms": reply.latency_ms, "model": reply.model,
                          "api": reply.api}
        with self._lock:
            self.stats["calls"] += 1
            self.stats["input_tokens"] += reply.input_tokens or 0
            self.stats["output_tokens"] += out or 0
            r = self.stats["by_role"].setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            r["calls"] += 1
            r["input_tokens"] += reply.input_tokens or 0
            r["output_tokens"] += out or 0

    def _structured(self, role: str, tier: str, parts: list[Part], schema: dict[str, Any] | None, *,
                    system: str | None, thinking: str | None | bool = True, timeout_s: float | None = None,
                    max_output_tokens: int | None = None) -> dict[str, Any]:
        self._tls.last = None
        think = _thinking_for(tier) if thinking is True else (thinking or None)
        reply = self.client.generate(self.model_for(tier), parts, system=system,
                                     schema=None if schema is None else gemini_schema(schema), thinking=think,
                                     max_output_tokens=max_output_tokens or self.max_output_tokens, timeout_s=timeout_s)
        self._note(role, tier, reply)
        if schema is None:
            return {"text": reply.text}
        try:
            obj = json.loads(reply.text)
        except json.JSONDecodeError:
            raise SchemaViolation("model did not return valid JSON") from None
        return validate_output(obj, schema)

    # ------------------------------------------------------------------ ModelPort
    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        system, text = _flatten(messages)
        return self._structured("planner", "accurate", [Part.text(text)], schema, system=system)

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Quarantined reader: raw untrusted content in, schema-checked fields out. No tools, nothing stored."""
        if not is_wrapped(untrusted):
            untrusted = wrap_untrusted(untrusted, max_chars=MAX_UNTRUSTED_CHARS)
        elif len(untrusted) > MAX_UNTRUSTED_CHARS + 500:
            untrusted = untrusted[: MAX_UNTRUSTED_CHARS + 500]
        parts = [Part.text("Extract the fields from the content below."), Part.text(untrusted)]
        return self._structured("reader", "fast", parts, schema, system=prompts.SYSTEM_READER)

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        safe = sanitize_untrusted(prompt, max_chars=20_000).text if not is_wrapped(prompt) else prompt
        return self._structured("fast", "fast", [Part.text(safe)], schema, system=prompts.SYSTEM_CHECK)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None, *, tier: str = "fast",
               thinking: str | None | bool = True, timeout_s: float | None = None) -> dict[str, Any]:
        """ModelPort vision: PNG or JPEG bytes (already gated by the caller) plus a prompt; the answer is validated against `schema`."""
        return self._structured("vision", tier, [Part.text(prompt), Part.image(image)], schema, system=prompts.SYSTEM_SCREEN,
                                thinking=thinking, timeout_s=timeout_s)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]],
                      *, session: str | None = None) -> Action | Done | SafetyStop:
        raise ProviderError("Gemini computer use is not wired in this provider (real clicks are frozen). Use OpenAI or mock.")

    # ------------------------------------------------------------------ direct capabilities (sandbox screenshots, the bake-off)
    def point(self, image: bytes, description: str, *, tier: str = "fast", thinking: str | None | bool = True,
              timeout_s: float | None = None) -> PointResult:
        raw = self._structured("point", tier, [Part.text(prompts.point_prompt(description)), Part.image(image)], POINT_SCHEMA,
                               system=prompts.SYSTEM_SCREEN, thinking=thinking, timeout_s=timeout_s, max_output_tokens=512)
        return parse_point(raw)

    def glance(self, image: bytes, *, tier: str = "fast", thinking: str | None | bool = True,
               timeout_s: float | None = None) -> GlanceResult:
        raw = self._structured("glance", tier, [Part.text(prompts.glance_prompt()), Part.image(image)], GLANCE_SCHEMA,
                               system=prompts.SYSTEM_SCREEN, thinking=thinking, timeout_s=timeout_s, max_output_tokens=512)
        return parse_glance(raw)

    def verify_screen(self, image: bytes, question: str, *, tier: str = "fast", thinking: str | None | bool = True,
                      timeout_s: float | None = None) -> dict[str, Any]:
        raw = self._structured("verify_screen", tier, [Part.text(prompts.verify_prompt(question)), Part.image(image)],
                               VERIFY_SCHEMA, system=prompts.SYSTEM_SCREEN, thinking=thinking, timeout_s=timeout_s,
                               max_output_tokens=256)
        return parse_verify(raw)


__all__ = ["GeminiProvider", "GeminiHTTPError", "DEFAULT_THINKING"]
