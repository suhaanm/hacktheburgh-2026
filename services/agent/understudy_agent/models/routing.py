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
model, latency, tokens, cost estimate, ok). Every image goes out through the privacy track's `egress.send_image` (one call per
step: gate, closed answer schema, ledger row before the send, tokens and cost recorded afterwards); if the gate refuses or the ledger
cannot be written, the privacy exception propagates and nothing is sent. Image bytes appear in none of these records.

The caller builds the privacy `SafeImage` (kind `point`, `glance` or `verify`) and the `ImageGate`; the router sends the SAME frame
to the escalation step (`release=False`) and wipes it once the role call is over. Pointing names a step by a fixed id
(`submit`, `next`, ...), glances and checks take fixed codes: the payloads are the privacy track's `SafePayload`s.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Protocol

import yaml

if TYPE_CHECKING:  # the privacy types are imported lazily so importing this module never loads the engine
    from understudy_engine.privacy.image import ImageGate, SafeImage

from .breaker import CircuitBreaker
from . import prompts
from .config import (gemini_flag_enabled, gemini_ids_from_env_or_none, gemini_key_present, mock_enabled,
                     model_ids_from_env_or_none)
from .errors import ConfigError, ModelRefusal, ProviderError, SchemaViolation
from .gemini_http import GeminiHTTPError
from .meter import CallRecord, Meter, default_meter_path
from .prices import cost_estimate
from .schemas import GlanceResult, PointResult, parse_glance, parse_point, parse_verify

When = Literal["primary", "escalate", "fallback"]
Outcome = Literal["answered", "timeout", "unavailable", "error", "blocked"]
ROLE_NAMES = ("point", "glance", "verify")
PURPOSE = {"point": "point.element", "glance": "awareness.glance", "verify": "verify.agent_run"}   # glance: the AWARENESS track's closed schema


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
        "verify": RoleRoute("verify", gemini_then_openai(), confidence_below=0.7, escalate_not_found=False,
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
    value: dict[str, Any]           # the validated answer (a closed schema)
    input_tokens: int | None
    output_tokens: int | None       # visible
    thought_tokens: int | None
    api: str | None = None


class Backend(Protocol):
    provider: str

    def available(self) -> bool: ...
    def model_for(self, tier: str) -> str: ...
    def vision(self, tier: str, image: bytes, prompt: str, schema: dict[str, Any], *, thinking: str | None | bool,
               timeout_s: float) -> BackendOut: ...


class _LazyBackend:
    provider = ""

    def __init__(self, factory: Callable[[], Any] | None = None, provider_obj: Any | None = None) -> None:
        self._factory, self._p = factory, provider_obj
        self._lock = threading.Lock()

    def _build(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def _provider(self) -> Any:
        with self._lock:
            if self._p is None:
                self._p = self._factory() if self._factory is not None else self._build()
            return self._p


class GeminiBackend(_LazyBackend):
    provider = "gemini"

    def _build(self) -> Any:
        from . import coverage
        from .gemini_provider import GeminiProvider

        return coverage.mark(GeminiProvider(), "egress")

    def available(self) -> bool:
        if self._p is not None:
            return True
        # flag-gated (REQ-5): with UNDERSTUDY_X_GEMINI off the router never reaches Gemini, even when a key and ids exist
        return gemini_flag_enabled() and gemini_key_present() and gemini_ids_from_env_or_none() is not None

    def model_for(self, tier: str) -> str:
        if self._p is not None:
            return self._p.model_for(tier)
        ids = gemini_ids_from_env_or_none()
        return getattr(ids, tier, "") if ids else ""

    def vision(self, tier: str, image: bytes, prompt: str, schema: dict[str, Any], *, thinking: str | None | bool,
               timeout_s: float) -> BackendOut:
        p = self._provider()
        raw = p.vision(image, prompt, schema, tier=tier, thinking=thinking, timeout_s=timeout_s)
        lc = p.last_call or {}
        out, thought = lc.get("output_tokens"), lc.get("thought_tokens") or 0
        return BackendOut(raw, lc.get("input_tokens"), None if out is None else out - thought, thought, lc.get("api"))


class OpenAIBackend(_LazyBackend):
    """OpenAI fast with the same prompts and closed schemas, through `OpenAIProvider.vision` (strict structured output)."""

    provider = "openai"

    def _build(self) -> Any:
        from . import coverage
        from .openai_provider import OpenAIProvider

        return coverage.mark(OpenAIProvider(), "egress")

    def available(self) -> bool:
        if self._p is not None:
            return True
        return bool(os.environ.get("OPENAI_API_KEY", "").strip()) and model_ids_from_env_or_none() is not None

    def model_for(self, tier: str) -> str:
        if self._p is not None:
            return self._p.models.fast
        ids = model_ids_from_env_or_none()
        return ids.fast if ids else ""

    def vision(self, tier: str, image: bytes, prompt: str, schema: dict[str, Any], *, thinking: str | None | bool,
               timeout_s: float) -> BackendOut:
        p = self._provider()
        raw = p.vision(image, prompt, schema, timeout_s=timeout_s)
        lc = p.last_call or {}
        return BackendOut(raw, lc.get("input_tokens"), lc.get("output_tokens"), 0, "responses")


def _error_kind(e: BaseException) -> str:
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


class StepPort:
    """A one-step `ModelPort` for `egress.send_image`: pins the provider, tier, thinking level and timeout of one routing step and
    keeps what the router needs afterwards (error kind, latency, tokens). The privacy track's guard calls `vision(bytes, prompt,
    schema)`, `model_for("vision")` and reads `last_call`; the failure is re-raised as is (the guard records only its type)."""

    offline = False

    def __init__(self, backend: Backend, tier: str, role: str, *, thinking: str | None | bool, timeout_s: float) -> None:
        self.backend, self.tier, self.role, self.thinking, self.timeout_s = backend, tier, role, thinking, timeout_s
        self.name = backend.provider
        self._model = backend.model_for(tier)
        self.last_call: dict[str, Any] | None = None
        self.error_kind: str | None = None
        self.latency_ms: int | None = None
        self.out: BackendOut | None = None

    def model_for(self, method: str = "vision") -> str:
        return self._model

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        if schema is None:
            raise ProviderError("a routed screen call needs a response schema")
        started = time.perf_counter()
        try:
            out = self.backend.vision(self.tier, image, prompts.format_note(self.role) + prompt, schema,
                                      thinking=self.thinking, timeout_s=self.timeout_s)
        except BaseException as e:  # noqa: BLE001 - classify, then re-raise unchanged
            self.latency_ms = round((time.perf_counter() - started) * 1000)
            self.error_kind = _error_kind(e)
            raise
        self.latency_ms = round((time.perf_counter() - started) * 1000)
        self.out = out
        billed = None if out.output_tokens is None else out.output_tokens + (out.thought_tokens or 0)
        self.last_call = {"input_tokens": out.input_tokens, "output_tokens": billed,
                          "cost_estimate_usd": cost_estimate(self.name, self.tier, out.input_tokens, billed)}
        return out.value


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
    """What a routed call returns. `value` is a PointResult / GlanceResult / verdict dict; `outcome` says whether anything answered
    (`blocked`: a gate, ledger or request check refused and `stopped` carries what the caller should return)."""

    value: Any
    outcome: Outcome
    weak: bool = False               # the answer came back but its confidence is under the role's bar
    escalated: bool = False
    attempts: list[Attempt] = field(default_factory=list)
    total_ms: int = 0
    stopped: Any = None

    @property
    def result(self) -> Any:
        return self.value


class StepFail(Exception):
    """One routing step failed as a provider (not a gate): `kind` is timeout, schema, auth, rate_limit, network, api, refusal ..."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class StepStop(Exception):
    """A gate, ledger or request check refused: nothing was sent, routing ends, `payload` is what the caller returns."""

    def __init__(self, payload: Any = None) -> None:
        super().__init__("stopped")
        self.payload = payload


_PARSE = {"point": parse_point, "glance": lambda raw: parse_glance(raw, check_enums=False), "verify": parse_verify}
Invoke = Callable[[Step, StepPort], Any]


class ModelRouter:
    def __init__(self, *, config: RoutingConfig | None = None, backends: dict[str, Backend] | None = None,
                 meter: Meter | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config or RoutingConfig()
        self.backends: dict[str, Backend] = backends if backends is not None else {
            "gemini": GeminiBackend(), "openai": OpenAIBackend()}
        self.meter = meter if meter is not None else Meter()
        self.clock = clock
        self.breakers: dict[str, CircuitBreaker] = {
            p: CircuitBreaker(failures=self.config.breaker_failures, window_s=self.config.breaker_window_s,
                              open_s=self.config.breaker_open_s, clock=clock) for p in ("gemini", "openai")}
        self.skips: dict[str, int] = {}

    @classmethod
    def from_env(cls, **kw: Any) -> "ModelRouter":
        meter = kw.pop("meter", None) or Meter(path=default_meter_path())
        return cls(config=kw.pop("config", None) or RoutingConfig.from_env(), meter=meter, **kw)

    # ------------------------------------------------------------------ public capabilities (privacy SafeImage + ImageGate)
    def point(self, image: "SafeImage", step: str, *, gate: "ImageGate") -> Routed:
        """Find the control for a fixed step id (the privacy track's `point.step` vocabulary: submit, next, back, ...)."""
        return self._route_image("point", image, {"step": step}, gate, judge=self._judge_point)

    def glance(self, image: "SafeImage", *, gate: "ImageGate", trigger: str = "stuck", app_kind: str = "unknown") -> Routed:
        """Classify a screen with the AWARENESS track's closed schema (`awareness.glance`)."""
        return self._route_image("glance", image, {"trigger": trigger, "app_kind": app_kind}, gate, judge=self._judge_generic)

    def verify(self, image: "SafeImage", check: str, *, gate: "ImageGate") -> Routed:
        """One fixed check on a screenshot (`page_shows_result`, `error_visible`, ...): verdict yes, no or unsure."""
        return self._route_image("verify", image, {"check": check}, gate, judge=self._judge_verify)

    def route_with(self, role: str, invoke: Invoke, *, image_sha: str | None = None, route: RoleRoute | None = None) -> Routed:
        """Routing for a caller that owns the egress call (the AWARENESS glance handler, the cue grounder): `invoke(step, port)` makes
        ONE ledgered send through `port` and returns the closed answer; it raises `StepFail(kind)` for a provider failure or a
        refused answer and `StepStop(payload)` when a gate, the ledger or a request check refused (routing ends, nothing more is sent)."""
        judge = {"point": self._judge_point, "glance": self._judge_generic, "verify": self._judge_verify}.get(role, self._judge_generic)
        return self._route(role, invoke, judge=judge, image_sha=image_sha, route=route)

    # ------------------------------------------------------------------ weakness rules (deterministic)
    # judge(route, value) -> (escalate, low_confidence). `escalate` triggers the next escalation step (a not-found answer escalates
    # for pointing, an unsure verdict for checks); `low_confidence` is what `Routed.weak` reports about the FINAL answer.
    @staticmethod
    def _low(route: RoleRoute, conf: float) -> bool:
        return route.confidence_below > 0 and conf < route.confidence_below

    @staticmethod
    def _conf(v: Any) -> float:
        return float(v.confidence) if hasattr(v, "confidence") else float(v.get("confidence", 1.0))

    @classmethod
    def _judge_point(cls, route: RoleRoute, v: Any) -> tuple[bool, bool]:
        found = v.found if hasattr(v, "found") else bool(v.get("found", v.get("chosen") is not None))
        low = cls._low(route, cls._conf(v))
        return (route.escalate_not_found if not found else low), low

    @classmethod
    def _judge_generic(cls, route: RoleRoute, v: Any) -> tuple[bool, bool]:
        low = cls._low(route, cls._conf(v))
        return low, low

    @classmethod
    def _judge_verify(cls, route: RoleRoute, v: Any) -> tuple[bool, bool]:
        low = cls._low(route, cls._conf(v))
        return (v["verdict"] == "unsure" or low), low

    # ------------------------------------------------------------------ the loop
    def _skip(self, attempts: list[Attempt], i: int, step: Step, model: str, reason: str) -> None:
        attempts.append(Attempt(i, step.provider, step.tier, model, "skipped", skipped_reason=reason))
        self.skips[reason] = self.skips.get(reason, 0) + 1

    def _route_image(self, role: str, image: "SafeImage", payload: dict[str, Any], gate: "ImageGate", *,
                     judge: Callable[[RoleRoute, Any], tuple[bool, bool]]) -> Routed:
        from understudy_engine.privacy import egress  # lazy: importing the router never loads the engine

        if role == "glance":
            import understudy_engine.awareness.purposes  # noqa: F401  (registers the `awareness.glance` image purpose)

        def invoke(step: Step, port: StepPort) -> Any:
            try:
                res = egress.send_image(PURPOSE[role], image, payload, gate=gate, port=port, release=False)
            except egress.ModelCallFailed:
                raise StepFail(port.error_kind or "api") from None
            except egress.ModelOutputRejected:
                raise StepFail("schema") from None
            try:
                return _PARSE[role](res.output)
            except SchemaViolation:
                raise StepFail("schema") from None

        try:
            return self._route(role, invoke, judge=judge, image_sha=image.sha8)
        finally:
            image.release()   # the frame is used for this role call only

    def _route(self, role: str, invoke: Invoke, *, judge: Callable[[RoleRoute, Any], tuple[bool, bool]],
               image_sha: str | None = None, route: RoleRoute | None = None) -> Routed:
        route = route or self.config.roles[role]
        t0 = self.clock()
        attempts: list[Attempt] = []
        if mock_enabled():   # mock mode never reaches a model client
            for i, step in enumerate(route.steps):
                self._skip(attempts, i, step, "", "mock_mode")
            return Routed(self._empty(role, "unavailable"), "unavailable", attempts=attempts)
        answer: Any = None            # latest valid answer
        answer_low = False
        escalate_next = False
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
            if step.when == "escalate":
                escalated = True
            if step.when == "primary":
                ran_primary = True
            port = StepPort(backend, step.tier, role, thinking=step.thinking, timeout_s=min(route.call_timeout_s, remaining))
            err_kind: str | None = None
            value: Any = None
            try:
                value = invoke(step, port)
            except StepFail as e:
                err_kind = e.kind
            except StepStop as stop:
                breaker.cancel_probe()   # a gate, ledger or request refusal is not a provider failure: nothing was sent
                return Routed(self._empty(role, "unavailable"), "blocked", escalated=escalated, attempts=attempts,
                              total_ms=round((self.clock() - t0) * 1000), stopped=stop.payload)
            except BaseException:
                breaker.cancel_probe()   # privacy exceptions (gate, ledger, payload) propagate: fail closed
                raise
            out = port.out
            billed = None if out is None or out.output_tokens is None else out.output_tokens + (out.thought_tokens or 0)
            self.meter.record(CallRecord(
                role=role, provider=step.provider, model=model, tier=step.tier, method=role, ok=err_kind is None,
                latency_ms=port.latency_ms, input_tokens=out.input_tokens if out else None,
                output_tokens=out.output_tokens if out else None, thought_tokens=out.thought_tokens if out else None,
                cost_usd=cost_estimate(step.provider, step.tier, out.input_tokens, billed) if out else None,
                error_kind=err_kind, image_sha=image_sha, step=i, api=out.api if out else None))
            if err_kind is not None:
                if err_kind != "refusal":   # refusals are not outages
                    breaker.record(False)
                attempts.append(Attempt(i, step.provider, step.tier, model, "failed", error_kind=err_kind, latency_ms=port.latency_ms))
                if err_kind == "timeout":
                    saw_timeout = True
                    escalate_next = route.escalate_timeout
                elif err_kind == "schema":
                    escalate_next = route.escalate_schema_failure
                else:
                    escalate_next = False
                    hard_failed.add(step.provider)
                continue
            breaker.record(True)
            do_escalate, low = judge(route, value)
            attempts.append(Attempt(i, step.provider, step.tier, model, "ok", latency_ms=port.latency_ms, weak=do_escalate))
            answer, answer_low, any_valid = value, low, True
            escalate_next = do_escalate
            if not do_escalate:
                break
        total_ms = round((self.clock() - t0) * 1000)
        if any_valid:
            return Routed(answer, "answered", weak=answer_low, escalated=escalated, attempts=attempts, total_ms=total_ms)
        outcome: Outcome = "timeout" if saw_timeout else (
            "unavailable" if all(a.status == "skipped" for a in attempts) else "error")
        return Routed(self._empty(role, outcome), outcome, escalated=escalated, attempts=attempts, total_ms=total_ms)

    @staticmethod
    def _empty(role: str, outcome: Outcome) -> Any:
        if role == "point":
            return PointResult(found=False, box_2d=None, confidence=0.0, reason=outcome if outcome in ("timeout", "unavailable", "error") else "unavailable")
        if role == "glance":
            return GlanceResult(app_kind="unknown", task_phase="unknown", blocker="unknown", confidence=0.0)
        return {"verdict": "unsure", "confidence": 0.0}   # a missing answer is never a tick

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        provs = {}
        for name, b in self.backends.items():
            br = self.breakers.get(name)
            provs[name] = {"available": bool(b.available()), "breaker": br.snapshot() if br else None,
                           "models": {t: b.model_for(t) for t in ("fast", "accurate")}}
        return {"providers": provs, "skips": dict(self.skips), "last_latencies_ms": self.meter.last_latencies(),
                "meter": self.meter.summary()}


# ---------------------------------------------------------------------------------------------------------- shared router
_router_lock = threading.Lock()
_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    """The process-wide router (config from `UNDERSTUDY_MODELS_YAML` or the defaults; meter to `model_meter.jsonl`). Providers are
    built lazily at the first call, so creating it makes no network call and needs no key."""
    global _router
    with _router_lock:
        if _router is None:
            _router = ModelRouter.from_env()
        return _router


def peek_router() -> ModelRouter | None:
    return _router


def reset_router() -> None:
    global _router
    with _router_lock:
        _router = None
