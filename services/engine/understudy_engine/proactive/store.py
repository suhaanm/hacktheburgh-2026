"""Persistence for the briefing: ``<data>/briefing.json``.

One small JSON file for everyone on the machine, replaced atomically (temp file and ``os.replace``) under a file lock so
the engine and a second process never see half a write::

    {"version": 1,
     "persons": {"p_x": {"generated_at": ISO|null,
                         "cards": [Card.to_dict()],
                         "suppress": {subject: {"until": unix|null, "reason": "not_now"|"never"|"fired"}},
                         "labels": [{"t": unix, "kind": str, "accepted": bool, "card": id}],
                         "viewed_runs": [run ids],
                         "seed": "demo_v1"|null}}}

Raw source text never enters this file: cards hold templated titles, pack text and numbers, and the worker's own edits.
Labels are what acceptance learning reads (PRO-3); a press is an accept, a dismissal a decline.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TypeVar

from .cards import Card
from .paths import briefing_path

T = TypeVar("T")
_TLOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()


def _tlock(key: str) -> threading.RLock:
    with _GUARD:
        return _TLOCKS.setdefault(key, threading.RLock())


def empty_person() -> dict[str, Any]:
    return {"generated_at": None, "cards": [], "suppress": {}, "labels": [], "viewed_runs": [], "seed": None}


class BriefingStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else briefing_path()
        self._lock_path = self.path.with_suffix(".lock")
        self._tl = _tlock(str(self.path))
        self._depth = threading.local()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._tl:
            if getattr(self._depth, "n", 0):
                self._depth.n += 1
                try:
                    yield
                finally:
                    self._depth.n -= 1
                return
            with open(self._lock_path, "a+") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                self._depth.n = 1
                try:
                    yield
                finally:
                    self._depth.n = 0
                    fcntl.flock(lf, fcntl.LOCK_UN)

    # ----- raw file -----
    def _read(self) -> dict[str, Any]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "persons": {}}
        if not isinstance(d, dict) or not isinstance(d.get("persons"), dict):
            return {"version": 1, "persons": {}}
        return d

    def _write(self, d: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(d, indent=1, sort_keys=True))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    # ----- person state -----
    def person(self, person: str) -> dict[str, Any]:
        """A copy of one person's state (never None)."""
        with self._locked():
            st = self._read()["persons"].get(person)
        return json.loads(json.dumps({**empty_person(), **(st or {})}))

    def mutate(self, person: str, fn: Callable[[dict[str, Any]], T]) -> T:
        """Run ``fn(state)`` under the lock and save what it changed. The one write path."""
        with self._locked():
            d = self._read()
            st = {**empty_person(), **d["persons"].get(person, {})}
            out = fn(st)
            d["persons"][person] = st
            self._write(d)
            return out

    def persons(self) -> list[str]:
        with self._locked():
            return sorted(self._read()["persons"])

    # ----- cards -----
    def cards(self, person: str) -> list[Card]:
        return [Card.from_dict(c) for c in self.person(person)["cards"]]

    def find(self, card_id: str) -> Card | None:
        with self._locked():
            for p, st in self._read()["persons"].items():
                for c in st.get("cards", []):
                    if c.get("id") == card_id:
                        return Card.from_dict({**c, "person": c.get("person", p)})
        return None

    def update_card(self, card_id: str, fn: Callable[[Card], T]) -> T | None:
        """Apply ``fn`` to one card and save it. Returns fn's result, or None when there is no such card."""
        with self._locked():
            d = self._read()
            for p, st in d["persons"].items():
                for i, c in enumerate(st.get("cards", [])):
                    if c.get("id") == card_id:
                        card = Card.from_dict({**c, "person": c.get("person", p)})
                        out = fn(card)
                        st["cards"][i] = card.to_dict()
                        self._write(d)
                        return out
        return None
