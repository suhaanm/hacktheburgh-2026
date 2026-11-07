"""Role routing by code (REQ-5 phase C): which provider and tier answers which role, when to escalate, when to fall back.

No model decides any of this. The table is DATA (`DEFAULT_ROLES`, overridable by a `models.yaml` named in
`UNDERSTUDY_MODELS_YAML`), and the bake-off report (`evals/modelbench/REPORT.md`) is what the lead reads before changing it.

A role has an ordered list of steps. `when` says when a step runs:

    primary    always (the first step)
    escalate   only when the previous step's answer was weak: not found, confidence under `confidence_below`, a schema failure
               or a timeout (each switchable). Escalation stays inside the role's hard deadline.
    fallback   only when no earlier step produced a valid answer because of a provider failure (error, open breaker, not configured)

Deterministic safety nets: a hard deadline per role call (pointing: 6 s, as in the old project), a per-call timeout, one circuit
breaker per provider (3 failures in 60 s open it for 60 s, then one probe), and a meter record for every call (role, provider,
model, latency, tokens, cost estimate, ok). Before an image leaves, an egress record is written; if that fails the call is not made
and `EgressBlocked` is raised (fail closed). Image bytes appear in none of these records.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

import yaml

from .breaker import CircuitBreaker
from .config import GeminiModelIds, ModelIds, gemini_ids_from_env_or_none, gemini_key_present, model_ids_from_env_or_none
from .egress import EgressBlocked, EgressEvent, EgressFn, ledger_egress
from .errors import ConfigError, ModelRefusal, ProviderError, SchemaViolation
from .gemini_http import GeminiHTTPError
from .meter import CallRecord, Meter, default_meter_path
from .prices import cost_estimate
from .safe_image import SafeImage
from .schemas import (GLANCE_SCHEMA, POINT_SCHEMA, VERIFY_SCHEMA, GlanceResult, PointResult, parse_glance, parse_point)
from . import prompts

When = Literal["primary", "escalate", "fallback"]
Outcome = Literal["answered", "timeout", "unavailable", "error"]
ROLE_NAMES = ("point", "glance", "verify_screen")


@dataclass(frozen=True)
class Step:
    provider: str                   # gemini | openai
    tier: str                       # fast | accurate
    when: When = "primary"
    thinking: str | None | bool = True   # True = the provider's default for the tier


@dataclass(frozen=True)
class RoleRoute:
    role: str
    steps: tuple[Step, ...]
    confidence_below: float = 0.7   # escalate when confidence is under this (0 turns it off)
    escalate_not_found: bool = True
    escalate_schema_failure: bool = True
    escalate_timeout: bool = True
    call_timeout_s: float = 6.0     # one call
    deadline_s: float | None = 6.0  # the whole role call, escalation included


def _default_roles() -> dict[str, RoleRoute]:
    gemini_then_openai = lambda: (  # noqa: E731
        Step("gemini", "fast", "primary"), Step("gemini", "accurate", "escalate"), Step("openai", "fast", "fallback"))
    return {
        # Pointing: flash-lite first, flash when not found / unsure / broken / slow, OpenAI fast with the same box prompt as the safety net.
        "point": RoleRoute("point", gemini_then_openai(), confidence_below=0.7, call_timeout_s=6.0, deadline_s=6.0),
        # Glance: the enums are a feature for the statistical layer, not a decision; escalate only on a broken or slow answer.
        "glance": RoleRoute("glance", gemini_then_openai(), confidence_below=0.0, escalate_not_found=False,
                            call_timeout_s=8.0, deadline_s=12.0),
        # Independent screen verifier: another model family from the OpenAI actor; an unsure answer escalates, never ticks.
        "verify_screen": RoleRoute("verify_screen", gemini_then_openai(), confidence_below=0.7, escalate_not_found=False,
                                   call_timeout_s=10.0, deadline_s=14.0),
    }


DEFAULT_ROLES: dict[str, RoleRoute] = _default_roles()


@dataclass(frozen=True)
class RoutingConfig:
    roles: dict[str, RoleRoute] = field(default_factory=_default_roles)
    breaker_failures: int = 3
    breaker_window_s: float = 60.0
    breaker_open_s: float = 60.0

    # ------------------------------------------------------------------ (de)serialisation: the config is data
    @classmethod
    def from_dict(cls, d: dict[str, Any], *, base: "RoutingConfig | None" = None) -> "RoutingConfig":
        base = base or cls()
        roles = dict(base.roles)
        for name, rd in (d.get("roles") or {}).items():
            if name not in ROLE_NAMES:
                raise ConfigError(f"unknown role {name!r} in routing config; known: {', '.join(ROLE_NAMES)}")
            steps = []
            for sd in rd.get("steps") or []:
                prov, tier, when = str(sd.get("provider", "")), str(sd.get("tier", "")), str(sd.get("when", "primary"))
                if prov not in ("gemini", "openai") or tier not in ("fast", "accurate") or when not in ("primary", "escalate", "fallback"):
                    raise ConfigError(f"bad step in routing role {name!r}: {sd!r}")
                steps.append(Step(prov, tier, when, sd.get("thinking", True)))  # type: ignore[arg-type]
            if not steps or steps[0].when != "primary":
                raise ConfigError(f"routing role {name!r} must start with a primary step")
            esc = rd.get("escalate") or {}
            prev = base.roles.get(name)
            roles[name] = RoleRoute(
                role=name, steps=tuple(steps),
                confidence_below=float(esc.get("confidence_below", prev.confidence_below if prev else 0.7)),
                escalate_not_found=bool(esc.get("not_found", prev.escalate_not_found if prev else True)),
                escalate_schema_failure=bool(esc.get("schema_failure", True)),
                escalate_timeout=bool(esc.get("timeout", True)),
                call_timeout_s=float(rd.get("call_timeout_s", prev.call_timeout_s if prev else 6.0)),
                deadline_s=(None if rd.get("deadline_s", "x") is None else float(rd.get("deadline_s", prev.deadline_s if prev else 6.0))),
            )
        b = d.get("breaker") or {}
        return cls(roles=roles, breaker_failures=int(b.get("failures", base.breaker_failures)),
                   breaker_window_s=float(b.get("window_s", base.breaker_window_s)),
                   breaker_open_s=float(b.get("open_s", base.breaker_open_s)))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RoutingConfig":
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as e:
            raise ConfigError(f"cannot read routing config ({type(e).__name__})") from None
        if not isinstance(raw, dict):
            raise ConfigError("routing config must be a mapping")
        return cls.from_dict(raw)

    @classmethod
    def from_env(cls) -> "RoutingConfig":
        p = os.environ.get("UNDERSTUDY_MODELS_YAML", "").strip()
        return cls.from_yaml(p) if p else cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "breaker": {"failures": self.breaker_failures, "window_s": self.breaker_window_s, "open_s": self.breaker_open_s},
            "roles": {
                n: {
                    "steps": [{"provider": s.provider, "tier": s.tier, "when": s.when, **({} if s.thinking is True else {"thinking": s.thinking})}
                              for s in r.steps],
                    "escalate": {"not_found": r.escalate_not_found, "confidence_below": r.confidence_below,
                                 "schema_failure": r.escalate_schema_failure, "timeout": r.escalate_timeout},
                    "call_timeout_s": r.call_timeout_s, "deadline_s": r.deadline_s,
                } for n, r in self.roles.items()
            },
        }

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


# ---------------------------------------------------------------------------------------------------------- backends
@dataclass
class BackendOut:
    value: Any                      # PointResult | GlanceResult | dict (verify)
    input_tokens: int | None
    output_tokens: int | None       # visible
    thought_tokens: int | None
    api: str | None = None


class Backend(Protocol):
    provider: str

    def available(self) -> bool: ...
    def model_for(self, tier: str) -> str: ...
    def call(self, role: str, tier: str, image: SafeImage, *, text: str, thinking: str | None | bool, timeout_s: float) -> BackendOut: ...


class GeminiBackend:
    provider = "gemini"

    def __init__(self, factory: Callable[[], Any] | None = None, provider_obj: Any | None = None) -> None:
        self._factory, self._p = factory, provider_obj
        self._lock = threading.Lock()

    def _provider(self) -> Any:
        with self._lock:
            if self._p is None:
                if self._factory is None:
                    from .gemini_provider import GeminiProvider

                    self._p = GeminiProvider()
                else:
                    self._p = self._factory()
            return self._p

    def available(self) -> bool:
        if self._p is not None:
            return True
        return gemini_key_present() and gemini_ids_from_env_or_none() is not None

    def model_for(self, tier: str) -> str:
        if self._p is not None:
            return self._p.model_for(tier)
        ids = gemini_ids_from_env_or_none()
        return getattr(ids, tier, "") if ids else ""

    def call(self, role: str, tier: str, image: SafeImage, *, text: str, thinking: str | None | bool, timeout_s: float) -> BackendOut:
        p = self._provider()
        if role == "point":
            v: Any = p.point(image, text, tier=tier, thinking=thinking, timeout_s=timeout_s)
        elif role == "glance":
            v = p.glance(image, tier=tier, thinking=thinking, timeout_s=timeout_s)
        elif role == "verify_screen":
            v = p.verify_screen(image, text, tier=tier, thinking=thinking, timeout_s=timeout_s)
        else:  # pragma: no cover - guarded by ROLE_NAMES
            raise ProviderError(f"unknown role {role!r}")
        lc = p.last_call or {}
        return BackendOut(v, lc.get("input_tokens"), (lc.get("output_tokens") or 0) - (lc.get("thought_tokens") or 0)
                          if lc.get("output_tokens") is not None else None, lc.get("thought_tokens"), lc.get("api"))


class OpenAIBackend:
    """OpenAI fast with the same prompts and closed schemas, through `OpenAIProvider.vision` (strict structured output)."""

    provider = "openai"

    def __init__(self, factory: Callable[[], Any] | None = None, provider_obj: Any | None = None) -> None:
        self._factory, self._p = factory, provider_obj
        self._lock = threading.Lock()

    def _provider(self) -> Any:
        with self._lock:
            if self._p is None:
                if self._factory is None:
                    from .openai_provider import OpenAIProvider

                    self._p = OpenAIProvider()
                else:
                    self._p = self._factory()
            return self._p

    def available(self) -> bool:
        if self._p is not None:
            return True
        return bool(os.environ.get("OPENAI_API_KEY", "").strip()) and model_ids_from_env_or_none() is not None

    def model_for(self, tier: str) -> str:
        if self._p is not None:
            return self._p.models.fast
        ids = model_ids_from_env_or_none()
        return ids.fast if ids else ""

    def call(self, role: str, tier: str, image: SafeImage, *, text: str, thinking: str | None | bool, timeout_s: float) -> BackendOut:
        p = self._provider()
        prompt, schema = {
            "point": (prompts.point_prompt(text), POINT_SCHEMA),
            "glance": (prompts.glance_prompt(), GLANCE_SCHEMA),
            "verify_screen": (prompts.verify_prompt(text), VERIFY_SCHEMA),
        }[role]
        raw = p.vision(image.data, prompt, schema, timeout_s=timeout_s)
        if role == "point":
            v: Any = parse_point(raw)
        elif role == "glance":
            v = parse_glance(raw)
        else:
            v = {"holds": bool(raw["holds"]), "confidence": float(max(0.0, min(1.0, raw.get("confidence", 0.0))))}
        lc = p.last_call or {}
        return BackendOut(v, lc.get("input_tokens"), lc.get("output_tokens"), 0, "responses")


# ---------------------------------------------------------------------------------------------------------- router
@dataclass
class Attempt:
    step: int
    provider: str
    tier: str
    model: str
    status: Literal["ok", "failed", "skipped"]
    error_kind: str | None = None
    skipped_reason: str | None = None
    latency_ms: int | None = None
    weak: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, False) or k == "status"}


@dataclass
class Routed:
    """What a routed call returns. `value` is a PointResult / GlanceResult / dict; `outcome` says whether anything answered."""

    value: Any
    outcome: Outcome
    weak: bool = False               # the answer came back but was below the confidence bar (no better step was left)
    escalated: bool = False
    attempts: list[Attempt] = field(default_factory=list)
    total_ms: int = 0

    @property
    def result(self) -> Any:
        return self.value


def _error_kind(e: Exception) -> str:
    if isinstance(e, GeminiHTTPError):
        return e.kind
    if isinstance(e, SchemaViolation):
        return "schema"
    if isinstance(e, ModelRefusal):
        return "refusal"
    msg = type(e).__name__.lower()
    if "timeout" in msg:
        return "timeout"
    if "ratelimit" in msg:
        return "rate_limit"
    if "authentication" in msg or "permission" in msg:
        return "auth"
    if "connection" in msg:
        return "network"
    return "api"


class ModelRouter:
    def __init__(self, *, config: RoutingConfig | None = None, backends: dict[str, Backend] | None = None,
                 meter: Meter | None = None, egress: EgressFn = ledger_egress,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config or RoutingConfig()
        self.backends: dict[str, Backend] = backends if backends is not None else {
            "gemini": GeminiBackend(), "openai": OpenAIBackend()}
        self.meter = meter if meter is not None else Meter()
        self.egress = egress
        self.clock = clock
        self.breakers: dict[str, CircuitBreaker] = {
            p: CircuitBreaker(failures=self.config.breaker_failures, window_s=self.config.breaker_window_s,
                              open_s=self.config.breaker_open_s, clock=clock) for p in ("gemini", "openai")}
        self.skips: dict[str, int] = {}

    @classmethod
    def from_env(cls, **kw: Any) -> "ModelRouter":
        meter = kw.pop("meter", None) or Meter(path=default_meter_path())
        return cls(config=kw.pop("config", None) or RoutingConfig.from_env(), meter=meter, **kw)

    # ------------------------------------------------------------------ public capabilities
    def point(self, image: SafeImage, description: str) -> Routed:
        return self._route("point", image, description, judge=self._judge_point)

    def glance(self, image: SafeImage) -> Routed:
        return self._route("glance", image, "", judge=self._judge_generic)

    def verify_screen(self, image: SafeImage, question: str) -> Routed:
        return self._route("verify_screen", image, question, judge=self._judge_generic)

    # ------------------------------------------------------------------ weakness rules (deterministic)
    # judge(route, value) -> (escalate, low_confidence). `escalate` triggers the next escalation step (a not-found answer escalates
    # for pointing); `low_confidence` is what `Routed.weak` reports about the FINAL answer.
    @staticmethod
    def _low(route: RoleRoute, conf: float) -> bool:
        return route.confidence_below > 0 and conf < route.confidence_below

    @classmethod
    def _judge_point(cls, route: RoleRoute, v: PointResult) -> tuple[bool, bool]:
        low = cls._low(route, v.confidence)
        return (route.escalate_not_found if not v.found else low), low

    @classmethod
    def _judge_generic(cls, route: RoleRoute, v: Any) -> tuple[bool, bool]:
        conf = v.confidence if hasattr(v, "confidence") else float(v.get("confidence", 1.0))
        low = cls._low(route, conf)
        return low, low

    # ------------------------------------------------------------------ the loop
    def _skip(self, attempts: list[Attempt], i: int, step: Step, model: str, reason: str) -> None:
        attempts.append(Attempt(i, step.provider, step.tier, model, "skipped", skipped_reason=reason))
        self.skips[reason] = self.skips.get(reason, 0) + 1

    def _route(self, role: str, image: SafeImage, text: str, *,
               judge: Callable[[RoleRoute, Any], tuple[bool, bool]]) -> Routed:
        if not isinstance(image, SafeImage):
            raise TypeError("images go to a model only as SafeImage")
        route = self.config.roles[role]
        t0 = self.clock()
        attempts: list[Attempt] = []
        answer: Any = None            # latest valid answer
        answer_weak = False
        escalate_next = False         # the previous step asked for escalation (weak answer, schema failure or timeout)
        any_valid = False
        hard_failed: set[str] = set() # providers that failed hard in this request
        saw_timeout = False
        escalated = False
        ran_primary = False
        for i, step in enumerate(route.steps):
            elapsed = self.clock() - t0
            remaining = (route.deadline_s - elapsed) if route.deadline_s is not None else float("inf")
            backend = self.backends.get(step.provider)
            model = backend.model_for(step.tier) if backend is not None else ""
            if step.when == "escalate" and not (ran_primary and escalate_next):
                continue
            if step.when == "fallback" and any_valid:
                continue
            if step.provider in hard_failed and step.when != "fallback":
                self._skip(attempts, i, step, model, "provider_failed")
                continue
            if remaining < 0.25:
                self._skip(attempts, i, step, model, "deadline")
                saw_timeout = True
                break
            if backend is None or not backend.available():
                self._skip(attempts, i, step, model, "not_configured")
                continue
            breaker = self.breakers.setdefault(step.provider, CircuitBreaker(clock=self.clock))
            if not breaker.allow():
                self._skip(attempts, i, step, model, "breaker_open")
                hard_failed.add(step.provider)
                continue
            # the ledger line first; if it cannot be written the call is not made (EgressBlocked propagates)
            try:
                self.egress(EgressEvent(provider=step.provider, model=model, method=role, purpose=role, nbytes=image.nbytes,
                                        sha256_prefix=image.sha256_prefix, source=image.source))
            except EgressBlocked:
                breaker.cancel_probe()  # a ledger problem is not a provider failure; the breaker must not move
                raise
            if step.when in ("escalate",):
                escalated = True
            if step.when == "primary":
                ran_primary = True
            timeout = min(route.call_timeout_s, remaining)
            started = time.perf_counter()
            out: BackendOut | None = None
            err: Exception | None = None
            try:
                out = backend.call(role, step.tier, image, text=text, thinking=step.thinking, timeout_s=timeout)
            except EgressBlocked:
                raise
            except ConfigError as e:
                err = e
            except ProviderError as e:
                err = e
            except Exception as e:  # noqa: BLE001 - SDK errors (openai.*) arrive as themselves when raised outside the provider's wrap
                err = e
            ms = round((time.perf_counter() - started) * 1000)
            cost = None
            if out is not None:
                billed = None if out.output_tokens is None else out.output_tokens + (out.thought_tokens or 0)
                cost = cost_estimate(step.provider, step.tier, out.input_tokens, billed)
            kind = None if err is None else _error_kind(err)
            self.meter.record(CallRecord(
                role=role, provider=step.provider, model=model, tier=step.tier, method=role, ok=err is None, latency_ms=ms,
                input_tokens=out.input_tokens if out else None, output_tokens=out.output_tokens if out else None,
                thought_tokens=out.thought_tokens if out else None, cost_usd=cost, error_kind=kind,
                image_sha=image.sha256_prefix, step=i, api=out.api if out else None))
            if err is not None:
                # refusals are not outages; everything else counts toward the breaker
                if kind != "refusal":
                    breaker.record(False)
                attempts.append(Attempt(i, step.provider, step.tier, model, "failed", error_kind=kind, latency_ms=ms))
                if kind == "timeout":
                    saw_timeout = True
                    escalate_next = route.escalate_timeout
                elif kind == "schema":
                    escalate_next = route.escalate_schema_failure
                else:
                    escalate_next = False
                    hard_failed.add(step.provider)
                continue
            breaker.record(True)
            do_escalate, low = judge(route, out.value)
            attempts.append(Attempt(i, step.provider, step.tier, model, "ok", latency_ms=ms, weak=do_escalate))
            answer, answer_weak, any_valid = out.value, low, True
            escalate_next = do_escalate
            if not do_escalate:
                break
        total_ms = round((self.clock() - t0) * 1000)
        if any_valid:
            return Routed(answer, "answered", weak=answer_weak, escalated=escalated, attempts=attempts, total_ms=total_ms)
        outcome: Outcome = "timeout" if saw_timeout else ("unavailable" if all(a.status == "skipped" for a in attempts) else "error")
        return Routed(self._empty(role, outcome), outcome, escalated=escalated, attempts=attempts, total_ms=total_ms)

    @staticmethod
    def _empty(role: str, outcome: Outcome) -> Any:
        if role == "point":
            return PointResult(found=False, box_2d=None, confidence=0.0, reason=outcome)
        if role == "glance":
            return GlanceResult(app_kind="unknown", task_phase="unknown", blocker="unknown", confidence=0.0)
        return {"holds": False, "confidence": 0.0}   # an unsure or missing answer is never a tick

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        provs = {}
        for name, b in self.backends.items():
            br = self.breakers.get(name)
            provs[name] = {"available": bool(b.available()), "breaker": br.snapshot() if br else None,
                           "models": {t: b.model_for(t) for t in ("fast", "accurate")}}
        return {"providers": provs, "skips": dict(self.skips), "last_latencies_ms": self.meter.last_latencies(),
                "meter": self.meter.summary()}
