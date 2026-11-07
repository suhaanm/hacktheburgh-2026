"""Append-only, redacted audit log (HND-8). File: data/audit.jsonl, one JSON object per line.

Lines carry NO page text. Free-text notes are stored only as a hash and a length. A short `note_code` (rule names,
reason codes, written by trusted code and never derived from page content) is kept readable. Every line also carries the
hash of the previous line, so truncation or editing is detectable (`verify_chain`).

Line shape (contract): {t, actor: human|agent|system, kind, routine, run_id, tier, outcome, note}, plus additive
fields: meta (numbers, booleans and short tokens only), prev, h.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .security.paths import audit_path

ACTORS = ("human", "agent", "system")
_TOKEN = re.compile(r"^[a-z0-9_.:@,\-]{1,200}$")
_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_META_TOKEN = re.compile(r"^[a-z0-9_.:\-]{1,40}$")
_MAX_META_KEYS = 16

# kinds the product writes (others are accepted if they are plain tokens)
KINDS = (
    "run_start", "run_end", "step", "tier_escalation", "gate", "queue_enqueued", "queue_decided",
    "injection_pause", "drift_pause", "stuck_loop", "dataflow", "denylist", "settings_blocked", "budget",
    "kill", "rung_lowered", "completion_check", "false_claim", "consent", "shadow", "offhours", "observation",
)


def hash_text(text: str) -> str:
    return "h:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def _token_or_hash(v: Any, pattern: re.Pattern[str] = _ID) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if pattern.match(s) else hash_text(s)


def redact_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in list((meta or {}).items())[:_MAX_META_KEYS]:
        key = str(k)
        if not _META_TOKEN.match(key):
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)) or v is None:
            out[key] = v
        elif isinstance(v, str):
            out[key] = v if _META_TOKEN.match(v) else hash_text(v)
        # anything else (lists, dicts, bytes) is dropped
    return out


def _canon(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class AuditLog:
    def __init__(self, path: Path | None = None, clock: Callable[[], datetime] | None = None, *, fsync: bool = True) -> None:
        self._path = path
        self._fsync = fsync
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path or audit_path()

    def append(self, actor: str, kind: str, *, routine: str | None = None, run_id: str | None = None,
               tier: int | None = None, outcome: str | None = None, note_code: str | None = None,
               note: str | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if actor not in ACTORS:
            raise ValueError(f"actor must be one of {ACTORS}")
        if tier is not None and tier not in (1, 2, 3):
            raise ValueError("tier must be 1, 2 or 3")
        if note_code is not None:
            note_out: str | None = note_code if _TOKEN.match(note_code) else hash_text(note_code)
        elif note is not None:
            note_out = f"{hash_text(note)} len={len(note)}"
        else:
            note_out = None
        line: dict[str, Any] = {
            "t": self._clock().astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "actor": actor,
            "kind": _token_or_hash(kind, _META_TOKEN),
            "routine": _token_or_hash(routine),
            "run_id": _token_or_hash(run_id),
            "tier": tier,
            "outcome": _token_or_hash(outcome, _META_TOKEN),
            "note": note_out,
        }
        m = redact_meta(meta)
        if m:
            line["meta"] = m
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, open(p, "a+b") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                line["prev"] = self._last_hash(f)
                line["h"] = hashlib.sha256((line["prev"] + _canon(line)).encode()).hexdigest()[:16]
                f.seek(0, os.SEEK_END)
                f.write((_canon(line) + "\n").encode("utf-8"))
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return line

    @staticmethod
    def _last_hash(f: Any) -> str:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return "genesis"
        f.seek(max(0, size - 4096))
        tail = f.read().decode("utf-8", "replace").strip().splitlines()
        if not tail:
            return "genesis"
        try:
            return json.loads(tail[-1]).get("h", "genesis")
        except json.JSONDecodeError:
            return "corrupt"

    # ---- reading
    def read(self, limit: int = 100, *, since: str | None = None) -> list[dict[str, Any]]:
        p = self.path
        if not p.exists():
            return []
        rows = []
        with open(p, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if since and row.get("t", "") < since:
                    continue
                rows.append(row)
        return rows[-limit:] if limit else rows

    def verify_chain(self) -> bool:
        prev = "genesis"
        p = self.path
        if not p.exists():
            return True
        with open(p, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                row = json.loads(raw)
                h = row.pop("h", None)
                if row.get("prev") != prev:
                    return False
                if hashlib.sha256((prev + _canon(row)).encode()).hexdigest()[:16] != h:
                    return False
                prev = h
        return True


_default: AuditLog | None = None


def get_audit_log() -> AuditLog:
    global _default
    if _default is None:
        _default = AuditLog()
    return _default
