"""Where the handoff routes get a person's events, episodes and (for synthetic personas) truth.

Uses engine-data's event store. Synthetic personas live in ``data/synthetic/<slug>/events.jsonl`` with a
``truth.json`` that names the person; real capture is ``data/real/<person>/<day>.jsonl``. Truth is returned only to
the evaluation helpers and to a "how did the finder score" note; fitting code never reads it.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core import Episode, Event
from ..memory.paths import data_dir


@dataclass
class PersonData:
    person: str
    origin: str                 # "synthetic" | "real"
    events: list[Event]
    role: str
    truth: dict[str, Any] | None = None
    slug: str | None = None

    @property
    def t_first(self) -> float:
        return self.events[0].t.timestamp() if self.events else 0.0

    @property
    def t_last(self) -> float:
        return self.events[-1].t.timestamp() if self.events else 0.0


def pack_mapping(role: str):
    """The role pack's own event-to-cog mapping (engine rule format); None means the engine default."""
    try:
        from ..packs import load_pack

        return load_pack(role).cog_mapping()
    except Exception:  # an unknown role or a pack without a usable mapping falls back to the default rules
        return None


def segment_for_role(events, role: str):
    from ..cogs import segment_episodes

    return segment_episodes(events, pack_mapping(role))


class PersonSource:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_dir()
        self._lock = threading.Lock()
        self._cache: dict[tuple, Any] = {}

    def _signature(self, person: str) -> tuple:
        paths = self._paths(person)
        return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.exists())

    def _index(self) -> dict[str, dict[str, Any]]:
        """person -> {origin, slug, files, truth_path}. Cheap: reads only the small truth files."""
        idx: dict[str, dict[str, Any]] = {}
        syn = self.root / "synthetic"
        if syn.exists():
            for d in sorted(p for p in syn.iterdir() if p.is_dir()):
                t = d / "truth.json"
                ev = d / "events.jsonl"
                if t.exists() and ev.exists():
                    try:
                        person = json.loads(t.read_text()).get("person")
                    except (json.JSONDecodeError, OSError):
                        person = None
                    if person:
                        idx[person] = {"origin": "synthetic", "slug": d.name, "files": [ev], "truth": t}
                    else:  # a group (learners, apprentices): one truth file naming several people
                        try:
                            people = [p["person"] for p in json.loads(t.read_text()).get("people", []) if isinstance(p, dict) and p.get("person")]
                        except (json.JSONDecodeError, OSError):
                            people = []
                        for pp in people:
                            idx[pp] = {"origin": "synthetic", "slug": d.name, "files": [ev], "truth": t}
        real = self.root / "real"
        if real.exists():
            for d in sorted(p for p in real.iterdir() if p.is_dir()):
                files = sorted(d.glob("*.jsonl"))
                if files:
                    idx[d.name] = {"origin": "real", "slug": d.name, "files": files, "truth": None}
        return idx

    def _paths(self, person: str) -> list[Path]:
        return list(self._index().get(person, {}).get("files", []))

    def persons(self) -> dict[str, str]:
        return {p: v["origin"] for p, v in self._index().items()}

    def default_person(self) -> str | None:
        ps = self.persons()
        for want in ("p_ninetofive",):
            if want in ps:
                return want
        real = [p for p, o in ps.items() if o == "real"]
        return real[0] if real else next(iter(ps), None)

    def load(self, person: str) -> PersonData | None:
        info = self._index().get(person)
        if info is None:
            return None
        key = (person, self._signature(person))
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
            from ..store import EventStore

            es = EventStore(self.root)
            events: list[Event] = []
            for f in info["files"]:
                events.extend(e for e in es.read_file(f) if e.person == person)
            events.sort(key=lambda e: (e.t, e.id))
            truth = json.loads(info["truth"].read_text()) if info["truth"] else None
            role = events[0].role if events else (truth or {}).get("role", "benefits-processor")
            for k in [k for k in self._cache if k[0] == person]:
                del self._cache[k]
            pd = PersonData(person, info["origin"], events, role, truth, info["slug"])
            self._cache[key] = pd
            return pd

    def episodes(self, pd: PersonData) -> list[Episode]:
        key = (pd.person, "episodes", self._signature(pd.person))
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        eps = segment_for_role(pd.events, pd.role)
        with self._lock:
            self._cache[key] = eps
        return eps
