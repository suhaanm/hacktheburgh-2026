"""A tiny deterministic generator of work episodes with stuck spells, for tests and offline fallback.

Mechanism (deliberately unlike the fitted logistic model): each task is a run of *units*. A fluent unit is
READ -> ENTER -> CHECK and ends in a `progress` event. With a person-specific probability a unit
turns into a *stuck spell* lasting a log-normal time. Most spells are a loop of SEARCH / REFORMULATE / READ
(sometimes IDLE); a share are *silent* (long READ and IDLE only, no searching), so the cog pattern alone
cannot tell. Many fluent units contain harmless decoys (a SEARCH, a REFORMULATE, a short IDLE). People
also differ in speed (all dwell times scale), so a slow person's fluent units look like a fast person's
early stuck. The generator returns the planted spells so tests can check recovery.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.core import Cog, Episode

T_BASE = 1_793_000_000.0  # about 26 Oct 2026, arbitrary


@dataclass
class SimTruth:
    spells: list[tuple[float, float]]  # (start, end) of every planted stuck spell


def _simulate_episode(rng: np.random.Generator, person: str, role: str, task: str, t0: float,
                      p_stuck: float, decoy: float, speed: float, silent: float) -> tuple[Episode, SimTruth]:
    cogs: list[Cog] = []
    progress: list[float] = []
    spells: list[tuple[float, float]] = []
    t = t0

    def add(cid: str, lo: float, hi: float) -> None:
        nonlocal t
        d = float(rng.uniform(lo, hi)) * speed
        cogs.append(Cog(t, t + d, cid))
        t += d

    for _ in range(int(rng.integers(5, 9))):
        add("READ", 6, 18)
        add("ENTER", 8, 25)
        if rng.random() < p_stuck:
            s0 = t
            target = float(np.clip(rng.lognormal(np.log(130.0), 0.5), 75.0, 420.0))
            is_silent = rng.random() < silent
            while t - s0 < target:
                if is_silent:
                    add("READ", 15, 45)
                    add("IDLE", 15, 50)
                else:
                    add("SEARCH", 8, 30)
                    add("REFORMULATE", 6, 25)
                    add("READ", 6, 20)
                    if rng.random() < 0.3:
                        add("IDLE", 10, 40)
            spells.append((s0, t))
            add("COMPARE" if rng.random() < 0.5 else "ASK", 6, 20)
        elif rng.random() < decoy:
            r = rng.random()
            if r < 0.4:
                add("SEARCH", 5, 18)
            elif r < 0.7:
                add("REFORMULATE", 5, 18)
            else:
                add("IDLE", 8, 30)
            add("READ", 4, 12)
        add("CHECK", 4, 12)
        progress.append(t)
        t += float(rng.uniform(1, 4))
    ep = Episode(task_id=task, person=person, role=role, origin="synthetic", t0=t0, t1=t, cogs=cogs,
                 progress_t=progress)
    return ep, SimTruth(spells)


def simulate_people(
    n_people: int = 4, episodes_per_person: int = 30, seed: int = 0, role: str = "benefits-processor",
    p_stuck: tuple[float, float] = (0.04, 0.12), decoy: float = 0.35, silent: float = 0.3,
    speed: tuple[float, float] = (0.8, 1.5),
) -> tuple[list[Episode], dict[str, list[SimTruth]]]:
    """Episodes for `n_people` people. Returns (episodes, truth by person)."""
    rng = np.random.default_rng(seed)
    probs = np.linspace(p_stuck[0], p_stuck[1], n_people)
    speeds = rng.permutation(np.linspace(speed[0], speed[1], n_people))
    eps: list[Episode] = []
    truth: dict[str, list[SimTruth]] = {}
    for i in range(n_people):
        person = f"p_sim{i}"
        t = T_BASE + i * 7 * 86400.0
        truth[person] = []
        for k in range(episodes_per_person):
            ep, tr = _simulate_episode(rng, person, role, f"t_{k}", t, float(probs[i]), decoy,
                                       float(speeds[i]), silent)
            eps.append(ep)
            truth[person].append(tr)
            t = ep.t1 + float(rng.uniform(600, 3600))
    return eps, truth
