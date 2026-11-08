"""The assist ledger (CUE-6): append-only JSONL, local, worker-owned. View, export, hard delete.

Path: ``<data>/assist/ledger.jsonl``. Schema: ``packages/schema/assist_ledger.schema.json`` (``additionalProperties: false``; enums,
numbers, a one-hour time bucket and id-patterned slugs; no text, no screenshots, no free strings). A row that does not validate is
refused at write time, so what is on disk is exactly what the schema allows.

One row per skill OCCURRENCE in the ``assist`` stream (the unit of the independence score), with or without a cue; ``delegated`` and
``automation`` rows are offloaded work, shown in their own list and never counted in any score number (see ``score``).

Delete is a hard delete (the rows are gone from the file, not flagged) and appends ONE audit line to ``data/audit.jsonl`` that holds
counts only. The caller (the route) also removes the stored intent labels and the summary line in the memory file.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import paths
from .types import OUTCOMES, STREAMS, TRIGGERS

FOLLOW_S = 10.0           # a step completed within 10 s of a cue was followed (policy/labels.py window)
_LOCK = threading.RLock()


class LedgerError(ValueError):
    """A row the schema refuses. The message names the field, never echoes a value."""


@lru_cache(maxsize=1)
def _validator():
    import jsonschema

    schema = json.loads(paths.schema_path().read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def t_hour(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H")


@lru_cache(maxsize=32768)
def hour_to_epoch(h: str) -> float:
    """An hour bucket's epoch. Pure, and there are few distinct strings (one per hour), but the growth score asks it about every ledger row hundreds of
    thousands of times per request (strptime is slow): remembered per string."""
    return datetime.strptime(h, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).timestamp()


def stuck_bucket(p: float | None) -> str | None:
    if p is None:
        return None
    return "p00_59" if p < 0.60 else ("p60_79" if p < 0.80 else ("p80_94" if p < 0.95 else "p95_100"))


def new_id(*parts: object) -> str:
    return "a_" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def validate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Raise ``LedgerError`` unless the row matches the schema. Reports the field, never the value."""
    errs = sorted(_validator().iter_errors(row), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        where = ".".join(str(x) for x in e.path) or "(row)"
        raise LedgerError(f"ledger row refused at {where}: {e.validator} does not hold")
    return row


def classify_outcome(*, completed: bool, error: bool = False, accepted: bool = False, answered: bool = False,
                     followed_within_s: float | None = None) -> str:
    """The outcome of one occurrence. Errors and not finishing are never independence; any accepted help is 'assisted';
    a step completed within 10 s of a cue counts as followed (the implicit label window)."""
    if not completed:
        return "abandoned"
    if error:
        return "error"
    if accepted or answered or (followed_within_s is not None and followed_within_s <= FOLLOW_S):
        return "assisted"
    return "clean"


def make_row(*, person: str, role: str, skill: str | None, t: float, outcome: str, origin: str = "real", step: str | None = None,
             stream: str = "assist", trigger: str = "none", tier: int = 0, options_shown: int = 0, answer_id: str | None = None,
             accepted: bool = False, dismissed: bool = False, seconds_to_progress: float | None = None, lost_s: float | None = None,
             p_stuck: float | None = None, level_before: int | None = None, level_after: int | None = None, taught: bool = False,
             retrieval: bool = False, origin_detail: str | None = None, routine: str | None = None, minutes: float | None = None,
             offload_outcome: str | None = None, row_id: str | None = None, serial: int = 0) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise LedgerError("outcome is not one of the allowed values")
    row: dict[str, Any] = {
        "id": row_id or new_id(person, round(t, 3), skill, step, stream, serial),
        "person": person, "origin": origin, "t_hour": t_hour(t), "role": role, "skill": skill, "step": step, "stream": stream,
        "trigger": trigger, "stuck_bucket": stuck_bucket(p_stuck) if trigger != "none" else None, "tier": int(tier),
        "options_shown": int(options_shown), "answer_id": answer_id, "accepted": bool(accepted), "dismissed": bool(dismissed),
        "seconds_to_progress": None if seconds_to_progress is None else round(float(min(3600.0, max(0.0, seconds_to_progress))), 1),
        "lost_s": None if lost_s is None else round(float(min(3600.0, max(-600.0, lost_s))), 1),
        "outcome": outcome, "level_before": level_before, "level_after": level_after, "taught": bool(taught), "retrieval": bool(retrieval),
    }
    if origin_detail:
        row["origin_detail"] = origin_detail
    if stream != "assist":
        row["routine"], row["minutes"], row["offload_outcome"] = routine, minutes, offload_outcome
    if trigger not in TRIGGERS or stream not in STREAMS:
        raise LedgerError("trigger or stream is not one of the allowed values")
    return validate_row(row)


class Ledger:
    """The JSONL file. ``Ledger(path)`` for a temp path in tests and the simulator; default is the worker's data dir."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else paths.ledger_path()

    # ---------------------------------------------------------------- write
    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        validate_row(row)
        line = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, line)
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
        return row

    def extend(self, rows: Iterable[dict[str, Any]]) -> int:
        n = 0
        for r in rows:
            self.append(r)
            n += 1
        return n

    # ---------------------------------------------------------------- read
    _cache: tuple | None = None

    def _read_all(self) -> list[dict[str, Any]]:
        try:
            s = self.path.stat()
        except OSError:
            return []
        key = (s.st_mtime_ns, s.st_size, s.st_ino)
        if self._cache is not None and self._cache[0] == key:
            return [dict(r) for r in self._cache[1]]
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue            # a torn line is skipped, never repaired or echoed
        self._cache = (key, [dict(r) for r in out])
        return out

    def rows(self, person: str | None = None, stream: str | None = None, *, limit: int | None = None, newest_first: bool = False,
             skill: str | None = None) -> list[dict[str, Any]]:
        rs = [r for r in self._read_all() if (person is None or r.get("person") == person) and (stream is None or r.get("stream") == stream)
              and (skill is None or r.get("skill") == skill)]
        rs.sort(key=lambda r: r.get("t_hour", ""), reverse=newest_first)    # stable: file order within an hour
        if newest_first:
            rs = _newest_first_stable(rs)
        return rs[:limit] if limit else rs

    def counts(self, person: str | None = None) -> dict[str, int]:
        c = Counter(r.get("stream") for r in self._read_all() if person is None or r.get("person") == person)
        return {s: int(c.get(s, 0)) for s in STREAMS}

    def persons(self) -> list[str]:
        return sorted({r.get("person") for r in self._read_all() if r.get("person")})

    def export(self, person: str | None = None) -> dict[str, Any]:
        rows = self.rows(person)
        return {"schema": "assist_ledger.schema.json", "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "person": person, "counts": self.counts(person), "rows": rows}

    # ---------------------------------------------------------------- delete (worker-owned, hard)
    def delete(self, person: str | None = None, *, audit: bool = True, actor: str = "human") -> dict[str, int]:
        """Remove the person's rows (everyone's when ``person`` is None) from the file. Appends one audit line with counts only."""
        with _LOCK:
            rows = self._read_all()
            gone = Counter()
            keep = []
            for r in rows:
                if person is None or r.get("person") == person:
                    gone[r.get("stream")] += 1
                else:
                    keep.append(r)
            if self.path.is_file():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix="ledger.", suffix=".tmp", dir=str(self.path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        for r in keep:
                            fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.replace(tmp, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp)
                    except FileNotFoundError:
                        pass
                    raise
        out = {s: int(gone.get(s, 0)) for s in STREAMS}
        if audit:
            _audit_delete(out, actor)
        return out


def _newest_first_stable(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Within one hour bucket keep the later-written row first (file order reversed)."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(rs):
        j = i
        while j < len(rs) and rs[j].get("t_hour") == rs[i].get("t_hour"):
            j += 1
        out.extend(reversed(rs[i:j]))
        i = j
    return out


def _audit_delete(counts: dict[str, int], actor: str) -> None:
    """One line, counts only. Nothing from any row is copied into it."""
    line = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "actor": actor if actor in ("human", "agent", "system") else "human",
            "kind": "assist_ledger_deleted", "routine": None, "run_id": None, "tier": None, "outcome": "deleted",
            "note": "rows removed: " + ", ".join(f"{k}={v}" for k, v in counts.items())}
    try:
        p = paths.data_dir() / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass
