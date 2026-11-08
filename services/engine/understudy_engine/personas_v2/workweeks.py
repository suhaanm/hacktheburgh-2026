"""``generate_workweeks``: continuous work over days (routines and ad hoc tasks, interruptions, breaks, days off).

Schedules are a hierarchy, not a template: a person-level habit (mean start, part-time or night shift, weekend work) with
day-level random effects (an AR(1) start time, days off and short streaks, lunch, short breaks, meetings), so there is no
schedule change planted on a known day. Tasks arrive with heavy-tailed gaps. A person has one to four routines (from the
role's library); each routine has two to four variants whose probabilities drift week by week, per-instance skips and
repeats, an interleaving chance (foreign steps inside the episode) and a split chance (a task-detector error cuts one
instance into two episodes). Ad hoc tasks come from the family's own free-form sampler.

The result has the v1 persona shapes: schema-valid events (including OS lock, unlock, sleep, resume and idle events and
untagged background activity), a truth dict with routine instances per person, and stuck episodes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from ..core import Episode, Event
from .core import Clock, Step, choose, lognormal, poisson, seeded
from .ctx import Ctx
from .emit import Emitter, emit_case, finalize, iso
from .families import FAMILY_ORDER, get_family
from .params import draw_hyper, params_sha256
from .people import Person, draw_people
from .roles import RoleSpec, RoutineT, get_role
from .cohort import LABEL, NO_NOISE, rows_to_events

START_WW = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)   # a Monday


@dataclass
class PRoutine:
    tpl: RoutineT
    edits: list[tuple[str, float, str]]        # variant programs: (kind, position fraction, cog)
    logit0: list[float]
    drift: list[list[float]]                   # per week, per variant
    rate: float
    dows: set[int]
    hour_mean: float
    hour_sd: float


@dataclass
class V2Workweeks:
    family: str
    role: str
    seed: int
    n_people: int
    n_days: int
    hyper: dict
    people: list[Person]
    rows: list[dict]
    truth: dict
    labels: dict[str, str]
    levels: dict[str, str]
    _cache: dict = field(default_factory=dict, repr=False)

    def events(self) -> list[Event]:
        if "events" not in self._cache:
            self._cache["events"] = rows_to_events(self.rows)
        return self._cache["events"]

    def episodes(self, mapping=None) -> list[Episode]:
        from ..cogs import segment_episodes
        from ..routines.sources import pack_mapping

        if "episodes" not in self._cache:
            self._cache["episodes"] = segment_episodes(self.events(), mapping if mapping is not None else pack_mapping(self.role))
        return self._cache["episodes"]

    def episodes_of(self, person: str) -> list[Episode]:
        return [e for e in self.episodes() if e.person == person]

    def planted_spells(self) -> dict[str, list[tuple[float, float]]]:
        out: dict[str, list[tuple[float, float]]] = {}
        for s in self.truth["stuck_episodes"]:
            out.setdefault(s["person"], []).append((_ts(s["t0"]), _ts(s["t1"])))
        return out


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ------------------------------------------------------------------------------------------ routines
def _base_steps(tpl: RoutineT, k: int) -> list[Step]:
    out = [Step(c) for c in tpl.head]
    ccount = 0
    for _ in range(k):
        for c in tpl.group:
            site = None
            if tpl.sites and c == "OPEN_CALCULATOR":
                site = f"calc{ccount % 3 + 1}"
                ccount += 1
            out.append(Step(c, site))
    out += [Step(c) for c in tpl.tail]
    return out


def _make_routine(tpl: RoutineT, role: RoleSpec, h: dict, rnd, n_days: int, exp_tasks_day: float, n_r: int) -> PRoutine:
    nv = rnd.randint(2, 4)
    filler = [c for c in role.pool if role.act_class.get(c) in ("read", "seek")] or list(role.pool)
    edits: list[tuple[str, float, str]] = [("none", 0.0, "")]
    for _ in range(nv - 1):
        kind = choose(rnd, ("insert", "swap", "drop"), (0.5, 0.25, 0.25))
        edits.append((kind, rnd.random(), filler[rnd.randrange(len(filler))]))
    weeks = n_days // 7 + 2
    drift: list[list[float]] = []
    cur = [0.0] * nv
    for _ in range(weeks):
        cur = [c + h["wk_routine_drift"] * 1.5 * rnd.gauss(0.0, 1.0) for c in cur]
        drift.append(list(cur))
    ndow = rnd.randint(3, 7)
    dows = set(rnd.sample(range(7), ndow))
    rate = max(0.3, h["wk_routine_share"] * exp_tasks_day / n_r * (7.0 / ndow) * rnd.uniform(0.6, 1.4))
    return PRoutine(tpl, edits, [rnd.gauss(0.0, 1.0) for _ in range(nv)], drift, rate, dows, rnd.uniform(9.0, 17.0), rnd.uniform(0.8, 3.0))


def _instance_steps(pr: PRoutine, role: RoleSpec, h: dict, rnd, week: int, interleave: bool) -> tuple[list[Step], int, int]:
    lg = [a + b for a, b in zip(pr.logit0, pr.drift[min(week, len(pr.drift) - 1)])]
    m = max(lg)
    vi = choose(rnd, list(range(len(lg))), [math.exp(x - m) for x in lg])
    k = rnd.randint(*pr.tpl.k)
    steps = _base_steps(pr.tpl, k)
    kind, pos, cog = pr.edits[vi]
    if kind == "insert":
        i = 1 + int(pos * max(1, len(steps) - 1))
        steps.insert(min(i, len(steps)), Step(cog))
    elif kind == "swap" and len(steps) > 3:
        i = 1 + int(pos * (len(steps) - 3))
        steps[i], steps[i + 1] = steps[i + 1], steps[i]
    elif kind == "drop" and len(steps) > 4:
        del steps[1 + int(pos * (len(steps) - 2))]
    out: list[Step] = []
    skipped = 0
    for i, s in enumerate(steps):
        if i > 0 and rnd.random() < 0.03:
            skipped += 1
            continue
        out.append(s)
        if rnd.random() < 0.04:
            out.append(s)
    if interleave and len(out) > 3:
        pool = role.pool
        at = rnd.randint(1, len(out) - 1)
        out[at:at] = [Step(pool[rnd.randrange(len(pool))]) for _ in range(rnd.randint(2, 4))]
    return out, vi, skipped


# ------------------------------------------------------------------------------------------ schedules
def _person_schedule(h: dict, rnd) -> dict:
    night = rnd.random() < 0.12
    return {
        "p_wd": min(0.99, max(0.4, h["wk_p_work_weekday"] + rnd.gauss(0.0, 0.08))),
        "p_we": min(0.9, max(0.0, h["wk_p_work_weekend"] + rnd.gauss(0.0, 0.06))),
        "part_time": rnd.sample(range(5), 3) if rnd.random() < 0.18 else None,
        "start_mean": (h["wk_start_mean_h"] + rnd.gauss(0.0, 1.2)) + (rnd.uniform(8.0, 13.0) if night else 0.0),
        "len_h": max(3.0, h["wk_len_h"] + rnd.gauss(0.0, 0.8)),
        "night": night,
    }


def _windows(sched: dict, h: dict, rnd, day: int, dow: int, prev: dict) -> tuple[list[tuple[float, float]], float | None]:
    """Working windows (hours from the day's midnight; may exceed 24) after breaks, or [] on a day off."""
    working = dow < 5 and (sched["part_time"] is None or dow in sched["part_time"])
    p = sched["p_wd"] if working else (sched["p_we"] if dow >= 5 else 0.0)
    if prev.get("off_left", 0) > 0:
        prev["off_left"] -= 1
        return [], None
    if rnd.random() >= p:
        return [], None
    if dow < 5 and rnd.random() < h["wk_holiday_p"]:
        prev["off_left"] = 1 if rnd.random() < 0.3 else 0
        return [], None
    ar = h["wk_start_ar"]
    mean = sched["start_mean"]
    last = prev.get("start", mean)
    start = mean + ar * (last - mean) + h["wk_start_day_sd_h"] * math.sqrt(1 - ar * ar) * rnd.gauss(0.0, 1.0)
    prev["start"] = start
    length = min(11.0, max(2.5, sched["len_h"] + rnd.gauss(0.0, 1.0)))
    end = start + length
    breaks: list[tuple[float, float]] = []
    lunch_at = start + length * rnd.uniform(0.35, 0.55)
    breaks.append((lunch_at, lunch_at + lognormal(rnd, 40.0, 0.4) / 60.0))
    for _ in range(poisson(rnd, 1.5)):
        a = rnd.uniform(start + 0.5, end - 0.5)
        breaks.append((a, a + rnd.uniform(5.0, 15.0) / 60.0))
    for _ in range(poisson(rnd, 0.6)):
        a = rnd.uniform(start + 0.5, end - 1.0)
        breaks.append((a, a + rnd.uniform(30.0, 90.0) / 60.0))
    breaks.sort()
    wins: list[tuple[float, float]] = []
    cur = start
    for a, b in breaks:
        if a > cur + 0.15:
            wins.append((cur, min(a, end)))
        cur = max(cur, b)
        if cur >= end:
            break
    if end > cur + 0.15:
        wins.append((cur, end))
    return [(a, b) for a, b in wins if b - a >= 0.15], start


def _os_events(em: Emitter, rnd, wins_abs: list[tuple[float, float]], day_gap_after: list[bool]) -> None:
    locked = False
    for i, (a, b) in enumerate(wins_abs):
        nxt = wins_abs[i + 1][0] if i + 1 < len(wins_abs) else None
        if i == 0 or day_gap_after[i - 1]:
            if rnd.random() < 0.85:
                em.plain("resume", a - 3.0 + em.skew, source="os")
            em.plain("unlock", a - 1.5 + em.skew, source="os")
        if nxt is None:
            em.plain("sleep" if rnd.random() < 0.85 else "lock", b + rnd.uniform(1, 600) + em.skew, source="os")
        elif not day_gap_after[i]:
            gap = nxt - b
            if gap >= 300 and rnd.random() < 0.65:
                em.plain("lock", b + min(gap - 2, rnd.uniform(30, 240)) + em.skew, source="os")
                em.plain("unlock", nxt - 1.5 + em.skew, source="os")
        elif nxt is not None:
            em.plain("sleep" if rnd.random() < 0.85 else "lock", b + rnd.uniform(1, 600) + em.skew, source="os")


def _background(em: Emitter, rnd, t0: float, t1: float, rate_per_s: float) -> None:
    """Untagged activity between tasks (email, chat, other tools): events that belong to no task."""
    t = t0
    while True:
        t += rnd.expovariate(rate_per_s)
        if t >= t1:
            return
        typ = ("scroll", "focus", "click", "tab", "nav")[rnd.randrange(5)]
        em.plain(typ, t, zone=("doc", "page", "form_field")[rnd.randrange(3)], trole="document", label_idx=rnd.randrange(0, 4),
                 meta={"depth_bin": rnd.randrange(0, 6)} if typ == "scroll" else None)


# ------------------------------------------------------------------------------------------ the generator
def generate_workweeks(family: str, role: str, n_people: int = 40, n_days: int = 14, seed: int = 0, *,
                       hyper_overrides: dict[str, float] | None = None, noise: bool = True, start: datetime | None = None) -> V2Workweeks:
    fam = get_family(family)
    rs = get_role(role)
    over = dict(hyper_overrides or {})
    if not noise:
        over = {**NO_NOISE, **over}
    h = draw_hyper(np.random.default_rng([seed, FAMILY_ORDER.index(family), 7919]), over)
    rnd = seeded(seed, FAMILY_ORDER.index(family), 11)
    people = draw_people(h, rs, n_people, fam.code, seed, rnd)
    for p in people:
        fam.prepare_person(p, rs, h, seeded(seed, FAMILY_ORDER.index(family), 12, p.idx))
    t_start = (start or START_WW).timestamp()

    all_rows: list[dict] = []
    labels: dict[str, str] = {}
    stuck_eps: list[dict] = []
    people_truth: list[dict] = []
    n_tasks_total = 0
    for p in people:
        prnd = seeded(seed, FAMILY_ORDER.index(family), 13, p.idx)
        em = Emitter(p, rs, h, seeded(seed, FAMILY_ORDER.index(family), 14, p.idx), f"{p.id[2:]}")
        sched = _person_schedule(h, prnd)
        prev: dict = {}
        day_wins: list[list[tuple[float, float]]] = []
        for d in range(n_days):
            w, _s = _windows(sched, h, prnd, d, d % 7, prev)
            day_wins.append(w)
        active_h = [sum(b - a for a, b in w) for w in day_wins if w]
        exp_tasks_day = h["wk_tasks_per_h"] * (sum(active_h) / max(1, len(active_h)) if active_h else 6.0) * 0.85
        n_r = prnd.randint(1, min(4, len(rs.routines)))
        chosen = prnd.sample(list(rs.routines), n_r)
        prs = [_make_routine(t, rs, h, prnd, n_days, exp_tasks_day, n_r) for t in chosen]
        due: list[tuple[float, int]] = []
        for d in range(n_days):
            if not day_wins[d]:
                continue
            for ri, pr in enumerate(prs):
                if (d % 7) not in pr.dows:
                    continue
                for _ in range(poisson(prnd, pr.rate)):
                    due.append((t_start + d * 86400.0 + max(0.0, prnd.gauss(pr.hour_mean, pr.hour_sd)) * 3600.0, ri))
        due.sort()
        di = 0
        wins_abs: list[tuple[float, float]] = []
        gap_after: list[bool] = []
        for d, w in enumerate(day_wins):
            for j, (a, b) in enumerate(w):
                wins_abs.append((t_start + d * 86400.0 + a * 3600.0, t_start + d * 86400.0 + b * 3600.0))
                gap_after.append(j == len(w) - 1)
        done_eff = 0.0
        task_no = 0
        routine_inst: dict[str, list[dict]] = {pr.tpl.id: [] for pr in prs}
        work_s, since = 0.0, 0.0
        for wi, (a, b) in enumerate(wins_abs):
            if wi == 0 or gap_after[wi - 1]:
                work_s, since = 0.0, 0.0
            t = a + prnd.uniform(5, 60)
            week = int((a - t_start) // (7 * 86400))
            while t < b - 90:
                gap = min(1800.0, lognormal(prnd, max(20.0, 3600.0 / h["wk_tasks_per_h"] * 0.35), h["wk_task_gap_sigma"]))
                _background(em, prnd, t, min(t + gap, b), 1.0 / 70.0)
                t += gap
                if t >= b - 90:
                    break
                routine_idx = None
                if di < len(due) and due[di][0] <= t:
                    routine_idx = due[di][1]
                    di += 1
                hour = (t - t_start) % 86400.0 / 3600.0
                clock = Clock(hour=hour, work_s=work_s, since_start_s=since)
                parts: list[list[Step]]
                rname = "adhoc"
                variant, skipped = -1, 0
                split = False
                if routine_idx is not None:
                    pr = prs[routine_idx]
                    steps, variant, skipped = _instance_steps(pr, rs, h, prnd, week, prnd.random() < h["wk_interleave_p"])
                    rname = pr.tpl.id
                    if len(steps) >= 6 and prnd.random() < h["wk_split_p"]:
                        m = prnd.randint(2, len(steps) - 2)
                        parts, split = [steps[:m], steps[m:]], True
                    else:
                        parts = [steps]
                else:
                    ctx0 = Ctx(prnd, rs, p, h, p.tenure + done_eff, clock, 1.0, fam.dur_fn)
                    n = 2 + int(lognormal(prnd, 4.0, 0.6))
                    parts = [fam.adhoc_steps(ctx0, min(25, max(3, n)))]
                tids = []
                t_run = t
                for part in parts:
                    task_no += 1
                    tid = f"t_{p.id[2:]}w{task_no:05d}"
                    tids.append(tid)
                    clock = Clock(hour=(t_run - t_start) % 86400.0 / 3600.0, work_s=work_s, since_start_s=since)
                    ctx = Ctx(prnd, rs, p, h, p.tenure + done_eff, clock, 1.0, fam.dur_fn)
                    fam.run_steps(ctx, part, deficits=True)
                    t_end, spans = emit_case(em, ctx.plan, t_run, tid)
                    labels[tid] = rname
                    for s in ctx.plan.stuck:
                        stuck_eps.append({"task_id": tid, "person": p.id, "t0": iso(spans[s.i0][0]), "t1": iso(spans[s.i1 - 1][1]),
                                          "duration_s": round(s.seconds, 2), "deficit": s.tag, "labelled": s.reported, "suppression": round(s.supp, 3),
                                          "silent": s.silent})
                    if rname != "adhoc":
                        routine_inst[rname].append({"task_id": tid, "t0": iso(t_run), "t1": iso(t_end), "n_cogs": len(ctx.plan.segs), "skipped": skipped,
                                                    "variant": variant, "split": split, "stuck": bool(ctx.plan.stuck), "duration_s": round(t_end - t_run, 2)})
                    dur = t_end - t_run
                    work_s += dur
                    since += dur
                    done_eff += 0.2
                    t_run = t_end + (prnd.uniform(5.0, 60.0) if split else 0.0)
                t = t_run
                n_tasks_total += len(parts)
            since += max(0.0, b - t)
        people_truth.append({
            "person": p.id, "level": p.level, "tenure_cases": round(p.tenure, 1), "g": round(p.g, 3), "night_shift": sched["night"],
            "part_time_days": sched["part_time"], "days_worked": sum(1 for w in day_wins if w), "n_days": n_days,
            "routines": [{"name": pr.tpl.id, "rate_per_day": round(pr.rate, 2), "days": sorted(pr.dows), "n_variants": len(pr.edits),
                          "n_instances": len(routine_inst[pr.tpl.id]), "instances": routine_inst[pr.tpl.id]} for pr in prs],
            "daily": [{"day": d + 1, "dow": d % 7, "windows": [[round(a, 2), round(b, 2)] for a, b in w]} for d, w in enumerate(day_wins)],
        })
        all_rows.extend(em.rows)
        _os_events_rows = Emitter(p, rs, h, seeded(seed, FAMILY_ORDER.index(family), 15, p.idx), f"{p.id[2:]}o")
        _os_events(_os_events_rows, prnd, wins_abs, gap_after)
        all_rows.extend(_os_events_rows.rows)

    rows = finalize(all_rows)
    from .cited import status_counts

    truth = {
        "schema": 1, "kind": "workweeks_v2", "origin": "synthetic", "role": rs.id, "family": family, "seed": seed, "n_days": n_days,
        "start_date": (start or START_WW).date().isoformat(), "tz": "UTC",
        "realism": {"label": LABEL, "family": family, "params_sha256": params_sha256(), "hyper": {k: round(v, 5) for k, v in h.items()},
                    "cited_status_counts": status_counts(),
                    "note": "Generated. No schedule change is planted on a known day."},
        "people": people_truth, "routine_labels": labels, "stuck_episodes": stuck_eps,
        "counts": {"events": len(rows), "tasks": n_tasks_total, "stuck_episodes": len(stuck_eps),
                   "routine_tasks": sum(1 for v in labels.values() if v != "adhoc")},
    }
    return V2Workweeks(family, rs.id, seed, n_people, n_days, h, people, rows, truth, labels, {p.id: p.level for p in people})
