"""Persona generator (CAP-9): events.jsonl plus truth.json per persona. Fully seeded and deterministic."""
from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..store.jsonl import EventStore
from ..store.paths import data_dir
from ..store.validate import fmt_t
from .profiles import (
    CHANGE_DAY, N_DAYS, PERSONAS, PERSONA_BY_SLUG, ROLE, START_DATE, PersonaSpec, day_date, windows_for_day,
)
from .states import BINS_PER_DAY, DAY_S, StateParams, simulate_states
from .tasks import (
    PRODUCTIVE, SKILL_ALPHA, SKILL_N0, SOFT_PRODUCTIVE, STUCK_GAMMA, STUCK_P0, AdHocChain, TaskPlan,
    expand_routine, judgement_share, nominal_template, plan_task, skill_at,
)
from .vocab import Emitter

T0 = START_DATE.timestamp()


def iso(t: float) -> str:
    return fmt_t(datetime.fromtimestamp(t, tz=timezone.utc))


@dataclass
class PersonaRun:
    spec: PersonaSpec
    rows: list[dict]
    truth: dict


# ------------------------------------------------------------------------------------- helpers
def _poisson(rnd: random.Random, lam: float) -> int:
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= L:
            return k
        k += 1


def _daily_plan(spec: PersonaSpec, n_days: int, rnd: random.Random):
    wins = [windows_for_day(spec, d, rnd) for d in range(n_days)]
    kinds = ["normal" if w else "off" for w in wins]
    working = [d for d in range(n_days) if wins[d]]
    wk2 = [d for d in working if 7 <= d <= 13 and d != 7]
    wk1 = [d for d in working if 1 <= d <= 5]
    sick = rnd.choice(wk2) if wk2 else None
    hol = rnd.choice([d for d in wk1]) if wk1 else None
    if sick is not None:
        wins[sick] = [(12.0, 13.25)]     # one short low-energy session
        kinds[sick] = "sick"
    if hol is not None and hol != sick:
        wins[hol] = []
        kinds[hol] = "holiday"
    return wins, kinds, sick, hol


def _os_events(em: Emitter, rnd: random.Random, segs, p: StateParams) -> None:
    """lock / unlock / sleep / resume / idle events at state boundaries."""
    locked = False
    slept = False
    for i, (state, a, b) in enumerate(segs):
        dur = b - a
        T = T0
        if state == "IDLE":
            if dur >= 150:
                em.add("idle", T + a + 120, source="os", meta={"idle_s": 120}, task=False)
        elif state == "AWAY":
            if rnd.random() < p.p_lock_when_away:
                em.add("lock", T + a + min(dur - 2, rnd.uniform(30, 240)), source="os", task=False)
                locked = True
            elif dur >= 150:
                em.add("idle", T + a + 120, source="os", meta={"idle_s": 120}, task=False)
        elif state == "OFF":
            if rnd.random() < p.p_sleep_when_off:
                em.add("sleep", T + a + min(dur - 2, rnd.uniform(1, 20)), source="os", task=False)
                slept = True
            else:
                em.add("lock", T + a + min(dur - 2, rnd.uniform(5, 60)), source="os", task=False)
                locked = True
        # leaving a non-active state into ACTIVE
        if state != "ACTIVE" and i + 1 < len(segs) and segs[i + 1][0] == "ACTIVE":
            if slept:
                em.add("resume", T + b - 3.0, source="os", task=False)
                slept = False
                if rnd.random() < 0.7:
                    locked = True
            if locked:
                em.add("unlock", T + b - 1.5, source="os", task=False)
                locked = False
        elif state == "ACTIVE":
            pass


def _noise(em: Emitter, rnd: random.Random, t0: float, t1: float, rate_per_s: float) -> None:
    t = t0
    while True:
        t += rnd.expovariate(rate_per_s)
        if t >= t1:
            return
        typ = rnd.choice(["scroll", "focus", "click", "tab", "nav"])
        zone = rnd.choice(["doc", "page", "form_field", "doc"])
        meta = {"depth_bin": rnd.randint(0, 5)} if typ == "scroll" else None
        em.add(typ, t, zone=zone if typ not in ("nav",) else "page", role="document", label_idx=rnd.randint(0, 3),
               meta=meta, task=False, site=None)


def simulate_persona(spec: PersonaSpec, n_days: int = N_DAYS, *, with_mc: bool = True) -> PersonaRun:
    rnd = random.Random(spec.seed)
    nrng = np.random.default_rng(spec.seed)
    p = StateParams()
    em = Emitter(spec.person, ROLE, spec.slug[:3] + "x", nrng)
    chain = AdHocChain(spec.seed + 7, spec.adhoc_entropy)

    wins, kinds, sick, hol = _daily_plan(spec, n_days, rnd)
    segs = simulate_states(wins, rnd, p)
    _os_events(em, rnd, segs, p)

    # planted routine instances: (due_t, spec) sorted by due time
    due: list[tuple[float, int]] = []
    for d in range(n_days):
        if kinds[d] == "holiday":
            continue
        dow = d % 7
        for ri, r in enumerate(spec.routines):
            if dow not in r.dow:
                continue
            n = _poisson(rnd, r.rate_per_day * (0.4 if kinds[d] == "sick" else 1.0))
            for _ in range(n):
                h = max(0.0, rnd.gauss(r.hour_mean, r.hour_sd))
                due.append((T0 + d * DAY_S + h * 3600.0, ri))
    due.sort()
    di = 0

    tasks_done = 0
    task_no = 0
    stuck_eps: list[dict] = []
    routine_inst: dict[str, list[dict]] = {r.name: [] for r in spec.routines}
    adhoc_n = 0
    skill_by_day: list[float] = []
    tasks_by_day: list[int] = []
    day_marks = {d: False for d in range(n_days)}

    for state, a, b in segs:
        if state != "ACTIVE":
            continue
        a_abs, b_abs = T0 + a, T0 + b
        d = int(a // DAY_S)
        for dd in range(d + 1):
            if not day_marks[dd]:
                day_marks[dd] = True
                skill_by_day.append(round(skill_at(spec.s0, tasks_done), 4))
                tasks_by_day.append(tasks_done)
        t = a_abs + rnd.uniform(5, 40)
        while t < b_abs - 40:
            gap = rnd.expovariate(1.0 / spec.gap_mean_s)
            gap = min(gap, 600.0)
            _noise(em, rnd, t, min(t + gap, b_abs), 1 / 90.0)
            t += gap
            skill = skill_at(spec.s0, tasks_done)
            if di < len(due) and due[di][0] <= t:
                ri = due[di][1]
                di += 1
                r = spec.routines[ri]
                seq, skipped = expand_routine(r, rnd)
                plan = plan_task(r.name, seq, rnd, speed=spec.speed, skill=skill, sigma=r.dur_sigma, skipped=skipped)
                kind = r.name
            else:
                n = rnd.randint(3, 9)
                cogs = chain.sample(rnd, n)
                seq = [(c, f"calc{rnd.randint(1, 3)}" if c == "OPEN_CALCULATOR" else None) for c in cogs]
                plan = plan_task("adhoc", seq, rnd, speed=spec.speed, skill=skill, sigma=0.4)
                kind = "adhoc"
            if t + plan.total > b_abs - 5:
                if kind == "adhoc":
                    # truncate to what fits; give up if too short
                    keep, acc = [], 0.0
                    for it in plan.items:
                        if t + acc + it.dur > b_abs - 8:
                            break
                        keep.append(it)
                        acc += it.dur
                    if len(keep) < 3:
                        break
                    plan.items = keep
                    plan.stuck_blocks = [sb for sb in plan.stuck_blocks if sb["start_item"] < len(keep)]
                else:
                    if di > 0:
                        di -= 1                       # defer the routine to the next active block
                    break
            task_no += 1
            tid = f"t_{spec.slug[:3]}{task_no:05d}"
            t_end, eps = _run_task(em, plan, t, tid, rnd, skill)
            for e in eps:
                e.update(task_id=tid, person=spec.person)
                stuck_eps.append(e)
            if kind == "adhoc":
                adhoc_n += 1
            else:
                routine_inst[kind].append({"task_id": tid, "t0": iso(t), "t1": iso(t_end), "n_cogs": len(plan.items), "skipped": plan.skipped,
                                           "stuck": bool(plan.stuck_blocks), "duration_s": round(t_end - t, 2)})
            tasks_done += 1
            t = t_end
        _noise(em, rnd, t, b_abs, 1 / 90.0)
    for dd in range(n_days):
        if not day_marks[dd]:
            skill_by_day.append(round(skill_at(spec.s0, tasks_done), 4))
            tasks_by_day.append(tasks_done)

    # unique, ordered rows
    rows = sorted(em.rows, key=lambda r: (r["t"], r["id"]))
    for r in rows:
        r["t"] = iso(r["t"])

    truth = _truth(spec, n_days, wins, kinds, sick, hol, segs, routine_inst, stuck_eps, skill_by_day, tasks_by_day,
                   adhoc_n, len(rows), with_mc)
    return PersonaRun(spec, rows, truth)


def _run_task(em: Emitter, plan: TaskPlan, t0: float, tid: str, rnd: random.Random, skill: float):
    em.task_start(t0, tid)
    t = t0
    eps: list[dict] = []
    blocks = {b["start_item"]: b for b in plan.stuck_blocks}
    cur_block = None
    block_t0 = 0.0
    for i, it in enumerate(plan.items):
        if i in blocks:
            cur_block = blocks[i]
            block_t0 = t
            cur_block["_t0"] = t
        if cur_block is not None and not it.stuck:
            # first non-stuck item after the block: the block ends here
            t_block_end = t
            lab = None
            if cur_block["label_frac"] is not None:
                lab = block_t0 + (t_block_end - block_t0) * cur_block["label_frac"]
                em.add("stuck", lab, source="desk")
            eps.append({"t0": iso(block_t0), "t1": iso(t_block_end), "duration_s": round(t_block_end - block_t0, 2),
                        "skill": round(skill, 4), "p_step": round(STUCK_P0 * (1 - skill) ** STUCK_GAMMA, 4),
                        "labelled": lab is not None, "label_t": iso(lab) if lab else None})
            cur_block = None
        t1 = t + it.dur
        em.cog(it.cog, t, t1, site=it.site, query_len=it.query_len)
        if not it.stuck:
            if it.cog in PRODUCTIVE or (it.cog in SOFT_PRODUCTIVE and rnd.random() < 0.4):
                kind = {"READ_RESULT": "result_read", "COPY_TO_NOTE": "note_field"}.get(it.cog, "step_done")
                em.progress(t1 - 0.05, kind)
        t = t1
    em.task_end(t + 0.2)
    return t + 0.2, eps


def _mc_expected(spec: PersonaSpec, post: bool, weeks: int = 150):
    """Monte Carlo of the state model alone: expected P(ACTIVE) per (dow, 15-min slot), and hours per state."""
    rnd = random.Random(spec.seed * 31 + (7 if post else 3))
    n_days = weeks * 7
    wins = [windows_for_day(spec, d, rnd, post=post, dow=d % 7) for d in range(n_days)]
    segs = simulate_states(wins, rnd)
    act = np.zeros((7, BINS_PER_DAY))
    hours = {"ACTIVE": 0.0, "IDLE": 0.0, "AWAY": 0.0, "OFF": 0.0}
    for state, a, b in segs:
        hours[state] += (b - a) / 3600.0
        if state != "ACTIVE":
            continue
        for bi in range(int(a // 900), int(math.ceil(b / 900))):
            lo, hi = max(a, bi * 900), min(b, (bi + 1) * 900)
            act[(bi // BINS_PER_DAY) % 7, bi % BINS_PER_DAY] += (hi - lo) / 900.0
    act /= weeks
    return np.round(act, 4).tolist(), {k: round(v / weeks, 2) for k, v in hours.items()}


def _truth(spec, n_days, wins, kinds, sick, hol, segs, routine_inst, stuck_eps, skill_by_day, tasks_by_day, adhoc_n, n_events, with_mc):
    routines = []
    for r in spec.routines:
        inst = routine_inst[r.name]
        durs = [i["duration_s"] for i in inst]
        nominal = nominal_template(r)
        routines.append({
            "name": r.name, "kind": r.kind, "rate_per_day": r.rate_per_day, "days": list(r.dow),
            "preferred_hour": {"mean": r.hour_mean, "sd": r.hour_sd}, "dur_sigma": r.dur_sigma,
            "skip_prob": r.skip_prob, "extra_prob": r.extra_prob, "group_k": list(r.group_k),
            "nominal_cogs": nominal, "judgement_share": round(judgement_share(nominal), 4),
            "n_instances": len(inst),
            "minutes_per_week": round(sum(durs) / 60.0 / (n_days / 7.0), 2),
            "mean_duration_s": round(statistics.fmean(durs), 2) if durs else None,
            "cv_duration": round(statistics.pstdev(durs) / statistics.fmean(durs), 4) if len(durs) > 1 else None,
            "instances": inst,
        })
    truth = {
        "schema": 1, "kind": "persona", "origin": "synthetic",
        "persona": spec.slug, "person": spec.person, "label": spec.label, "role": ROLE, "seed": spec.seed,
        "start_date": START_DATE.date().isoformat(), "n_days": n_days, "tz": "UTC",
        "change_day": CHANGE_DAY, "change_description": spec.change,
        "schedule": None if spec.random_days else {
            "pre": {str(d): [list(w) for w in ws] for d, ws in sorted(spec.pre.items())},
            "post": {str(d): [list(w) for w in ws] for d, ws in sorted(spec.post.items())},
            "note": "weekday 0 = Monday; hours are UTC from midnight of the window's own day; end > 24 spills past midnight",
        },
        "daily": [
            {"day": d + 1, "date": day_date(d).date().isoformat(), "dow": d % 7, "kind": kinds[d],
             "windows": [list(w) for w in wins[d]], "phase": "post" if d + 1 >= CHANGE_DAY else "pre"}
            for d in range(n_days)
        ],
        "sick_day": None if sick is None else {"day": sick + 1, "date": day_date(sick).date().isoformat()},
        "holiday": None if hol is None else {"day": hol + 1, "date": day_date(hol).date().isoformat()},
        "states": [{"state": s, "t0": iso(T0 + a), "t1": iso(T0 + b)} for s, a, b in segs],
        "routines": routines,
        "stuck_episodes": stuck_eps,
        "skill": {
            "model": "s(n) = 1 - (1 - s0) * (1 + n / n0) ** (-alpha), n = tasks completed so far",
            "s0": spec.s0, "n0": SKILL_N0, "alpha": SKILL_ALPHA,
            "stuck_hazard": {"model": "p_step = p0 * (1 - skill) ** gamma, applied before each productive cog", "p0": STUCK_P0, "gamma": STUCK_GAMMA},
            "by_day": skill_by_day, "tasks_done_at_day_start": tasks_by_day,
        },
        "counts": {"events": n_events, "tasks": sum(len(v) for v in routine_inst.values()) + adhoc_n,
                   "adhoc_tasks": adhoc_n, "routine_tasks": sum(len(v) for v in routine_inst.values()),
                   "stuck_episodes": len(stuck_eps), "stuck_labelled": sum(1 for e in stuck_eps if e["labelled"])},
    }
    if with_mc:
        pre_p, pre_h = _mc_expected(spec, False)
        post_p, post_h = _mc_expected(spec, True)
        truth["expected_active_prob"] = {"pre": pre_p, "post": post_p, "note": "Monte Carlo of the state model alone, 150 weeks; [dow][slot of 15 min]"}
        truth["state_hours_per_week"] = {"pre": pre_h, "post": post_h}
    return truth


# ------------------------------------------------------------------------------------- output
def write_persona(spec: PersonaSpec, root: Path | None = None, n_days: int = N_DAYS, with_mc: bool = True) -> dict:
    run = simulate_persona(spec, n_days, with_mc=with_mc)
    root = Path(root) if root is not None else data_dir()
    store = EventStore(root)
    out_dir = root / "synthetic" / spec.slug
    n = store.write_file(out_dir / "events.jsonl", run.rows)
    (out_dir / "truth.json").write_text(json.dumps(run.truth, indent=1, sort_keys=True))
    return {"persona": spec.slug, "person": spec.person, "events": n, "dir": str(out_dir)}


def write_all_personas(root: Path | None = None, only: list[str] | None = None, n_days: int = N_DAYS) -> list[dict]:
    specs = [PERSONA_BY_SLUG[s] for s in only] if only else list(PERSONAS)
    return [write_persona(s, root, n_days) for s in specs]
