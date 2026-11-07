"""The three contenders and how one call is made. Live calls happen here and nowhere else in the project's tests.

    gemini_fast      GEMINI_MODEL_FAST      (flash-lite class)   Interactions API unless GEMINI_API says otherwise
    gemini_accurate  GEMINI_MODEL_ACCURATE  (flash class)
    openai_fast      OPENAI_MODEL_FAST      through OpenAIProvider.vision with the same prompt and closed schema

Model ids come only from the environment. Two call paths:

* direct       `point_desc`: pointing by a plain description, straight on the provider (sandbox screenshots only);
* production   `point_step`, `glance`, `verify`: through the privacy track's `egress.send_image` with a one-step port, exactly the
               path real frames take (gate, closed schema, ledger row before the send; here the gate source is `sandbox`).

Every call is timed here (wall clock around the provider call, 30 s hard cap so the latency tail is visible; the 6 s pointing
deadline is applied afterwards in the analysis). Image bytes are only ever passed to the provider; the result records the answer,
tokens, latency and cost estimate.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

BENCH_TIMEOUT_S = 30.0
EST_COST_PER_CALL = {"gemini_fast": 0.0012, "gemini_accurate": 0.0040, "openai_fast": 0.0040}   # conservative, for the guard only
NAMES = ("gemini_fast", "gemini_accurate", "openai_fast")


@dataclass
class Out:
    ok: bool
    error_kind: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None       # visible
    thought_tokens: int | None
    cost_usd: float | None
    value: dict[str, Any] | None    # the closed answer exactly as the model gave it (validated against the closed schema)

    def as_row(self) -> dict[str, Any]:
        return {"ok": self.ok, "error_kind": self.error_kind, "latency_ms": self.latency_ms, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "thought_tokens": self.thought_tokens, "cost_usd": self.cost_usd, "value": self.value}


class Contender:
    def __init__(self, name: str) -> None:
        if name not in NAMES:
            raise ValueError(name)
        self.name = name
        self.provider = "openai" if name.startswith("openai") else "gemini"
        self.tier = "accurate" if name == "gemini_accurate" else "fast"
        self._p: Any = None
        self._backend: Any = None

    # ---- configuration (read from the environment, never guessed)
    def _provider(self) -> Any:
        if self._p is None:
            if self.provider == "gemini":
                from understudy_agent.models.gemini_provider import GeminiProvider

                self._p = GeminiProvider(timeout_s=BENCH_TIMEOUT_S)
            else:
                from understudy_agent.models.openai_provider import OpenAIProvider

                self._p = OpenAIProvider(timeout_s=BENCH_TIMEOUT_S)
        return self._p

    @property
    def model(self) -> str:
        if self.provider == "gemini":
            return os.environ.get("GEMINI_MODEL_FAST" if self.tier == "fast" else "GEMINI_MODEL_ACCURATE", "").strip()
        return os.environ.get("OPENAI_MODEL_FAST", "").strip()

    @property
    def api(self) -> str:
        if self.provider == "gemini":
            return os.environ.get("GEMINI_API", "").strip().lower() or "interactions"
        return "responses"

    @property
    def thinking(self) -> str:
        if self.provider == "gemini":
            from understudy_agent.models.gemini_provider import _thinking_for

            return str(_thinking_for(self.tier))
        from understudy_agent.models.config import effort_for

        return f"effort={effort_for('vision')}"

    def est_cost(self) -> float:
        return EST_COST_PER_CALL[self.name]

    # ---- one call
    def call(self, kind: str, jpeg: bytes, *, desc: str = "", step: str = "", check: str = "page_shows_result") -> Out:
        if kind == "point_desc":
            return self._direct_point(jpeg, desc)
        return self._via_egress(kind, jpeg, step=step, check=check)

    def _usage(self, started: float) -> tuple[int, int | None, int | None, int | None, float | None]:
        ms = round((time.perf_counter() - started) * 1000)
        lc = self._provider().last_call or {}
        thought = lc.get("thought_tokens") or 0
        out = lc.get("output_tokens")
        return ms, lc.get("input_tokens"), (None if out is None else out - thought), thought, lc.get("cost_estimate_usd")

    def _direct_point(self, jpeg: bytes, desc: str) -> Out:
        from understudy_agent.models import prompts
        from understudy_agent.models.schemas import POINT_SCHEMA

        p = self._provider()
        prompt = prompts.point_prompt(desc)
        started = time.perf_counter()
        try:
            if self.provider == "gemini":
                raw = p.vision(jpeg, prompt, POINT_SCHEMA, tier=self.tier, thinking=True, timeout_s=BENCH_TIMEOUT_S)
            else:
                raw = p.vision(jpeg, prompt, POINT_SCHEMA, timeout_s=BENCH_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001
            from understudy_agent.models.routing import _error_kind

            return Out(False, _error_kind(e), round((time.perf_counter() - started) * 1000), None, None, None, None, None)
        ms, tin, tout, think, cost = self._usage(started)
        return Out(True, None, ms, tin, tout, think, cost, raw)

    def _via_egress(self, kind: str, jpeg: bytes, *, step: str, check: str) -> Out:
        import understudy_engine.awareness.purposes  # noqa: F401  (registers the `awareness.glance` image purpose)
        from understudy_engine.privacy import egress
        from understudy_engine.privacy.image import ImageGate, SafeImage

        from understudy_agent.models.routing import GeminiBackend, OpenAIBackend, StepPort

        role, purpose, img_kind, payload = {
            "point_step": ("point", "point.element", "point", {"step": step}),
            "glance": ("glance", "awareness.glance", "glance", {"trigger": "stuck", "app_kind": "browser"}),
            "verify": ("verify", "verify.agent_run", "verify", {"check": check}),
        }[kind]
        if self._backend is None:
            self._backend = GeminiBackend(provider_obj=self._provider()) if self.provider == "gemini" else OpenAIBackend(
                provider_obj=self._provider())
        port = StepPort(self._backend, self.tier, role, thinking=True, timeout_s=BENCH_TIMEOUT_S)
        gate = ImageGate(consent=False, denylisted_app=False, secure_input=False, unattended=True, source="sandbox")
        try:
            res = egress.send_image(purpose, SafeImage(jpeg, img_kind, source="sandbox"), payload, gate=gate, port=port)
        except egress.ModelCallFailed:
            return Out(False, port.error_kind or "api", port.latency_ms, None, None, None, None, None)
        except egress.ModelOutputRejected:
            o = port.out
            return Out(False, "schema", port.latency_ms, o.input_tokens if o else None, o.output_tokens if o else None,
                       o.thought_tokens if o else None, None, None)
        o = port.out
        assert o is not None
        return Out(True, None, port.latency_ms, o.input_tokens, o.output_tokens, o.thought_tokens,
                   (port.last_call or {}).get("cost_estimate_usd"), res.output)


def check_environment() -> dict[str, str]:
    """Model ids and API for the report's meta block; raises ConfigError (naming the variable) when one is missing."""
    from understudy_agent.models.config import ConfigError

    need = ("GEMINI_MODEL_FAST", "GEMINI_MODEL_ACCURATE", "OPENAI_MODEL_FAST")
    missing = [k for k in need if not os.environ.get(k, "").strip()]
    if missing:
        raise ConfigError("the bake-off needs " + ", ".join(missing) + " in the environment (run with --env-file .env)")
    return {c: Contender(c).model for c in NAMES}
