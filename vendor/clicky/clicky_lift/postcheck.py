# Adapted from rickkdev/clicky (fork of farzaa/clicky) (MIT) hermes-clicky-plugin/post_action_verification.py
# Copyright (c) 2026 Farza. Full licence text: vendor/clicky/LICENSE.
"""Postcondition check after an agent step (code decides, never a model).

What was taken from Clicky's `PostActionVerificationRunner`: the verdict vocabulary (success, failed, uncertain,
blocked by a prompt, skipped), the rule that blockers are looked at before any evidence of success, the rule that
"changed but unverified" is `uncertain` and stops the run for a human, and the observe-after-acting seam. What was
changed for Understudy:

* Clicky classified a handful of booleans that a caller (in practice the model) supplied about the screen. Here the
  step declares a `Condition`, a short list of checks over NAMED FIELDS that trusted code read from a fresh
  observation (DOM state, the quarantined reader's schema-checked fields, a URL host). A model's claim of success is
  never an input.
* Fail closed: a field that cannot be read, has the wrong type, or is too long gives `uncertain`, never `success`.
  Exact matching only (no Unicode folding, so look-alike characters do not match), strict types (`True` is not `1`).
* Output carries only tokens and numbers (check names come from the declaration, not from the page), so it can be
  logged and shown without leaking page text and cannot be steered by it.

Every broad `except Exception` below is deliberate: this layer fails closed (uncertain or failed), it never raises
into the run loop.

Point checks at NARROW fields (the saved-note cell, the result row), not at whole-page text: a page can print any
string, so a whole-page `contains` proves little. This helper cannot know which fields are narrow; the caller does.

    cond = Condition.of(matches("note_id", r"CN-\\d{4}"), equals("status", "saved"), absent("banner", "error"))
    post = verify(cond, after=Observation({"note_id": "CN-1234", "status": "saved", "banner": ""}))
    if not post.ok: pause_for_human(post.reason)
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Check", "Condition", "Observation", "PostResult", "absent", "changed", "contains", "equals", "in_range",
           "matches", "present", "run_step", "verify"]

MAX_FIELD_CHARS = 20_000
MAX_CHECKS = 32
MAX_PATTERN_CHARS = 200
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_FIELD_TYPES = (str, int, float, bool, type(None))
_MISSING = object()
PROMPT_BLOCKERS = frozenset({"permission_prompt"})   # everything else in `blockers` is a plain failure


@dataclass(frozen=True)
class Observation:
    """What trusted code read after (or before) the step. `fields` holds scalars only; `blockers` are tokens such as
    `permission_prompt`, `error_dialog`, `app_lost_focus`, `injection_hit` raised by detectors, never by the model."""

    fields: Mapping[str, Any] = field(default_factory=dict)
    blockers: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Check:
    name: str
    op: str
    field: str
    operand: Any = None
    casefold: bool = False
    pattern: Any = None   # compiled regex for op == "matches"


@dataclass(frozen=True)
class Condition:
    checks: tuple[Check, ...] = ()
    required: bool = True

    @staticmethod
    def of(*checks: Check) -> Condition:
        if not checks:
            raise ValueError("a condition needs at least one check; use Condition.none() for a step with nothing to verify")
        if len(checks) > MAX_CHECKS:
            raise ValueError(f"at most {MAX_CHECKS} checks")
        names = [c.name for c in checks]
        if len(set(names)) != len(names):
            raise ValueError("check names must be unique")
        return Condition(tuple(checks), True)

    @staticmethod
    def none() -> Condition:
        """An explicit 'nothing to verify' (a pure read). A step with no declared condition is `uncertain`, not skipped."""
        return Condition((), False)

    @property
    def needs_before(self) -> bool:
        return any(c.op == "changed" for c in self.checks)


# ---------------------------------------------------------------- check constructors (trusted code calls these)
def _tok(kind: str, value: Any) -> str:
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise ValueError(f"{kind} must be a lowercase token like 'note_id'")
    return value


def _mk(op: str, fld: str, operand: Any, name: str | None, casefold: bool = False, pattern: Any = None) -> Check:
    f = _tok("field", fld)
    return Check(_tok("name", name) if name is not None else f"{op}_{f}"[:40], op, f, operand, casefold, pattern)


def equals(fld: str, value: Any, *, name: str | None = None) -> Check:
    if type(value) not in (str, int, float, bool) or (type(value) is float and not math.isfinite(value)):
        raise ValueError("equals needs a finite scalar")
    return _mk("equals", fld, value, name)


def contains(fld: str, token: str, *, name: str | None = None, casefold: bool = False) -> Check:
    if type(token) is not str or not token:
        raise ValueError("contains needs a non-empty string (an empty string would match everything)")
    return _mk("contains", fld, token, name, casefold)


def absent(fld: str, token: str, *, name: str | None = None, casefold: bool = False) -> Check:
    if type(token) is not str or not token:
        raise ValueError("absent needs a non-empty string")
    return _mk("absent", fld, token, name, casefold)


def matches(fld: str, pattern: str, *, name: str | None = None) -> Check:
    if type(pattern) is not str or not pattern or len(pattern) > MAX_PATTERN_CHARS:
        raise ValueError("matches needs a short non-empty pattern")
    try:
        compiled = re.compile(pattern, re.ASCII)   # ASCII: \d must not match full-width or Arabic-Indic digits
    except re.error as exc:
        raise ValueError("bad pattern") from exc
    return _mk("matches", fld, pattern, name, pattern=compiled)


def present(fld: str, *, name: str | None = None) -> Check:
    return _mk("present", fld, None, name)


def changed(fld: str, *, name: str | None = None) -> Check:
    return _mk("changed", fld, None, name)


def in_range(fld: str, lo: float, hi: float, *, name: str | None = None) -> Check:
    for v in (lo, hi):
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError("in_range needs finite numbers")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return _mk("in_range", fld, (lo, hi), name)


# ---------------------------------------------------------------- result
@dataclass(frozen=True)
class PostResult:
    verdict: str                    # success | failed | uncertain | blocked_by_prompt | skipped
    reason: str                     # a token: ok, field_missing, check_failed, permission_prompt, ...
    failed_checks: tuple[str, ...] = ()
    unknown_checks: tuple[str, ...] = ()
    blocker: str | None = None
    checks_run: int = 0

    @property
    def ok(self) -> bool:
        """True when the run may go on: success, or a step that declared nothing to verify."""
        return self.verdict in ("success", "skipped")

    @property
    def continue_run(self) -> bool:
        return self.ok

    @property
    def needs_human(self) -> bool:
        return self.verdict in ("uncertain", "blocked_by_prompt")

    def audit_meta(self) -> dict[str, Any]:
        """Flat tokens and numbers, valid as `AuditLog.append(meta=...)`."""
        return {"verdict": self.verdict, "reason": self.reason, "n_failed": len(self.failed_checks),
                "n_unknown": len(self.unknown_checks), "checks": self.checks_run}


def _result(verdict: str, reason: str, **kw: Any) -> PostResult:
    return PostResult(verdict, reason, **kw)


# ---------------------------------------------------------------- evaluation
def _scalar(value: Any) -> tuple[bool, str]:
    """(usable, code). Exact scalar types only; `type(x) in`, so a subclass with a lying __eq__ is not accepted."""
    if type(value) not in _FIELD_TYPES:
        return False, "bad_field_type"
    if type(value) is str and len(value) > MAX_FIELD_CHARS:
        return False, "field_too_long"
    if type(value) is float and not math.isfinite(value):
        return False, "bad_field_type"
    return True, "ok"


def _get(obs: Mapping[str, Any] | None, fld: str) -> Any:
    if obs is None:
        return _MISSING
    return obs.get(fld, _MISSING)


def _eval(check: Check, after: Mapping[str, Any], before: Mapping[str, Any] | None) -> tuple[str, str]:
    """-> ("pass" | "fail" | "unknown", code)."""
    value = _get(after, check.field)
    if value is _MISSING:
        return "unknown", "field_missing"
    usable, code = _scalar(value)
    if not usable:
        return "unknown", code
    op = check.op
    if op == "present":
        ok = value is not None and not (type(value) is str and not value.strip())
        return ("pass", "ok") if ok else ("fail", "empty")
    if op == "equals":
        ok = type(value) is type(check.operand) and value == check.operand
        return ("pass", "ok") if ok else ("fail", "mismatch")
    if op in ("contains", "absent"):
        if type(value) is not str:
            return "fail", "not_text"
        hay, needle = (value.casefold(), check.operand.casefold()) if check.casefold else (value, check.operand)
        found = needle in hay
        if op == "contains":
            return ("pass", "ok") if found else ("fail", "token_not_found")
        return ("fail", "token_present") if found else ("pass", "ok")
    if op == "matches":
        if type(value) is not str:
            return "fail", "not_text"
        return ("pass", "ok") if check.pattern.fullmatch(value) else ("fail", "pattern_mismatch")
    if op == "in_range":
        if type(value) not in (int, float):
            return "fail", "not_number"
        lo, hi = check.operand
        return ("pass", "ok") if lo <= value <= hi else ("fail", "out_of_range")
    if op == "changed":
        old = _get(before, check.field)
        if old is _MISSING:
            return "unknown", "no_baseline"
        old_ok, _ = _scalar(old)
        if not old_ok:
            return "unknown", "bad_field_type"
        same = type(old) is type(value) and old == value
        return ("fail", "unchanged") if same else ("pass", "ok")
    return "unknown", "unknown_check"


def _as_mapping(obs: Any) -> tuple[Mapping[str, Any] | None, frozenset[str], str | None]:
    """(fields, blockers, problem). Accepts an Observation or a plain mapping of fields."""
    if isinstance(obs, Observation):
        fields, blockers = obs.fields, obs.blockers
    elif isinstance(obs, Mapping):
        fields, blockers = obs, frozenset()
    else:
        return None, frozenset(), "bad_observation"
    if not isinstance(fields, Mapping):
        return None, frozenset(), "bad_observation"
    try:
        bl = frozenset(blockers)
    except Exception:
        return None, frozenset(), "bad_blockers"
    return fields, bl, None


def verify(condition: Condition, after: Any, *, before: Any = None, executed: bool = True) -> PostResult:
    """Classify the state after a step. Never raises; any internal error is `uncertain`."""
    try:
        return _verify(condition, after, before, executed)
    except Exception:
        return _result("uncertain", "verifier_error")


def _verify(condition: Condition, after: Any, before: Any, executed: bool) -> PostResult:
    if not executed:
        return _result("failed", "action_not_executed")
    if not isinstance(condition, Condition):
        return _result("uncertain", "no_condition")
    if not condition.checks:
        if condition.required:
            return _result("uncertain", "no_checks")
        if after is None:
            return _result("skipped", "nothing_to_verify")   # a pure read that was not observed afterwards
    fields, blockers, problem = _as_mapping(after)
    if problem is not None or fields is None:
        return _result("uncertain", problem or "bad_observation")
    # 1. blockers first: no evidence of success can outvote them (also for a step with nothing else to verify)
    for b in blockers:
        if type(b) is not str or not _TOKEN.fullmatch(b):
            return _result("failed", "bad_blocker", blocker="invalid")
    hit_prompt = sorted(b for b in blockers if b in PROMPT_BLOCKERS)
    if hit_prompt:
        return _result("blocked_by_prompt", hit_prompt[0], blocker=hit_prompt[0])
    if blockers:
        first = min(blockers)
        return _result("failed", first, blocker=first)
    if not condition.checks:
        return _result("skipped", "nothing_to_verify")
    # 2. the declared checks
    before_fields = None
    if before is not None:
        before_fields, _, bproblem = _as_mapping(before)
        if bproblem is not None:
            before_fields = None
    failed: list[str] = []
    unknown: list[str] = []
    first_fail = first_unknown = ""
    for chk in condition.checks:
        status, code = _eval(chk, fields, before_fields)
        if status == "fail":
            failed.append(chk.name)
            first_fail = first_fail or code
        elif status == "unknown":
            unknown.append(chk.name)
            first_unknown = first_unknown or code
    n = len(condition.checks)
    if failed:
        return _result("failed", first_fail, failed_checks=tuple(failed), unknown_checks=tuple(unknown), checks_run=n)
    if unknown:
        return _result("uncertain", first_unknown, unknown_checks=tuple(unknown), checks_run=n)
    return _result("success", "ok", checks_run=n)


def run_step(do: Callable[[], Any], observe: Callable[[], Any], condition: Condition) -> tuple[Any, PostResult]:
    """Observe before when a check needs it, act, observe after, verify. Returns (value of `do`, result).

    `do` raising gives `failed` (the exception text is dropped: it may carry page text); `observe` raising gives
    `uncertain`. Nothing is retried."""
    before = None
    try:
        if isinstance(condition, Condition) and condition.needs_before:
            before = observe()
    except Exception:
        return None, _result("uncertain", "observe_failed")
    try:
        value = do()
    except Exception:
        return None, _result("failed", "action_raised")
    try:
        after = observe()
    except Exception:
        return value, _result("uncertain", "observe_failed")
    return value, verify(condition, after, before=before)
