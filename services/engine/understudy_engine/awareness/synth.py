"""Synthetic awareness events for the four personas (``data/synthetic/<persona>/``), deterministic, labelled ``origin: "synthetic"``.

Purpose: let the hazard track run an ablation (stuck hazard with and without ``features.AWARENESS_COLUMNS``) before any real awareness
data exists. Read this before quoting a result from it:

* The coupling between a planted stuck spell and cursor behaviour is ASSUMED here, in the parameters below (more dwelling, wandering,
  back-and-forth and flicking inside a spell, with strength per persona). A lift on these events therefore shows only that the pipeline
  can use a planted signal. It says nothing about whether real people's cursors carry one; that needs real data and the honest label
  "n = people" the project requires.
* To keep the test from being trivially easy, a share of spells (``QUIET_SHARE``) leave no trace in the cursor at all, and a share of
  ordinary windows (``FALSE_ALARM_SHARE``) look stuck-like (a person hunting for a control), and the strength differs by persona.
* The mechanism is not the hazard model's: this generator draws features from per-state distributions given the spell labels in
  ``truth.json``; the hazard model is a logistic regression on cogs and timing. They share the labels only.

Task intervals come from the persona's ``events.jsonl`` (``task_start`` to ``task_end``); planted spells from ``truth.json``. Windows are
two seconds long and only exist inside tasks. Glances follow the planted spells (and optionally a periodic timer). Clicks are unknown
(``null``), as in real data. Same persona, root and seed give byte-identical output.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import schema
from .paths import data_dir
from .store import AppendResult, AwarenessStore

PERSONA_DIRS = ("nine-to-five", "night-owl", "shift-worker", "irregular")
WINDOW_S = 2.0
# How strongly a visible spell shows in cursor behaviour (0..1). Assumed, per persona.
COUPLING = {"nine-to-five": 0.85, "night-owl": 0.65, "shift-worker": 0.75, "irregular": 0.40}
QUIET_SHARE = 0.25          # spells with no cursor trace at all
FALSE_ALARM_SHARE = 0.04    # ordinary windows that look stuck-like
LEAD_IN_S = 20.0            # behaviour starts to change this long before a visible spell
WORK_ZONES = ("household_form", "calc_result", "case_note", "calc_site", "results_tabs")
STUCK_ZONES = ("calc_result", "cliff_button", "cliff_panel", "help", "search_box")
APP_WEIGHTS = (("browser", 0.78), ("spreadsheet", 0.10), ("email", 0.05), ("other", 0.07))
STUCK_BLOCKERS = (("cannot_find_control", 0.30), ("unclear_next_step", 0.30), ("error_message", 0.15), ("needs_information", 0.15), ("unexpected_state", 0.10))
PHASES = ("reading", "searching", "entering", "comparing", "reviewing")


@dataclass(frozen=True)
class Spell:
    t0: float
    t1: float
    visible: bool          # False: the spell leaves no trace in the cursor features


@dataclass
class SynthResult:
    persona: str
    person: str
    role: str
    seed: int
    events: list[dict[str, Any]]
    spells: list[Spell]
    note: str = ("Synthetic awareness events. The link between stuck spells and cursor behaviour is assumed by the generator, so any "
                 "lift measured on them is not evidence about real people.")


def _poisson(rnd: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= limit:
            return k
        k += 1


def _pick(rnd: random.Random, weighted: tuple[tuple[str, float], ...]) -> str:
    r = rnd.random() * sum(w for _, w in weighted)
    for k, w in weighted:
        r -= w
        if r <= 0:
            return k
    return weighted[-1][0]


def _task_intervals(events_path: Path) -> list[tuple[float, float]]:
    starts: dict[str, float] = {}
    out: list[tuple[float, float]] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if e.get("type") == "task_start" and e.get("task_id"):
                starts[e["task_id"]] = schema.parse_time(e["t"])
            elif e.get("type") == "task_end" and e.get("task_id") in starts:
                out.append((starts.pop(e["task_id"]), schema.parse_time(e["t"])))
    return sorted(out)


def _cursor(rnd: random.Random, s: float) -> dict[str, Any]:
    """Cursor features for a window at stuck-likeness ``s`` in 0..1 (0 = ordinary work)."""
    dwell = rnd.random() < 0.10 + 0.50 * s
    dwell_s = round(rnd.uniform(1.3, 1.95), 2) if dwell else 0.0
    zones = STUCK_ZONES if s > 0.3 else WORK_ZONES
    known = rnd.random() < 0.6                                  # a zone resolver does not cover every window
    wander = round(min(20.0, 1.0 + rnd.expovariate(1.0 / (0.5 + 2.5 * s))), 2)
    bf = min(6, _poisson(rnd, 0.05 + 1.2 * s))
    za = zb = None
    if bf > 0 and known:
        za, zb = sorted(rnd.sample(zones, 2))
    idle_gap = round(min(WINDOW_S, dwell_s * rnd.uniform(0.7, 1.0)), 2) if dwell else round(min(WINDOW_S, rnd.uniform(0.0, 0.8) * (1 + s)), 2)
    return {
        "dwell_s": dwell_s, "dwell_zone": rnd.choice(zones) if dwell and known else None, "wander": wander, "back_forth": bf,
        "zone_a": za, "zone_b": zb, "speed_bursts": min(6, _poisson(rnd, 0.2 + 0.9 * s)), "idle_gap_s": idle_gap, "clicks": None,
    }


def _glance(rnd: random.Random, *, spell_visible: bool | None, kind: str) -> dict[str, Any]:
    stuck = spell_visible is not None
    shows_block = rnd.random() < (0.65 if spell_visible else 0.40 if stuck else 0.06)
    blocker = _pick(rnd, STUCK_BLOCKERS) if shows_block else ("none" if rnd.random() < 0.9 else "unknown")
    conf = round(0.55 + 0.40 * rnd.random(), 3) if shows_block else round(0.40 + 0.50 * rnd.random(), 3)
    return {"app_kind": kind if rnd.random() < 0.85 else "other", "task_phase": rnd.choice(PHASES), "blocker": blocker, "confidence": conf}


def make(persona: str, *, root: Path | str | None = None, seed: int | None = None, max_tasks: int | None = None,
         periodic_s: float | None = None) -> SynthResult:
    """Awareness events for one persona directory (for example ``"nine-to-five"``). Needs ``<root>/synthetic/<persona>/`` (``understudy synth``).

    ``max_tasks`` keeps the first N tasks (tests); ``periodic_s`` adds periodic glances at that spacing inside tasks (default none:
    the periodic glance is opt-in in the product too)."""
    if persona not in COUPLING:
        raise ValueError(f"unknown persona {persona!r}; known: {', '.join(PERSONA_DIRS)}")
    base = (Path(root) if root else data_dir()) / "synthetic" / persona
    ev_path, tr_path = base / "events.jsonl", base / "truth.json"
    if not ev_path.exists() or not tr_path.exists():
        raise FileNotFoundError(f"synthetic persona data missing: {ev_path}")
    truth = json.loads(tr_path.read_text(encoding="utf-8"))
    use_seed = int(truth.get("seed", 0) if seed is None else seed)
    rnd = random.Random(f"awareness:{persona}:{use_seed}")
    person, role = truth["person"], truth["role"]
    tasks = _task_intervals(ev_path)
    if max_tasks is not None:
        tasks = tasks[:max_tasks]
    spells_all = [(schema.parse_time(s["t0"]), schema.parse_time(s["t1"])) for s in truth.get("stuck_episodes", [])]
    visible = {i: rnd.random() >= QUIET_SHARE for i in range(len(spells_all))}
    coupling = COUPLING[persona]
    horizon = tasks[-1][1] if tasks else 0.0
    spells = [Spell(a, b, visible[i]) for i, (a, b) in enumerate(spells_all) if a <= horizon]

    events: list[dict[str, Any]] = []
    n = 0

    def add(t: float, **body: Any) -> None:
        nonlocal n
        n += 1
        events.append({"schema": 1, "id": f"aw{persona[:2]}-{n:08d}", "t": schema.iso(t), "origin": "synthetic", "person": person, "role": role, **body})

    kind = "browser"
    si = 0
    for a, b in tasks:
        batch_start = len(events)
        # windows
        k = 0
        while a + WINDOW_S * (k + 1) <= b:
            t = a + WINDOW_S * k
            k += 1
            while si < len(spells) and spells[si].t1 < t:
                si += 1
            s = 0.0
            if si < len(spells):
                sp = spells[si]
                if sp.visible and sp.t0 <= t < sp.t1:
                    s = coupling
                elif sp.visible and sp.t0 - LEAD_IN_S <= t < sp.t0:
                    s = 0.35 * coupling
            if s == 0.0 and rnd.random() < FALSE_ALARM_SHARE:
                s = 0.7 * coupling
            if rnd.random() > 0.93:
                kind = _pick(rnd, APP_WEIGHTS)
            sys_idle = min(60.0, rnd.expovariate(1.0 / (1.2 + 4.0 * s)))
            add(t, type="window", window_s=WINDOW_S, app_kind=kind, sys_idle_s=round(sys_idle, 1), cursor=_cursor(rnd, s))
        # glances that follow spells inside this task
        for j, sp in enumerate(spells):
            if sp.t1 < a or sp.t0 > b:
                continue
            dur = sp.t1 - sp.t0
            if sp.visible or rnd.random() < 0.5:
                add(sp.t0 + min(30.0, 0.6 * dur), type="glance", trigger="stuck", glance=_glance(rnd, spell_visible=sp.visible, kind=kind))
            if sp.visible and rnd.random() < 0.12:
                add(sp.t0 + rnd.uniform(0.3, 0.9) * dur, type="glance", trigger="hotkey", glance=_glance(rnd, spell_visible=True, kind=kind))
        if periodic_s:
            t = a + periodic_s
            while t < b:
                add(t, type="glance", trigger="periodic", glance=_glance(rnd, spell_visible=None, kind=kind))
                t += periodic_s
        events[batch_start:] = sorted(events[batch_start:], key=lambda e: (e["t"], e["id"]))
    return SynthResult(persona, person, role, use_seed, events, spells)


def iter_events(persona: str, **kw: Any) -> Iterator[dict[str, Any]]:
    yield from make(persona, **kw).events


def make_all(*, root: Path | str | None = None, max_tasks: int | None = None, periodic_s: float | None = None) -> dict[str, SynthResult]:
    return {p: make(p, root=root, max_tasks=max_tasks, periodic_s=periodic_s) for p in PERSONA_DIRS}


def write(result: SynthResult, store: AwarenessStore | None = None) -> AppendResult:
    """Append a persona's synthetic events to the synthetic partition of the store (never the real one)."""
    st = store or AwarenessStore()
    total = AppendResult()
    for i in range(0, len(result.events), 500):
        r = st.append(result.events[i:i + 500])
        total.accepted += r.accepted
        total.duplicates += r.duplicates
        total.rejected.extend((i + idx, why) for idx, why in r.rejected)
    return total
