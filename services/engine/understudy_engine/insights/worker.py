"""Worker insight candidates (REQ-9): pure functions of one person's assist-ledger rows and a clock.

Each generator returns zero or more ``InsightCandidate``. A generator never decides what is shown: it computes the effect, its interval and
p-value, n, the guard metrics and the pre-conditions; ``select`` applies the reliability gate, the family control, the score and the caps.
A candidate that cannot be tested yet carries a closed ``reason_pre`` so ``why`` can say so.

Rules every generator follows (docs/INSIGHTS_DESIGN.md section 3):
* assist rows only (``rows.assist_only``): delegated and automation rows never reach an independence number;
* rows of the current role at or after the role change only (baselines reset);
* 3-week windows, ``lost_s`` clipped, the sign must hold in 2 of the last 3 weeks that have data (regression to the mean);
* the first occurrences of each skill after an absence are excluded from relapse and time evidence (``rows.grace_flags``).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import stats as S
from . import vocab as V
from .freshness import MAX_AGE_S
from .params import DAY, DEFAULT, Params
from .rows import (
    current_role_rows,
    grace_flags,
    is_independent,
    lost_values,
    origin_of,
    row_t,
    weekly_buckets,
)
from .types import Guard, InsightCandidate, PersonRecord, insight_id

KIND = V.KINDS


@dataclass
class WorkerCtx:
    """Optional inputs from other layers; all absent by default (the layers are off or not present)."""
    routines: Sequence[dict[str, Any]] = ()          # this person's routine records (finder value, shadow statistics)
    pointers: Sequence[dict[str, Any]] = ()          # calendar and git layers' flagged suggestions
    hitlist: Sequence[dict[str, Any]] = ()           # the repeat list's top rows (already normalised)
    badge: str = "made-up firm"


@dataclass
class WorkerOutcome:
    status: str = "ok"                                # ok | onboarding | stale | no_data | role_changed
    candidates: list[InsightCandidate] = field(default_factory=list)
    stale_sources: list[str] = field(default_factory=list)
    seen: int = 0
    needed: int = 0
    last_t: float | None = None


def _round5(x: float) -> int:
    return max(5, int(round(abs(x) / 5.0)) * 5)


def _cid(person: str, kind: str, subject: str) -> str:
    return insight_id("worker", person, kind, subject)


def _by_skill(rows: Sequence[dict[str, Any]]) -> dict[str, list[int]]:
    d: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r.get("skill"):
            d[r["skill"]].append(i)
    return d


def _base(person: PersonRecord, kind: str, subject: str, *, ctx: WorkerCtx, rows: Sequence[dict[str, Any]], **kw) -> InsightCandidate:
    spec = KIND[kind]
    return InsightCandidate(
        id=kw.pop("cid", None) or _cid(person.id, kind, subject), kind=kind, audience="worker", subject=subject, group=person.id,
        polarity=kw.pop("polarity", spec.polarity), origin=origin_of(rows) if rows else person.origin, badge=ctx.badge,
        action_id=kw.pop("action_id", spec.action_id), person=person.id, **kw)


def share_guard(name: str, kb: int, nb: int, ka: int, na: int, p: Params) -> Guard:
    """A quality share (errors, unfinished cases) is WORSE when it rose by at least ``guard_share_tol``, by at least two cases, and credibly: the one-sided
    two-proportion p of the rise is at most ``guard_p``. A rise inside the noise neither turns a celebration into a trade-off nor hides one."""
    rb, ra = kb / nb, ka / na
    nc = S.newcombe(ka, na, kb, nb)
    worse = bool(nc is not None and ra - rb >= p.guard_share_tol and ka >= 2 and (nc[3] / 2.0) <= p.guard_p)
    return Guard(name, round(rb, 4), round(ra, 4), nb, na, worse)


def _guards(rows_before: Sequence[dict[str, Any]], rows_after: Sequence[dict[str, Any]], p: Params) -> tuple[Guard, ...]:
    out: list[Guard] = []
    for name, pred in (("error_share", lambda r: r["outcome"] == "error"), ("abandoned_share", lambda r: r["outcome"] == "abandoned")):
        nb, na = len(rows_before), len(rows_after)
        if nb == 0 or na == 0:
            continue
        kb, ka = sum(1 for r in rows_before if pred(r)), sum(1 for r in rows_after if pred(r))
        out.append(share_guard(name, kb, nb, ka, na, p))
    tb = sorted(r["seconds_to_progress"] for r in rows_before if r.get("seconds_to_progress") is not None)
    ta = sorted(r["seconds_to_progress"] for r in rows_after if r.get("seconds_to_progress") is not None)
    if len(tb) >= 4 and len(ta) >= 4:
        mb, ma = tb[len(tb) // 2], ta[len(ta) // 2]
        out.append(Guard("time_to_progress", round(float(mb), 1), round(float(ma), 1), len(tb), len(ta),
                         bool(ma > mb * p.guard_ttp_ratio and ma - mb >= p.guard_ttp_abs_s)))
    return tuple(out)


def _persist(vals_by_bucket: Sequence[Sequence[float]], pred, median: bool = False) -> tuple[bool, int, int]:
    """(ok, weeks_with_data, weeks_holding): the effect (at least half its floor) must hold in at least 2 of the last 3 weeks, and at least 2 weeks must have data."""
    have = [v for v in vals_by_bucket if len(v) >= 2]
    holding = sum(1 for v in have if pred(float(np.median(v)) if median else sum(v) / len(v)))
    return (len(have) >= 2 and holding >= 2), len(have), holding


# ------------------------------------------------------------------------------------------------ time loss and improvement
def time_loss_habit(person: PersonRecord, rows: Sequence[dict[str, Any]], grace: Sequence[bool], now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    fam = f"w:{person.id}"
    for skill, idx in sorted(_by_skill(rows).items()):
        rec = [rows[i] for i in idx if now - p.recent_days * DAY < row_t(rows[i]) <= now]
        if not rec:
            continue
        ev = [rows[i] for i in idx if now - p.recent_days * DAY < row_t(rows[i]) <= now and not grace[i]]
        n_grace = len(rec) - len(ev)
        vals = lost_values(ev, p.lost_clip)
        pre = None
        est = S.median_est(vals) if len(vals) >= 2 else None
        if len(ev) >= p.min_n_loss and len(vals) < 0.5 * len(ev):
            pre = "no_expert_reference"
        elif len(vals) < p.min_n_loss:
            pre = "short_absence" if n_grace > 0 else "not_enough_data"
        buckets = [lost_values([r for r in ev if a < row_t(r) <= b], p.lost_clip) for a, b in weekly_buckets(now)]
        ok, wk, _ = _persist(buckets, lambda m: m >= p.floor_loss_s / 2.0, median=True)
        if pre is None and wk < 2:
            pre = "not_enough_data"
        mean = est.value if est else None
        out.append(_base(person, "time_loss_habit", skill, ctx=ctx, rows=rec,
                         value=None if mean is None else round(mean, 2), unit="seconds", lo=None if est is None else round(est.lo, 2),
                         hi=None if est is None else round(est.hi, 2), p=None if est is None else est.p, n=len(vals), split={"window": "last_3_weeks"},
                         evidence_ref=f"ledger:{person.id}/{skill}/lost_s", recency_t=max(row_t(r) for r in rec), family=fam, floor=p.floor_loss_s,
                         sign=1, persist_ok=ok, reason_pre=pre,
                         impact_raw=0.0 if mean is None else max(0.0, mean) * (len(vals) / 3.0) / 60.0,
                         slots={"skill": skill, "seconds": _round5(mean or 0.0)}))
    return out


def habit_improved(person: PersonRecord, rows: Sequence[dict[str, Any]], grace: Sequence[bool], now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    fam = f"w:{person.id}"
    e0, e1 = now - p.earlier_start_days * DAY, now - p.earlier_end_days * DAY
    for skill, idx in sorted(_by_skill(rows).items()):
        rec_rows = [rows[i] for i in idx if now - p.recent_days * DAY < row_t(rows[i]) <= now and not grace[i]]
        old_rows = [rows[i] for i in idx if e0 < row_t(rows[i]) <= e1 and not grace[i]]
        if not rec_rows or not old_rows:
            continue
        vr, vo = lost_values(rec_rows, p.lost_clip), lost_values(old_rows, p.lost_clip)
        pre = None
        if (len(rec_rows) >= p.min_n_improved and len(vr) < 0.5 * len(rec_rows)) or (len(old_rows) >= p.min_n_improved and len(vo) < 0.5 * len(old_rows)):
            pre = "no_expert_reference"
        elif len(vr) < p.min_n_improved or len(vo) < p.min_n_improved:
            pre = "not_enough_data"
        est = S.median_diff(vo, vr, p.n_boot, S.seed_from('improved', person.id, skill, len(vo), len(vr))) if len(vr) >= 2 and len(vo) >= 2 else None        # earlier minus recent: positive = faster now
        buckets = [lost_values([r for r in rec_rows if a < row_t(r) <= b], p.lost_clip) for a, b in weekly_buckets(now)]
        mo = float(np.median(vo)) if vo else 0.0
        ok, wk, _ = _persist(buckets, lambda m, mo=mo: m <= mo - p.floor_improved_s / 2.0, median=True)
        if pre is None and wk < 2:
            pre = "not_enough_data"
        guards = _guards(old_rows, rec_rows, p)
        worse = [g for g in guards if g.worse]
        slots: dict[str, Any] = {"skill": skill, "seconds": _round5(est.value if est else 0.0)}
        if worse:
            g = worse[0]
            slots.update({"guard": g.name, "before": g.before, "after": g.after, "k_before": round(g.before * g.n_before), "n_before": g.n_before,
                          "k_after": round(g.after * g.n_after), "n_after": g.n_after})
        out.append(_base(person, "habit_improved", skill, ctx=ctx, rows=rec_rows,
                         value=None if est is None else round(est.value, 2), unit="seconds", lo=None if est is None else round(est.lo, 2),
                         hi=None if est is None else round(est.hi, 2), p=None if est is None else est.p, n=min(len(vr), len(vo)),
                         split={"window": "last_3_weeks_vs_weeks_4_to_6_ago", "n_recent": len(vr), "n_earlier": len(vo)},
                         evidence_ref=f"ledger:{person.id}/{skill}/lost_s", recency_t=max(row_t(r) for r in rec_rows), family=fam,
                         floor=p.floor_improved_s, sign=1, persist_ok=ok, reason_pre=pre, guards=guards,
                         impact_raw=0.0 if est is None else max(0.0, est.value) * (len(vr) / 3.0) / 60.0, slots=slots))
    return out


# ------------------------------------------------------------------------------------------------ independence-based states
def independence_milestone(person: PersonRecord, rows: Sequence[dict[str, Any]], now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    """Needing less help: the share finished without help over the last 20 occurrences of a skill against the person's FIRST 20 on it. It needs 40 occurrences (two
    blocks that can be compared fairly) and a point gain of at least ``milestone_gain_floor``. The gate then asks, at the family-adjusted multiplier, that the
    Newcombe interval of the gain excludes zero and that the Wilson lower bound of the last 20 has newly reached a level (0.5, 0.65 or 0.8)
    (``select.resolve_milestone``). Stable independence (an expert, or no change) is never a milestone."""
    out: list[InsightCandidate] = []
    fam = f"w:{person.id}"
    W = p.milestone_window
    for skill, idx in sorted(_by_skill(rows).items()):
        occ = [rows[i] for i in idx]
        if len(occ) < 2 * W:
            continue
        w, ref = occ[-W:], occ[:W]
        k = sum(1 for r in w if is_independent(r))
        kp = sum(1 for r in ref if is_independent(r))
        if (k - kp) / W < p.milestone_gain_floor:
            continue
        last_t = row_t(w[-1])
        out.append(_base(person, "independence_milestone", skill, ctx=ctx, rows=w, value=round(k / W, 4), unit="share", n=W,
                         split={"window": f"last_{W}_occurrences", "reference": f"first_{W}_occurrences"}, evidence_ref=f"ledger:{person.id}/{skill}/outcome", recency_t=last_t,
                         family=fam, impact_raw=max(0.0, (k - kp) / W) * (W / 3.0) * p.assist_cost_s / 60.0,
                         slots={"skill": skill, "k": k, "n": W}, extras={"k": k, "n": W, "kp": kp, "np": W}))
    return out


def retention_due(person: PersonRecord, rows: Sequence[dict[str, Any]], now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    """A mastered skill that has not come up for a while is due for practice. Time-aware: this is what a break produces, never a relapse.
    The evidence is fresh when the person's ledger as a whole is (their newest row of any skill), which ``worker_run`` has already checked."""
    out: list[InsightCandidate] = []
    newest = max((row_t(r) for r in rows), default=now)
    for skill, idx in sorted(_by_skill(rows).items()):
        occ = [rows[i] for i in idx]
        if len(occ) < p.retention_min_n:
            continue
        days = (now - row_t(occ[-1])) / DAY
        if not (p.retention_min_days <= days <= p.retention_max_days):
            continue
        last10 = occ[-10:]
        share = sum(1 for r in last10 if is_independent(r)) / len(last10)
        if share < p.retention_mastered:
            continue
        span_w = max(1.0, (row_t(occ[-1]) - row_t(occ[0])) / (7 * DAY))
        out.append(_base(person, "retention_due", skill, ctx=ctx, rows=last10, value=round(days, 1), unit="days", n=len(occ),
                         split={"independence_last_10": round(share, 3)}, evidence_ref=f"ledger:{person.id}/{skill}/t",
                         recency_t=newest, impact_raw=min(3.0, days / 14.0) * (len(occ) / span_w) * p.assist_cost_s * 0.25 / 60.0,
                         slots={"skill": skill, "days": int(round(days))}))
    return out


def relapse(person: PersonRecord, rows: Sequence[dict[str, Any]], grace: Sequence[bool], now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    """A skill that was independent over 15 occurrences needs help clearly more often over the last up to 10 (after the absence grace)."""
    out: list[InsightCandidate] = []
    fam = f"w:{person.id}"
    for skill, idx in sorted(_by_skill(rows).items()):
        ng = [rows[i] for i in idx if not grace[i]]
        n_grace_recent = sum(1 for i in idx if grace[i] and now - row_t(rows[i]) <= 28 * DAY)
        last = ng[-p.relapse_recent_max:]
        base = ng[:-p.relapse_recent_max][-p.relapse_baseline_n:]
        if len(base) < p.relapse_baseline_n:
            continue
        kb = sum(1 for r in base if is_independent(r))
        if kb / len(base) < p.relapse_baseline_share:
            continue
        recent = [r for r in last if now - row_t(r) <= 28 * DAY]
        if not recent and n_grace_recent == 0:
            continue
        kr = sum(1 for r in recent if is_independent(r))
        pre = None
        if len(recent) < p.relapse_recent_min:
            pre = "short_absence" if n_grace_recent > 0 else "not_enough_data"
        nc = S.newcombe(kb, len(base), kr, len(recent)) if recent else None
        d, lo, hi, pv = (nc if nc else (None, None, None, None))
        out.append(_base(person, "relapse", skill, ctx=ctx, rows=recent or base[-3:], value=None if d is None else round(d, 4), unit="share",
                         lo=None if lo is None else round(lo, 4), hi=None if hi is None else round(hi, 4), p=pv, n=len(recent),
                         split={"baseline_n": len(base), "recent_n": len(recent)}, evidence_ref=f"ledger:{person.id}/{skill}/outcome",
                         recency_t=max((row_t(r) for r in recent), default=None), family=fam, floor=p.relapse_drop_floor, sign=1, reason_pre=pre,
                         impact_raw=0.0 if d is None else max(0.0, d) * (len(recent) / 3.0) * p.assist_cost_s / 60.0,
                         slots={"skill": skill}))
    return out


# ------------------------------------------------------------------------------------------------ routines, calendar, git, hit list
def automation_opportunity(person: PersonRecord, now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    for r in ctx.routines:
        if r.get("status") != "proposed":
            continue
        t = r.get("t")
        lo = r.get("hours_lo")
        pre = None
        if int(r.get("support", 0)) < p.automation_min_support:
            pre = "not_enough_data"
        elif lo is None or lo < p.automation_hours_floor:
            pre = "below_effect_floor"
        hz = max(1.0, float(r.get("horizon_weeks", 4)))
        out.append(InsightCandidate(
            id=_cid(person.id, "automation_opportunity", str(r["id"])), kind="automation_opportunity", audience="worker", subject=str(r["id"]), group=person.id,
            polarity="note", value=None if lo is None else round(float(lo), 2), unit="hours", lo=None if lo is None else float(lo), hi=r.get("hours_hi"),
            n=int(r.get("support", 0)), n_unit="repeats", origin=person.origin, badge=ctx.badge, evidence_ref=f"routines:{person.id}/{r['id']}",
            recency_t=t, action_id="open_routines", impact_raw=0.0 if lo is None else float(lo) * 60.0 / hz, reason_pre=pre, person=person.id,
            slots={"count": int(r.get("support", 0)), "what": "the same steps"}))
    for h in ctx.hitlist:
        pre = None
        if h.get("t") is None or now - h["t"] > MAX_AGE_S["hitlist"]:
            pre = "stale"
        elif int(h.get("count", 0)) < p.automation_min_support:
            pre = "not_enough_data"
        elif h.get("hours_lo") is not None and h["hours_lo"] < p.automation_hours_floor:
            pre = "below_effect_floor"
        hz = max(1.0, float(h.get("horizon_weeks", 4)))
        hl = h.get("hours_lo")
        out.append(InsightCandidate(
            id=_cid(person.id, "automation_opportunity", str(h["id"])), kind="automation_opportunity", audience="worker", subject=str(h["id"]), group=person.id,
            polarity="note", value=None if hl is None else round(float(hl), 2), unit="hours", lo=None if hl is None else float(hl), hi=h.get("hours_hi"),
            n=int(h.get("count", 0)), n_unit="repeats", origin=h.get("origin", person.origin), badge=ctx.badge, evidence_ref=f"hitlist:{person.id}/{h['id']}",
            recency_t=h.get("t"), action_id="open_repeats", impact_raw=(float(hl) * 60.0 / hz) if hl is not None else float(h.get("count", 0)) * 0.5, reason_pre=pre,
            person=person.id, slots={"count": int(h.get("count", 0)), "what": h.get("what", "the same step"), "days": int(h.get("window_days", 14))}))
    return out


def layer_pointers(person: PersonRecord, now: float, p: Params, ctx: WorkerCtx) -> list[InsightCandidate]:
    """The calendar and git layers' own flagged suggestions, as pointers; only when those layers supplied them (they are off by default)."""
    out: list[InsightCandidate] = []
    for q in ctx.pointers:
        src = q.get("source")
        kind = {"calendar": "calendar_pointer", "git": "git_pointer"}.get(src)
        if kind is None:
            continue
        ci = q.get("ci") or [None, None]
        delta = q.get("delta")
        sign = -1 if q.get("direction") == "lower_worse" else 1
        pv = None
        if delta is not None and ci[0] is not None and ci[1] is not None and ci[1] > ci[0]:
            se = (ci[1] - ci[0]) / (2 * S.Z95)
            pv = S.norm_two_sided_p(delta / max(se, 1e-12))
        pre = None if int(q.get("n", 0)) >= KIND[kind].n_min else "not_enough_data"
        out.append(InsightCandidate(
            id=_cid(person.id, kind, str(q["id"])), kind=kind, audience="worker", subject=str(q["id"]), group=person.id, polarity="note",
            value=delta, unit=str(q.get("unit", "count")), lo=ci[0], hi=ci[1], p=pv, n=int(q.get("n", 0)), n_unit=str(q.get("n_unit", "weeks")),
            origin=q.get("origin", person.origin), badge=ctx.badge, evidence_ref=f"{src}:{person.id}/{q['id']}", recency_t=q.get("t"),
            action_id=KIND[kind].action_id, family=f"w:{person.id}", floor=float(q.get("floor", 0.0)), sign=sign, reason_pre=pre, person=person.id,
            impact_raw=float(q.get("impact_min_per_week", 1.0)), slots={"what": str(q["id"])}))
    return out


# ------------------------------------------------------------------------------------------------ the driver
def worker_run(person: PersonRecord, now: float, p: Params = DEFAULT, ctx: WorkerCtx | None = None) -> WorkerOutcome:
    """All candidates for one worker at ``now``, plus the person's status (new, stale, role changed). Pure."""
    ctx = ctx or WorkerCtx()
    rows = current_role_rows(person)
    n = len(rows)
    out = WorkerOutcome(seen=n, needed=p.onboard_min)
    if n == 0:
        out.status = "no_data"
        return out
    last_t = max(row_t(r) for r in rows)
    out.last_t = last_t
    changed = person.role_since_t is not None and 0.0 <= now - person.role_since_t <= 28 * DAY
    if now - last_t > p.stale_days * DAY:
        out.status = "stale"
        out.stale_sources = ["ledger"]
        out.candidates.append(InsightCandidate(
            id=_cid(person.id, "stale_data", "ledger"), kind="stale_data", audience="worker", subject="ledger", group=person.id, polarity="note",
            value=round((now - last_t) / DAY, 1), unit="days", n=n, origin=origin_of(rows), badge=ctx.badge, evidence_ref=f"ledger:{person.id}/t",
            recency_t=now, impact_raw=30.0, person=person.id, slots={"days": int((now - last_t) / DAY)}))
        return out
    if n < p.onboard_min:
        out.status = "role_changed" if changed else "onboarding"
        out.candidates.append(InsightCandidate(
            id=_cid(person.id, "onboarding", "role_changed" if changed else "start"), kind="onboarding", audience="worker",
            subject="role_changed" if changed else "start", group=person.id, polarity="note", value=float(n), unit="occurrences", n=n,
            origin=origin_of(rows), badge=ctx.badge, evidence_ref=f"ledger:{person.id}/count", recency_t=now, impact_raw=30.0, person=person.id,
            slots={"seen": n, "needed": p.onboard_min, "reason": "role_changed" if changed else "new"}))
        return out
    grace = grace_flags(rows, p)
    cands: list[InsightCandidate] = []
    cands += time_loss_habit(person, rows, grace, now, p, ctx)
    cands += habit_improved(person, rows, grace, now, p, ctx)
    cands += independence_milestone(person, rows, now, p, ctx)
    cands += retention_due(person, rows, now, p, ctx)
    cands += relapse(person, rows, grace, now, p, ctx)
    cands += automation_opportunity(person, now, p, ctx)
    cands += layer_pointers(person, now, p, ctx)
    if changed:
        cands.append(InsightCandidate(
            id=_cid(person.id, "onboarding", "role_changed"), kind="onboarding", audience="worker", subject="role_changed", group=person.id, polarity="note",
            value=float(n), unit="occurrences", n=n, origin=origin_of(rows), badge=ctx.badge, evidence_ref=f"ledger:{person.id}/count", recency_t=now,
            impact_raw=4.0, person=person.id, slots={"seen": n, "needed": p.onboard_min, "reason": "role_changed"}))
    out.candidates = cands
    return out
