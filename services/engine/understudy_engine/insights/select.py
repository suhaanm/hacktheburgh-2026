"""Selection (REQ-9): the reliability gate, family control, guard metrics, score, diversity, caps and order. A pure function.

Same candidates, same history, same parameters and the same ``now`` give the same ``Selection``, byte for byte. There is no clock and no
randomness in this module. docs/INSIGHTS_DESIGN.md section 4 is the specification; the order of steps is:

1. gate each candidate (pre-conditions, n, freshness, floor, persistence, interval, family control, thresholds, feedback, novelty);
2. an improvement whose guard metric got worse becomes a trade-off, never a celebration;
3. score = impact x actionability x novelty x recency;
4. diversity (one per subject and kind; one per subject for a worker; at most 3 per group for an admin);
5. caps, with one reserved slot for a risk or data-feed signal (admin) and at least one positive insight when one passes;
6. order by score, ties by id.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace

from . import stats as S
from . import vocab as V
from .freshness import is_fresh
from .params import DAY, DEFAULT, Params
from .types import (
    History,
    HistoryEntry,
    InsightCandidate,
    Scored,
    Selection,
    Suppressed,
)

KIND = V.KINDS


# ------------------------------------------------------------------------------------------------ resolvers
def resolve_milestone(c: InsightCandidate, z: float, p: Params) -> tuple[bool, float]:
    """At the family-adjusted multiplier ``z``: the level the Wilson lower bound of the last 20 has reached, whether that is above the level the first 20 had
    reached, and whether the Newcombe interval of the gain excludes zero. Returns ``(ok, level_now)``."""
    e = c.extras
    k, n, kp, np_ = e["k"], e["n"], e.get("kp"), e.get("np", 0)
    lo_now = S.wilson_interval(k, n, z)[0]
    now_lvl = max((t for t in p.milestone_levels if lo_now >= t), default=0.0)
    if kp is None or not np_:
        return False, now_lvl
    lo_prev = S.wilson_interval(kp, np_, z)[0]
    prev_lvl = max((t for t in p.milestone_levels if lo_prev >= t), default=0.0)
    nc = S.newcombe(k, n, kp, np_, z)
    ok = now_lvl > prev_lvl and now_lvl > 0.0 and nc is not None and nc[1] > 0.0
    return bool(ok), now_lvl


# ------------------------------------------------------------------------------------------------ gate
def _family(cands: list[InsightCandidate]) -> list[InsightCandidate]:
    """The admissible tests: a family member with no pre-suppression. Effect values play no part in what is admissible."""
    return [c for c in cands if c.family and c.reason_pre is None]


def gate(c: InsightCandidate, *, audience: str, now: float, p: Params, m: int, z_m: float, bh: set[str] | None) -> tuple[str | None, InsightCandidate]:
    """``(reason, candidate)``: a closed suppression reason, or None when the candidate passes. The candidate may come back updated (milestone level)."""
    spec = KIND[c.kind]
    if c.reason_pre:
        return c.reason_pre, c
    if c.n < spec.n_min:
        return "not_enough_data", c
    if c.recency_t is None or not is_fresh(spec.source, now, c.recency_t):
        return "stale", c
    if c.kind == "independence_milestone":
        ok, lvl = resolve_milestone(c, z_m, p)
        c = replace(c, slots={**c.slots, "level": lvl})
        return (None if ok else "below_effect_floor"), c
    if c.family:                                                   # an effect test
        if c.value is None:
            return "not_enough_data", c
        v = c.value * c.sign
        if v <= 0 or (c.floor is not None and v < c.floor):
            return "below_effect_floor", c
        if not c.persist_ok:
            return "not_persistent", c
        if c.lo is None or c.hi is None or not ((c.lo > 0) if c.sign > 0 else (c.hi < 0)):
            return "interval_spans_zero", c
        if c.p is None:
            return "not_significant_after_family_control", c
        if audience == "worker":
            ok = c.p <= p.alpha_worker / max(1, m)
        else:
            ok = bh is not None and c.id in bh
        return (None if ok else "not_significant_after_family_control"), c
    return (None if c.threshold_ok else "below_effect_floor"), c      # a state kind


# ------------------------------------------------------------------------------------------------ score
def material_change(c: InsightCandidate, last: HistoryEntry, p: Params) -> bool:
    lvl = c.slots.get("level")
    lvl_i = None if lvl is None else int(round(float(lvl) * 100))
    if lvl_i is not None and last.level is not None and lvl_i != last.level:
        return True
    if c.value is None or last.value is None:
        return False
    if (c.value >= 0) != (last.value >= 0):
        return True
    if last.value == 0:
        return c.value != 0
    return abs(c.value - last.value) >= p.material_change * abs(last.value)


def novelty(c: InsightCandidate, hist: History, now: float, p: Params) -> tuple[float, int]:
    """``(novelty, repeats)``: halves for each time the same insight was shown in the window, reset by a material change. A risk signal never decays."""
    if KIND[c.kind].reserved:
        return 1.0, 0
    ents = [e for e in hist.shown if e.id == c.id and 0.0 <= now - e.t <= p.novelty_window_days * DAY]
    if not ents:
        return 1.0, 0
    last = max(ents, key=lambda e: (e.t, e.value if e.value is not None else 0.0))
    if material_change(c, last, p):
        return 1.0, 0
    return 0.5 ** len(ents), len(ents)


def impact_norm(raw: float, audience: str, p: Params) -> float:
    scale = p.impact_scale_worker if audience == "worker" else p.impact_scale_admin
    return float(1.0 - math.exp(-max(0.0, raw) / scale))


def recency_factor(c: InsightCandidate, now: float, p: Params) -> float:
    if c.recency_t is None:
        return 1.0
    age_days = max(0.0, (now - c.recency_t) / DAY)
    return float(math.exp(-age_days / p.recency_tau_days))


def convert_tradeoff(c: InsightCandidate) -> InsightCandidate:
    """An improvement with a worse guard metric is shown as a trade-off, with the same id so the insight stays the same insight."""
    spec = V.KINDS[c.kind]
    if spec.improvement and any(g.worse for g in c.guards) and c.kind not in ("trade_off",):
        new_kind = "trade_off" if c.audience == "worker" else c.kind
        return replace(c, kind=new_kind, polarity="tradeoff", action_id=c.action_id or "open_growth" if c.audience == "worker" else c.action_id,
                       slots={**c.slots, "tradeoff": True})
    return c


# ------------------------------------------------------------------------------------------------ the selection
def select(cands: list[InsightCandidate], *, audience: str, scope: str, now: float, history: History | None = None, params: Params = DEFAULT,
           cap: int | None = None) -> Selection:
    p = params
    hist = history or History()
    cap = (p.worker_cap if audience == "worker" else p.admin_cap) if cap is None else cap
    fam = _family(cands)
    m = len(fam) if p.family_control else 1
    z_m = S.bonferroni_z(p.alpha_worker, m) if audience == "worker" else S.Z95
    if audience == "admin":
        bh = S.bh_pass([(c.id, c.p) for c in fam if c.p is not None], p.q_admin) if p.family_control else {c.id for c in fam if c.p is not None and c.p <= 0.05}
    else:
        bh = None
    sel = Selection(audience=audience, scope=scope)
    sel.family = ({"method": "bonferroni", "alpha": p.alpha_worker, "m": m, "per_test_alpha": p.alpha_worker / max(1, m)} if audience == "worker"
                  else {"method": "benjamini_hochberg", "q": p.q_admin, "m": m, "n_pass": len(bh or ())})
    passed: list[Scored] = []
    for c0 in cands:
        sel.all_candidates[c0.id] = c0
        reason, c = gate(c0, audience=audience, now=now, p=p, m=m, z_m=z_m, bh=bh)
        if reason is None:
            if c.kind in hist.hidden_kinds or c0.kind in hist.hidden_kinds or c.id in hist.quiet_ids and now - hist.quiet_ids[c.id] <= p.novelty_window_days * DAY:
                reason = "hidden_by_feedback"
        if reason is not None:
            sel.suppressed.append(Suppressed(c.id, c.kind, c.subject, reason))
            continue
        c = convert_tradeoff(c)
        nov, reps = novelty(c, hist, now, p)
        if nov <= p.novelty_floor:
            sel.suppressed.append(Suppressed(c.id, c.kind, c.subject, "repeat_recently"))
            continue
        imp = impact_norm(c.impact_raw, audience, p)
        act = 1.0 if c.action_id else p.actionability_none
        rec = recency_factor(c, now, p)
        score = round(imp * act * nov * rec, 9)
        sel.all_candidates[c.id] = c
        passed.append(Scored(c, score, {"impact": round(imp, 6), "actionability": act, "novelty": nov, "recency": round(rec, 6), "repeats": float(reps)}, 0, ""))
    passed.sort(key=lambda s: (-s.score, s.cand.id))
    kept: list[Scored] = []
    seen_sk: set[tuple[str, str]] = set()
    seen_subject: set[tuple[str, bool]] = set()          # a worker may hear one thing about a skill that is going well and one that is not, never two of the same sort
    per_group: Counter[str] = Counter()
    for s in passed:
        c = s.cand
        if (c.subject, c.kind) in seen_sk:
            sel.suppressed.append(Suppressed(c.id, c.kind, c.subject, "same_kind_lower_score"))
        elif audience == "worker" and (c.subject, c.polarity == "positive") in seen_subject:
            sel.suppressed.append(Suppressed(c.id, c.kind, c.subject, "same_subject_lower_score"))
        elif audience == "admin" and per_group[c.group] >= p.admin_max_per_group:
            sel.suppressed.append(Suppressed(c.id, c.kind, c.subject, "over_cap"))
        else:
            kept.append(s)
            seen_sk.add((c.subject, c.kind))
            seen_subject.add((c.subject, c.polarity == "positive"))
            per_group[c.group] += 1
    top = kept[:cap]
    rest = kept[cap:]
    why: dict[str, str] = {}
    # one reserved slot for a risk or data-feed signal (admin)
    if audience == "admin" and cap >= 1 and not any(KIND[s.cand.kind].reserved for s in top):
        res = next((s for s in rest if KIND[s.cand.kind].reserved), None)
        if res is not None:
            drop = min((s for s in top), key=lambda s: (s.score, s.cand.id), default=None)
            if drop is not None:
                top.remove(drop)
                rest.append(drop)
            top.append(res)
            rest.remove(res)
            why[res.cand.id] = "selected_reserved_risk"
    # at least one positive insight when any passes
    if top and not any(s.cand.polarity == "positive" for s in top):
        pos = next((s for s in sorted(rest, key=lambda s: (-s.score, s.cand.id)) if s.cand.polarity == "positive"), None)
        if pos is not None:
            cands_drop = [s for s in top if not KIND[s.cand.kind].reserved]
            if cands_drop:
                drop = min(cands_drop, key=lambda s: (s.score, s.cand.id))
                top.remove(drop)
                rest.append(drop)
                top.append(pos)
                rest.remove(pos)
                why[pos.cand.id] = "selected_positive_slot"
    top.sort(key=lambda s: (-s.score, s.cand.id))
    for i, s in enumerate(top, start=1):
        r = why.get(s.cand.id) or ("selected_trade_off" if s.cand.polarity == "tradeoff" else "selected_top_score")
        sel.selected.append(Scored(s.cand, s.score, s.parts, i, r))
    for s in rest:
        sel.suppressed.append(Suppressed(s.cand.id, s.cand.kind, s.cand.subject, "over_cap"))
    sel.suppressed.sort(key=lambda x: (x.reason, x.id))
    return sel


def history_entry(c: InsightCandidate, now: float) -> HistoryEntry:
    lvl = c.slots.get("level")
    return HistoryEntry(c.id, now, c.value, None if lvl is None else int(round(float(lvl) * 100)))
