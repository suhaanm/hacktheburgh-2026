"""Admin insight candidates (REQ-9): pure functions of an ``AdminView``. The audience is Admin; the subject of an insight is a role, a unit, a skill
within a role, a signal or the firm, never a person. For coaching and onboarding, not for evaluating individuals.

Comparisons are always (a) within skill, and (b) standardised: a role-level gap uses the experts' skill mix as fixed weights, a trend is a
within-person panel change with the first window's mix as fixed weights, and a unit is compared with the rest of its role on the role's mix.
A raw pooled rate is never compared across groups or over time (Simpson's paradox); the drill-down shows the raw figure beside the
standardised one. Groups come only from ``AdminView.cohort``, which refuses fewer than 5 people.
"""
from __future__ import annotations

import math
import warnings
from collections import defaultdict
from typing import Any

import numpy as np

from . import stats as S
from . import vocab as V
from .params import DAY, Params
from .rows import is_independent, row_t
from .summary import AdminView, PersonSummary, est, skill_label
from .types import Guard, InsightCandidate, insight_id
from .worker import share_guard

FAM = "admin:firm"


def _cid(kind: str, subject: str) -> str:
    return insight_id("admin", "firm", kind, subject)


def _newest(people: list[PersonSummary]) -> float | None:
    ts = [s.last_t for s in people if s.last_t is not None]
    return max(ts) if ts else None


def _origin(people: list[PersonSummary]) -> str:
    o = {s.origin for s in people}
    return "mixed" if len(o) > 1 else (next(iter(o)) if o else "synthetic")


def _cand(view: AdminView, kind: str, subject: str, group: str, **kw: Any) -> InsightCandidate:
    spec = V.KINDS[kind]
    return InsightCandidate(id=kw.pop("cid", None) or _cid(kind, subject), kind=kind, audience="admin", subject=subject, group=group,
                            polarity=kw.pop("polarity", spec.polarity), origin=kw.pop("origin", view.snap.origin), badge=view.snap.badge,
                            action_id=kw.pop("action_id", spec.action_id), **kw)


def _occ_per_week(people: list[PersonSummary], p: Params) -> float:
    if not people:
        return 0.0
    return float(np.mean([s.n_window for s in people])) / (p.admin_window_days / 7.0)


# ------------------------------------------------------------------------------------------------ role gap: experts versus juniors
def role_gap_detail(view: AdminView, role: str) -> dict[str, Any]:
    """The expert-junior comparison for a role, within skill and standardised to the experts' skill mix, or ``{"reason": ...}``."""
    key = ("role_gap", role)
    if key in view._cache:
        return view._cache[key]
    p = view.p
    out: dict[str, Any] = {"role": role}
    experts, juniors = view.cohort(role=role, level="expert"), view.cohort(role=role, level="junior")
    n_exp_all = len(view.people(role=role, level="expert"))
    if experts is None:
        out["reason"] = "no_expert_reference"
        out.update(n_expert=n_exp_all, n_junior=len(view.people(role=role, level="junior")))
        view._cache[key] = out
        return out
    if juniors is None:
        out["reason"] = "group_too_small"
        out.update(n_expert=len(experts), n_junior=len(view.people(role=role, level="junior")))
        view._cache[key] = out
        return out
    pe = {s.id: view.person_skill(s) for s in experts}
    pj = {s.id: view.person_skill(s) for s in juniors}
    skills = sorted({sk for d in list(pe.values()) + list(pj.values()) for sk in d})
    cols: list[str] = []
    for sk in skills:
        ne = sum(1 for d in pe.values() if sk in d and d[sk]["n"] >= p.min_n_skill_person and not math.isnan(d[sk]["lost"]))
        nj = sum(1 for d in pj.values() if sk in d and d[sk]["n"] >= p.min_n_skill_person and not math.isnan(d[sk]["lost"]))
        if ne >= p.k_anon and nj >= p.k_anon:
            cols.append(sk)
    out.update(n_expert=len(experts), n_junior=len(juniors))
    if not cols:
        out["reason"] = "group_too_small"
        view._cache[key] = out
        return out

    def mat(d: dict[str, dict[str, dict[str, float]]], ids: list[str], field: str) -> np.ndarray:
        m = np.full((len(ids), len(cols)), np.nan)
        for i, pid in enumerate(ids):
            for j, sk in enumerate(cols):
                v = d[pid].get(sk)
                if v and v["n"] >= p.min_n_skill_person and not math.isnan(v[field]):
                    m[i, j] = v[field]
        return m

    ide, idj = sorted(pe), sorted(pj)
    Le, Lj = mat(pe, ide, "lost"), mat(pj, idj, "lost")
    Ae, Aj = mat(pe, ide, "assisted"), mat(pj, idj, "assisted")
    occ_e = np.array([sum(pe[pid][sk]["n"] for pid in ide if sk in pe[pid]) for sk in cols], float)
    w = occ_e / occ_e.sum()
    habits = []
    for j, sk in enumerate(cols):
        ge = S.welch(Lj[~np.isnan(Lj[:, j]), j], Le[~np.isnan(Le[:, j]), j])
        ar_e = S.one_sample(Ae[~np.isnan(Ae[:, j]), j])
        ar_j = S.one_sample(Aj[~np.isnan(Aj[:, j]), j])
        habits.append({"skill": sk, "label": skill_label(role, sk), "gap": ge, "weight": float(w[j]), "assisted_expert": ar_e, "assisted_junior": ar_j,
                       "n_expert": int((~np.isnan(Le[:, j])).sum()), "n_junior": int((~np.isnan(Lj[:, j])).sum()),
                       "n_expert_occ": int(occ_e[j]), "n_junior_occ": int(sum(pj[pid][sk]["n"] for pid in idj if sk in pj[pid]))})
    point = float(sum(h["weight"] * h["gap"].value for h in habits if h["gap"] is not None))
    seed = S.seed_from("role_gap", role, len(ide), len(idj))
    rng = np.random.default_rng(seed)
    B = p.n_boot

    def draw(M: np.ndarray, B: int) -> np.ndarray:
        idx = rng.integers(0, M.shape[0], size=(B, M.shape[0]))
        v = np.where(np.isnan(M), 0.0, M)
        c = (~np.isnan(M)).astype(float)
        num, den = v[idx].sum(axis=1), c[idx].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / den, np.nan)

    de, dj = draw(Le, B), draw(Lj, B)
    gaps = ((dj - de) * w).sum(axis=1)
    gaps = gaps[np.isfinite(gaps)]
    se = float(gaps.std(ddof=1)) if gaps.size > 2 else float("nan")
    lo, hi = (float(np.quantile(gaps, 0.025)), float(np.quantile(gaps, 0.975))) if gaps.size > 20 else (float("nan"), float("nan"))
    pv = S.norm_two_sided_p(point / max(se, 1e-9)) if not math.isnan(se) else 1.0
    for h in habits:
        g = h["gap"]
        h["explains"] = None if g is None else {"value": h["weight"] * g.value, "lo": h["weight"] * g.lo, "hi": h["weight"] * g.hi}
        h["share"] = (h["weight"] * g.value / point) if (g is not None and point > 0) else None
    # per-person standardised time against the expert reference, for the measure row
    def person_std(M: np.ndarray) -> list[float]:
        vals = []
        for i in range(M.shape[0]):
            ok = ~np.isnan(M[i])
            if ok.sum() >= 2:
                vals.append(float((M[i, ok] * w[ok]).sum() / w[ok].sum()))
        return vals

    se_e, se_j = person_std(Le), person_std(Lj)
    # tenure bands of juniors (cells below 5 merged into Other), the same gap against the same expert reference
    from .summary import merge_small

    cells = defaultdict(list)
    for s in juniors:
        cells[s.band].append(s.id)
    tenure = []
    means_e = np.nanmean(Le, axis=0)
    for label, ids in merge_small(dict(cells), p.k_anon):
        rows = [idj.index(i) for i in ids]
        vals = []
        for r in rows:
            ok = ~np.isnan(Lj[r]) & ~np.isnan(means_e)
            if ok.sum() >= 2:
                vals.append(float(((Lj[r, ok] - means_e[ok]) * w[ok]).sum() / w[ok].sum()))
        e1 = S.one_sample(vals) if len(vals) >= 2 else None
        tenure.append({"band": label, "n": len(ids), "gap": e1})
    out.update({"gap": {"value": point, "lo": lo, "hi": hi, "se": se, "p": pv}, "habits": habits, "weights": {sk: float(w[j]) for j, sk in enumerate(cols)},
                "independence": _group_measure(experts, juniors, "indep", view), "assisted": _group_measure(experts, juniors, "assisted", view),
                "std_expert": S.one_sample(se_e) if len(se_e) >= 2 else None, "std_junior": S.one_sample(se_j) if len(se_j) >= 2 else None,
                "tenure": tenure, "newest": _newest(experts + juniors), "origin": _origin(experts + juniors),
                "occ_per_week": _occ_per_week(juniors, p), "experts": [s.id for s in experts], "juniors": [s.id for s in juniors]})
    view._cache[key] = out
    return out


def _group_measure(experts: list[PersonSummary], juniors: list[PersonSummary], field: str, view: AdminView) -> dict[str, Any]:
    """Person-level share (unaided or assisted) over the window for each group, each person counted once, and the difference."""
    def vals(g: list[PersonSummary]) -> list[float]:
        out = []
        for s in g:
            ps = view.person_skill(s)
            n = sum(v["n"] for v in ps.values())
            if n >= view.p.min_person_n:
                out.append(sum(v[field] * v["n"] for v in ps.values()) / n)
        return out

    ve, vj = vals(experts), vals(juniors)
    return {"expert": S.one_sample(ve) if len(ve) >= 2 else None, "junior": S.one_sample(vj) if len(vj) >= 2 else None,
            "gap": S.welch(vj, ve) if len(ve) >= 2 and len(vj) >= 2 else None}


def role_gap(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    for role in view.roles():
        d = role_gap_detail(view, role)
        if d.get("reason"):
            out.append(_cand(view, "role_gap", role, role, value=None, unit="seconds", n=int(d.get("n_expert", 0)) + int(d.get("n_junior", 0)), n_unit="people",
                             recency_t=view.now, family=FAM, floor=view.p.role_gap_floor_s, reason_pre=d["reason"], slots={"role": role}, extras={"role": role}))
            continue
        g = d["gap"]
        habits = sorted([h for h in d["habits"] if h["explains"] is not None], key=lambda h: (-h["explains"]["value"], h["skill"]))
        top = [h["skill"] for h in habits[:2]]
        n = len(d["experts"]) + len(d["juniors"])
        out.append(_cand(
            view, "role_gap", role, role, value=round(g["value"], 2), unit="seconds", lo=round(g["lo"], 2), hi=round(g["hi"], 2), p=g["p"], n=n, n_unit="people",
            split={"experts": len(d["experts"]), "juniors": len(d["juniors"]), "top_habits": top, "standard": "expert skill mix, within skill"},
            origin=d["origin"], evidence_ref=f"firm:{role}/lost_s", recency_t=d["newest"], family=FAM, floor=view.p.role_gap_floor_s, sign=1,
            impact_raw=max(0.0, g["value"]) * d["occ_per_week"] * len(d["juniors"]) / 60.0,
            slots={"role": role, "seconds": max(5, int(round(abs(g["value"]) / 5.0)) * 5), "habit1": top[0] if top else "", "habit2": top[1] if len(top) > 1 else ""},
            extras={"role": role}))
    return out


# ------------------------------------------------------------------------------------------------ cohort trend (within-person panel, standardised)
def trend_detail(view: AdminView, role: str) -> dict[str, Any]:
    key = ("trend", role)
    if key in view._cache:
        return view._cache[key]
    p = view.p
    out: dict[str, Any] = {"role": role}
    juniors = [s for s in view.people(role=role, level="junior") if s.status in ("ok", "stale") and s.n >= p.onboard_min]
    early = (p.trend_early_start_days, p.trend_early_end_days)
    pan: list[tuple[PersonSummary, dict, dict]] = []
    for s in juniors:
        e = view.person_skill(s, since_days=early[0], until_days=early[1])
        l = view.person_skill(s, since_days=p.recent_days)
        ne, nl = sum(v["n"] for v in e.values()), sum(v["n"] for v in l.values())
        if ne >= p.trend_min_n and nl >= p.trend_min_n:
            pan.append((s, e, l))
    out["panel_n"] = len(pan)
    if len(pan) < p.k_anon:
        out["reason"] = "group_too_small"
        view._cache[key] = out
        return out
    skills = sorted({sk for _s, e, l in pan for sk in list(e) + list(l)})
    wmix = {sk: sum(e[sk]["n"] for _s, e, _l in pan if sk in e) + sum(l[sk]["n"] for _s, _e, l in pan if sk in l) for sk in skills}
    tot = sum(wmix.values())
    wmix = {sk: v / tot for sk, v in wmix.items()}
    deltas, std_e, std_l = [], [], []
    for s, e, l in pan:
        common = [sk for sk in skills if sk in e and sk in l and e[sk]["n"] >= 2 and l[sk]["n"] >= 2]
        if len(common) < 2:
            continue
        ws = sum(wmix[sk] for sk in common)
        a = sum(wmix[sk] * e[sk]["indep"] for sk in common) / ws
        b = sum(wmix[sk] * l[sk]["indep"] for sk in common) / ws
        deltas.append(b - a)
        std_e.append(a)
        std_l.append(b)
    out["used_n"] = len(deltas)
    if len(deltas) < p.k_anon:
        out["reason"] = "group_too_small"
        view._cache[key] = out
        return out
    est1 = S.one_sample(deltas)
    # raw pooled change on the same panel, to show what a pooled comparison would have said
    def pooled(idx: int) -> float:
        k = n = 0
        for s, e, l in pan:
            d = (e, l)[idx]
            for sk, v in d.items():
                k += v["indep"] * v["n"]
                n += v["n"]
        return k / n if n else float("nan")

    raw_e, raw_l = pooled(0), pooled(1)
    errs_e = sum(v["errors"] for _s, e, _l in pan for v in e.values())
    n_e = sum(v["n"] for _s, e, _l in pan for v in e.values())
    errs_l = sum(v["errors"] for _s, _e, l in pan for v in l.values())
    n_l = sum(v["n"] for _s, _e, l in pan for v in l.values())
    if n_e and n_l:
        guard = share_guard("error_share", int(round(errs_e)), int(n_e), int(round(errs_l)), int(n_l), p)
    else:
        guard = Guard("error_share", 0.0, 0.0, int(n_e), int(n_l), False)
    cls = "cannot_tell_yet"
    if est1.lo > 0:
        cls = "improving"
    elif est1.hi < 0:
        cls = "needs_attention"
    # weekly series of the standardised pooled share of the role's juniors (people with at least 3 occurrences that week), approximate interval
    series = []
    for wk in range(int(p.admin_window_days // 7)):
        until, since = wk * 7, (wk + 1) * 7
        k_n: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        persons = 0
        for s in juniors:
            d = view.person_skill(s, since_days=since, until_days=until)
            if sum(v["n"] for v in d.values()) >= 3:
                persons += 1
                for sk, v in d.items():
                    k_n[sk][0] += v["indep"] * v["n"]
                    k_n[sk][1] += v["n"]
        if persons < p.k_anon:
            continue
        have = [sk for sk in wmix if k_n[sk][1] >= 3]
        if len(have) < 2:
            continue
        ws = sum(wmix[sk] for sk in have)
        val = sum(wmix[sk] * k_n[sk][0] / k_n[sk][1] for sk in have) / ws
        var = sum((wmix[sk] / ws) ** 2 * (k_n[sk][0] / k_n[sk][1]) * (1 - k_n[sk][0] / k_n[sk][1]) / k_n[sk][1] for sk in have)
        half = 1.96 * math.sqrt(var)
        series.append({"x": -wk, "y": round(val, 4), "lo": round(max(0.0, val - half), 4), "hi": round(min(1.0, val + half), 4), "n": int(sum(k_n[sk][1] for sk in have)), "people": persons})
    series.sort(key=lambda r: r["x"])
    out.update({"est": est1, "class": cls, "slope_per_4w": est(est1.value * 4.0 / 6.0, est1.lo * 4.0 / 6.0, est1.hi * 4.0 / 6.0), "guard": guard, "raw_early": raw_e,
                "raw_late": raw_l, "std_early": float(np.mean(std_e)), "std_late": float(np.mean(std_l)), "weights": wmix, "series": series,
                "newest": _newest([s for s, _e, _l in pan]), "origin": _origin([s for s, _e, _l in pan]), "occ_per_week": _occ_per_week([s for s, _e, _l in pan], p)})
    view._cache[key] = out
    return out


def cohort_trend(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p = view.p
    for role in view.roles():
        d = trend_detail(view, role)
        if d.get("reason"):
            out.append(_cand(view, "cohort_trend", role, role, unit="share", n=int(d.get("used_n", d.get("panel_n", 0))), n_unit="people", recency_t=view.now,
                             family=FAM, floor=p.trend_floor, reason_pre=d["reason"], slots={"role": role}, extras={"role": role}))
            continue
        e = d["est"]
        sign = 1 if e.value >= 0 else -1
        pol = "positive" if sign > 0 else "attention"
        out.append(_cand(
            view, "cohort_trend", role, role, polarity=pol, value=round(e.value, 4), unit="share", lo=round(e.lo, 4), hi=round(e.hi, 4), p=e.p, n=int(d["used_n"]),
            n_unit="people", split={"windows": "3 weeks, 6 weeks apart", "standard": "within person, first-window skill mix", "raw_pooled_change": round(d["raw_late"] - d["raw_early"], 4)},
            origin=d["origin"], evidence_ref=f"firm:{role}/independence", recency_t=d["newest"], family=FAM, floor=p.trend_floor, sign=sign,
            guards=(d["guard"],) if sign > 0 else (), impact_raw=abs(e.value) * d["occ_per_week"] * d["used_n"] * p.assist_cost_s / 60.0,
            slots={"role": role, "points": max(1, int(round(abs(e.value) * 100))), "direction": "up" if sign > 0 else "down",
                   **({"guard": d["guard"].name, "before": d["guard"].before, "after": d["guard"].after} if d["guard"].worse else {})}, extras={"role": role}))
    return out


# ------------------------------------------------------------------------------------------------ bottleneck skill
def bottleneck(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p = view.p
    for role in view.roles():
        juniors = view.cohort(role=role, level="junior")
        if juniors is None:
            out.append(_cand(view, "bottleneck_skill", role, role, unit="share", n=len(view.people(role=role, level="junior")), n_unit="people", recency_t=view.now,
                             family=FAM, floor=p.bottleneck_floor, reason_pre="group_too_small", slots={"role": role}, extras={"role": role}))
            continue
        ps = {s.id: view.person_skill(s) for s in juniors}
        skills = sorted({sk for d in ps.values() for sk in d})
        best: list[InsightCandidate] = []
        for sk in skills:
            diffs, vals = [], []
            for d in ps.values():
                v = d.get(sk)
                if not v or v["n"] < p.min_n_skill_person:
                    continue
                others = [o["assisted"] for k2, o in d.items() if k2 != sk and o["n"] >= p.min_n_skill_person]
                if others:
                    diffs.append(v["assisted"] - sum(others) / len(others))
                    vals.append(v["assisted"])
            if len(diffs) < p.k_anon:
                continue
            e = S.one_sample(diffs)
            if e is None:
                continue
            best.append(_cand(
                view, "bottleneck_skill", role, role, value=round(e.value, 4), unit="share", lo=round(e.lo, 4), hi=round(e.hi, 4), p=e.p, n=len(diffs), n_unit="people",
                split={"skill": sk, "mean_assisted_share": round(float(np.mean(vals)), 4), "compared_with": "the same people's other skills"},
                origin=_origin(juniors), evidence_ref=f"firm:{role}/{sk}/assisted", recency_t=_newest(juniors), family=FAM, floor=p.bottleneck_floor, sign=1,
                impact_raw=max(0.0, e.value) * _occ_per_week(juniors, p) / max(1, len(skills)) * len(diffs) * p.assist_cost_s / 60.0,
                slots={"role": role, "skill": sk, "share": int(round(float(np.mean(vals)) * 100)), "points": int(round(max(0.0, e.value) * 100))},
                cid=insight_id("admin", "firm", "bottleneck_skill", f"{role}:{sk}"), extras={"role": role, "skill": sk}))
        # the diversity rule is one per (subject, kind); the subject is the role, so give every skill of the role the same subject
        out.extend(_with_subject(c, role) for c in best)
    return out


def _with_subject(c: InsightCandidate, subject: str) -> InsightCandidate:
    from dataclasses import replace

    return replace(c, subject=subject)


# ------------------------------------------------------------------------------------------------ units, standardised
def unit_attention(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p = view.p
    for role in view.roles():
        juniors_all = [s for s in view.people(role=role, level="junior") if s.enough(p)]
        units = sorted({s.unit for s in juniors_all})
        if len(units) < 2:
            continue
        ps = {s.id: view.person_skill(s) for s in juniors_all}
        mix: dict[str, float] = defaultdict(float)
        for d in ps.values():
            for sk, v in d.items():
                mix[sk] += v["n"]
        tot = sum(mix.values()) or 1.0
        mix = {k: v / tot for k, v in mix.items()}

        def std(d: dict[str, dict[str, float]], mix: dict[str, float] = mix) -> float | None:
            ok = [sk for sk, v in d.items() if v["n"] >= 2 and sk in mix]
            if len(ok) < 2:
                return None
            ws = sum(mix[sk] for sk in ok)
            return sum(mix[sk] * d[sk]["indep"] for sk in ok) / ws

        scores = {s.id: std(ps[s.id]) for s in juniors_all}
        for unit in units:
            inn = [scores[s.id] for s in juniors_all if s.unit == unit and scores[s.id] is not None]
            rest = [scores[s.id] for s in juniors_all if s.unit != unit and scores[s.id] is not None]
            subject = f"{role}:{unit}"
            if len(inn) < p.k_anon or len(rest) < p.k_anon:
                if len(inn) >= 1:
                    out.append(_cand(view, "unit_attention", subject, role, unit="share", n=len(inn), n_unit="people", recency_t=view.now, family=FAM,
                                     floor=p.unit_floor, reason_pre="group_too_small", slots={"role": role, "unit": unit}, extras={"role": role, "unit": unit}))
                continue
            e = S.welch(rest, inn)                          # positive = this unit's juniors need more help than the rest of the role
            if e is None:
                continue
            members = [s for s in juniors_all if s.unit == unit]
            out.append(_cand(
                view, "unit_attention", subject, role, value=round(e.value, 4), unit="share", lo=round(e.lo, 4), hi=round(e.hi, 4), p=e.p, n=len(inn), n_unit="people",
                split={"unit_people": len(inn), "rest_of_role": len(rest), "standard": "the role's skill mix"}, origin=_origin(members),
                evidence_ref=f"firm:{role}/{unit}/independence", recency_t=_newest(members), family=FAM, floor=p.unit_floor, sign=1,
                impact_raw=max(0.0, e.value) * _occ_per_week(members, p) * len(inn) * p.assist_cost_s / 60.0, slots={"role": role, "unit": unit, "points": int(round(max(0.0, e.value) * 100))},
                extras={"role": role, "unit": unit}))
    return out


# ------------------------------------------------------------------------------------------------ onboarding speed (Kaplan-Meier)
def followed(view: AdminView, role: str) -> list[PersonSummary]:
    """Juniors whose current-role ledger starts within 14 days of joining, so the occurrence count is from the start (no left truncation)."""
    out = []
    for s in view.people(role=role, level="junior"):
        pr = s._person
        if pr is None or pr.joined_t is None or not s._rows:
            continue
        first = row_t(s._rows[0])
        if first - pr.joined_t <= 14 * DAY:
            out.append(s)
    return sorted(out, key=lambda s: s.id)


def onboarding_detail(view: AdminView, role: str) -> dict[str, Any]:
    key = ("onboarding", role)
    if key in view._cache:
        return view._cache[key]
    p = view.p
    out: dict[str, Any] = {"role": role}
    fol = followed(view, role)
    out["n"] = len(fol)
    if len(fol) < p.k_anon:
        out["reason"] = "group_too_small"
        view._cache[key] = out
        return out
    times = [float(s.reached_at if s.reached else s.n) for s in fol]
    events = [bool(s.reached) for s in fol]
    xmax = int(min(200, max(times)))
    grid = list(range(20, max(25, xmax) + 1, 5))
    if p.target_occurrences not in grid:
        grid = sorted(set(grid + [p.target_occurrences]))
    pts = S.km(times, events, grid)
    at_T = next(pt for pt in pts if pt.x == p.target_occurrences)
    out["censored"] = int(sum(1 for e in events if not e))
    out["km"] = [{"x": int(pt.x), "y": round(1.0 - pt.s, 4), "lo": round(1.0 - pt.hi, 4), "hi": round(1.0 - pt.lo, 4), "n_at_risk": pt.at_risk} for pt in pts if pt.at_risk >= 1]
    reached = {"value": 1.0 - at_T.s, "lo": 1.0 - at_T.hi, "hi": 1.0 - at_T.lo, "at_risk": at_T.at_risk}
    out["reached_by_target"] = reached
    med = S.km_median(times, events)
    rng = np.random.default_rng(S.seed_from("onb", role, len(fol)))
    meds = []
    t_arr, e_arr = np.asarray(times), np.asarray(events)
    for _ in range(200):
        i = rng.integers(0, len(fol), len(fol))
        m = S.km_median(t_arr[i], e_arr[i])
        meds.append(m)
    ok = [m for m in meds if m is not None]
    out["median"] = {"value": med, "ci": [float(np.quantile(ok, 0.025)), float(np.quantile(ok, 0.975))] if med is not None and len(ok) >= 0.95 * len(meds) else None}
    # the learning curve: independence over blocks of 10 occurrences, people with at least x occurrences, person-level interval
    curve = []
    for x in range(10, int(max(times)) + 1, 5):
        blocks = []
        for s in fol:
            if len(s._rows) >= x:
                blk = s._rows[x - 10:x]
                blocks.append(sum(1 for r in blk if is_independent(r)) / 10.0)
        if len(blocks) < p.k_anon:
            break
        e = S.one_sample(blocks)
        curve.append({"x": x, "y": round(e.value, 4), "lo": round(max(0.0, e.lo), 4), "hi": round(min(1.0, e.hi), 4), "n": len(blocks)})
    out["curve"] = curve
    out.update({"newest": _newest(fol), "origin": _origin(fol), "occ_per_week": _occ_per_week(fol, p)})
    view._cache[key] = out
    return out


def onboarding_speed(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p = view.p
    for role in view.roles():
        d = onboarding_detail(view, role)
        if d.get("reason"):
            if d["n"] > 0:
                out.append(_cand(view, "onboarding_speed", role, role, unit="share", n=d["n"], n_unit="people", recency_t=view.now, family=FAM, floor=p.onboarding_floor,
                                 reason_pre="group_too_small", slots={"role": role}, extras={"role": role}))
            continue
        r = d["reached_by_target"]
        if r["at_risk"] < 3:
            out.append(_cand(view, "onboarding_speed", role, role, unit="share", n=d["n"], n_unit="people", recency_t=d["newest"], family=FAM, floor=p.onboarding_floor,
                             reason_pre="not_enough_data", slots={"role": role}, extras={"role": role}))
            continue
        diff = r["value"] - p.target_reached_share
        lo, hi = r["lo"] - p.target_reached_share, r["hi"] - p.target_reached_share
        se = max((hi - lo) / (2 * S.Z95), 1e-9)
        pv = S.norm_two_sided_p(diff / se)
        sign = 1 if diff >= 0 else -1
        n_behind = d["n"]
        cand_guards: tuple[Guard, ...] = ()
        out.append(_cand(
            view, "onboarding_speed", role, role, polarity="positive" if sign > 0 else "attention", value=round(diff, 4), unit="share", lo=round(lo, 4), hi=round(hi, 4), p=pv,
            n=d["n"], n_unit="people", split={"target_occurrences": p.target_occurrences, "target_share": p.target_reached_share, "reached_share": round(r["value"], 4),
                                              "censored": d["censored"]},
            origin=d["origin"], evidence_ref=f"firm:{role}/time_to_independence", recency_t=d["newest"], family=FAM, floor=p.onboarding_floor, sign=sign, guards=cand_guards,
            impact_raw=abs(diff) * n_behind * d["occ_per_week"] * p.assist_cost_s * 0.5 / 60.0,
            slots={"role": role, "reached": int(round(r["value"] * 100)), "target_pct": int(round(p.target_reached_share * 100)), "occurrences": p.target_occurrences,
                   "direction": "ahead" if sign > 0 else "behind"}, extras={"role": role}))
    return out


# ------------------------------------------------------------------------------------------------ automation, risk, coverage, stale feeds
def automation(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p, snap, now = view.p, view.snap, view.now
    approved = [r for r in snap.routines if r.get("status") in ("approval", "unattended")]
    rows = [r for pr in sorted(snap.people, key=lambda x: x.id) for r in pr.rows if r.get("stream") == "automation" and r.get("offload_outcome") == "done" and now - row_t(r) <= 28 * DAY]
    if approved or rows:
        runs = sum(int(r.get("shadow_runs", 0)) for r in approved)
        match = sum(int(r.get("shadow_matches", 0)) for r in approved)
        lower = S.wilson_interval(match, runs)[0] if runs else 0.0
        hours = math.fsum(r.get("minutes") or 0.0 for r in rows) / 60.0
        n_runs = len(rows)
        fc = sum(1 for e in snap.risk_events if e.get("kind") == "false_claim" and e.get("age_days", 1e9) <= 28)
        pre = None
        if len(approved) < p.automation_min_routines or n_runs < p.automation_min_runs:
            pre = "not_enough_data"
        elif lower < p.automation_shadow_lower:
            pre = "below_effect_floor"
        newest = max((row_t(r) for r in rows), default=None)
        out.append(_cand(
            view, "automation_value", "firm", "firm", value=round(hours, 2), unit="hours", n=n_runs, n_unit="runs", split={"approved_routines": len(approved), "people": len({r["person"] for r in rows}),
                                                                                                                   "shadow_matches": match, "shadow_runs": runs, "shadow_lower": round(lower, 4)},
            evidence_ref="firm:automation/minutes", recency_t=newest, impact_raw=hours * 60.0 / 4.0, reason_pre=pre,
            guards=(Guard("false_claims", 0.0, float(fc), n_runs, n_runs, fc > 0),), slots={"hours": max(1, int(round(hours))), "routines": len(approved), "runs": n_runs, "matches": match, "shadow_runs": runs},
            extras={"routines": sorted({r["id"] for r in approved})}))
    pend = [r for r in snap.routines if r.get("status") == "proposed" and (r.get("hours_lo") or 0.0) >= p.automation_hours_floor and now - (r.get("t") or 0) <= 30 * DAY]
    if pend:
        h = math.fsum(r["hours_lo"] for r in pend)
        out.append(_cand(view, "automation_pending", "firm", "firm", value=round(h, 2), unit="hours", n=len(pend), n_unit="routines", evidence_ref="firm:routines/proposed",
                         recency_t=max(r["t"] for r in pend), impact_raw=h * 60.0 / 4.0,
                         reason_pre=None if len(pend) >= p.automation_min_routines else "not_enough_data", slots={"count": len(pend), "hours": max(1, int(round(h)))},
                         split={"proposals": len(pend), "people": len({r['person'] for r in pend})}))
    return out


def risk(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p, snap, now = view.p, view.snap, view.now
    t_feed = snap.feed_t.get("risk_feed")
    if t_feed is None or now - t_feed > p.feed_stale_days_risk * DAY:
        out.append(_cand(view, "data_stale", "risk_feed", "firm", value=None if t_feed is None else round((now - t_feed) / DAY, 1), unit="days", n=1, n_unit="feeds",
                         recency_t=now, impact_raw=50.0, slots={"feed": "risk_feed", "days": None if t_feed is None else int((now - t_feed) / DAY)}))
        return out
    imp = dict(p.risk_impact)
    ages = [a.get("age_h", 0.0) for a in snap.approvals]
    if ages and max(ages) >= p.risk_backlog_h:
        out.append(_cand(view, "risk_signal", "approval_backlog", "firm", value=round(max(ages), 1), unit="hours", n=len(ages), n_unit="approvals", recency_t=t_feed,
                         impact_raw=imp["approval_backlog"] * min(3.0, max(ages) / 24.0), slots={"signal": "approval_backlog", "hours": int(max(ages)), "open": len(ages)}))
    for sig, kind, days in (("injection_pauses", "injection_pause", p.risk_window_days), ("false_claims", "false_claim", 30.0), ("kill_events", "kill", p.risk_window_days)):
        n = sum(1 for e in snap.risk_events if e.get("kind") == kind and e.get("age_days", 1e9) <= days)
        if n >= 1:
            out.append(_cand(view, "risk_signal", sig, "firm", value=float(n), unit="count", n=n, n_unit="events", recency_t=t_feed, impact_raw=imp[sig] * min(3.0, float(n)),
                             slots={"signal": sig, "count": n, "days": int(days)}))
    return out


def coverage_and_stale(view: AdminView) -> list[InsightCandidate]:
    out: list[InsightCandidate] = []
    p = view.p
    cov = view.coverage()
    if cov["users"] and cov["share_enough"] < p.coverage_floor:
        out.append(_cand(view, "coverage", "firm", "firm", value=cov["share_enough"], unit="share", n=cov["users"], n_unit="people", recency_t=view.now, impact_raw=20.0,
                         slots={"enough": cov["enough_data"], "users": cov["users"]}))
    newest = max((s.last_t for s in view.sums.values() if s.last_t is not None), default=None)
    if newest is not None and view.now - newest > p.stale_days * DAY:
        out.append(_cand(view, "data_stale", "ledger", "firm", value=round((view.now - newest) / DAY, 1), unit="days", n=1, n_unit="feeds", recency_t=view.now, impact_raw=40.0,
                         slots={"feed": "ledger", "days": int((view.now - newest) / DAY)}))
    return out


def admin_run(view: AdminView) -> list[InsightCandidate]:
    """The fixed candidate list for the admin audience."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        c: list[InsightCandidate] = []
        c += role_gap(view)
        c += cohort_trend(view)
        c += bottleneck(view)
        c += onboarding_speed(view)
        c += unit_attention(view)
        c += automation(view)
        c += risk(view)
        c += coverage_and_stale(view)
    return c
