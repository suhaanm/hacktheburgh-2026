"""The one place a call to a connected server is decided and made (CONNECTIONS).

Every refusal here is CODE and is recorded as a metadata-only ledger row; nothing is decided by a model. In order:

 1. the call's shape (an object, JSON, small, shallow);
 2. the connection exists in the curated list, the worker switched it on, and the pinned command hash still matches (``needs_reconfirm`` stops it);
 3. the kill flag is not set, and the worker's denylist does not name the app's hosts or the app;
 4. the tool is one the server really offers, and our table or verb rules allow it (``unlisted: refuse`` presets never call an unknown tool);
 5. unattended: only a READ, only for a connection the worker opted THIS routine into;
 6. anything but a read needs ``gate_ok``: the SafetyPipeline has authorised it, which for these classes means a person clicked (the pipeline
    makes the queue item; a write that reaches here without that is refused as ``needs_click``);
 7. the ledger row is written BEFORE the call (if it cannot be, the call is not made).

A server's own annotations never lower a class (see ``classify``). The result comes back as UNTRUSTED text for the detector and the quarantined reader;
this module never shows it to a model.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from understudy_engine.connections import ledger as cledger
from understudy_engine.connections import registry, state
from understudy_engine.connections import secrets as sec
from understudy_engine.connections.manifest import Preset

from ..security.denylist import Denylist
from ..security.killflag import is_killed
from .classify import CLASS_ORDER, Classification, classify
from .runner import RawResult, RunnerError, ToolInfo, build_launch, default_runner

MAX_ARG_BYTES = 24_000
MAX_DEPTH = 6
MAX_STR = 20_000


class Refused(Exception):
    """A call that was not made. ``code`` is short and stable; ``outcome`` is the ledger outcome (refused, blocked or needs_click)."""

    def __init__(self, code: str, message: str, outcome: str = "refused") -> None:
        super().__init__(message)
        self.code, self.outcome = code, outcome


@dataclass(frozen=True)
class CallOutcome:
    klass: str
    source: str
    text: str
    is_error: bool
    blocks_other: int
    truncated: bool
    bytes_args: int
    bytes_result: int
    example: bool


def check_arguments(args: Any) -> int:
    """Return the size in bytes of valid arguments, or raise ``Refused``. Keys are short strings; nesting and strings are bounded."""
    if args is None:
        return 2
    if not isinstance(args, dict):
        raise Refused("bad_arguments", "The arguments must be an object.")

    def walk(v: Any, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise Refused("bad_arguments", "The arguments are nested too deeply.")
        if isinstance(v, dict):
            for k, x in v.items():
                if not isinstance(k, str) or len(k) > 80:
                    raise Refused("bad_arguments", "An argument name is not valid.")
                walk(x, depth + 1)
        elif isinstance(v, list):
            if len(v) > 200:
                raise Refused("bad_arguments", "A list in the arguments is too long.")
            for x in v:
                walk(x, depth + 1)
        elif isinstance(v, str):
            if len(v) > MAX_STR or "\x00" in v:
                raise Refused("bad_arguments", "A value in the arguments is not valid.")
        elif not (v is None or isinstance(v, (bool, int, float))):
            raise Refused("bad_arguments", "The arguments must be plain JSON.")

    walk(args, 0)
    try:
        n = len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise Refused("bad_arguments", "The arguments must be plain JSON.") from None
    if n > MAX_ARG_BYTES:
        raise Refused("bad_arguments", "The arguments are too large.")
    return n


class ConnectionService:
    def __init__(self, runner=None, *, denylist_loader=Denylist.load, killed=is_killed) -> None:
        self.runner = runner or default_runner()
        self._denylist = denylist_loader
        self._killed = killed

    # ---- reading the state
    def _preset(self, conn_id: str) -> Preset:
        p = registry.get(conn_id)
        if p is None:
            raise Refused("unknown_connection", "That connection is not in the curated list.")
        return p

    def usable(self, conn_id: str) -> tuple[Preset, dict[str, Any]]:
        """The preset and its record, only when the worker switched it on and the pin matches; otherwise ``Refused``."""
        p = self._preset(conn_id)
        rec = state.record(conn_id)
        st = state.status(p, rec)["state"]
        if st == "needs_reconfirm":
            raise Refused("needs_reconfirm", "This connection changed since you agreed. Confirm it again to use it.")
        if st not in ("connected", "error") or rec is None:
            raise Refused("not_connected", "This connection is off. Connect it first.")
        return p, rec

    # ---- start and stop
    def start(self, conn_id: str) -> dict[str, Any]:
        """The worker's start (or a start after a change): the restart budget begins afresh."""
        self.runner.clear_restarts(conn_id)
        return self._start(conn_id)

    def _start(self, conn_id: str) -> dict[str, Any]:
        """Start a connection the worker already switched on, list its tools, and return COUNTS (never a name or a description)."""
        try:
            p, rec = self.usable(conn_id)
            launch = build_launch(p, rec["mode"], dict(rec.get("params") or {}), sec.load_env(conn_id, p.credential_envs))
            tools = self.runner.start(conn_id, launch)
        except (Refused, RunnerError) as e:
            return {"ok": False, "code": e.code, "tools": 0, "counts": {}}
        counts: dict[str, int] = {c: 0 for c in CLASS_ORDER}
        refused = 0
        for t in tools:
            c = classify(p, t.name, None, t.annotations)
            if c.refused:
                refused += 1
            else:
                counts[c.klass] += 1
        return {"ok": True, "tools": len(tools), "counts": {**counts, "refused": refused}, "code": None}

    def stop(self, conn_id: str) -> dict[str, Any]:
        return {"stopped": self.runner.stop(conn_id), "id": conn_id}

    # ---- classification (used by the pipeline mapping before anything runs)
    def classify_call(self, conn_id: str, tool: str, arguments: dict[str, Any] | None) -> tuple[Preset, Classification]:
        p, _ = self.usable(conn_id)
        info: ToolInfo | None = self.runner.tools(conn_id).get(tool)
        c = classify(p, tool, arguments, info.annotations if info else None)
        if c.refused:
            raise Refused("tool_not_allowed", "That tool is outside what this connection was set up for.")
        return p, c

    # ---- the call
    def _row(self, conn_id: str, tool: str, klass: str, nbytes: int, outcome: str, mock: bool) -> dict[str, Any]:
        try:
            return cledger.record_call(server=conn_id, tool=tool, klass=klass if klass in cledger.CLASSES else "unknown", bytes_args=nbytes, outcome=outcome, mock=mock)
        except OSError:
            raise Refused("ledger_unavailable", "The privacy ledger could not be written, so the call was not made.") from None
        except ValueError:
            raise Refused("bad_request", "That call is not valid.") from None

    def _note_refusal(self, conn_id: str, tool: str, klass: str, nbytes: int, err: Refused, mock: bool) -> None:
        try:
            cledger.record_call(server=conn_id, tool=tool, klass=klass if klass in cledger.CLASSES else "unknown", bytes_args=nbytes, outcome=err.outcome, mock=mock)
        except (OSError, ValueError):
            pass                                                   # a refusal is already fail-closed; a missing row does not turn it into a call

    def call(self, conn_id: str, tool: str, arguments: dict[str, Any] | None, *, gate_ok: bool = False, expect_class: str | None = None,
             unattended: bool = False, routine_id: str | None = None, timeout: float = 30.0) -> CallOutcome:
        """``gate_ok``: the SafetyPipeline authorised this step (a person clicked, for anything but a read). ``expect_class``: the class it authorised;
        if the call is classified differently now (the server's tool list changed under us), it is refused."""
        mock, klass, nbytes = False, "unknown", 0
        try:
            nbytes = check_arguments(arguments)
            p, rec = self.usable(conn_id)
            mock = rec.get("mode") == "example"
            if self._killed():
                raise Refused("kill_flag", "The kill switch is set.", "blocked")
            self._check_denylist(p, rec)
            if not self.runner.is_running(conn_id):                      # first use after the agent restarted, or a crash: start it (consented and pinned)
                if self.runner.has_session(conn_id) and not self.runner.may_restart(conn_id):
                    raise Refused("keeps_stopping", "It keeps stopping, so it was left off. Connect it again to try.")
                if not self._start(conn_id)["ok"]:
                    raise Refused("start_failed", "The connection could not be started.")
            info = self.runner.tools(conn_id).get(tool)
            if info is None:
                raise Refused("unknown_tool", "That server has no such tool.")
            c = classify(p, tool, arguments, info.annotations)
            klass = c.klass
            if c.refused:
                raise Refused("tool_not_allowed", "That tool is outside what this connection was set up for.")
            if expect_class is not None and c.klass != expect_class:
                raise Refused("class_changed", "This call is not what was approved any more.")
            if unattended:
                if not state.routine_allows(conn_id, routine_id):
                    raise Refused("routine_not_opted_in", "This routine was not allowed to use this connection while you are away.")
                if c.klass != "read":
                    raise Refused("unattended_read_only", "Only reading is allowed while you are away.")
            if c.klass != "read" and not gate_ok:
                raise Refused("needs_click", "A person has to click before this runs.", "needs_click")
        except Refused as e:
            if e.code != "bad_arguments":
                self._note_refusal(conn_id, tool, klass, nbytes, e, mock)
            raise
        row = self._row(conn_id, tool, klass, nbytes, "ok", mock)             # BEFORE the call; fails closed
        t0 = time.monotonic()
        try:
            raw: RawResult = self.runner.call(conn_id, tool, arguments or {}, timeout=timeout)
        except RunnerError as e:
            cledger.finish_call(row, outcome="timeout" if e.code == "timeout" else "error", bytes_result=0, ms=int((time.monotonic() - t0) * 1000))
            raise Refused(e.code, str(e), "refused") from None
        cledger.finish_call(row, outcome="error" if raw.is_error else "ok", bytes_result=raw.bytes, ms=int((time.monotonic() - t0) * 1000))
        return CallOutcome(klass, c.source, raw.text, raw.is_error, raw.blocks_other, raw.truncated, nbytes, raw.bytes, mock)

    def _check_denylist(self, p: Preset, rec: dict[str, Any]) -> None:
        try:
            dl = self._denylist()
        except (OSError, ValueError):
            return
        for host in p.hosts(rec.get("params") or {}):
            if host and "." in host and dl.check_url(f"https://{host}/").denied:
                raise Refused("denylisted", "You put this app's address on your denylist.", "blocked")
        if dl.check_app(p.app).denied:
            raise Refused("denylisted", "You put this app on your denylist.", "blocked")


_service: ConnectionService | None = None


def default_service() -> ConnectionService:
    global _service
    if _service is None:
        _service = ConnectionService()
    return _service
