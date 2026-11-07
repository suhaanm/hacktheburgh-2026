"""Shared building blocks of the realistic generators: segments, plans, scalar samplers and time modifiers.

A *segment* is one stretch of one cog with a duration. A *case plan* is the ordered segments of one task attempt plus
the bookkeeping the truth file needs (per-deficit added and saved seconds, hidden stuck episodes, interruptions).
The families (`markov`, `latent_skill`, `process_trace`) differ in how they produce segments; everything after that
(interruptions, event emission, noise, the progress process) is shared and listed as such in the report.

All scalar draws use ``random.Random`` seeded from the dataset seed, so a dataset is a pure function of its arguments.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# ------------------------------------------------------------------------------------------ small samplers


def seeded(*parts: int) -> random.Random:
    """A Random seeded from integers, stable across processes and platforms."""
    h = 1469598103934665603
    for p in parts:
        h ^= (int(p) & 0xFFFFFFFFFFFFFFFF)
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return random.Random(h)


def expit(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def poisson(rnd: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 40:
        return max(0, int(round(rnd.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= L:
            return k
        k += 1


def lomax(rnd: random.Random, alpha: float, scale: float) -> float:
    """Pareto II: heavy-tailed with tail index alpha."""
    u = rnd.random()
    return scale * ((1.0 - u) ** (-1.0 / alpha) - 1.0)


def lognormal(rnd: random.Random, median: float, sigma: float) -> float:
    return median * math.exp(rnd.gauss(0.0, sigma))


def choose(rnd: random.Random, items, weights):
    tot = float(sum(weights))
    x = rnd.random() * tot
    for it, w in zip(items, weights):
        x -= w
        if x <= 0:
            return it
    return items[-1]


def dirichlet(rnd: random.Random, alphas) -> list[float]:
    g = [rnd.gammavariate(max(a, 1e-3), 1.0) for a in alphas]
    s = sum(g)
    return [x / s for x in g]


# ------------------------------------------------------------------------------------------ plan types
PAUSE_CAP_S = 600.0


@dataclass(frozen=True)
class Step:
    """One nominal step of a task grammar."""

    cog: str
    site: str | None = None
    unit: str = ""


@dataclass(frozen=True)
class Unit:
    """A named group of steps with prerequisites (the pack's expert-policy checks)."""

    id: str
    steps: tuple[Step, ...]
    after: tuple[str, ...] = ()
    required: bool = True
    critical: bool = False


@dataclass
class Seg:
    cog: str
    dur: float
    site: str | None = None
    tag: str | None = None           # deficit id when a deficit added this segment
    kind: str = "work"               # work | pause | detour | interrupt
    stuck_id: int | None = None      # hidden stuck episode this segment belongs to
    query_len: int | None = None
    traced: bool = True              # carries the task id (an interruption's events may not)
    unit: str = ""
    wrong_zone: bool = False


@dataclass
class Stuck:
    id: int
    i0: int                          # first segment index
    i1: int                          # one past the last
    supp: float                      # progress-rate multiplier while stuck (0 = fully suppressed)
    silent: bool                     # a quiet stall (no detour cogs)
    tag: str | None = None
    seconds: float = 0.0
    reported: bool = False           # a self-reported stuck event was emitted inside it


@dataclass
class CasePlan:
    segs: list[Seg] = field(default_factory=list)
    deficits: dict[str, dict] = field(default_factory=dict)       # d -> {instances, added_s, saved_s}
    stuck: list[Stuck] = field(default_factory=list)
    interrupts: list[dict] = field(default_factory=list)
    strategy: dict = field(default_factory=dict)
    skipped: int = 0
    pending: dict = field(default_factory=dict)                   # family scratch (rework owed)

    def note(self, d: str, *, added: float = 0.0, saved: float = 0.0, instances: int = 0) -> None:
        b = self.deficits.setdefault(d, {"instances": 0, "added_s": 0.0, "saved_s": 0.0})
        b["instances"] += instances
        b["added_s"] += added
        b["saved_s"] += saved

    def total(self) -> float:
        return sum(s.dur for s in self.segs)

    def add(self, seg: Seg) -> Seg:
        self.segs.append(seg)
        return seg


# ------------------------------------------------------------------------------------------ time modifiers
def practice_mult(person, n_eff: float) -> float:
    """Time multiplier above the asymptote after ``n_eff`` cases of practice (>= 1).

    Half of the people follow a power law, half an exponential (Heathcote et al. 2000: individual curves are
    exponential and the averaged curve only looks like a power law).
    """
    if person.learn_form == "power":
        return 1.0 + person.learn_beta * (1.0 + n_eff) ** (-person.learn_alpha)
    tau = 3.0 / max(person.learn_alpha, 0.05)
    return 1.0 + person.learn_beta * math.exp(-n_eff / tau)


def mastery_gap(person, n_eff: float) -> float:
    """Fraction of the initial mastery gap still open after ``n_eff`` cases (1 at zero practice, towards 0)."""
    if person.learn_form == "power":
        return (1.0 + n_eff) ** (-person.learn_alpha)
    tau = 3.0 / max(person.learn_alpha, 0.05)
    return math.exp(-n_eff / tau)


def theta_at(person, skill: str, n_eff: float, gap: float) -> float:
    """Log-odds mastery of a skill after n_eff cases of practice."""
    return person.theta_inf[skill] - gap * person.theta_gap * mastery_gap(person, n_eff)


def severity(person, skill: str, n_eff: float, gap: float) -> float:
    """Deficit severity in (0, 1): the probability-scale lack of mastery."""
    return expit(-theta_at(person, skill, n_eff, gap))


def draw_pause(rnd: random.Random, h: dict) -> float:
    """A hesitation pause: a mixture of a lognormal and a Lomax (heavy tail), at least one second, capped."""
    if rnd.random() < h["pause_mix_lognormal"]:
        d = lognormal(rnd, h["pause_ln_median_s"], h["pause_ln_sigma"])
    else:
        d = 1.0 + lomax(rnd, h["pause_lomax_alpha"], h["pause_lomax_scale_s"])
    return min(PAUSE_CAP_S, max(1.0, d))


def circadian(person, h: dict, hour: float) -> float:
    return 1.0 + h["circadian_amp"] * math.cos(2.0 * math.pi * (hour - person.chrono_phase_h) / 24.0)


# ------------------------------------------------------------------------------------------ session clock
@dataclass
class Clock:
    """Where the person is in their working session when a case starts, and how it changes within the case."""

    hour: float = 10.0                 # hour of day at the case start
    work_s: float = 0.0                # continuous work since the last real break (s)
    since_start_s: float = 1e9         # time since the session started (s)
    local_s: float = 0.0               # time within this case so far (s)
    resume_left: int = 0               # steps left that carry the resumption slowdown
    resumed: bool = False              # right after an interruption

    def mult(self, person, h: dict) -> float:
        warm = 1.0 + h["warmup"] * math.exp(-(self.since_start_s + self.local_s) / 600.0)
        fat = 1.0 + person.fatigue * max(0.0, (self.work_s + self.local_s) / 3600.0 - 0.25)
        return warm * fat * circadian(person, h, self.hour + (self.local_s) / 3600.0)
