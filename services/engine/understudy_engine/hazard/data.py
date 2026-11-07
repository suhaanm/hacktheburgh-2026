"""Load the synthetic personas (engine-data's output) as Episodes, plus the planted stuck spells for validation.

Uses engine-data's `store` and `cogs` modules; nothing here writes anything. The planted spells come from each
persona's `truth.json` (`stuck_episodes`), which the model never sees: they are only used to check that what the
hazard model flags is what was planted.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from understudy_engine.core import Episode

PERSONA_DIRS = ("nine-to-five", "night-owl", "shift-worker", "irregular")


def _ts(s: str) -> float:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_persona_episodes(root: Path | str | None = None, dirs: tuple[str, ...] = PERSONA_DIRS,
                          ) -> tuple[list[Episode], dict[str, list[tuple[float, float]]], dict]:
    """Returns (episodes, planted spells by person as (t0, t1) unix seconds, info). Raises FileNotFoundError if absent."""
    from understudy_engine.cogs import segment_episodes
    from understudy_engine.store import EventStore, data_dir

    base = Path(root) if root else data_dir()
    store = EventStore(base)
    eps: list[Episode] = []
    planted: dict[str, list[tuple[float, float]]] = {}
    seeds = {}
    for d in dirs:
        ev_path = base / "synthetic" / d / "events.jsonl"
        tr_path = base / "synthetic" / d / "truth.json"
        if not ev_path.exists() or not tr_path.exists():
            raise FileNotFoundError(f"synthetic persona data missing: {ev_path}")
        persona_eps = segment_episodes(store.read_file(ev_path))
        eps.extend(persona_eps)
        truth = json.loads(tr_path.read_text())
        planted[truth["person"]] = [(_ts(s["t0"]), _ts(s["t1"])) for s in truth.get("stuck_episodes", [])]
        seeds[truth["person"]] = truth.get("seed")
    info = {"personas": list(dirs), "seeds": seeds, "n_episodes": len(eps),
            "n_planted_spells": {p: len(v) for p, v in planted.items()}}
    return eps, planted, info


def load_apprentice_episodes(root: Path | str | None = None) -> tuple[list[Episode], dict[str, list[tuple[float, float]]], dict]:
    """The 24 apprentices (8 experts, 16 novices, 2 cases each) with their planted stuck spells (one per deficit
    occurrence). These traces are scripted task sequences, so progress timing is partly predictable from the
    cog grammar; see the caveat in `evaluate_hazard_data`."""
    from understudy_engine.cogs import segment_episodes
    from understudy_engine.store import EventStore, data_dir

    base = Path(root) if root else data_dir()
    ev_path, tr_path = base / "synthetic" / "apprentices" / "events.jsonl", base / "synthetic" / "apprentices" / "truth.json"
    if not ev_path.exists() or not tr_path.exists():
        raise FileNotFoundError(f"synthetic apprentice data missing: {ev_path}")
    eps = segment_episodes(EventStore(base).read_file(ev_path))
    truth = json.loads(tr_path.read_text())
    task_person = {e.task_id: e.person for e in eps}
    planted: dict[str, list[tuple[float, float]]] = {}
    for s in truth.get("stuck_episodes", []):
        person = task_person.get(s["task_id"])
        if person:
            planted.setdefault(person, []).append((_ts(s["t0"]), _ts(s["t1"])))
    info = {"n_people": len({e.person for e in eps}), "n_episodes": len(eps), "n_planted_spells": sum(len(v) for v in planted.values())}
    return eps, planted, info
