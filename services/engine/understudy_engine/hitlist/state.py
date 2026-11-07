"""What the worker has told the hit list: rows they hid, and when they last pressed "start counting again".

Stored beside their other private state (``<UNDERSTUDY_HOME>/hitlist_state.json``, written atomically). Only the worker's own UI
writes it (the routes check the actor and the origin). It holds ids, counts and step names from the routine finder, never a page,
a title, a file or a value. Resetting clears these two things and nothing else: events, episodes, routines, consent, ledgers and
the memory file are not read or touched here.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..memory.paths import data_dir, home_dir
from ..memory.store import atomic_write

_lock = threading.RLock()


class HitState:
    def __init__(self, home: str | Path | None = None) -> None:
        self.path = (Path(home).expanduser() if home else home_dir()) / "hitlist_state.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"people": {}}
        try:
            d = json.loads(self.path.read_text())
            return d if isinstance(d, dict) and isinstance(d.get("people"), dict) else {"people": {}}
        except (json.JSONDecodeError, OSError):
            return {"people": {}}

    def _save(self, st: dict[str, Any]) -> None:
        atomic_write(self.path, json.dumps(st, indent=1, sort_keys=True))

    def get(self, person: str) -> dict[str, Any]:
        """``{"reset_at": float | None, "hidden": {id: {"count": int, "signature": [str]}}}`` for one person."""
        p = self._load()["people"].get(person) or {}
        hidden = {str(k): {"count": int(v.get("count") or 0), "signature": [str(s) for s in v.get("signature") or []]}
                  for k, v in (p.get("hidden") or {}).items() if isinstance(v, dict)}
        reset = p.get("reset_at")
        return {"reset_at": float(reset) if isinstance(reset, (int, float)) else None, "hidden": hidden}

    def hide(self, person: str, rid: str, count: int, signature: list[str]) -> None:
        with _lock:
            st = self._load()
            p = st["people"].setdefault(person, {})
            p.setdefault("hidden", {})[rid] = {"count": int(count), "signature": list(signature)[:40]}
            self._save(st)

    def unhide(self, person: str, rid: str) -> bool:
        with _lock:
            st = self._load()
            hid = (st["people"].get(person) or {}).get("hidden") or {}
            if rid not in hid:
                return False
            del hid[rid]
            self._save(st)
            return True

    def reset(self, person: str, now: float) -> int:
        """Start counting again from ``now``: forget the hidden marks. Returns how many marks were cleared."""
        with _lock:
            st = self._load()
            p = st["people"].setdefault(person, {})
            cleared = len(p.get("hidden") or {})
            p["hidden"] = {}
            p["reset_at"] = float(now)
            self._save(st)
            return cleared


def audit(kind: str, note: str, *, outcome: str = "ok", actor: str = "worker") -> None:
    """One redacted line in ``<data>/audit.jsonl``, the same shape the other routes write. Counts only: no label, id or text."""
    line = {"t": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "actor": actor, "kind": kind,
            "routine": None, "run_id": None, "tier": None, "outcome": outcome, "note": note[:120]}
    try:
        p = data_dir() / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass
