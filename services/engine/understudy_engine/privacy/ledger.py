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

Image calls (``egress.send_image``) write ``kind: "image"`` rows. The file stays append-only, so an image call is one ``image`` line
written before the call and one small ``image_result`` line written after (latency, tokens, cost, ok); ``read_all()`` merges the
pair, so every consumer sees exactly ONE row per call. A call refused by the gate is one row with ``status: "blocked"`` and a reason.
An image row may hold only: sha8 (the first 8 bytes of the SHA-256), bytes, width, height, kind, source, provider, model,
latency_ms, input and output tokens, a cost estimate and ok. Never the image.

Two more row kinds follow the same two-line, merged-on-read pattern and carry no content either: ``audio`` (one worker turn of live
audio: a seconds bucket, bytes, model, source) and ``reported`` (a call another process makes and reports: its content kind, byte count,
item count, provider, model, source). Both can be refused by the same gate (a ``blocked`` row with a reason).
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
                  mock: bool | None = None) -> dict[str, Any]:
    """A call the worker asked for through another path (for example an agent step). Metadata only: the content is raw
    and is deliberately not stored here. ``mock`` defaults to true in mock mode or when the model id names the mock or a test port."""
    if mock is None:
        from ._paths import is_mock

        mock = is_mock() or model.split(":", 1)[0] in ("mock", "capturing")
    return append({
        "kind": "direct", "purpose": purpose, "schema": None, "fields": [], "payload": None, "content_logged": False,
        "model": model, "bytes": int(bytes_sent), "method": method, "mock": bool(mock), "note": note[:120],
    })


def begin_row(kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    """The first line of a call row (``image``, ``audio`` or ``reported``), written BEFORE the call with status ``sending``. Raises
    OSError if it cannot be written."""
    if kind not in CALL_ROW_KINDS:
        raise ValueError(f"unknown call row kind {kind!r}")
    return append({**entry, "kind": kind, "status": "sending"})


def begin_image(entry: dict[str, Any]) -> dict[str, Any]:
    """The ``image`` line, written BEFORE the call (status ``sending``). Raises OSError if it cannot be written."""
    return begin_row("image", entry)


def finish_image(ref: str, *, status: str, ok: bool, latency_ms: int | None, input_tokens: int | None = None,
                 output_tokens: int | None = None, cost_estimate_usd: float | None = None, error: str | None = None,
                 bytes_sent: int | None = None, seconds_bucket: str | None = None) -> None:
    """The ``image_result`` line written AFTER the call: numbers and an error type name only (also finishes ``audio`` and ``reported``
    rows; ``bytes_sent`` and ``seconds_bucket`` are known only afterwards for audio). Never raises (the call already happened; a missing
    result line leaves the row at status ``sending``, which is honest)."""
    line: dict[str, Any] = {"id": new_id(), "t": now_iso(), "kind": "image_result", "ref": ref, "status": status, "ok": bool(ok),
                            "latency_ms": latency_ms, "input_tokens": input_tokens, "output_tokens": output_tokens,
                            "cost_estimate_usd": cost_estimate_usd, "error": (error or None) and str(error)[:60]}
    if bytes_sent is not None:
        line["bytes"] = int(bytes_sent)
    if seconds_bucket is not None:
        line["seconds_bucket"] = seconds_bucket
    try:
        _append_line(ledger_path(), line)
    except OSError:
        pass


def record_blocked_row(kind: str, *, purpose: str, reason: str, source: str, meta: dict[str, Any] | None = None, mock: bool = False,
                       meta_key: str = "image") -> dict[str, Any]:
    """One row for a call the gate refused (kind ``image``, ``audio`` or ``reported``). Needs no content. Nothing was sent."""
    if kind not in CALL_ROW_KINDS:
        raise ValueError(f"unknown call row kind {kind!r}")
    return append({"kind": kind, "status": "blocked", "reason": reason, "purpose": purpose, "source": source, "schema": None,
                   "fields": [], "payload": None, meta_key: meta, "provider": None, "model": None, "bytes": 0, "mock": bool(mock), "ok": False})


def record_image_blocked(*, purpose: str, reason: str, source: str, image_meta: dict[str, Any] | None = None, mock: bool = False) -> dict[str, Any]:
    """One row for a frame the gate refused. Needs no image: ``image_meta`` may be None. Nothing was sent."""
    return record_blocked_row("image", purpose=purpose, reason=reason, source=source, meta=image_meta, mock=mock, meta_key="image")


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


IMAGE_RESULT_FIELDS = ("status", "ok", "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error")
CALL_ROW_KINDS = ("image", "audio", "reported")          # kinds written as a begin line and finished by an image_result line


def _merge_image_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per call: fold each ``image_result`` line into the ``image``, ``audio`` or ``reported`` line it refers to (and drop it)."""
    by_id = {r["id"]: r for r in rows if r.get("kind") in CALL_ROW_KINDS and isinstance(r.get("id"), str)}
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("kind") == "image_result":
            parent = by_id.get(r.get("ref"))
            if parent is not None:
                for k in IMAGE_RESULT_FIELDS:
                    if k in r:
                        parent[k] = r[k]
                if "bytes" in r:                                  # the actual size, known only after the call
                    parent["bytes"] = r["bytes"]
                    for sub in ("audio", "content"):
                        if isinstance(parent.get(sub), dict):
                            parent[sub]["bytes"] = r["bytes"]
                if "seconds_bucket" in r and isinstance(parent.get("audio"), dict):
                    parent["audio"]["seconds_bucket"] = r["seconds_bucket"]
                    if isinstance(parent.get("payload"), dict):
                        parent["payload"]["seconds_bucket"] = r["seconds_bucket"]
            continue
        out.append(r)
    return out


def read_all() -> list[dict[str, Any]]:
    """Every readable row, oldest first. An image call's two physical lines are merged into one row."""
    with _lock:
        rows = [o for o, _ in _iter_lines(ledger_path()) if o is not None]
    return _merge_image_results(rows)


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


def reset_all() -> None:
    """Delete the ledger, refusal lines, clear-notes and canary record WITHOUT leaving a trace (``make demo`` reseeding). The worker's
    own action is ``clear()``, which keeps a note that it happened; do not use this one for that."""
    with _lock:
        for p in (ledger_path(), blocked_path(), meta_path(), canary_path()):
            try:
                p.unlink()
            except FileNotFoundError:
                pass


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
    """Counts by purpose, the last call, how many were mock, how many were direct, images sent and blocked, refusals, clears, and
    the honest note. Rows the gate refused (``status: "blocked"``) are not calls: nothing was sent."""
    rows = read_all()
    by_purpose: dict[str, int] = {}
    mock = direct = 0
    sent = [r for r in rows if r.get("status") != "blocked"]
    images = [r for r in rows if r.get("kind") == "image"]
    blocked_images = [r for r in images if r.get("status") == "blocked"]
    for r in sent:
        p = str(r.get("purpose", "?"))
        by_purpose[p] = by_purpose.get(p, 0) + 1
        mock += 1 if r.get("mock") else 0
        direct += 1 if r.get("kind") == "direct" else 0
    last = sent[-1] if sent else None
    meta = _read_meta()
    by_reason: dict[str, int] = {}
    for r in blocked_images:
        by_reason[str(r.get("reason"))] = by_reason.get(str(r.get("reason")), 0) + 1
    sent_images = [r for r in images if r.get("status") != "blocked"]
    by_source: dict[str, int] = {}
    for r in sent_images:
        by_source[str(r.get("source"))] = by_source.get(str(r.get("source")), 0) + 1

    def block(kind: str) -> dict[str, Any]:
        mine = [r for r in rows if r.get("kind") == kind]
        ok_rows = [r for r in mine if r.get("status") != "blocked"]
        reasons: dict[str, int] = {}
        for r in mine:
            if r.get("status") == "blocked":
                reasons[str(r.get("reason"))] = reasons.get(str(r.get("reason")), 0) + 1
        out: dict[str, Any] = {"sent": len(ok_rows), "blocked": len(mine) - len(ok_rows), "blocked_by_reason": dict(sorted(reasons.items())),
                               "bytes_sent": sum(int(r.get("bytes") or 0) for r in ok_rows)}
        if kind == "reported":
            by_kind: dict[str, int] = {}
            by_provider: dict[str, int] = {}
            for r in ok_rows:
                by_kind[str((r.get("content") or {}).get("kind"))] = by_kind.get(str((r.get("content") or {}).get("kind")), 0) + 1
                by_provider[str(r.get("provider"))] = by_provider.get(str(r.get("provider")), 0) + 1
            out["sent_by_kind"], out["sent_by_provider"] = dict(sorted(by_kind.items())), dict(sorted(by_provider.items()))
        return out
    return {
        "calls": len(sent),
        "by_purpose": dict(sorted(by_purpose.items())),
        "last_call": ({"t": last.get("t"), "purpose": last.get("purpose"), "model": last.get("model"), "bytes": last.get("bytes"),
                       "mock": bool(last.get("mock"))} if last else None),
        "mock_calls": mock,
        "worker_requested_calls": direct,
        "images": {"sent": len(sent_images), "blocked": len(blocked_images), "blocked_by_reason": dict(sorted(by_reason.items())),
                   "sent_by_source": dict(sorted(by_source.items())),
                   "bytes_sent": sum(int((r.get("image") or {}).get("bytes", 0)) for r in sent_images),
                   "note": "Frames are held in memory for one call and never stored; a row records size, a short hash, model and latency only."},
        "audio": {**block("audio"), "note": "A row is one worker turn: a seconds bucket, bytes, model and source. Audio and transcripts are never stored."},
        "reported": {**block("reported"), "note": "Calls another process reports (legacy desktop paths): content kind, bytes, count, provider, model. Never the content."},
        "blocked_attempts": len([1 for o, _ in _iter_lines(blocked_path()) if o is not None]),
        "cleared": {"times": int(meta.get("clear_count", 0)), "calls_removed": int(meta.get("calls_removed_total", 0)),
                    "last_cleared_at": meta.get("last_cleared_at")},
        "local_only_note": LOCAL_ONLY_NOTE,
        "canary": {k: v for k, v in canary_summary().items() if k in ("runs", "planted", "leaked", "last_run")},
    }
