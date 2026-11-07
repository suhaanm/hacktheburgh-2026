"""The insights layer's own state on this device (REQ-9): what was shown (for novelty), what the person said about it (only ever quieter), the
week's pinned worker pointers. Ids, enums, numbers and timestamps only; one JSON file under ``<data>/insights/``, written atomically.
It never reaches a model or the network. ``delete_person`` removes everything held for a worker (their ledger was deleted, or they ask).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import paths
from .types import History, HistoryEntry

_MAX_SHOWN, _MAX_EVENTS = 300, 300


class InsightsStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else paths.state_path()
        self._lock = threading.RLock()

    # ----- persistence
    def _load(self) -> dict[str, Any]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("version") == 1:
                return d
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 1, "scopes": {}, "pins": {}}

    def _save(self, d: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(d, fh, sort_keys=True, separators=(",", ":"))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def _scope(self, d: dict[str, Any], scope: str) -> dict[str, Any]:
        return d["scopes"].setdefault(scope, {"shown": [], "quiet": {}, "hidden_kinds": [], "events": []})

    # ----- history for novelty and quieting
    def history(self, scope: str, *, before: float | None = None) -> History:
        """What was shown before ``before`` (so a week's own entries never change that week's selection), and the quieting on record."""
        with self._lock:
            sc = self._scope(self._load(), scope)
        shown = [HistoryEntry(e["id"], float(e["t"]), e.get("value"), e.get("level")) for e in sc["shown"] if before is None or float(e["t"]) < before]
        return History(shown=shown, quiet_ids={k: float(v) for k, v in sc["quiet"].items()}, hidden_kinds=frozenset(sc["hidden_kinds"]))

    def record_shown(self, scope: str, entries: list[HistoryEntry]) -> None:
        """Idempotent: an entry with the same id and time is not added twice."""
        with self._lock:
            d = self._load()
            sc = self._scope(d, scope)
            have = {(e["id"], float(e["t"])) for e in sc["shown"]}
            for e in entries:
                if (e.id, float(e.t)) not in have:
                    sc["shown"].append({"id": e.id, "t": float(e.t), "value": e.value, "level": e.level})
            sc["shown"] = sc["shown"][-_MAX_SHOWN:]
            self._save(d)

    # ----- feedback: only ever quieter
    def feedback(self, scope: str, insight: str, event: str, kind: str | None, t: float) -> None:
        with self._lock:
            d = self._load()
            sc = self._scope(d, scope)
            if event in ("not_useful", "dismissed", "done"):
                sc["quiet"][insight] = float(t)
            elif event in ("hide_kind", "never_show") and kind:
                if kind not in sc["hidden_kinds"]:
                    sc["hidden_kinds"].append(kind)
                    sc["hidden_kinds"].sort()
            elif event == "show_kind" and kind:
                sc["hidden_kinds"] = [k for k in sc["hidden_kinds"] if k != kind]
            sc["events"].append({"id": insight, "event": event, "t": float(t)})
            sc["events"] = sc["events"][-_MAX_EVENTS:]
            self._save(d)

    def events(self, scope: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._scope(self._load(), scope)["events"])

    # ----- the week's pinned worker pointers
    def get_pin(self, person: str, week: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load()["pins"].get(person, {}).get(week)

    def set_pin(self, person: str, week: str, pin: dict[str, Any]) -> None:
        with self._lock:
            d = self._load()
            weeks = d["pins"].setdefault(person, {})
            weeks[week] = pin
            for old in sorted(weeks)[:-8]:                    # keep the last 8 weeks
                weeks.pop(old, None)
            self._save(d)

    def drop_pin(self, person: str, week: str) -> None:
        with self._lock:
            d = self._load()
            d["pins"].get(person, {}).pop(week, None)
            self._save(d)

    # ----- the worker's right to delete
    def delete_person(self, person: str) -> int:
        """Remove the person's pins, history and feedback. Returns how many records went."""
        with self._lock:
            d = self._load()
            n = len(d["pins"].pop(person, {}))
            sc = d["scopes"].pop(person, None)
            if sc:
                n += len(sc["shown"]) + len(sc["events"]) + len(sc["quiet"])
            self._save(d)
            return n
