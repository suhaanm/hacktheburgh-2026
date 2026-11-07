# Adapted from rickkdev/clicky (fork of farzaa/clicky) (MIT) hermes-clicky-plugin/scoped_autopilot.py
# Copyright (c) 2026 Farza. Full licence text: vendor/clicky/LICENSE.
"""Time-boxed permission leases for child agents (BGA-1).

What was taken from Clicky's `ScopedAutopilotSession`: a session with a deadline, a step cap and a scope that STOPS
(fails closed) on the first violation, plus "a failed or uncertain verification stops the session" and an explicit
cancel. What was changed for Understudy:

* The scope is a set of TOOL names (the `AgentSpec.tools` list), never sites, hosts or apps: D12 and SEC-10 forbid
  any list of permitted places. There is an optional deny set, also of tool names.
* Time comes from a monotonic clock fixed at construction. Clicky's `evaluate_next_action(now=...)` let the caller
  pass the time, so a buggy or hostile caller could rewind it. Here nobody can: a clock that runs backwards, jumps to
  NaN or raises either changes nothing or stops the lease.
* Leases only narrow. A child's tools, deadline and step cap can never exceed its parent's, a revoked or expired
  parent stops its children on their next check, and there is deliberately no `extend` or `widen`: more power means
  trusted code issues a new lease. Models never call any of this; trusted runtime code does.
* Every event is audit-safe: tokens and numbers only, so it can go straight into `AuditLog.append(meta=...)`.
  A tool name that did not come from trusted code is never echoed.
* Content checks stay in the SafetyPipeline. A lease answers only "may this child still act, with this tool?".

Typical use (runtime/child.py)::

    book = LeaseBook(killed=is_killed, on_event=sink)
    lease = book.issue(holder="child_1", tools={"read_file", "git_log"}, ttl_s=300, max_steps=20)
    ...
    d = lease.check(action.kind)          # before pipeline.authorise
    if not d.allowed: stop_child(d.code)
    ... act, then verify with clicky_lift.postcheck ...
    lease.record(post_result)              # a failed or uncertain step stops the lease
"""
from __future__ import annotations

import math
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["Lease", "LeaseBook", "LeaseDecision", "LeaseError", "LeaseLimits", "StopReason"]

_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")          # tool names, reason codes
_ID = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,39}$")        # lease ids and holders (also valid audit meta tokens)
_DEFAULT_STOP_VERDICTS = frozenset({"failed", "uncertain", "blocked_by_prompt"})
_KNOWN_VERDICTS = frozenset({"success", "failed", "uncertain", "blocked_by_prompt", "skipped"})  # postcheck's vocabulary


class LeaseError(ValueError):
    """The lease request is malformed or asks for more than its parent holds."""


class StopReason:
    """Short stable codes for the audit log (plain strings, valid audit tokens)."""

    EXPIRED = "expired"
    MAX_STEPS = "max_steps"
    SCOPE_VIOLATION = "scope_violation"
    REVOKED = "revoked"
    PARENT_STOPPED = "parent_stopped"
    KILL_FLAG = "kill_flag"
    CLOCK_ERROR = "clock_error"
    VERIFICATION = "verification_stopped"
    NOT_ACTIVE = "not_active"


@dataclass(frozen=True)
class LeaseLimits:
    max_ttl_s: float = 6 * 3600.0
    max_steps: int = 500
    max_tools: int = 32


DEFAULT_LIMITS = LeaseLimits()


@dataclass(frozen=True)
class LeaseDecision:
    allowed: bool
    code: str                 # "ok", or a StopReason code saying why not
    step: int                 # steps used so far, including this one when allowed
    remaining_s: float
    remaining_steps: int


def _number(name: str, value: Any, *, lo: float, hi: float, integer: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LeaseError(f"{name} must be a number")
    if integer and not isinstance(value, int):
        raise LeaseError(f"{name} must be a whole number")
    if isinstance(value, float) and not math.isfinite(value):
        raise LeaseError(f"{name} must be finite")
    if not (lo < value <= hi):
        raise LeaseError(f"{name} must be above {lo} and at most {hi}")
    return float(value)


def _tool_set(name: str, tools: Iterable[Any], *, max_tools: int, allow_empty: bool) -> frozenset[str]:
    if isinstance(tools, (str, bytes)):
        raise LeaseError(f"{name} must be a collection of tool names, not one string")
    out: set[str] = set()
    for t in tools:
        if type(t) is not str or not _TOKEN.fullmatch(t):
            raise LeaseError(f"{name} holds an invalid tool name")
        out.add(t)
    if not out and not allow_empty:
        raise LeaseError(f"{name} must name at least one tool")
    if len(out) > max_tools:
        raise LeaseError(f"{name} names more than {max_tools} tools")
    return frozenset(out)


def _ident(name: str, value: Any) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise LeaseError(f"{name} must match {_ID.pattern}")
    return value


def _reason(value: Any, default: str) -> str:
    return value if type(value) is str and _TOKEN.fullmatch(value) else default


class Lease:
    """One child's right to act: a tool scope, a deadline, a step cap, and a kill switch of its own."""

    def __init__(self, *, lease_id: str, holder: str, tools: Iterable[str], ttl_s: float, max_steps: int,
                 denied_tools: Iterable[str] = (), parent: Lease | None = None, max_violations: int = 1,
                 stop_on_verdicts: Iterable[str] = _DEFAULT_STOP_VERDICTS,
                 clock: Callable[[], float] = time.monotonic, killed: Callable[[], bool] | None = None,
                 on_event: Callable[[dict[str, Any]], None] | None = None,
                 limits: LeaseLimits | None = None) -> None:
        limits = limits or DEFAULT_LIMITS
        self.lease_id = _ident("lease_id", lease_id)
        self.holder = _ident("holder", holder)
        ttl = _number("ttl_s", ttl_s, lo=0.0, hi=limits.max_ttl_s)
        steps = int(_number("max_steps", max_steps, lo=0.0, hi=limits.max_steps, integer=True))
        mv = int(_number("max_violations", max_violations, lo=0.0, hi=100, integer=True))
        want = _tool_set("tools", tools, max_tools=limits.max_tools, allow_empty=False)
        deny = _tool_set("denied_tools", denied_tools, max_tools=limits.max_tools, allow_empty=True)
        self._stop_verdicts = frozenset(v for v in stop_on_verdicts if v in _KNOWN_VERDICTS)
        self._clock = clock
        self._killed = killed
        self._on_event = on_event
        self.parent = parent
        self.event_errors = 0
        self._lock = threading.RLock()
        self._state = "active"
        self._stop_reason: str | None = None
        self._steps = 0
        self._violations = 0
        self._max_violations = mv
        self._last = self._read_clock_or_raise()
        self._issued = self._last
        self._deadline = self._issued + ttl
        self._ttl = ttl
        self._max_steps = steps
        self.denied_tools = deny | (parent.denied_tools if parent else frozenset())
        self.tools = want - self.denied_tools
        if not self.tools:
            raise LeaseError("every requested tool is denied")
        if parent is not None:
            self._check_narrower_than(parent, want, steps)

    # ---------------------------------------------------------------- construction helpers
    def _read_clock_or_raise(self) -> float:
        t = self._clock()
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            raise LeaseError("the clock returned a bad value")
        return float(t)

    def _check_narrower_than(self, parent: Lease, want: frozenset[str], steps: int) -> None:
        if not parent.is_active():
            raise LeaseError("the parent lease is not active")
        if not want <= parent.tools:
            raise LeaseError("a child cannot hold a tool its parent does not")
        if self._deadline > parent._deadline + 1e-9:
            raise LeaseError("a child cannot outlive its parent")
        if steps > parent._max_steps:
            raise LeaseError("a child cannot have more steps than its parent")

    # ---------------------------------------------------------------- time
    def _now(self) -> float | None:
        """Monotonic non-decreasing time, or None when the clock misbehaves (the caller then stops the lease)."""
        try:
            t = self._clock()
        except Exception:
            return None
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            return None
        self._last = max(self._last, float(t))
        return self._last

    # ---------------------------------------------------------------- state
    def _emit(self, events: list[dict[str, Any]]) -> None:
        cb = self._on_event
        if cb is None:
            return
        for ev in events:
            try:
                cb(ev)
            except Exception:
                self.event_errors += 1

    def _event(self, kind: str, outcome: str, code: str, tool: str | None = None) -> dict[str, Any]:
        ev: dict[str, Any] = {"kind": kind, "lease_id": self.lease_id, "holder": self.holder, "outcome": outcome,
                              "code": code, "steps": self._steps}
        if tool is not None:
            ev["tool"] = tool
        return ev

    def _stop(self, reason: str, events: list[dict[str, Any]], tool: str | None = None) -> None:
        if self._state != "active":
            return
        self._state = "revoked" if reason == StopReason.REVOKED else "stopped"
        self._stop_reason = reason
        events.append(self._event("lease_stopped", self._state, reason, tool))

    def _remaining(self, now: float) -> float:
        return max(0.0, self._deadline - now) if self._state == "active" else 0.0

    def _evaluate_terminal(self, events: list[dict[str, Any]]) -> float | None:
        """Stop the lease if time, kill flag, clock or parent say so. Returns the current time, or None when stopped."""
        now = self._now()
        if now is None:
            self._stop(StopReason.CLOCK_ERROR, events)
            return None
        if self._killed is not None:
            try:
                killed = bool(self._killed())
            except Exception:
                killed = True  # an unreadable kill flag counts as set: fail closed
            if killed:
                self._stop(StopReason.KILL_FLAG, events)
                return None
        if now >= self._deadline:
            self._stop(StopReason.EXPIRED, events)
            return None
        if self.parent is not None and not self.parent.is_active():
            self._stop(StopReason.PARENT_STOPPED, events)
            return None
        if self._steps >= self._max_steps:
            self._stop(StopReason.MAX_STEPS, events)
            return None
        return now

    def poll(self) -> str:
        """Current state without using a step: active, revoked, or stopped."""
        events: list[dict[str, Any]] = []
        with self._lock:
            if self._state == "active":
                self._evaluate_terminal(events)
            state = self._state
        self._emit(events)
        return state

    def is_active(self) -> bool:
        return self.poll() == "active"

    # ---------------------------------------------------------------- the one question
    def check(self, tool: Any) -> LeaseDecision:
        """May the holder use `tool` right now? Counts a step when it may. Never raises, whatever `tool` is."""
        events: list[dict[str, Any]] = []
        with self._lock:
            if self._state != "active":
                dec = LeaseDecision(False, self._stop_reason or StopReason.NOT_ACTIVE, self._steps, 0.0,
                                    max(0, self._max_steps - self._steps))
            else:
                dec = self._check_active(tool, events)
        self._emit(events)
        return dec

    def _check_active(self, tool: Any, events: list[dict[str, Any]]) -> LeaseDecision:
        now = self._evaluate_terminal(events)
        if now is None:
            return self._denied(self._stop_reason or StopReason.NOT_ACTIVE)
        # `type(tool) is str` (not isinstance): a str subclass could lie in __eq__ or __hash__ and slip into the set test.
        well_formed = type(tool) is str and bool(_TOKEN.fullmatch(tool))
        if not (well_formed and tool in self.tools):
            self._violations += 1
            safe = tool if well_formed else "invalid"
            events.append(self._event("lease_denied", "denied", StopReason.SCOPE_VIOLATION, safe))
            if self._violations >= self._max_violations:
                self._stop(StopReason.SCOPE_VIOLATION, events, safe)
                return self._denied(StopReason.SCOPE_VIOLATION)
            return LeaseDecision(False, StopReason.SCOPE_VIOLATION, self._steps, round(self._remaining(now), 3),
                                 self._max_steps - self._steps)
        self._steps += 1
        return LeaseDecision(True, "ok", self._steps, round(self._remaining(now), 3), self._max_steps - self._steps)

    def _denied(self, code: str) -> LeaseDecision:
        return LeaseDecision(False, code, self._steps, 0.0, max(0, self._max_steps - self._steps))

    # ---------------------------------------------------------------- outcomes and control
    def record(self, verdict: Any) -> bool:
        """Feed in a postcheck verdict (a string, or an object with `.verdict`). Returns True while the lease is still
        active. failed, uncertain and blocked_by_prompt stop it; success and skipped do not; anything unrecognised
        stops it (fail closed)."""
        try:
            v = getattr(verdict, "verdict", verdict)
        except Exception:
            v = None
        events: list[dict[str, Any]] = []
        with self._lock:
            if self._state == "active":
                known = type(v) is str and v in _KNOWN_VERDICTS
                if not known or v in self._stop_verdicts:
                    self._stop(StopReason.VERIFICATION, events)
                else:
                    self._evaluate_terminal(events)
            active = self._state == "active"
        self._emit(events)
        return active

    def revoke(self, reason: str = StopReason.REVOKED) -> bool:
        """Stop the lease now. Idempotent; the first reason wins. Returns True if this call did the stopping."""
        events: list[dict[str, Any]] = []
        with self._lock:
            was_active = self._state == "active"
            if was_active:
                self._stop(StopReason.REVOKED, events)
                self._stop_reason = _reason(reason, StopReason.REVOKED)
                events[-1]["code"] = self._stop_reason
        self._emit(events)
        return was_active

    # ---------------------------------------------------------------- reporting
    def snapshot(self) -> dict[str, Any]:
        """Audit-safe view for the Agents screen: state, countdown, steps. Never raw text."""
        self.poll()
        with self._lock:
            now = self._last
            return {"lease_id": self.lease_id, "holder": self.holder, "state": self._state,
                    "stop_reason": self._stop_reason, "steps_used": self._steps, "max_steps": self._max_steps,
                    "ttl_s": self._ttl, "remaining_s": round(self._remaining(now), 1),
                    "tools": sorted(self.tools), "parent": self.parent.lease_id if self.parent else None}

    def audit_meta(self) -> dict[str, Any]:
        """Flat tokens and numbers, valid as `AuditLog.append(meta=...)`."""
        s = self.snapshot()
        return {"state": s["state"], "stop_reason": s["stop_reason"] or "none", "steps": s["steps_used"],
                "remaining_s": int(s["remaining_s"])}


class LeaseBook:
    """Issues leases and revokes them as a group (the stop button, the kill switch, the end of a parent)."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, killed: Callable[[], bool] | None = None,
                 on_event: Callable[[dict[str, Any]], None] | None = None, limits: LeaseLimits | None = None,
                 max_active: int = 8) -> None:
        self._clock = clock
        self._killed = killed
        self._on_event = on_event
        self._limits = limits or DEFAULT_LIMITS
        self._max_active = max_active
        self._leases: dict[str, Lease] = {}
        self._lock = threading.RLock()  # re-entrant: an event sink may call back into the book

    def issue(self, *, holder: str, tools: Iterable[str], ttl_s: float, max_steps: int,
              parent: Lease | str | None = None, denied_tools: Iterable[str] = (), lease_id: str | None = None,
              max_violations: int = 1, stop_on_verdicts: Iterable[str] = _DEFAULT_STOP_VERDICTS) -> Lease:
        with self._lock:
            parent_lease: Lease | None
            if isinstance(parent, str):
                parent_lease = self._leases.get(parent)
                if parent_lease is None:
                    raise LeaseError("unknown parent lease")
            else:
                parent_lease = parent
            if sum(1 for ls in self._leases.values() if ls.is_active()) >= self._max_active:
                raise LeaseError("too many active leases")
            lid = lease_id if lease_id is not None else "ls_" + secrets.token_hex(4)
            if lid in self._leases:
                raise LeaseError("lease id already in use")
            lease = Lease(lease_id=lid, holder=holder, tools=tools, ttl_s=ttl_s, max_steps=max_steps,
                          denied_tools=denied_tools, parent=parent_lease, max_violations=max_violations,
                          stop_on_verdicts=stop_on_verdicts, clock=self._clock, killed=self._killed,
                          on_event=self._on_event, limits=self._limits)
            self._leases[lid] = lease
        if self._on_event is not None:
            try:
                self._on_event({"kind": "lease_issued", "lease_id": lid, "holder": lease.holder, "outcome": "active",
                                "code": "ok", "steps": 0})
            except Exception:
                lease.event_errors += 1
        return lease

    def get(self, lease_id: str) -> Lease | None:
        with self._lock:
            return self._leases.get(lease_id) if type(lease_id) is str else None

    def active(self) -> list[Lease]:
        with self._lock:
            leases = list(self._leases.values())
        return [ls for ls in leases if ls.is_active()]

    def revoke(self, lease_id: str, reason: str = StopReason.REVOKED) -> bool:
        """Revoke a lease and every lease below it. True if the named lease was still active."""
        target = self.get(lease_id)
        if target is None:
            return False
        done = target.revoke(reason)
        with self._lock:
            leases = list(self._leases.values())
        for ls in leases:
            if ls is not target and _descends_from(ls, target):
                ls.revoke(StopReason.PARENT_STOPPED)
        return done

    def revoke_all(self, reason: str = StopReason.REVOKED) -> int:
        with self._lock:
            leases = list(self._leases.values())
        return sum(1 for ls in leases if ls.revoke(reason))

    def snapshots(self) -> list[Mapping[str, Any]]:
        with self._lock:
            leases = list(self._leases.values())
        return [ls.snapshot() for ls in leases]


def _descends_from(lease: Lease, ancestor: Lease) -> bool:
    p = lease.parent
    while p is not None:
        if p is ancestor:
            return True
        p = p.parent
    return False
