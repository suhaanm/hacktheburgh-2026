"""Glue between the pure hit list (``build.py``) and the rest of the engine: whose episodes, which role pack, what the worker has
already decided about each routine, what is on their denylist, whether capture is allowed. Reads only; the one write path is the
worker's own hide, unhide and reset (``state.py``). No model, no network.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..memory.onboarding import capture_enabled, load_profile
from ..memory.packinfo import PackView, load_pack
from ..memory.paths import data_dir
from ..memory.store import MemoryStore
from ..routines.finder import edit_distance
from ..routines.store import RoutineStore
from . import vocab as V
from .build import HitConfig, RoutineView, _empty, build_hitlist, iso
from .state import HitState

_TRUE = ("1", "true", "yes", "on")
FLAG = "UNDERSTUDY_X_HITLIST"
WINDOWS = (7, 30)


def enabled() -> bool:
    """On with the master flag UNDERSTUDY_X or its own UNDERSTUDY_X_HITLIST. Read on every call, never cached."""
    return any(os.environ.get(n, "").strip().lower() in _TRUE for n in ("UNDERSTUDY_X", FLAG))


class UnknownPerson(LookupError):
    pass


@dataclass
class Result:
    data: dict[str, Any]
    origin: str
    person: str | None
    role: str | None
    sigs: dict[str, tuple[str, ...]]
    now: float


def load_denylist() -> list[dict[str, Any]]:
    """The worker's own denylist entries (``<data>/denylist.json``, written by the worker, read here, never changed here)."""
    p = data_dir() / "denylist.json"
    try:
        entries = json.loads(p.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [e for e in entries if isinstance(e, dict)]


def _lookup_for(mem: MemoryStore, person: str):
    """``lookup(id, signature) -> RoutineView | None`` over the worker's routine registry. An unnamed routine seen again keeps the
    registry's id by the same signature rule the registry itself uses (edit distance 0.3 or less)."""
    store = RoutineStore(mem)
    mine = {rid: r for rid, r in store._load().get("routines", {}).items() if r.get("person") == person}

    def lookup(rid: str, sig: tuple[str, ...]) -> RoutineView | None:
        r = mine.get(rid)
        if r is None and rid.startswith("auto-"):
            for oid in sorted(mine):
                o = mine[oid]
                if o.get("template_id") is None and o.get("signature") and edit_distance(tuple(o["signature"]), sig) <= 0.3:
                    r = o
                    break
        if r is None:
            return None
        e = store.effective(r)
        return RoutineView(id=str(e["id"]), status=str(e["status"]), rung=str(e.get("rung", "A0")), proposable=bool(e.get("proposable", False)))

    return lookup


def _pack(role: str) -> PackView:
    try:
        return load_pack(role)
    except KeyError:
        return load_pack("benefits-processor")


def compute(person: str | None, window_days: int, *, now: float | None = None, cfg: HitConfig | None = None) -> Result:
    """The hit list for a person, from this device's own record. ``now`` is the end of a synthetic person's data (never the wall
    clock) and the wall clock for a real one, unless the caller says otherwise."""
    from .. import routes_handoff as rh            # the engine's own source of people, episodes and routine detection

    mem = MemoryStore()
    pid, pd = rh._resolve(person)
    wall = now if now is not None else time.time()
    if pd is None:
        known = (load_profile(mem) or {}).get("person")
        if person and person != known:
            raise UnknownPerson(person)
        return Result(_empty(window_days, wall - window_days * 86400.0, wall, None, 0, "new_user", V.sentence_new_user()),
                      "real", pid, None, {}, wall)
    # In a seeded demo the demo person borrows another persona's traces and only the routine ids the seed lists (the Routines screen does
    # the same, ``routes_handoff._detections_for``): the hit list must show the same routines the worker sees there.
    demo = rh._demo(mem)
    src_pd, only = pd, None
    if demo.get("person") == pd.person and demo.get("routine_source"):
        other = rh._src().load(demo["routine_source"])
        # Only another persona of the SAME role (as the Routines screen does): a programmer never reads a benefits processor's traces.
        if other is not None and other.role == pd.role:
            src_pd, only = other, (set(demo.get("routine_ids") or []) or None)
    at = now if now is not None else (src_pd.t_last if src_pd.origin == "synthetic" else time.time())
    pack = _pack(src_pd.role)
    st = HitState().get(pd.person)
    if pd.origin == "real" and not capture_enabled(mem.read()):
        data = _empty(window_days, at - window_days * 86400.0, at, None, 0, "capture_off", V.sentence_capture_off())
        return Result(data, pd.origin, pd.person, pd.role, {}, at)
    episodes = rh._src().episodes(src_pd)
    try:
        rh._sync_routines(pd, mem)                  # the registry knows these routines, so Automate has something to open
    except Exception:
        pass
    sigs: dict[str, tuple[str, ...]] = {}
    data = build_hitlist(episodes, pack, person=pd.person, now=at, window_days=window_days, reset_at=st["reset_at"], hidden=st["hidden"],
                         lookup=_lookup_for(mem, pd.person), denylist=load_denylist(), cfg=cfg, sig_out=sigs, only_ids=only)
    return Result(data, pd.origin, pd.person, pd.role, sigs, at)


def meta_for(res: Result) -> dict[str, Any]:
    d = res.data
    return {"origin": res.origin, "n": int(d.get("episodes_in_window") or 0), "n_unit": "episodes", "split": None, "interval_level": 0.95,
            "note": V.note_meta(res.origin), "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


def hide(person: str | None, rid: str, window_days: int) -> dict[str, Any]:
    res = compute(person, window_days)
    row = next((r for r in res.data["rows"] if r["id"] == rid), None)
    if row is None or res.person is None:
        raise KeyError(rid)
    HitState().hide(res.person, rid, int(row["count"]), list(res.sigs.get(rid, ())))
    return {"hidden": rid, "count": int(row["count"]), "returns_at": math.ceil(HitConfig().hide_factor * int(row["count"]))}


def unhide(person: str | None, rid: str) -> bool:
    res = compute(person, 30)
    return res.person is not None and HitState().unhide(res.person, rid)


def reset(person: str | None) -> dict[str, Any]:
    """Start counting again: forget the counts so far and any hidden marks. Counts, nothing else."""
    res = compute(person, 30)
    if res.person is None:
        return {"cleared": {"counters": 0, "hidden_marks": 0}, "counting_since": iso(res.now)}
    d = res.data
    counters = len(d["rows"]) + len(d["automated"]) + len(d["hidden"])
    marks = HitState().reset(res.person, res.now)
    return {"cleared": {"counters": counters, "hidden_marks": marks}, "counting_since": iso(res.now)}


def top_rows(person: str | None = None, limit: int = 1) -> list[dict[str, Any]]:
    """The worker's biggest repeated actions, for the insights layer's "automation opportunity" pointer. Pure read, ids and numbers
    only: ``label_id`` is a pack routine id or an automatic id, never text from the screen. Empty when anything is missing."""
    try:
        for w in WINDOWS:
            res = compute(person, w)
            if res.data["rows"]:
                out = []
                for r in res.data["rows"][:max(0, int(limit))]:
                    mp = r["minutes_per_week"]
                    out.append({
                        "id": r["id"], "label_id": r["id"], "count": r["count"], "window_days": w, "seconds_per_time": r["seconds_per_time"],
                        "hours_saved": {"value": round(mp["point"] * 4 / 60, 2), "lo": round(mp["lo"] * 4 / 60, 2), "hi": round(mp["hi"] * 4 / 60, 2),
                                        "horizon_weeks": 4},
                        "n": r["count"], "origin": res.origin, "t": r["t"], "action_to": "repeats",
                    })
                return out
    except Exception:
        return []
    return []
