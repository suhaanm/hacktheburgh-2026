"""Simulated learners with PLANTED learning curves and known true mastery, for validating the independence score (CUE-7).

SIMULATED: nobody here is a person. A learner has a latent mastery ``m`` per skill, moving by rules this module states:

* practice: after an occurrence ``m`` moves up by ``lr_self * (1 - m)`` when the learner managed alone and ``lr_help * (1 - m)`` after
  accepted help (flat learners have both at 0: their true skill does not change);
* forgetting: between occurrences ``m`` decays toward 0 with stability ``stability_days``.

The probability of finishing the step cleanly with NO help is ``q = guess + (1 - guess) * m`` (``guess`` = 0.10). That ``q`` is the truth the
score is judged against. What the learner does on an occurrence, and the row the ledger gets (built with the real ``make_row`` and
``classify_outcome``):

* with probability ``q`` the learner needs nothing: clean (a false alarm cue shows with probability ``false_alarm`` and is dismissed);
* otherwise a cue fires with probability ``cue_p``; with probability ``accept`` it is accepted (assisted, seconds to progress about 9 s);
  a cue that is not accepted, or no cue, leaves the learner to error (``p_error``), walk away (``p_abandon``) or grind through alone
  (the rest: a clean row that the system cannot tell from real independence: the "leak").
* a ``gamer`` dismisses every cue (accept 0) and never accepts help; it does not learn faster, it only avoids the assisted label.

Stated assumptions, not facts about people.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from . import ledger as L

GUESS = 0.10
DAY = 86400.0


@dataclass(frozen=True)
class LearnerSpec:
    kind: str                           # improving | flat | forgetting | gamer
    m0: float = 0.15
    lr_self: float = 0.05
    lr_help: float = 0.12
    stability_days: float = 30.0
    accept: float = 0.80
    cue_p: float = 0.90
    false_alarm: float = 0.05
    p_error: float = 0.50
    p_abandon: float = 0.30
    lost0_s: float = 40.0               # seconds lost vs the expert at m = 0
    mean_gap_days: float = 1.0
    gap_after: int | None = None        # forgetting: a long absence after this occurrence
    gap_days: float = 0.0
    origin_detail: str = "synthetic_learner"


def preset(kind: str, **kw) -> LearnerSpec:
    base = {
        "improving": LearnerSpec("improving", m0=0.15, lr_self=0.06, lr_help=0.14),
        "flat": LearnerSpec("flat", m0=0.45, lr_self=0.0, lr_help=0.0, stability_days=1e9),
        "forgetting": LearnerSpec("forgetting", m0=0.15, lr_self=0.06, lr_help=0.14, stability_days=12.0, gap_after=24, gap_days=21.0),
        "gamer": LearnerSpec("gamer", m0=0.30, lr_self=0.0, lr_help=0.0, stability_days=1e9, accept=0.0, cue_p=0.95),
        "declining": LearnerSpec("declining", m0=0.80, lr_self=0.0, lr_help=0.0, stability_days=25.0),
    }[kind]
    return replace(base, **kw)


def q_of(m: float) -> float:
    return GUESS + (1.0 - GUESS) * m


@dataclass
class Truth:
    """Per occurrence, aligned with the rows' order: the planted values the score never sees."""
    m: list[float]
    q: list[float]
    skill: list[str]
    t: list[float]
    taught_t: list[float | None]
    final_m: dict[str, float] | None = None
    last_t: dict[str, float] | None = None
    stability_days: float = 30.0


def simulate_learner(spec: LearnerSpec, rng: np.random.Generator, *, person: str, role: str = "benefits-processor",
                     skills: tuple[str, ...] = ("check-the-cliff", "reconcile-before-noting", "enter-household-once"), n_per_skill: int = 40,
                     t0: float = 1_790_000_000.0, origin: str = "synthetic", naive_label: bool = False) -> tuple[list[dict], Truth]:
    """Rows (ledger schema, assist stream) for one learner and the truth. Occurrences of the skills interleave in time."""
    state = {s: spec.m0 for s in skills}
    last_t = {s: t0 for s in skills}
    count = {s: 0 for s in skills}
    taught_day: dict[str, int] = {}
    t = t0
    rows: list[dict] = []
    truth = Truth([], [], [], [], [])
    serial = 0
    total = n_per_skill * len(skills)
    order = list(skills) * n_per_skill
    rng.shuffle(order)
    for s in order:
        gap = float(rng.exponential(spec.mean_gap_days * DAY / len(skills)))
        if spec.gap_after is not None and count[s] == spec.gap_after:
            gap += spec.gap_days * DAY
        t += gap
        dt_days = (t - last_t[s]) / DAY
        m = spec.m0 if count[s] == 0 else state[s] * math.exp(-dt_days / spec.stability_days)
        q = q_of(m)
        truth.m.append(m), truth.q.append(q), truth.skill.append(s), truth.t.append(t)
        needs_nothing = rng.random() < q
        lost = spec.lost0_s * (1.0 - m) + float(rng.normal(0, 4.0))
        kw: dict = dict(person=person, role=role, skill=s, step=s.replace("-", "_")[:40], t=t, origin=origin, serial=serial, lost_s=lost,
                        origin_detail=spec.origin_detail, level_before=1 + int(3 * m), level_after=1 + int(3 * m))
        taught = False
        if needs_nothing:
            dismissed = rng.random() < spec.false_alarm
            row = L.make_row(outcome="clean", trigger="auto" if dismissed else "none", tier=1 if dismissed else 0, dismissed=dismissed,
                             p_stuck=0.7 if dismissed else None, **kw)
            gain = spec.lr_self
        else:
            shown = rng.random() < spec.cue_p
            accepted = shown and rng.random() < spec.accept
            if accepted:
                day = int(t // DAY)
                taught = taught_day.get(s) != day
                taught_day[s] = day
                row = L.make_row(outcome="assisted", trigger="auto", tier=int(rng.integers(1, 3)), accepted=True, taught=taught, p_stuck=0.85,
                                 seconds_to_progress=float(rng.lognormal(math.log(9.0), 0.3)), **kw)
                gain = spec.lr_help
            else:
                u = rng.random()
                dismissed = shown
                if u < spec.p_error:
                    outcome, gain = "error", spec.lr_self * 0.5
                elif u < spec.p_error + spec.p_abandon:
                    outcome, gain = "abandoned", 0.0
                else:
                    outcome, gain = "clean", spec.lr_self      # ground through alone: indistinguishable from independence
                if naive_label and outcome in ("abandoned", "error"):
                    outcome = "clean"                          # what an unguarded scorer would believe
                row = L.make_row(outcome=outcome, trigger="auto" if shown else "none", tier=int(rng.integers(1, 3)) if shown else 0, dismissed=dismissed,
                                 p_stuck=0.85 if shown else None, **kw)
        truth.taught_t.append(t if taught else None)
        rows.append(row)
        state[s] = m + gain * (1.0 - m)
        last_t[s] = t
        count[s] += 1
        serial += 1
    truth.final_m, truth.last_t, truth.stability_days = dict(state), dict(last_t), spec.stability_days
    return rows, truth
