"""Learner trajectories: three novices working about three benefits cases a day for ten days.

Reuses the apprentice trace machinery (same five planted deficits, same events). What changes is *when* a deficit
appears: each deficit has a per-case probability that falls with practice.

Planted mechanism (deliberately not a logistic model, a Beta-Bernoulli tracer or a hazard model): a power law of
practice on an effective practice count,

    p_d(case) = p0_d * (1 + n_eff / n0_d) ** (-alpha_d)

``n_eff`` grows by `rate` per case, by an extra `COACH_BOOST` after a case where the deficit appeared, the coach showed
a prompt and the learner followed it (a ``coach_shown`` and ``coach_followed`` pair), and shrinks by exp(-gap_days / tau)
over an absence (partial forgetting: the deficit probability recovers part of the way back). truth.json holds every
per-case probability, which deficits occurred, which coach prompts helped, and the true skill curve
``skill = 1 - mean_d(p_d / p0_d)``.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..store.jsonl import EventStore
from ..store.paths import data_dir
from ..store.validate import fmt_t
from .apprentices import DEFICIT_ORDER, DEFICITS, ROLE, build_trace, _emit_trace, expert_median_s
from .vocab import Emitter

SEED = 9909
START = datetime(2026, 10, 26, tzinfo=timezone.utc)          # Monday
N_CASES = 30
CASES_PER_DAY = 3
COACH_BOOST = 2.0
TAU_FORGET_DAYS = 6.0

# deficit -> (p0, n0, alpha): starting probability, practice scale, curve steepness
PARAMS = {
    "skipped_check_cliff": (0.55, 12.0, 0.9),
    "repeated_read_result": (0.60, 6.0, 1.1),
    "search_loop": (0.50, 8.0, 1.0),
    "copy_error": (0.40, 10.0, 0.8),
    "idle_before_enter": (0.65, 5.0, 1.2),
}

# person -> learner traits
LEARNERS = {
    "p_learn01": {"rate": 1.2, "follow": 0.75, "speed0": 1.30, "absence": None},
    "p_learn02": {"rate": 1.0, "follow": 0.65, "speed0": 1.35, "absence": {"after_case": 15, "days": 3}},
    "p_learn03": {"rate": 0.7, "follow": 0.45, "speed0": 1.40, "absence": None},
}


def prob(d: str, n_eff: float) -> float:
    p0, n0, a = PARAMS[d]
    return p0 * (1.0 + n_eff / n0) ** (-a)


def skill(ps: dict[str, float]) -> float:
    return 1.0 - sum(ps[d] / PARAMS[d][0] for d in PARAMS) / len(PARAMS)


def _step_starts(plan, t0: float) -> list[float]:
    out, t = [], t0
    for s in plan.steps:
        out.append(t)
        t += s.dur
    return out


def generate(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else data_dir()
    nrng = np.random.default_rng(SEED)
    rows: list[dict] = []
    traces: list[dict] = []
    people: list[dict] = []

    for pi, (person, traits) in enumerate(LEARNERS.items()):
        rnd = random.Random(SEED + 17 * (pi + 1))
        em = Emitter(person, ROLE, person[2:], nrng)
        n_eff = {d: 0.0 for d in PARAMS}
        day = 0
        curve: list[dict] = []
        for case in range(1, N_CASES + 1):
            ab = traits["absence"]
            if ab and case == ab["after_case"] + 1:
                factor = math.exp(-ab["days"] / TAU_FORGET_DAYS)
                n_eff = {d: v * factor for d, v in n_eff.items()}
                day += ab["days"]
            if (case - 1) % CASES_PER_DAY == 0 and case > 1:
                day += 1
            slot = (case - 1) % CASES_PER_DAY
            t0 = (START + timedelta(days=day, hours=9.5 + 2.5 * slot, minutes=rnd.uniform(-12, 12))).timestamp()
            ps = {d: prob(d, n_eff[d]) for d in PARAMS}
            occur = tuple(d for d in DEFICIT_ORDER if rnd.random() < ps[d])
            practice = sum(n_eff.values()) / len(PARAMS)
            speed = 1.05 + (traits["speed0"] - 1.05) * (1.0 + practice / 15.0) ** -0.8      # pace converges toward the expert's
            complexity = rnd.choice([1.0, 1.0, 1.2, 1.45])
            plan = build_trace(person, "novice", case, rnd, variant="A", speed=speed, sigma=0.22, complexity=complexity, deficits=occur)
            tid = f"t_{person[2:]}_{case:02d}"
            starts = _step_starts(plan, t0)
            t_end, cogs, stuck = _emit_trace(em, plan, t0, tid, rnd)
            # the coach: shows a prompt when a deficit starts (less often as the deficit fades); the learner follows or dismisses
            coach = []
            for d in occur:
                first = next(i for i, s in enumerate(plan.steps) if s.tag == d)
                t_show = starts[first]
                shown = rnd.random() < (0.85 if ps[d] > 0.25 else 0.5)
                followed = dismissed = False
                if shown:
                    for typ, dt in (("coach_shown", 0.0),):
                        em.add(typ, t_show + dt, source="coach", meta={"level": 1 if ps[d] > 0.4 else 2}, task=False)
                        em.rows[-1]["task_id"] = tid
                    if rnd.random() < traits["follow"]:
                        followed = True
                        em.add("coach_followed", t_show + rnd.uniform(2.0, 8.0), source="coach", task=False)
                    elif rnd.random() < 0.7:
                        dismissed = True
                        em.add("coach_dismissed", t_show + rnd.uniform(1.0, 3.5), source="coach", task=False)
                    em.rows[-1]["task_id"] = tid
                coach.append({"deficit": d, "shown": shown, "followed": followed, "dismissed": dismissed, "helped": shown and followed})
            curve.append({"case": case, "skill": round(skill(ps), 4)})
            traces.append({
                "task_id": tid, "person": person, "case": case, "day": day + 1, "date": (START + timedelta(days=day)).date().isoformat(),
                "t0": fmt_t(datetime.fromtimestamp(t0, tz=timezone.utc)), "t1": fmt_t(datetime.fromtimestamp(t_end, tz=timezone.utc)),
                "duration_s": round(t_end - t0, 2), "complexity": complexity, "speed_factor": round(speed, 3),
                "expert_median_s": round(expert_median_s(complexity), 2),
                "p_deficit": {d: round(ps[d], 4) for d in PARAMS}, "n_eff": {d: round(n_eff[d], 3) for d in PARAMS},
                "deficits": [{"type": d, "instances": b["instances"], "added_s": round(b["added_s"], 2), "saved_s": round(b["saved_s"], 2),
                              "price_s": round(b["price_s"], 2)} for d, b in plan.deficits.items()],
                "price_total_s": round(sum(b["price_s"] for b in plan.deficits.values()), 2),
                "coach": coach, "skill": round(skill(ps), 4),
                "cogs": cogs,
            })
            # learning update for the next case
            for d in PARAMS:
                n_eff[d] += traits["rate"]
            for c in coach:
                if c["helped"]:
                    n_eff[c["deficit"]] += COACH_BOOST * traits["rate"]
        people.append({"person": person, "rate": traits["rate"], "coach_follow_prob": traits["follow"], "speed0": traits["speed0"],
                       "absence": traits["absence"], "skill_curve": curve})
        rows.extend(em.rows)

    for r in rows:
        r["t"] = fmt_t(datetime.fromtimestamp(r["t"], tz=timezone.utc))
    truth = {
        "schema": 1, "kind": "learners", "origin": "synthetic", "role": ROLE, "seed": SEED,
        "description": "Three novices, 30 benefits cases each (three a day for ten days). Each planted deficit appears with a per-case probability that falls with practice; a coach prompt that is shown and followed speeds the decline; learner p_learn02 is absent for three days after case 15 and partly forgets.",
        "mechanism": {
            "p": "p_d = p0_d * (1 + n_eff / n0_d) ** (-alpha_d)",
            "n_eff_update": "after each case: n_eff += rate; n_eff += coach_boost * rate when the deficit appeared and the coach prompt was shown and followed",
            "forgetting": "over an absence of g days: n_eff *= exp(-g / tau_days)",
            "skill": "skill = 1 - mean_d(p_d / p0_d)",
            "coach_boost": COACH_BOOST, "tau_days": TAU_FORGET_DAYS,
            "deficit_params": {d: {"p0": p0, "n0": n0, "alpha": a} for d, (p0, n0, a) in PARAMS.items()},
        },
        "deficit_types": DEFICITS, "people": people, "traces": traces,
        "counts": {"events": len(rows), "traces": len(traces)},
    }
    store = EventStore(root)
    out = root / "synthetic" / "learners"
    n = store.write_file(out / "events.jsonl", rows)
    (out / "truth.json").write_text(json.dumps(truth, indent=1, sort_keys=True))
    return {"events": n, "traces": len(traces), "dir": str(out)}
