"""The egress ledger (PRV-2): an append-only record, kept on this machine, of every call to a remote model that the
extension layers make.

``<data dir>/egress_ledger.jsonl``: one JSON line per call, written BEFORE the call is made. A line holds the time, the
purpose, the schema id, the field names, the payload exactly as sent, the model id and the byte count. It never holds raw
source text, because none can reach a ``SafePayload``.

Other files beside it, all under the data dir:

* ``egress_blocked.jsonl``: attempts the guard refused (purpose, rule names, field paths; never values),
* ``egress_ledger_meta.json``: how many times and when the worker cleared the ledger (so a cleared ledger is not mistaken
  for "no calls ever"),
* ``privacy_canary.json``: the last canary evaluation (written by ``canary.record_run``).

Lines for calls the worker asked for through other paths (an agent run) may be added with ``record_direct``: metadata only
(model, method, byte count), never the content, because the content there is raw.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ._paths import data_dir

LEDGER_NAME = "egress_ledger.jsonl"
BLOCKED_NAME = "egress_blocked.jsonl"
META_NAME = "egress_ledger_meta.json"
CANARY_NAME = "privacy_canary.json"

_lock = threading.RLock()

LOCAL_ONLY_NOTE = (
    "This list shows each call to a remote model made by an Understudy extension feature, with exactly the content that was "
    "sent: numbers, codes and fixed ids, never free text. Calls you asked for yourself, such as an agent run, are model calls "
    "too and are listed here (without content) when they go through the guard; the count below says how many are. This page "
    "does not claim that nothing else leaves this laptop: the browser extension, your own sign-ins and any site an agent "
    "visits are outside this ledger."
)


def ledger_path() -> Path:
    return data_dir() / LEDGER_NAME


def blocked_path() -> Path:
    return data_dir() / BLOCKED_NAME


def meta_path() -> Path:
    return data_dir() / META_NAME


def canary_path() -> Path:
    return data_dir() / CANARY_NAME


def now_iso(now: datetime | None = None) -> str:
    t = now or datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return f"e_{time.time_ns():x}{uuid.uuid4().hex[:4]}"


def _append_line(path: Path, obj: dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=True, separators=(",", ":"), sort_keys=False) + "\n"
    data = line.encode("ascii")
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)


def append(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one ledger line. Fills ``id`` and ``t`` when missing. Raises OSError when the file cannot be written (the
    caller then does not make the call)."""
    entry = dict(entry)
    entry.setdefault("id", new_id())
    entry.setdefault("t", now_iso())
    _append_line(ledger_path(), entry)
    return entry


def log_blocked(purpose: str, reason: str, rules: list[str], fields: list[str]) -> None:
    """Record a refused attempt: what was refused and why, never the content."""
    try:
        _append_line(blocked_path(), {"id": new_id(), "t": now_iso(), "purpose": purpose, "reason": reason,
                                      "rules": rules[:12], "fields": fields[:12]})
    except OSError:
        pass  # a refusal is already fail-closed; not being able to note it must not turn into a send


def record_direct(*, method: str, model: str, bytes_sent: int, purpose: str = "worker_requested", note: str = "",
                  mock: bool = False) -> dict[str, Any]:
    """A call the worker asked for through another path (for example an agent step). Metadata only: the content is raw
    and is deliberately not stored here."""
    return append({
        "kind": "direct", "purpose": purpose, "schema": None, "fields": [], "payload": None, "content_logged": False,
        "model": model, "bytes": int(bytes_sent), "method": method, "mock": bool(mock), "note": note[:120],
    })


def _iter_lines(path: Path) -> Iterator[tuple[dict[str, Any] | None, str]]:
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError:
        return
    with fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                yield None, raw
                continue
            yield (obj if isinstance(obj, dict) else None), raw


def read_all() -> list[dict[str, Any]]:
    """Every readable line, oldest first."""
    with _lock:
        return [o for o, _ in _iter_lines(ledger_path()) if o is not None]


def read(limit: int | None = 100) -> list[dict[str, Any]]:
    """The newest ``limit`` lines, newest first (``limit=None`` for all)."""
    rows = read_all()
    rows.reverse()
    return rows if limit is None else rows[: max(0, limit)]


def count() -> int:
    return len(read_all())


def blocked(limit: int | None = 100) -> list[dict[str, Any]]:
    rows = [o for o, _ in _iter_lines(blocked_path()) if o is not None]
    rows.reverse()
    return rows if limit is None else rows[: max(0, limit)]


def _read_meta() -> dict[str, Any]:
    try:
        return json.loads(meta_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clear() -> dict[str, Any]:
    """The worker clears the ledger: the call lines and the refusal lines are removed; a small note of how many times and
    when it happened is kept so the Privacy screen can say so. Returns ``{cleared, blocked_cleared, at}``."""
    with _lock:
        rows = read_all()
        brows = [o for o, _ in _iter_lines(blocked_path()) if o is not None]
        for p in (ledger_path(), blocked_path()):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        meta = _read_meta()
        at = now_iso()
        meta["clear_count"] = int(meta.get("clear_count", 0)) + 1
        meta["calls_removed_total"] = int(meta.get("calls_removed_total", 0)) + len(rows)
        meta["last_cleared_at"] = at
        meta_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = meta_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp, meta_path())
    return {"cleared": len(rows), "blocked_cleared": len(brows), "at": at}


def export_jsonl() -> str:
    """The ledger as the JSONL text on disk (oldest first), for the worker to save."""
    with _lock:
        try:
            return ledger_path().read_text(encoding="utf-8")
        except OSError:
            return ""


def canary_summary() -> dict[str, Any]:
    """The last canary evaluation: ``{runs, planted, leaked, last_run}``; zeros when none has been recorded."""
    try:
        raw = json.loads(canary_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return {
        "runs": int(raw.get("runs", 0)), "planted": int(raw.get("planted", 0)), "leaked": int(raw.get("leaked", 0)),
        "last_run": raw.get("last_run"), "flows": raw.get("flows", []),
    }


def summary() -> dict[str, Any]:
    """Counts by purpose, the last call, how many were mock, how many were direct, refusals, clears, and the honest note."""
    rows = read_all()
    by_purpose: dict[str, int] = {}
    mock = direct = 0
    for r in rows:
        p = str(r.get("purpose", "?"))
        by_purpose[p] = by_purpose.get(p, 0) + 1
        mock += 1 if r.get("mock") else 0
        direct += 1 if r.get("kind") == "direct" else 0
    last = rows[-1] if rows else None
    meta = _read_meta()
    return {
        "calls": len(rows),
        "by_purpose": dict(sorted(by_purpose.items())),
        "last_call": ({"t": last.get("t"), "purpose": last.get("purpose"), "model": last.get("model"), "bytes": last.get("bytes"),
                       "mock": bool(last.get("mock"))} if last else None),
        "mock_calls": mock,
        "worker_requested_calls": direct,
        "blocked_attempts": len([1 for o, _ in _iter_lines(blocked_path()) if o is not None]),
        "cleared": {"times": int(meta.get("clear_count", 0)), "calls_removed": int(meta.get("calls_removed_total", 0)),
                    "last_cleared_at": meta.get("last_cleared_at")},
        "local_only_note": LOCAL_ONLY_NOTE,
        "canary": {k: v for k, v in canary_summary().items() if k in ("runs", "planted", "leaked", "last_run")},
    }
