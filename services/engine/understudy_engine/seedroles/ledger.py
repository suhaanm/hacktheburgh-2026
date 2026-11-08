"""Twelve weeks of the worker's own assist ledger under another role (programmer, data analyst), for the same worker id.

Why: when the worker switches their profile to a role that has no work behind it, Growth, the pointers on Home and the coach have nothing to show. This writes a credible
twelve-week history for the role into ``<data>/assist/ledger.jsonl``, beside (never over) the rows of any other role: every row carries its role, ``GET /growth`` reads one role at a
time (``?role=`` reads another), and the insights worker reads rows by the profile's role, so histories stay apart and come back when the worker returns to a role.

What the history looks like (a dozen things that real work has, none of them typed into a screen):

* skills and ids come from the role pack's own curriculum; the step id from its expert policy (``expert_steps.yaml``); the time lost against the expert from the policy's own
  ``expert_median_s`` for that step, scaled per skill. Six to eight skills are practised, not all of them all the time (a skill starts in the second month, another stops
  once it is mastered).
* the learner dynamics are ``cue.simlearn``'s (a latent mastery per skill, a gain from managing alone and a larger one from accepted help, forgetting between occurrences,
  the chance of finishing unaided ``GUESS + (1 - GUESS) * m``), with per-skill arcs: one skill that STAYS hard (a ceiling the learner never gets over), one that improves fast, one
  that plateaus, one that was mastered and not touched for weeks (due for practice), one that slips after a break.
* the calendar of the work: a different time-of-day pattern per role, weekdays (and the odd weekend for programmers), one unwell week with two rows, one break of twelve days,
  a quieter week, a busier one. Some occurrences come straight after an interruption and need more help and lose more time. Help is accepted, dismissed or not shown; some
  cases end in an error or are abandoned; the one-line reason is shown once a skill a day; help is sometimes withheld on purpose for a mastered skill.
* routines that emerge: from the second half of the history, automation and delegated rows for routines the pack's own routine templates name (listed as offloaded work,
  never counted in any score).

Idempotent: a marker file ``<data>/.seed-ledger-<role>`` is written once the rows are in; a second call writes nothing. Only a demo data directory is ever written. Deterministic
for a given ``now``. No model, no network, no clock but ``now``. Every row keeps the data enum ``origin: synthetic``; nothing here is text a person reads.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..cue import ledger as L
from ..cue.simlearn import GUESS, q_of
from . import PERSON

DAY = 86400.0
WEEKS = 12
LAG_HOURS = 5.0                 # the last row is this long before ``now`` (the demo growth seed's own is 2: this role never looks newer than the person's base role)
M_EXPERT = 0.95
ORIGIN_DETAIL = "synthetic_learner"
MARKER = ".seed-ledger-{role}"
#: ledger serials are offset per role so ids never collide with another role's rows or the demo growth rows (ids are hashes of person, time, skill, step, stream and serial)
SERIAL0 = {"programmer": 10_000, "data-analyst": 20_000}


@dataclass(frozen=True)
class Arc:
    """One skill's course through the twelve weeks. ``lost_x`` is the seconds lost at zero mastery as a multiple of the expert median for the skill's step."""
    skill: str
    m0: float
    lr_self: float
    lr_help: float
    start_w: int = 0
    end_w: int = WEEKS - 1
    weight: float = 1.0
    lost_x: float = 1.2
    cap: float | None = None            # mastery never rises above this (a skill that stays hard, a plateau)
    stability_days: float = 150.0
    cap_from_w: int = 0


@dataclass(frozen=True)
class Plan:
    arcs: tuple[Arc, ...]
    seed: int
    base_per_week: float                # assist occurrences in an ordinary week
    hours: tuple[tuple[int, int, float], ...]       # (first hour, last hour, weight): when in the day the work happens (UTC)
    dow_weights: tuple[float, ...]      # Monday to Sunday
    sick_week: int                      # one unwell week: two rows
    break_days: tuple[int, int]         # [from, to) in days since the start: no rows at all
    quiet_weeks: tuple[int, ...]        # weeks at half the pace
    busy_weeks: tuple[int, ...]         # weeks at 1.4 times the pace
    p_interrupt: float
    routines: tuple[tuple[str, str, int, float], ...]   # (routine id, stream, from week, rows a week)


#: Each plan's ``seed`` was chosen from 1 to 30 by looking at what Growth and Home show for the role (the independence trend reads "needs less help" over the twelve weeks, at
#: least three pointers, a mastered skill due for practice or a milestone). Nothing here is an evaluation, and no held-out result was looked at.
PLANS: dict[str, Plan] = {
    # Programmer: a late-morning start, work again after dinner now and then, some weekend; test-first stays hard; reproducing before fixing is learned fast; reading the
    # failing trace is mastered early and the commit-message habit slips after the break.
    "programmer": Plan(
        arcs=(
            Arc("read-the-trace-first", m0=0.10, lr_self=0.050, lr_help=0.10, weight=1.1, lost_x=1.1, stability_days=200.0),
            Arc("smallest-change", m0=0.08, lr_self=0.045, lr_help=0.09, weight=1.1, lost_x=1.0),
            Arc("confirm-the-fix", m0=0.15, lr_self=0.040, lr_help=0.08, weight=1.0, lost_x=1.2, cap=0.70, cap_from_w=5, stability_days=22.0),
            Arc("inspect-the-inputs", m0=0.25, lr_self=0.060, lr_help=0.11, end_w=8, weight=0.9, lost_x=1.0, stability_days=200.0),
            Arc("test-first-clean-commits", m0=0.05, lr_self=0.012, lr_help=0.03, weight=0.55, lost_x=1.7, cap=0.45),
            Arc("reproduce-before-fixing", m0=0.05, lr_self=0.075, lr_help=0.14, start_w=2, weight=1.0, lost_x=1.5),
            Arc("open-a-reviewable-pr", m0=0.15, lr_self=0.060, lr_help=0.11, start_w=6, weight=0.5, lost_x=1.3),
            Arc("message-for-the-next-reader", m0=0.30, lr_self=0.050, lr_help=0.09, start_w=5, weight=0.4, lost_x=1.0, stability_days=14.0),
        ),
        seed=23, base_per_week=23.0,
        hours=((10, 13, 0.40), (14, 18, 0.42), (20, 23, 0.18)),
        dow_weights=(1.0, 1.1, 1.2, 1.1, 0.8, 0.12, 0.08),
        sick_week=3, break_days=(41, 53), quiet_weeks=(8,), busy_weeks=(10,), p_interrupt=0.15,
        routines=(("rerun-failed-ci", "automation", 6, 2.2), ("ci-status-sweep", "delegated", 7, 1.0), ("open-pr-from-branch", "automation", 9, 0.8)),
    ),
    # Data analyst: office hours, heavier on Monday and Tuesday; reconciling to the control figure stays hard; segmenting before concluding is learned fast; the
    # magnitude check is mastered early and then not needed for weeks; comparing with the last period slips after the break.
    "data-analyst": Plan(
        arcs=(
            Arc("profile-before-querying", m0=0.35, lr_self=0.055, lr_help=0.10, weight=1.1, lost_x=0.9, stability_days=200.0),
            Arc("inspect-before-trusting", m0=0.12, lr_self=0.060, lr_help=0.11, weight=1.1, lost_x=1.1),
            Arc("compare-to-last-period", m0=0.15, lr_self=0.045, lr_help=0.085, weight=1.0, lost_x=1.2, cap=0.68, cap_from_w=5, stability_days=22.0),
            Arc("reconcile-to-control", m0=0.05, lr_self=0.012, lr_help=0.03, weight=0.5, lost_x=1.8, cap=0.45),
            Arc("segment-before-concluding", m0=0.06, lr_self=0.080, lr_help=0.15, start_w=1, weight=1.0, lost_x=1.4),
            Arc("trace-the-source", m0=0.20, lr_self=0.060, lr_help=0.11, start_w=4, weight=0.6, lost_x=1.3),
            Arc("join-without-multiplying", m0=0.15, lr_self=0.065, lr_help=0.12, start_w=6, weight=0.7, lost_x=1.4),
            Arc("sanity-check-magnitudes", m0=0.30, lr_self=0.070, lr_help=0.12, end_w=8, weight=0.8, lost_x=1.0, stability_days=200.0),
        ),
        seed=1, base_per_week=20.0,
        hours=((9, 12, 0.50), (13, 17, 0.44), (18, 19, 0.06)),
        dow_weights=(1.3, 1.2, 1.0, 0.9, 0.7, 0.0, 0.0),
        sick_week=2, break_days=(34, 46), quiet_weeks=(7,), busy_weeks=(9,), p_interrupt=0.12,
        routines=(("weekly-metric-refresh", "automation", 5, 1.0), ("reload-and-reprofile", "delegated", 6, 0.8), ("parameterised-weekly-query", "automation", 8, 0.6)),
    ),
}


class SeedError(RuntimeError):
    pass


def _is_demo_dir(dd: Path) -> bool:
    from ..demo import is_demo_data_dir      # lazy: demo imports this package's contract only when it runs

    return is_demo_data_dir(dd)


def _pack_facts(role: str) -> dict[str, Any]:
    """What the role pack says about the skills used: label ids, step per skill, expert median seconds, routines (skill by cog, minutes per run)."""
    from ..packs import load_pack

    pack = load_pack(role)
    cur = pack.file("curriculum")
    skills = {str(s["id"]): s for s in (cur.get("skills", []) if isinstance(cur, dict) else [])}
    steps: dict[str, dict[str, Any]] = {}
    try:
        policy = pack.nested("expert_policy", "steps")
        checks = policy.get("checks", []) if isinstance(policy, dict) else []
        for c in checks:
            if c.get("skill") and str(c["skill"]) not in steps:
                steps[str(c["skill"])] = {"id": str(c["id"]), "median": float(c.get("expert_median_s", 60.0))}
        for sid, sk in skills.items():            # a skill the policy does not name: the check that shares one of its cogs
            if sid not in steps:
                hit = next((c for c in checks if set(c.get("cogs") or []) & set(sk.get("cogs") or [])), None)
                if hit is not None:
                    steps[sid] = {"id": str(hit["id"]), "median": float(hit.get("expert_median_s", 60.0))}
    except Exception:
        pass
    cog_skill: dict[str, str] = {}
    for sid, s in skills.items():
        for cg in s.get("cogs", []) or []:
            cog_skill.setdefault(str(cg), sid)
    try:
        rt = pack.file("routines")
        routines = {str(t["id"]): t for t in (rt.get("templates", []) if isinstance(rt, dict) else [])}
    except Exception:
        routines = {}
    return {"skills": skills, "steps": steps, "cog_skill": cog_skill, "routines": routines}


def _level(share: float) -> int:
    """The help level (1 full help .. 4 gone) from the running share of recent occurrences finished without help: what Cue believes, so a level never contradicts the score."""
    return 1 + (share >= 0.35) + (share >= 0.60) + (share >= 0.80)


def _hour(rng: np.random.Generator, bands: tuple[tuple[int, int, float], ...]) -> int:
    w = np.array([b[2] for b in bands], float)
    lo, hi, _ = bands[int(rng.choice(len(bands), p=w / w.sum()))]
    return int(rng.integers(lo, hi + 1))


def _schedule(plan: Plan, t0: float, t_end: float, rng: np.random.Generator) -> list[float]:
    """The times of the assist occurrences, oldest first: weekdays heavier than weekends, the hours of the role, a sick week, a break, a quiet and a busy week."""
    times: list[float] = []
    for w in range(WEEKS):
        # the seven real days of this week (the history ends at ``t_end``, whatever weekday that is), weighted by their real weekday
        dw = np.array([plan.dow_weights[int(datetime.fromtimestamp(t0 + (w * 7 + d) * DAY + 3600.0, timezone.utc).weekday())] for d in range(7)], float)
        if w == plan.sick_week:
            n = 2
        else:
            mult = 0.5 if w in plan.quiet_weeks else (1.4 if w in plan.busy_weeks else 1.0)
            n = int(rng.poisson(plan.base_per_week * mult * float(rng.uniform(0.85, 1.15))))
        for _ in range(n):
            d = int(rng.choice(7, p=dw / dw.sum()))
            day = w * 7 + d
            if plan.break_days[0] <= day < plan.break_days[1]:
                continue
            t = t0 + day * DAY + _hour(rng, plan.hours) * 3600.0 + float(rng.uniform(0.0, 3599.0))
            if t0 < t <= t_end:
                times.append(t)
    times.sort()
    return times


def _week_of(t: float, t0: float) -> int:
    return min(WEEKS - 1, max(0, int((t - t0) // (7 * DAY))))


def build_rows(role: str, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The rows (assist, then offloaded) and a report. Pure and deterministic for a given ``now``: it writes nothing."""
    plan = PLANS[role]
    facts = _pack_facts(role)
    arcs = [a for a in plan.arcs if a.skill in facts["skills"]]
    missing = [a.skill for a in plan.arcs if a.skill not in facts["skills"]]
    if len(arcs) < 4:
        raise SeedError(f"the {role} pack names too few of the skills this history uses (missing: {', '.join(missing)})")
    rng = np.random.default_rng(plan.seed)
    t_end = float(int(now.timestamp() - LAG_HOURS * 3600.0) // 3600 * 3600)
    t0 = float(int(t_end // DAY) * DAY) - (WEEKS * 7 - 1) * DAY       # midnight UTC of the first of 84 days, the last of which is the day of t_end
    times = _schedule(plan, t0, t_end, rng)
    state: dict[str, float] = {}
    last_t: dict[str, float] = {}
    count: dict[str, int] = {}
    taught_day: dict[tuple[str, int], bool] = {}
    seen: dict[str, float] = {}           # what the system believes: a running share of recent occurrences finished without help, per skill (the help level follows it)
    rows: list[dict[str, Any]] = []
    serial = SERIAL0[role]
    seen_ids: set[str] = set()
    for t in times:
        w = _week_of(t, t0)
        live = [a for a in arcs if a.start_w <= w <= a.end_w]
        if not live:
            continue
        wts = np.array([a.weight for a in live], float)
        a = live[int(rng.choice(len(live), p=wts / wts.sum()))]
        s = a.skill
        info = facts["steps"].get(s)
        step = (info["id"] if info else s.replace("-", "_"))[:48]
        median = float(info["median"]) if info else 60.0
        if s not in state:
            state[s], last_t[s], count[s] = a.m0, t, 0
        else:
            state[s] *= math.exp(-((t - last_t[s]) / DAY) / a.stability_days)          # forgetting between occurrences, a break included
        m = state[s]
        interrupted = rng.random() < plan.p_interrupt
        q = q_of(m)
        if interrupted:
            q = max(0.05, q - 0.18)
        lost = a.lost_x * median * max(0.0, M_EXPERT - m) / M_EXPERT + float(rng.normal(0.0, 0.12 * median))
        if interrupted:
            lost += float(rng.uniform(15.0, 60.0))
        if rng.random() < 0.04:
            lost += float(rng.uniform(100.0, 300.0))
        ew0 = seen.setdefault(s, q_of(a.m0))
        lvl = _level(ew0)
        common: dict[str, Any] = dict(person=PERSON, role=role, skill=s, step=step, t=t, origin="synthetic", origin_detail=ORIGIN_DETAIL, lost_s=lost,
                                      level_before=lvl, serial=serial)
        row_id = L.new_id(PERSON, role, round(t, 3), s, serial)
        if row_id in seen_ids:
            serial += 1
            continue
        seen_ids.add(row_id)
        common["row_id"] = row_id
        serial += 1
        if rng.random() < q:                                                        # managed alone
            false_alarm = rng.random() < 0.05
            retrieval = (not false_alarm) and m >= 0.85 and rng.random() < 0.10      # help withheld on purpose for a mastered skill
            gain = a.lr_self
            nm = m + gain * (1.0 - m)
            row = L.make_row(outcome="clean", trigger="auto" if false_alarm else "none", tier=1 if false_alarm else 0, dismissed=false_alarm,
                             p_stuck=0.7 if false_alarm else None, retrieval=retrieval, **common)
        else:
            shown = rng.random() < 0.90
            accepted = shown and rng.random() < 0.80
            if accepted:
                asked = rng.random() < 0.15
                day = int(t // DAY)
                taught = not taught_day.get((s, day))
                taught_day[(s, day)] = True
                nm = m + a.lr_help * (1.0 - m)
                row = L.make_row(outcome="assisted", trigger="asked" if asked else "auto", tier=int(rng.integers(1, 4)), accepted=True, taught=taught,
                                 options_shown=int(rng.integers(0, 4)), p_stuck=float(rng.uniform(0.6, 0.97)),
                                 seconds_to_progress=float(rng.lognormal(math.log(9.0), 0.35)), **common)
            else:
                u = rng.random()
                if u < 0.45:
                    outcome, gain = "error", a.lr_self * 0.5
                elif u < 0.65:
                    outcome, gain = "abandoned", 0.0
                else:
                    outcome, gain = "clean", a.lr_self                          # ground through alone
                nm = m + gain * (1.0 - m)
                row = L.make_row(outcome=outcome, trigger="auto" if shown else "none", tier=int(rng.integers(1, 3)) if shown else 0, dismissed=shown,
                                 p_stuck=float(rng.uniform(0.6, 0.97)) if shown else None, **common)
        if a.cap is not None and w >= a.cap_from_w:
            nm = min(nm, a.cap)
        state[s], last_t[s] = nm, t
        ew1 = 0.85 * ew0 + 0.15 * (1.0 if (row["outcome"] == "clean" and not row["accepted"]) else 0.0)
        seen[s] = ew1
        row["level_after"] = _level(ew1)
        count[s] = count.get(s, 0) + 1
        rows.append(row)
    n_assist = len(rows)

    # routines that emerge: offloaded work from the second half of the history, for routines the role pack's own templates name
    off: list[dict[str, Any]] = []
    for rid, stream, from_w, per_week in plan.routines:
        tpl = facts["routines"].get(rid)
        if tpl is None:
            continue
        per_run = float((tpl.get("value_defaults") or {}).get("manual_minutes_per_run", 4.0))
        sk = next((facts["cog_skill"][c] for c in (tpl.get("skill_cogs") or tpl.get("cogs") or []) if c in facts["cog_skill"]), None)
        for w in range(from_w, WEEKS):
            for _ in range(int(rng.poisson(per_week))):
                day = w * 7 + int(rng.integers(0, 5))
                if plan.break_days[0] <= day < plan.break_days[1]:
                    continue
                t = t0 + day * DAY + _hour(rng, plan.hours) * 3600.0 + float(rng.uniform(0.0, 3599.0))
                if not (t0 < t <= t_end):
                    continue
                u = float(rng.random())
                done = "done" if u < 0.82 else ("queued" if u < 0.90 else ("yielded" if u < 0.95 else "failed"))
                oid = L.new_id(PERSON, role, round(t, 3), rid, serial)
                off.append(L.make_row(person=PERSON, role=role, skill=sk, t=t, outcome="clean", origin="synthetic", origin_detail=ORIGIN_DETAIL, stream=stream, routine=rid,
                                      minutes=per_run * float(rng.uniform(0.8, 1.6)), offload_outcome=done, row_id=oid, serial=serial))
                serial += 1
    off.sort(key=lambda r: r["t_hour"])
    labels = {a.skill: L_label(role, a.skill) for a in arcs}
    report = {"role": role, "assist": n_assist, "offloaded": len(off), "skills": [a.skill for a in arcs], "skipped_skills": missing,
              "first": rows[0]["t_hour"] if rows else None, "last": rows[-1]["t_hour"] if rows else None, "unlabelled": sorted(s for s, lab in labels.items() if lab == s)}
    return rows + off, report


def L_label(role: str, skill: str) -> str:
    from ..cue.vocab import skill_info

    return skill_info(role, skill)["label"]


def seed(dd: Path, role: str, now: datetime, out: Callable[[str], None] = print) -> dict[str, Any]:
    """Write the role's twelve weeks of ledger rows into ``<dd>/assist/ledger.jsonl``. Idempotent (a marker); demo data directories only. Returns what it did."""
    if role not in PLANS:
        raise SeedError(f"no ledger history is written for {role!r}")
    dd = Path(dd)
    if not _is_demo_dir(dd):
        out(f"ledger ({role}): {dd} is not a demo data dir; not written.")
        return {"seeded": False, "reason": "not_demo_dir"}
    marker = dd / MARKER.format(role=role)
    if marker.exists():
        out(f"ledger ({role}): already seeded; nothing changed.")
        return {"seeded": False, "reason": "already_seeded"}
    rows, rep = build_rows(role, now)
    ledger = L.Ledger(dd / "assist" / "ledger.jsonl")
    n = ledger.extend(rows)
    marker.write_text(now.isoformat() + "\n")
    out(f"ledger ({role}): {rep['assist']} assist occurrences over {WEEKS} weeks on {len(rep['skills'])} skills, {rep['offloaded']} offloaded rows (listed, never scored); "
        f"{n} rows in assist/ledger.jsonl, {rep['first']} to {rep['last']}")
    if rep["unlabelled"]:
        out(f"ledger ({role}): note: the pack has no label for {', '.join(rep['unlabelled'])}")
    return {"seeded": True, "rows": n, **rep}
