"""The four personas: schedule templates, planted routines, speed and skill parameters.

Day 1 is Monday 2026-10-12 (UTC). The schedule change happens on day 15 (Monday 2026-10-26). Times are UTC
hours from local midnight; a window end above 24 spills into the next calendar day.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

START_DATE = datetime(2026, 10, 12, tzinfo=timezone.utc)   # Monday, day 1
N_DAYS = 21
CHANGE_DAY = 15                                              # 1-indexed
ROLE = "benefits-processor"

Window = tuple[float, float]


@dataclass(frozen=True)
class RoutineSpec:
    name: str
    kind: str                       # template id understood by tasks.expand_routine
    rate_per_day: float             # Poisson mean on the days it occurs
    dow: tuple[int, ...]            # 0 = Monday
    hour_mean: float                # preferred start hour of day
    hour_sd: float
    dur_sigma: float                # log-normal sigma of per-step dwell (parameter variation)
    skip_prob: float = 0.04         # chance a non-first step is skipped
    extra_prob: float = 0.05        # chance a step is repeated once
    group_k: tuple[int, int] = (3, 3)   # repeat count range for the repeated group (when the kind has one)


@dataclass(frozen=True)
class PersonaSpec:
    slug: str                       # directory name under data/synthetic/
    person: str                     # p_<slug>
    label: str
    seed: int
    pre: dict[int, list[Window]]    # weekday -> windows, before the change
    post: dict[int, list[Window]]   # after the change
    random_days: bool = False       # irregular: windows sampled per day
    speed: float = 1.0              # multiplies cog dwell (>1 = slower)
    gap_mean_s: float = 200.0       # mean pause between tasks while active
    s0: float = 0.25                # initial skill
    routines: tuple[RoutineSpec, ...] = ()
    change: str = ""
    adhoc_entropy: float = 0.6      # Dirichlet alpha of the ad hoc cog transition matrix


def _wk(win: Window, days=(0, 1, 2, 3, 4)) -> dict[int, list[Window]]:
    return {d: [win] for d in days}


PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        slug="nine-to-five", person="p_ninetofive", label="Nine to five", seed=1101,
        pre=_wk((9.0, 17.25)), post=_wk((8.0, 16.25)),
        speed=1.0, gap_mean_s=420, s0=0.28,
        change="Starts and finishes one hour earlier from day 15.",
        routines=(
            RoutineSpec("calc-entry-3x", "calc3", 4.5, (0, 1, 2, 3, 4), 10.5, 1.4, 0.22),
            RoutineSpec("case-note-copy", "note", 3.5, (0, 1, 2, 3, 4), 14.5, 1.2, 0.30),
            RoutineSpec("weekly-report", "weekly", 1.0, (4,), 15.5, 0.5, 0.25),
        ),
    ),
    PersonaSpec(
        slug="night-owl", person="p_nightowl", label="Night owl", seed=2202,
        pre={**_wk((13.0, 26.5)), 5: [(15.0, 27.0)], 6: [(15.0, 27.0)]},
        post={**_wk((10.0, 22.5)), 5: [(12.0, 24.0)], 6: [(12.0, 24.0)]},
        speed=1.05, gap_mean_s=480, s0=0.22,
        change="Starts about three hours earlier from day 15 and stops finishing after midnight.",
        routines=(
            RoutineSpec("queue-sweep", "sweep", 4.0, (0, 1, 2, 3, 4, 5, 6), 21.0, 2.0, 0.28),
            RoutineSpec("calc-entry-3x", "calc3", 3.0, (0, 1, 2, 3, 4), 17.0, 1.5, 0.20),
            RoutineSpec("cliff-recheck", "cliff", 2.2, (1, 3), 23.0, 1.0, 0.26),
        ),
    ),
    PersonaSpec(
        slug="shift-worker", person="p_shiftwkr", label="Shift worker", seed=3303,
        pre={**{d: [(6.0, 14.25)] for d in (6, 0, 1)}, **{d: [(14.0, 22.25)] for d in (3, 4)}},
        post={**{d: [(14.0, 22.25)] for d in (6, 0, 1)}, **{d: [(6.0, 14.25)] for d in (3, 4)}},
        speed=0.95, gap_mean_s=380, s0=0.30,
        change="The early and late shifts swap from day 15.",
        routines=(
            RoutineSpec("queue-sweep", "sweep", 4.0, (6, 0, 1, 3, 4), 8.0, 2.5, 0.25),
            RoutineSpec("case-note-copy", "note", 3.0, (6, 0, 1, 3, 4), 12.0, 3.0, 0.32),
            RoutineSpec("calc-entry-3x", "calc3", 2.4, (6, 0, 1, 3, 4), 10.0, 2.5, 0.18, group_k=(2, 3)),
        ),
    ),
    PersonaSpec(
        slug="irregular", person="p_irregular", label="Irregular", seed=4404,
        pre={}, post={}, random_days=True,
        speed=1.1, gap_mean_s=520, s0=0.24, adhoc_entropy=1.6,
        change="Works on more days and for longer from day 15.",
        routines=(
            RoutineSpec("calc-entry-3x", "calc3", 3.0, (0, 1, 2, 3, 4, 5, 6), 12.0, 4.0, 0.30),
            RoutineSpec("weekly-report", "weekly", 1.0, (2,), 14.0, 3.0, 0.30),
            RoutineSpec("queue-sweep", "sweep", 2.2, (0, 1, 2, 3, 4, 5, 6), 11.0, 4.0, 0.33),
        ),
    ),
)

PERSONA_BY_SLUG = {p.slug: p for p in PERSONAS}


def day_date(day_idx: int) -> datetime:
    return START_DATE + timedelta(days=day_idx)


def sample_irregular_windows(post: bool, rnd: random.Random) -> list[Window]:
    p_main, p_eve = (0.88, 0.40) if post else (0.68, 0.28)
    wins: list[Window] = []
    if rnd.random() < p_main:
        s = rnd.uniform(7.0, 15.0)
        length = rnd.uniform(4.0, 9.0) if post else rnd.uniform(3.0, 7.0)
        wins.append((round(s, 2), round(s + length, 2)))
    if rnd.random() < p_eve:
        s = rnd.uniform(19.5, 21.5)
        wins.append((round(s, 2), round(s + rnd.uniform(1.0, 2.5), 2)))
    return wins


def windows_for_day(spec: PersonaSpec, day_idx: int, rnd: random.Random, *, post: bool | None = None, dow: int | None = None) -> list[Window]:
    post = (day_idx + 1 >= CHANGE_DAY) if post is None else post
    dow = (day_idx % 7) if dow is None else dow
    if spec.random_days:
        return sample_irregular_windows(post, rnd)
    return list((spec.post if post else spec.pre).get(dow, []))
