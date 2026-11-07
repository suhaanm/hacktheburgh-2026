"""Task plans for the persona simulator: planted routines, ad hoc tasks, skill and stuck episodes."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .profiles import RoutineSpec
from .vocab import BASE_DWELL

JUDGEMENT = frozenset({"SEARCH", "REFORMULATE", "COMPARE", "DECIDE", "ASK"})
PRODUCTIVE = frozenset({"READ_RESULT", "COPY_TO_NOTE", "ENTER_HOUSEHOLD", "CHECK_CLIFF", "RECONCILE", "DECIDE", "PASTE"})
SOFT_PRODUCTIVE = frozenset({"ENTER", "COPY"})        # progress with probability 0.4

# Skill: practice curve in tasks done. s(n) = 1 - (1 - s0) * (1 + n / N0) ** (-ALPHA).
SKILL_N0 = 120.0
SKILL_ALPHA = 0.7
# Step-level stuck hazard before a productive cog: P0 * (1 - skill) ** GAMMA.
STUCK_P0 = 0.14
STUCK_GAMMA = 1.3

ADHOC_POOL = (
    "READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "ASK",
    "ENTER_HOUSEHOLD", "READ_RESULT", "COPY_TO_NOTE", "OPEN_CALCULATOR", "CHECK_CLIFF",
)


def skill_at(s0: float, n_done: float) -> float:
    return 1.0 - (1.0 - s0) * (1.0 + n_done / SKILL_N0) ** (-SKILL_ALPHA)


def p_stuck(skill: float) -> float:
    return STUCK_P0 * (1.0 - skill) ** STUCK_GAMMA


@dataclass
class PlanItem:
    cog: str
    dur: float
    site: str | None = None
    stuck: bool = False
    query_len: int | None = None


@dataclass
class TaskPlan:
    kind: str                       # routine name or "adhoc"
    items: list[PlanItem]
    skipped: int = 0
    stuck_blocks: list[dict] = field(default_factory=list)   # {start_item, dur, label_frac|None}

    @property
    def total(self) -> float:
        return sum(i.dur for i in self.items)


def nominal_template(spec: RoutineSpec) -> list[str]:
    """The un-varied cog sequence of a routine (modal repeat count)."""
    k = (spec.group_k[0] + spec.group_k[1]) // 2
    return [c for c, _ in _base_sequence(spec, k, random.Random(0))]


def judgement_share(cogs: list[str]) -> float:
    return sum(1 for c in cogs if c in JUDGEMENT) / max(1, len(cogs))


def _base_sequence(spec: RoutineSpec, k: int, rnd: random.Random) -> list[tuple[str, str | None]]:
    kind = spec.kind
    if kind == "calc3":
        seq: list[tuple[str, str | None]] = []
        for i in range(k):
            site = f"calc{i + 1}"
            seq += [("OPEN_CALCULATOR", site), ("ENTER_HOUSEHOLD", None), ("READ_RESULT", None)]
        seq.append(("RECONCILE", None))
        return seq
    if kind == "note":
        return [(c, None) for _ in range(max(2, k - 1)) for c in ("READ_RESULT", "COPY_TO_NOTE")]
    if kind == "sweep":
        return [(c, None) for _ in range(k + 1) for c in ("NAVIGATE", "READ", "CHECK", "DECIDE")]
    if kind == "weekly":
        return [(c, None) for c in ("NAVIGATE", "READ", "COPY", "NAVIGATE", "PASTE", "ENTER", "ENTER", "DECIDE")]
    if kind == "cliff":
        return [(c, None) for c in ("ENTER_HOUSEHOLD", "CHECK_CLIFF", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE")]
    raise ValueError(kind)


def expand_routine(spec: RoutineSpec, rnd: random.Random) -> tuple[list[tuple[str, str | None]], int]:
    k = rnd.randint(*spec.group_k)
    base = _base_sequence(spec, k, rnd)
    out: list[tuple[str, str | None]] = []
    skipped = 0
    for i, step in enumerate(base):
        if i > 0 and rnd.random() < spec.skip_prob:
            skipped += 1
            continue
        out.append(step)
        if rnd.random() < spec.extra_prob:
            out.append(step)
    return out, skipped


def dwell(cog: str, rnd: random.Random, *, speed: float, skill: float, sigma: float) -> float:
    med = BASE_DWELL[cog] * speed * (1.35 - 0.35 * skill)
    lo = 1.5 if cog in ("COPY", "PASTE", "REVERT") else 2.5
    return min(160.0, max(lo, rnd.lognormvariate(math.log(med), sigma)))


class AdHocChain:
    """Random first-order chain over cogs; low Dirichlet alpha gives more structured (repetitive) work."""

    def __init__(self, seed: int, alpha: float):
        rnd = random.Random(seed)
        self.pool = list(ADHOC_POOL)
        self.rows: dict[str, list[float]] = {}
        for c in self.pool:
            g = [rnd.gammavariate(alpha, 1.0) + 1e-6 for _ in self.pool]
            s = sum(g)
            self.rows[c] = [x / s for x in g]

    def sample(self, rnd: random.Random, n: int) -> list[str]:
        cur = rnd.choice(self.pool)
        out = [cur]
        while len(out) < n:
            cur = rnd.choices(self.pool, weights=self.rows[cur])[0]
            out.append(cur)
        return out


def plan_task(kind: str, seq: list[tuple[str, str | None]], rnd: random.Random, *, speed: float, skill: float,
              sigma: float, skipped: int = 0) -> TaskPlan:
    items: list[PlanItem] = []
    blocks: list[dict] = []
    for cog, site in seq:
        if cog in PRODUCTIVE and rnd.random() < p_stuck(skill):
            d = min(400.0, max(25.0, rnd.lognormvariate(math.log(70.0 * (1.3 - 0.5 * skill)), 0.45)))
            start = len(items)
            remaining = d
            while remaining > 4.0:
                pat = rnd.random()
                if pat < 0.45:
                    pair = ["SEARCH", "REFORMULATE"] if rnd.random() < 0.5 else ["REFORMULATE", "SEARCH"]
                    chunk = pair * rnd.randint(1, 2)
                elif pat < 0.80:
                    chunk = ["READ_RESULT" if cog in ("READ_RESULT", "COPY_TO_NOTE", "RECONCILE") else "READ"] * rnd.randint(1, 3)
                else:
                    chunk = [rnd.choice(["ASK", "IDLE", "REVERT"])]
                for c in chunk:
                    if remaining <= 4.0:
                        break
                    dd = min(remaining, rnd.uniform(6.0, 14.0)) if c != "IDLE" else min(remaining, rnd.uniform(15.0, 40.0))
                    items.append(PlanItem(c, dd, stuck=True, query_len=rnd.randint(8, 40) if c in ("SEARCH", "REFORMULATE") else None))
                    remaining -= dd
            blocks.append({"start_item": start, "dur": d, "label_frac": rnd.uniform(0.4, 0.9) if rnd.random() < 0.35 else None})
        items.append(PlanItem(cog, dwell(cog, rnd, speed=speed, skill=skill, sigma=sigma), site=site))
    return TaskPlan(kind=kind, items=items, skipped=skipped, stuck_blocks=blocks)
