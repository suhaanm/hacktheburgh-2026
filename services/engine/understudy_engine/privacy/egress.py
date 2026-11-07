"""The egress guard (PRV-1): the ONE function the extension layers may use to send content to a model.

    from understudy_engine.privacy import egress
    result = egress.send("calendar.suggestion_wording", payload)          # payload: the registered SafePayload

What ``send`` does, in order, failing closed (plain error, nothing sent) at every step:

1. the purpose must be registered (``register_payload``); unknown purposes are refused;
2. the payload is validated against the registered ``SafePayload`` (strict: no free strings) and bucketed;
3. the PII and canary backstop scans what is about to go (emails, phones, paths, URLs, NI numbers, long digit runs,
   secret-like tokens, the sensitive-field patterns, oversized numbers);
4. the model port is resolved (mock mode never reaches a network client);
5. the ledger line is written (if it cannot be written, nothing is sent);
6. only then the model port is called, and its answer is checked against the registered response schema and scanned.

No other module under ``calendar/``, ``gitanalysis/``, ``proactive/``, ``localmodel/`` or ``plugins/`` may import a model
client or ``ModelPort``; ``tests/privacy/test_static_guard.py`` enforces that.

The model's answer is untrusted text: show it to the worker, never execute it or feed it to another prompt as an instruction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import jsonschema
from pydantic import ValidationError

from . import ledger
from ._paths import is_mock
from ._stub import BuiltinMockPort
from .patterns import Hit, clean_rules, scan_text, scan_value
from .payload import (
    MAX_PAYLOAD_BYTES, PurposeError, SafePayload, explain_validation_error, get_purpose,
)

OFFLINE_PORT_NAMES = frozenset({"mock", "capturing"})
_ALLOWED_KW = frozenset({"now", "mock"})


class EgressError(Exception):
    """Base class. ``code`` is a short machine-readable reason; the message is plain and never contains payload values."""

    code = "egress_error"

    def __init__(self, message: str, *, purpose: str | None = None, rules: list[str] | None = None,
                 fields: list[str] | None = None, ledger_id: str | None = None) -> None:
        super().__init__(message)
        self.purpose, self.rules, self.fields, self.ledger_id = purpose, rules or [], fields or [], ledger_id


class UnknownPurpose(EgressError):
    code = "unknown_purpose"


class PayloadRejected(EgressError):
    code = "payload_rejected"


class EgressBlocked(EgressError):
    code = "blocked_by_backstop"


class EgressUnavailable(EgressError):
    code = "egress_unavailable"


class ModelCallFailed(EgressError):
    code = "model_call_failed"


class ModelOutputRejected(EgressError):
    code = "model_output_rejected"


@dataclass
class EgressResult:
    """What a send returned. ``output`` is the model's answer (untrusted). ``ledger_id`` names the ledger line."""

    output: Any
    ledger_id: str
    purpose: str
    schema: str
    model: str
    method: str
    bytes: int
    mock: bool
    payload: dict[str, Any] = field(default_factory=dict)
    bucketed: dict[str, list[str]] = field(default_factory=dict)


# --------------------------------------------------------------------------------------------------------- steps
def _coerce(model: type[SafePayload], payload: Any, purpose: str) -> SafePayload:
    """Validate (and bucket) ``payload`` into the registered model. Instances are re-validated from their own JSON, so a
    payload built with ``model_construct`` cannot skip the checks."""
    try:
        if isinstance(payload, SafePayload):
            if type(payload) is not model:
                raise PayloadRejected(
                    f"the payload is a {type(payload).__name__} but purpose {purpose!r} takes a {model.__name__}.", purpose=purpose)
            return model.model_validate_json(payload.model_dump_json())
        if isinstance(payload, dict):
            try:
                return model.model_validate(payload)
            except ValidationError as first:
                try:
                    return model.model_validate_json(json.dumps(payload))
                except (ValidationError, TypeError, ValueError):
                    raise first
        raise PayloadRejected(f"the payload must be a {model.__name__} or a dict for it, not {type(payload).__name__}.", purpose=purpose)
    except ValidationError as exc:
        lines = explain_validation_error(exc)
        raise PayloadRejected(
            f"the payload for {purpose!r} was refused: " + "; ".join(lines),
            purpose=purpose, fields=[ln.split(":", 1)[0] for ln in lines]) from None


def _bucket_check(model: type[SafePayload], p: SafePayload, purpose: str) -> dict[str, Any]:
    """The wire form, after verifying that bucketing is stable (re-validating gives the same bytes)."""
    wire = p.to_wire()
    again = model.model_validate_json(json.dumps(wire)).to_wire()
    if again != wire:
        raise EgressBlocked(f"the bucketing for {purpose!r} is not stable, so nothing was sent.", purpose=purpose, rules=["unstable_bucketing"])
    return wire


def _resolve_port(port: Any, mock_mode: bool, purpose: str) -> tuple[Any, bool]:
    """(port, is_mock). In mock mode only offline ports are accepted, so mock mode can never reach a network client."""
    if port is not None:
        offline = bool(getattr(port, "offline", False)) or getattr(port, "name", "") in OFFLINE_PORT_NAMES
        if mock_mode and not offline:
            raise EgressBlocked(
                "UNDERSTUDY_MOCK is on, so only the mock or a test port is accepted; nothing was sent.", purpose=purpose, rules=["mock_mode"])
        return port, mock_mode or offline
    if mock_mode:
        try:
            from understudy_agent.models import get_model_port  # lazy: only the model port is imported, never a client

            return get_model_port(mock=True), True
        except ImportError:
            return BuiltinMockPort(), True
    try:
        from understudy_agent.models import get_model_port
    except ImportError:
        raise EgressUnavailable(
            "The model port is not available here (run the engine in the agent environment), so nothing was sent.",
            purpose=purpose) from None
    try:
        return get_model_port(), False
    except Exception as exc:  # no key, no model ids: fail closed with a plain message
        raise EgressUnavailable(
            f"No model is configured ({type(exc).__name__}), so nothing was sent. Set UNDERSTUDY_MOCK=1 to run offline.",
            purpose=purpose) from None


def _model_id(port: Any, method: str) -> str:
    name = str(getattr(port, "name", type(port).__name__))
    models = getattr(port, "models", None)
    mid = getattr(models, "planner" if method == "plan" else "fast", None) if models is not None else None
    return f"{name}:{mid}" if mid else name


def _block(purpose: str, hits: list[Hit], reason: str) -> EgressBlocked:
    rules = clean_rules(hits)
    fields = sorted({h.path for h in hits})
    ledger.log_blocked(purpose, reason, rules, fields)
    return EgressBlocked(
        f"the payload for {purpose!r} was blocked by the privacy backstop ({', '.join(rules)}) at "
        f"{', '.join(fields[:5]) or 'the payload'}; nothing was sent.", purpose=purpose, rules=rules, fields=fields)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# --------------------------------------------------------------------------------------------------------- public API
def preview(purpose: str, payload: Any) -> dict[str, Any]:
    """Validate, bucket and scan without sending or writing anything. Returns ``{purpose, schema, method, payload, bytes,
    bucketed, unbucketed_numeric}`` or raises the same errors as ``send``. Handy for tests and for 'what would be sent'."""
    try:
        pur = get_purpose(purpose)
    except PurposeError as exc:
        raise UnknownPurpose(str(exc), purpose=purpose) from None
    p = _coerce(pur.model, payload, purpose)
    wire = _bucket_check(pur.model, p, purpose)
    user_text = _canonical({"purpose": purpose, "schema": pur.schema, "payload": wire})
    if len(user_text.encode()) > MAX_PAYLOAD_BYTES:
        raise PayloadRejected(f"the payload for {purpose!r} is larger than {MAX_PAYLOAD_BYTES} bytes.", purpose=purpose)
    hits = scan_value(wire)
    if hits:
        raise _block(purpose, hits, "backstop")
    ihits = scan_text(pur.instructions)
    if ihits:
        raise _block(purpose, [Hit("instructions", r) for r in ihits], "backstop_instructions")
    return {"purpose": purpose, "schema": pur.schema, "method": pur.method, "payload": wire, "bytes": len(user_text.encode()),
            "bucketed": pur.model.bucketed_fields(), "unbucketed_numeric": pur.model.unbucketed_numeric_fields()}


def send(purpose: str, payload: Any, *, port: Any = None, **kw: Any) -> EgressResult:
    """Send ``payload`` for ``purpose`` to the model, through every check. See the module docstring.

    ``port``: a ``ModelPort`` (tests pass a ``CapturingPort``); default ``get_model_port()``.
    ``now``: a ``datetime`` for the ledger time (simulated clocks). ``mock``: force mock-mode behaviour.
    Raises an ``EgressError`` subclass; the message is plain and never contains a payload value.
    """
    extra = set(kw) - _ALLOWED_KW
    if extra:
        raise TypeError(f"send() got unexpected keyword arguments {sorted(extra)}; allowed: {sorted(_ALLOWED_KW)}")
    now: datetime | None = kw.get("now")
    mock_mode = bool(kw["mock"]) if kw.get("mock") is not None else is_mock()

    info = preview(purpose, payload)  # raises UnknownPurpose / PayloadRejected / EgressBlocked
    pur = get_purpose(purpose)
    wire = info["payload"]
    user_text = _canonical({"purpose": purpose, "schema": pur.schema, "payload": wire})
    port, is_mock_call = _resolve_port(port, mock_mode, purpose)

    if pur.method == "plan":
        messages = [{"role": "system", "content": pur.instructions}, {"role": "user", "content": user_text}]
        request = {"messages": messages, "schema": pur.response_schema}
    else:
        prompt = pur.instructions + "\n\n" + user_text
        request = {"prompt": prompt, "schema": pur.response_schema}
    n_bytes = len(_canonical(request).encode())
    model = _model_id(port, pur.method)

    entry = {
        "kind": "extension", "purpose": purpose, "schema": pur.schema, "method": pur.method,
        "fields": list(wire), "payload": wire, "bucketed": info["bucketed"], "unbucketed_numeric": info["unbucketed_numeric"],
        "model": model, "bytes": n_bytes, "mock": is_mock_call,
    }
    if now is not None:
        entry["t"] = ledger.now_iso(now)
    try:
        written = ledger.append(entry)  # BEFORE the call: if this fails, nothing is sent
    except OSError:
        raise EgressUnavailable("The privacy ledger could not be written, so nothing was sent.", purpose=purpose) from None

    try:
        if pur.method == "plan":
            out = port.plan(messages, pur.response_schema)
        else:
            out = port.check(prompt, pur.response_schema)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        raise ModelCallFailed(
            f"The model call for {purpose!r} failed ({type(exc).__name__}{f', status {status}' if status else ''}). "
            f"The ledger keeps line {written['id']}: the request may have been sent.", purpose=purpose, ledger_id=written["id"]) from None

    if pur.response_schema is not None:
        try:
            jsonschema.validate(out, pur.response_schema)
        except jsonschema.ValidationError:
            raise ModelOutputRejected(
                f"The model's answer for {purpose!r} did not match the expected shape and was discarded.",
                purpose=purpose, ledger_id=written["id"]) from None
    ohits = scan_value(out, names=False)
    if ohits:
        raise ModelOutputRejected(
            f"The model's answer for {purpose!r} contained something that looks like personal data "
            f"({', '.join(clean_rules(ohits))}) and was discarded.", purpose=purpose, rules=clean_rules(ohits), ledger_id=written["id"])
    return EgressResult(output=out, ledger_id=written["id"], purpose=purpose, schema=pur.schema, model=model, method=pur.method,
                        bytes=n_bytes, mock=is_mock_call, payload=wire, bucketed=info["bucketed"])
