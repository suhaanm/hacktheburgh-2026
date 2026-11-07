"""Synthetic apprentices for the benefits-processor task (EVL-1, ANA-2 to 4 ground truth).

Task: enter a household into three calculators, read the results, check cliff edges, reconcile, copy to the
case note. Experts follow the expert sequence with small natural variation (and one allowed reordering).
Novices are generically slower and carry planted deficits, each with an exact price in seconds:

    price_s = seconds the deficit added - seconds it removed, versus the same person's same case without it.

The counterfactual is built by drawing the baseline durations first and the deficit blocks separately, so the
price is known by construction, not estimated. ``truth.json`` records every deficit instance, the cog
sequence of each trace and the expert reference.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..store.jsonl import EventStore
from ..store.paths import data_dir
from ..store.validate import fmt_t
from .vocab import BASE_DWELL, Emitter

ROLE = "benefits-processor"
SEED = 8808
BASE_DAY = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
N_EXPERTS = 8
N_NOVICES = 16
CASES_PER_PERSON = 2
TASK = "benefits-household-entry"

DEFICITS = {
    "skipped_check_cliff": {
        "description": "Skips CHECK_CLIFF on one to three calculators; the miss is found at reconciliation and reworked (revert, re-enter, late check, re-read).",
        "cogs": ["CHECK_CLIFF", "REVERT", "ENTER_HOUSEHOLD", "READ_RESULT"],
    },
    "repeated_read_result": {
        "description": "Re-reads the same calculator result one or two extra times.",
        "cogs": ["READ_RESULT"],
    },
    "search_loop": {
        "description": "Search, read the hits, reformulate, read again (two to four rounds) before entering the household.",
        "cogs": ["SEARCH", "REFORMULATE", "READ"],
    },
    "copy_error": {
        "description": "Copies the wrong figure to the note; found on a second reconcile, reverted and copied again.",
        "cogs": ["RECONCILE", "REVERT", "COPY_TO_NOTE"],
    },
    "idle_before_enter": {
        "description": "A long IDLE (30 to 75 s) before ENTER_HOUSEHOLD, hesitating on the first form and sometimes the others.",
        "cogs": ["IDLE"],
    },
}
DEFICIT_ORDER = tuple(DEFICITS)


@dataclass
class Step:
    cog: str
    dur: float
    site: str | None = None
    tag: str | None = None            # deficit name for steps a deficit added
    progress: str | None = None       # kind of progress event emitted at the end of the step
    stuck_block: int | None = None    # id of a stuck block this step belongs to


def _expert_sequence(variant: str) -> list[tuple[str, str | None]]:
    seq: list[tuple[str, str | None]] = [("READ", None)]
    if variant == "A":     # cliff check right after each result
        for i in (1, 2, 3):
            seq += [("OPEN_CALCULATOR", f"calc{i}"), ("ENTER_HOUSEHOLD", None), ("READ_RESULT", None), ("CHECK_CLIFF", None)]
    else:                  # variant B: the allowed reordering, all cliff checks after the three results
        for i in (1, 2, 3):
            seq += [("OPEN_CALCULATOR", f"calc{i}"), ("ENTER_HOUSEHOLD", None), ("READ_RESULT", None)]
        seq += [("CHECK_CLIFF", None)] * 3
    seq += [("RECONCILE", None), ("COPY_TO_NOTE", None)]
    return seq


def expert_median_s(complexity: float) -> float:
    """Median expert total for a case of this complexity (sum of median dwells, variant-independent)."""
    seq = _expert_sequence("A")
    return sum(BASE_DWELL[c] * (complexity if c == "ENTER_HOUSEHOLD" else 1.0) for c, _ in seq)


def _draw(cog: str, rnd: random.Random, speed: float, sigma: float, complexity: float) -> float:
    med = BASE_DWELL[cog] * speed * (complexity if cog == "ENTER_HOUSEHOLD" else 1.0)
    return max(1.5, rnd.lognormvariate(math.log(med), sigma))


def _progress_kind(cog: str) -> str | None:
    return {"READ_RESULT": "result_read", "CHECK_CLIFF": "cliff_checked", "COPY_TO_NOTE": "note_field"}.get(cog)


@dataclass
class TracePlan:
    person: str
    level: str
    case: int
    complexity: float
    variant: str
    speed: float
    steps: list[Step]
    deficits: dict[str, dict] = field(default_factory=dict)   # name -> {instances, added_s, saved_s, price_s}
    baseline_s: float = 0.0
    n_stuck_blocks: int = 0


def build_trace(person: str, level: str, case: int, rnd: random.Random, *, variant: str, speed: float, sigma: float,
                complexity: float, deficits: tuple[str, ...]) -> TracePlan:
    steps: list[Step] = []
    for cog, site in _expert_sequence(variant):
        steps.append(Step(cog, _draw(cog, rnd, speed, sigma, complexity), site, progress=_progress_kind(cog)))
    baseline = sum(s.dur for s in steps)
    plan = TracePlan(person, level, case, complexity, variant, speed, steps, baseline_s=baseline)
    book: dict[str, dict] = {d: {"instances": 0, "added_s": 0.0, "saved_s": 0.0} for d in deficits}
    block_id = 0

    def d_draw(cog: str, scale: float = 1.0) -> float:
        return _draw(cog, rnd, speed, sigma, complexity) * scale

    for d in deficits:
        b = book[d]
        if d == "skipped_check_cliff":
            check_idx = [i for i, s in enumerate(plan.steps) if s.cog == "CHECK_CLIFF" and s.tag is None]
            k = rnd.randint(1, 3)
            drop = sorted(rnd.sample(check_idx, k), reverse=True)
            for i in drop:
                b["saved_s"] += plan.steps[i].dur
                del plan.steps[i]
            rework = [Step("REVERT", d_draw("REVERT"), tag=d), Step("ENTER_HOUSEHOLD", d_draw("ENTER_HOUSEHOLD", 0.7), tag=d)]
            rework += [Step("CHECK_CLIFF", d_draw("CHECK_CLIFF"), tag=d, progress="cliff_checked") for _ in range(k)]
            rework += [Step("READ_RESULT", d_draw("READ_RESULT"), tag=d)]
            at = next(i for i, s in enumerate(plan.steps) if s.cog == "RECONCILE" and s.tag is None) + 1
            plan.steps[at:at] = rework
            b["added_s"] += sum(s.dur for s in rework)
            b["instances"] += k
        elif d == "repeated_read_result":
            i = 0
            while i < len(plan.steps):
                s = plan.steps[i]
                if s.cog == "READ_RESULT" and s.tag is None and rnd.random() < 0.8:
                    block_id += 1
                    extra = [Step("READ_RESULT", d_draw("READ_RESULT", 0.6), tag=d, stuck_block=block_id) for _ in range(rnd.randint(1, 2))]
                    plan.steps[i + 1:i + 1] = extra
                    b["added_s"] += sum(e.dur for e in extra)
                    b["instances"] += 1
                    i += len(extra)
                i += 1
        elif d == "search_loop":
            block_id += 1
            ent = [i for i, s in enumerate(plan.steps) if s.cog == "ENTER_HOUSEHOLD" and s.tag is None]
            at = rnd.choice(ent)
            loop = []
            for r in range(rnd.randint(2, 4)):   # search, read the hits, reformulate, read, ...
                first = r == 0
                loop += [Step("SEARCH" if first else "REFORMULATE", d_draw("SEARCH" if first else "REFORMULATE"), tag=d, stuck_block=block_id),
                         Step("READ", d_draw("READ", 0.6), tag=d, stuck_block=block_id)]
            plan.steps[at:at] = loop
            b["added_s"] += sum(s.dur for s in loop)
            b["instances"] += 1
        elif d == "copy_error":
            at = max(i for i, s in enumerate(plan.steps) if s.cog == "COPY_TO_NOTE" and s.tag is None)
            plan.steps[at].progress = None
            tail = [Step("RECONCILE", d_draw("RECONCILE", 0.8), tag=d), Step("REVERT", d_draw("REVERT"), tag=d),
                    Step("COPY_TO_NOTE", d_draw("COPY_TO_NOTE"), tag=d, progress="note_field")]
            plan.steps[at + 1:at + 1] = tail
            b["added_s"] += sum(s.dur for s in tail)
            b["instances"] += 1
        elif d == "idle_before_enter":
            ent = [i for i, s in enumerate(plan.steps) if s.cog == "ENTER_HOUSEHOLD" and s.tag is None]
            picks = [ent[0]] + [i for i in ent[1:] if rnd.random() < 0.4]
            for i in sorted(picks, reverse=True):
                block_id += 1
                st = Step("IDLE", rnd.uniform(30.0, 75.0), tag=d, stuck_block=block_id)
                plan.steps.insert(i, st)
                b["added_s"] += st.dur
                b["instances"] += 1
    for d, b in book.items():
        b["price_s"] = b["added_s"] - b["saved_s"]
    plan.deficits = book
    plan.n_stuck_blocks = block_id
    return plan


def _emit_trace(em: Emitter, plan: TracePlan, t0: float, tid: str, rnd: random.Random):
    em.task_start(t0, tid)
    t = t0
    cogs = []
    blocks: dict[int, list[float]] = {}
    for s in plan.steps:
        t1 = t + s.dur
        em.cog(s.cog, t, t1, site=s.site)
        if s.progress:
            em.progress(t1 - 0.05, s.progress)
        if s.stuck_block is not None:
            blocks.setdefault(s.stuck_block, [t, t1])[1] = t1
        cogs.append([s.cog, round(s.dur, 2), s.tag])
        t = t1
    stuck = []
    for bid, (a, b) in sorted(blocks.items()):
        lab = rnd.random() < 0.6
        if lab:
            em.add("stuck", a + (b - a) * rnd.uniform(0.4, 0.9), source="desk")
        tag = next(s.tag for s in plan.steps if s.stuck_block == bid)
        stuck.append({"task_id": tid, "t0": fmt_t(datetime.fromtimestamp(a, tz=timezone.utc)), "t1": fmt_t(datetime.fromtimestamp(b, tz=timezone.utc)),
                      "duration_s": round(b - a, 2), "deficit": tag, "labelled": lab})
    em.task_end(t + 0.2)
    return t + 0.2, cogs, stuck


def _assign_deficits(rnd: random.Random) -> list[tuple[str, ...]]:
    """Each novice gets each deficit with probability 0.5; each deficit is present in 6 to 11 and absent in 5+ of 16."""
    while True:
        rows = [tuple(d for d in DEFICIT_ORDER if rnd.random() < 0.5) for _ in range(N_NOVICES)]
        counts = [sum(d in r for r in rows) for d in DEFICIT_ORDER]
        if all(6 <= c <= N_NOVICES - 5 for c in counts) and sum(1 for r in rows if not r) <= 2:
            return rows


def generate(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else data_dir()
    rnd = random.Random(SEED)
    nrng = np.random.default_rng(SEED)
    novice_deficits = _assign_deficits(rnd)

    rows: list[dict] = []
    traces: list[dict] = []
    stuck_all: list[dict] = []
    people: list[dict] = []
    t_cursor = BASE_DAY.timestamp()

    def run_person(person: str, level: str, variant: str, speed: float, sigma: float, deficits: tuple[str, ...], idx: int):
        nonlocal t_cursor
        em = Emitter(person, ROLE, person[2:], nrng)
        for case in range(1, CASES_PER_PERSON + 1):
            complexity = rnd.choice([1.0, 1.0, 1.2, 1.45])
            plan = build_trace(person, level, case, rnd, variant=variant, speed=speed, sigma=sigma, complexity=complexity, deficits=deficits)
            tid = f"t_{person[2:]}{'ab'[case - 1]}"
            start = t_cursor + rnd.uniform(0, 120)
            t_end, cogs, stuck = _emit_trace(em, plan, start, tid, rnd)
            t_cursor = t_end + 900.0
            exp_med = expert_median_s(complexity)
            total = t_end - start
            traces.append({
                "task_id": tid, "person": person, "level": level, "case": case, "complexity": complexity,
                "order_variant": variant, "t0": fmt_t(datetime.fromtimestamp(start, tz=timezone.utc)),
                "t1": fmt_t(datetime.fromtimestamp(t_end, tz=timezone.utc)), "duration_s": round(total, 2),
                "baseline_s": round(plan.baseline_s, 2), "expert_median_s": round(exp_med, 2),
                "slowness_s": round(plan.baseline_s - exp_med, 2),
                "deficits": [{"type": d, "instances": b["instances"], "added_s": round(b["added_s"], 2), "saved_s": round(b["saved_s"], 2),
                              "price_s": round(b["price_s"], 2)} for d, b in plan.deficits.items()],
                "price_total_s": round(sum(b["price_s"] for b in plan.deficits.values()), 2),
                "cogs": cogs,
            })
            stuck_all.extend(stuck)
        rows.extend(em.rows)

    expert_variants = ["A"] * (N_EXPERTS - 2) + ["B"] * 2
    for i in range(N_EXPERTS):
        person = f"p_exp{i + 1:02d}"
        speed = rnd.uniform(0.92, 1.08)
        people.append({"person": person, "level": "expert", "order_variant": expert_variants[i], "speed_factor": round(speed, 3), "deficits": []})
        run_person(person, "expert", expert_variants[i], speed, 0.15, (), i)
    for i in range(N_NOVICES):
        person = f"p_nov{i + 1:02d}"
        speed = rnd.uniform(1.12, 1.40)
        people.append({"person": person, "level": "novice", "order_variant": "A", "speed_factor": round(speed, 3), "deficits": list(novice_deficits[i])})
        run_person(person, "novice", "A", speed, 0.25, novice_deficits[i], i)

    for r in rows:
        r["t"] = fmt_t(datetime.fromtimestamp(r["t"], tz=timezone.utc))

    totals = {}
    nov_traces = [t for t in traces if t["level"] == "novice"]
    for d in DEFICIT_ORDER:
        present = [x for t in nov_traces for x in t["deficits"] if x["type"] == d]
        persons = {t["person"] for t in nov_traces if any(x["type"] == d for x in t["deficits"])}
        totals[d] = {
            "novices_with": len(persons), "novices_without": N_NOVICES - len(persons),
            "traces_with": len(present),
            "mean_price_s_when_present": round(sum(x["price_s"] for x in present) / max(1, len(present)), 2),
            "total_price_s": round(sum(x["price_s"] for x in present), 2),
        }
    truth = {
        "schema": 1, "kind": "apprentices", "origin": "synthetic", "task": TASK, "role": ROLE, "seed": SEED,
        "description": "Expert and novice traces of the benefits-processor household task with planted deficits. price_s = seconds added minus seconds removed versus the same trace without that deficit (exact by construction).",
        "n_experts": N_EXPERTS, "n_novices": N_NOVICES, "cases_per_person": CASES_PER_PERSON,
        "deficit_types": DEFICITS, "people": people, "traces": traces, "stuck_episodes": stuck_all,
        "deficit_totals": totals,
        "expert_reference": {
            "sequence_A": [c for c, _ in _expert_sequence("A")], "sequence_B": [c for c, _ in _expert_sequence("B")],
            "median_s_by_complexity": {str(c): round(expert_median_s(c), 2) for c in (1.0, 1.2, 1.45)},
            "note": "Variant B is an allowed reordering (all cliff checks after the three results); two experts use it.",
        },
        "counts": {"events": len(rows), "traces": len(traces)},
    }
    store = EventStore(root)
    out = root / "synthetic" / "apprentices"
    n = store.write_file(out / "events.jsonl", rows)
    (out / "truth.json").write_text(json.dumps(truth, indent=1, sort_keys=True))
    return {"events": n, "traces": len(traces), "dir": str(out)}
