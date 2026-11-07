"""The attention store (REQ-8): item state, the worker's settings, the day's counters, the one-voice lock, the reaction labels.

Everything in it is an id, an enum, a count or a timestamp: the same metadata the events carry. It lives on the device
(``<data>/attention/state.json`` plus an append-only ``log.jsonl`` of transitions), can be exported and deleted by the worker, and never
reaches a model or the network. With no path it is memory only (the simulated workday and most tests use that).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .events import Item
from .learning import Acceptance, Label
from .state import DEFAULT, Params, Settings

VERSION = 1


@dataclass
class PersonState:
    person: str
    items: dict[str, Item] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)               # {modes, budget_per_day, level_glance}
    day: str = ""
    budget_used: int = 0
    wait_toasts: int = 0
    last_interruption_t: float | None = None
    level_glances: list[float] = field(default_factory=list)
    lock: dict[str, Any] | None = None
    labels: list[dict[str, Any]] = field(default_factory=list)
    never_subjects: list[str] = field(default_factory=list)
    last_digest_t: float | None = None
    last_active_t: float | None = None
    away_since: float | None = None
    returned_t: float | None = None
    pending_return: dict[str, Any] | None = None
    last_ws: dict[str, Any] | None = None
    seq: int = 0
    counters: dict[str, int] = field(default_factory=dict)               # today's shown/held/dropped by channel and reason
    acc: Acceptance = field(default_factory=Acceptance, repr=False)

    def get_settings(self) -> Settings:
        s = self.settings
        return Settings(modes=dict(s.get("modes", {})), budget_per_day=int(s.get("budget_per_day", DEFAULT.budget_per_day)),
                        level_glance=bool(s.get("level_glance", True)))

    def to_dict(self) -> dict[str, Any]:
        return {"person": self.person, "items": {k: v.to_dict() for k, v in self.items.items()}, "settings": self.settings, "day": self.day,
                "budget_used": self.budget_used, "wait_toasts": self.wait_toasts, "last_interruption_t": self.last_interruption_t,
                "level_glances": self.level_glances, "lock": self.lock, "labels": self.labels, "never_subjects": self.never_subjects,
                "last_digest_t": self.last_digest_t, "last_active_t": self.last_active_t, "away_since": self.away_since,
                "returned_t": self.returned_t, "pending_return": self.pending_return, "last_ws": self.last_ws, "seq": self.seq,
                "counters": self.counters}

    @classmethod
    def from_dict(cls, d: dict[str, Any], params: Params = DEFAULT) -> PersonState:
        ps = cls(person=d["person"])
        for k in ("settings", "day", "budget_used", "wait_toasts", "last_interruption_t", "level_glances", "lock", "labels", "never_subjects",
                  "last_digest_t", "last_active_t", "away_since", "returned_t", "pending_return", "last_ws", "seq", "counters"):
            if k in d:
                setattr(ps, k, d[k])
        ps.items = {k: Item.from_dict(v) for k, v in d.get("items", {}).items()}
        ps.rebuild_acceptance(params)
        return ps

    def rebuild_acceptance(self, params: Params = DEFAULT) -> None:
        self.acc = Acceptance([Label.from_dict(x) for x in self.labels], params)


class AttentionStore:
    def __init__(self, path: Path | str | None = None, log_path: Path | str | None = None, params: Params = DEFAULT) -> None:
        self.path = Path(path) if path else None
        self.log_path = Path(log_path) if log_path else None
        self.params = params
        self._lock = threading.RLock()
        self._persons: dict[str, PersonState] = {}
        self._loaded = False

    # ------------------------------------------------------------------------------------------------ io
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.path is None or not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text())
            for pid, pd in d.get("persons", {}).items():
                self._persons[pid] = PersonState.from_dict(pd, self.params)
        except (OSError, ValueError, KeyError):
            self._persons = {}                  # a damaged state file must not take the layer down: start clean, the log is intact

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                doc = {"version": VERSION, "persons": {pid: ps.to_dict() for pid, ps in self._persons.items()}}
                fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(doc, f, separators=(",", ":"))
                    os.replace(tmp, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            except OSError:
                pass                              # losing a save only loses held state; the worker is never blocked by it

    def log(self, entry: dict[str, Any]) -> None:
        """One metadata line: time, person, item id, type, from and to state, reason code, channel. Never any text."""
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, (json.dumps(entry, separators=(",", ":")) + "\n").encode())
            finally:
                os.close(fd)
        except OSError:
            pass

    # ------------------------------------------------------------------------------------------------ access
    def person(self, pid: str) -> PersonState:
        with self._lock:
            self._load()
            ps = self._persons.get(pid)
            if ps is None:
                ps = self._persons[pid] = PersonState(person=pid)
                ps.rebuild_acceptance(self.params)
            return ps

    def persons(self) -> list[str]:
        with self._lock:
            self._load()
            return sorted(self._persons)

    def find(self, item_id: str) -> tuple[PersonState, Item] | None:
        with self._lock:
            self._load()
            for ps in self._persons.values():
                it = ps.items.get(item_id)
                if it is not None:
                    return ps, it
        return None

    def export(self, pid: str) -> dict[str, Any]:
        ps = self.person(pid)
        d = ps.to_dict()
        d["learned"] = ps.acc.summary()
        return {"version": VERSION, "metadata_only": True, "person": pid, "state": d}

    def delete(self, pid: str | None = None) -> int:
        with self._lock:
            self._load()
            n = len(self._persons) if pid is None else int(pid in self._persons)
            if pid is None:
                self._persons.clear()
            else:
                self._persons.pop(pid, None)
            self.save()
            if pid is None and self.log_path is not None:
                try:
                    self.log_path.unlink()
                except OSError:
                    pass
            return n
