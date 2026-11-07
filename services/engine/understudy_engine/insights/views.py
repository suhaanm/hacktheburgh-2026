"""Admin response payloads (REQ-9): roles, firm, onboarding, drill-down. Shapes agreed with ADMIN-UI (docs/INSIGHTS_DESIGN.md section 7).

Everything here is built from ``PersonSummary`` numbers and enums and from the admin computations; no ledger row, row id or hour bucket is
ever put into a payload (a test scans every admin response). Per-user rows are in label order, never ranked, with no single score.
"""
from __future__ import annotations

from typing import Any

from . import admin as A
from . import stats as S
from . import vocab as V
from .summary import AdminView, est, est_from, merge_small, skill_label
from .types import InsightCandidate


def _verdict(lo: float | None, hi: float | None) -> str:
    return "gap" if (lo is not None and hi is not None and (lo > 0 or hi < 0)) else "cannot_tell"


def _gap_est(e: S.Est | None) -> dict[str, Any] | None:
    return est_from(e)


def roles_payload(view: AdminView) -> dict[str, Any]:
    roles = []
    for role in view.roles():
        d = A.role_gap_detail(view, role)
        rc: dict[str, Any] = {"role": role, "name": V.role_name(role), "n_expert": int(d.get("n_expert", 0)), "n_junior": int(d.get("n_junior", 0)),
                              "enough": not d.get("reason"), "reason": d.get("reason"), "measures": [], "habits": [], "tenure": [],
                              "standard": "Compared within each skill, then combined with the experts' skill mix as fixed weights, so a difference in task mix cannot create or hide a gap."}
        if not d.get("reason"):
            g = d["gap"]
            for key, label, unit, field in (("independence", "Finished without help", "share", "independence"), ("assisted_share", "Needed help", "share", "assisted")):
                m = d[field]
                gg = m["gap"]
                rc["measures"].append({"key": key, "label": label, "unit": unit, "expert": _gap_est(m["expert"]), "junior": _gap_est(m["junior"]), "gap": _gap_est(gg),
                                       "verdict": _verdict(gg.lo, gg.hi) if gg else "cannot_tell"})
            rc["measures"].append({"key": "time_vs_expert", "label": "Seconds per case beyond the expert median", "unit": "seconds", "expert": _gap_est(d["std_expert"]),
                                   "junior": _gap_est(d["std_junior"]), "gap": est(g["value"], g["lo"], g["hi"], 2), "verdict": _verdict(g["lo"], g["hi"])})
            for h in sorted(d["habits"], key=lambda h: (-(h["explains"]["value"] if h["explains"] else -1e9), h["skill"])):
                ge = h["gap"]
                ex = h["explains"]
                rc["habits"].append({"id": h["skill"], "label": h["label"], "explains_s": est(ex["value"], ex["lo"], ex["hi"], 2) if ex else None,
                                     "expert_rate": _gap_est(h["assisted_expert"]), "junior_rate": _gap_est(h["assisted_junior"]), "n": int(h["n_junior"]),
                                     "share_of_gap": None if h["share"] is None else round(float(h["share"]), 4), "gap_s": _gap_est(ge),
                                     "verdict": _verdict(ge.lo, ge.hi) if ge else "cannot_tell"})
            rc["tenure"] = [{"band": t["band"], "n": t["n"], "gap_s": _gap_est(t["gap"])} for t in d["tenure"]]
            rc["overall"] = {"gap_s": est(g["value"], g["lo"], g["hi"], 2), "standardised_to": "expert skill mix"}
        roles.append(rc)
    return {"roles": roles, "same_scale": {"min": 0, "max": 1}, "method": "Person-level means, each person counted once; Welch intervals per skill; a person-level bootstrap for the combined gap."}


def _aggregate(view: AdminView, role: str) -> dict[str, Any] | None:
    ok = [s for s in view.people(role=role) if s.status == "ok" and s.independence is not None]
    if len(ok) < view.p.k_anon:
        return None
    ind = S.one_sample([s.independence["value"] for s in ok])
    asst = S.one_sample([s.assisted["value"] for s in ok if s.assisted])
    onb = A.onboarding_detail(view, role)
    tti = {"median": None, "ci": None, "unit": "occurrences", "reached_share": None}
    if not onb.get("reason"):
        r = onb["reached_by_target"]
        tti = {"median": onb["median"]["value"], "ci": onb["median"]["ci"], "unit": "occurrences", "reached_share": est(r["value"], r["lo"], r["hi"])}
    return {"n_users": len(ok), "independence": est_from(ind), "assisted_share": est_from(asst), "time_to_independence": tti}


def _units(view: AdminView, members) -> list[dict[str, Any]]:
    cells: dict[str, list[str]] = {}
    for s in members:
        if s.status != "no_data":
            cells.setdefault(s.unit, []).append(s.id)
    out = []
    for label, ids in merge_small(cells, view.p.k_anon):
        vals = [view.sums[i].independence["value"] for i in ids if view.sums[i].independence is not None]
        out.append({"unit": label.replace("_", " ") if label != "Other" else "Other", "n": len(ids), "independence": est_from(S.one_sample(vals)) if len(vals) >= 2 else None})
    return out


def firm_payload(view: AdminView) -> dict[str, Any]:
    k = view.p.k_anon
    small, groups = [], []
    for role in view.roles():
        members = [s for s in view.people(role=role) if s.status != "no_data"]
        (small if len(members) < k else groups).append(role)
    out_groups = []
    for role in groups:
        td = A.trend_detail(view, role)
        trend = {"class": td.get("class", "not_enough_data"), "label": V.TREND_LABEL[td.get("class", "not_enough_data")],
                 "slope_per_4w": td.get("slope_per_4w"), "n_people": int(td.get("used_n", td.get("panel_n", 0)))}
        out_groups.append({"role": role, "name": V.role_name(role), "merged": False, "users": view.person_rows(role), "aggregate": _aggregate(view, role), "trend": trend,
                           "units": _units(view, view.people(role=role))})
    if small:
        members = [s for r in small for s in view.people(role=r)]
        agg = None
        ok = [s for s in members if s.status == "ok" and s.independence is not None]
        if len(ok) >= k:
            agg = {"n_users": len(ok), "independence": est_from(S.one_sample([s.independence["value"] for s in ok])), "assisted_share": None,
                   "time_to_independence": {"median": None, "ci": None, "unit": "occurrences", "reached_share": None}}
        out_groups.append({"role": "other", "name": V.role_name("other"), "merged": True, "users": [s.to_row() for s in sorted(members, key=lambda s: (s.label, s.id))], "aggregate": agg,
                           "trend": {"class": "not_enough_data", "label": V.TREND_LABEL["not_enough_data"], "slope_per_4w": None, "n_people": 0}, "units": []})
    cov = view.coverage()
    return {"roles": out_groups, "privacy": {"min_group": k, "merged_roles": small, "note": "Comparison tables need at least 5 people; smaller groups are merged into Other. Per-user rows are numbers and enums only, in label order, with no ranking and no score."},
            "totals": {"users": cov["users"], "enough_data": cov["enough_data"]}, "coverage": cov}


def onboarding_payload(view: AdminView) -> dict[str, Any]:
    p = view.p
    roles = []
    for role in view.roles():
        d = A.onboarding_detail(view, role)
        if d.get("reason"):
            roles.append({"role": role, "name": V.role_name(role), "n": int(d.get("n", 0)), "curve": [], "km": [], "censored": 0, "median_to_target": None, "reached_share": None,
                          "reason": d["reason"]})
            continue
        r = d["reached_by_target"]
        med = d["median"]
        roles.append({"role": role, "name": V.role_name(role), "n": int(d["n"]), "curve": d["curve"], "km": d["km"], "censored": d["censored"],
                      "median_to_target": est(med["value"], *(med["ci"] or (None, None)), nd=1) if med["value"] is not None else None,
                      "reached_share": est(r["value"], r["lo"], r["hi"]), "at_risk_at_target": r["at_risk"], "reason": None})
    return {"target": {"value": p.target_share, "label": "design target", "occurrences": p.target_occurrences, "reached_share": p.target_reached_share,
                       "note": "A design target the firm sets, not a measured standard. The default is an assumption."},
            "x_unit": "occurrences", "roles": roles,
            "method": "Independence is the share of the last 20 occurrences finished without help. Kaplan-Meier with censoring: a person who has not reached the line yet is censored at their occurrence count. The curve uses blocks of 10 occurrences and a person-level interval, and stops where fewer than 5 people remain."}


# ------------------------------------------------------------------------------------------------ drill-down
def _row(label: str, values: dict[str, Any], group: str | None = None, n: int | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"label": label, "values": values}
    if group:
        r["group"] = group
    if n is not None:
        r["n"] = n
    return r


def _pair(e: S.Est | None, nd: int = 2) -> Any:
    return None if e is None else [round(e.lo, nd), round(e.hi, nd)]


def drill_payload(view: AdminView, c: InsightCandidate, all_cands: dict[str, InsightCandidate], headline: str) -> dict[str, Any]:
    k = c.kind
    cols: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    notes: list[str] = []
    role = c.extras.get("role") or c.slots.get("role")
    if k == "role_gap" and role:
        d = A.role_gap_detail(view, role)
        cols = [{"key": "weight", "label": "Share of expert occurrences", "unit": "share"}, {"key": "gap", "label": "Gap per case", "unit": "seconds"},
                {"key": "gap_ci", "label": "Interval", "unit": "seconds"}, {"key": "explains", "label": "Explains", "unit": "seconds"},
                {"key": "share", "label": "Share of the gap", "unit": "share"}, {"key": "expert_rate", "label": "Experts needed help", "unit": "share"},
                {"key": "junior_rate", "label": "Juniors needed help", "unit": "share"}]
        for h in sorted(d.get("habits", []), key=lambda h: (-(h["explains"]["value"] if h["explains"] else -1e9), h["skill"])):
            g = h["gap"]
            rows.append(_row(h["label"], {"weight": round(h["weight"], 4), "gap": None if g is None else round(g.value, 2), "gap_ci": _pair(g),
                                          "explains": None if h["explains"] is None else round(h["explains"]["value"], 2),
                                          "share": None if h["share"] is None else round(h["share"], 4),
                                          "expert_rate": None if h["assisted_expert"] is None else round(h["assisted_expert"].value, 4),
                                          "junior_rate": None if h["assisted_junior"] is None else round(h["assisted_junior"].value, 4)}, n=int(h["n_junior"])))
        if d.get("tenure"):
            tables.append({"id": "tenure", "title": "Juniors by tenure band (groups under 5 are merged into Other)",
                           "columns": [{"key": "gap", "label": "Gap per case", "unit": "seconds"}, {"key": "ci", "label": "Interval", "unit": "seconds"}],
                           "rows": [_row(t["band"], {"gap": None if t["gap"] is None else round(t["gap"].value, 2), "ci": _pair(t["gap"])}, n=t["n"]) for t in d["tenure"]]})
        notes += ["Each person counts once. Gaps are compared within each skill, then combined with the experts' skill mix as fixed weights.",
                  "The interval for the combined gap is a person-level bootstrap."]
    elif k == "cohort_trend" and role:
        d = A.trend_detail(view, role)
        if not d.get("reason"):
            cols = [{"key": "early", "label": "Six weeks ago", "unit": "share"}, {"key": "late", "label": "Last three weeks", "unit": "share"}, {"key": "change", "label": "Change", "unit": "share"}]
            rows = [_row("Standardised, within each person", {"early": round(d["std_early"], 4), "late": round(d["std_late"], 4), "change": round(d["est"].value, 4)}, n=d["used_n"]),
                    _row("Raw pooled, for comparison only", {"early": round(d["raw_early"], 4), "late": round(d["raw_late"], 4), "change": round(d["raw_late"] - d["raw_early"], 4)}, n=d["panel_n"])]
            series = [{"label": "Juniors, standardised independence by week", "points": d["series"]}]
            notes += ["Two windows of 3 weeks, 6 weeks apart (3-week smoothing). Only people with enough occurrences in both windows are included, so joiners do not distort it.",
                      "The standardised row holds the skill mix fixed at the first window's; the raw pooled row can fall or rise only because the mix changed."]
    elif k == "bottleneck_skill" and role:
        sibs = sorted([x for x in all_cands.values() if x.kind == "bottleneck_skill" and x.extras.get("role") == role and x.value is not None], key=lambda x: (-x.value, x.id))
        cols = [{"key": "share", "label": "Needed help", "unit": "share"}, {"key": "excess", "label": "Above their other skills", "unit": "share"}, {"key": "ci", "label": "Interval", "unit": "share"}]
        rows = [_row(skill_label(role, x.extras["skill"]), {"share": x.split.get("mean_assisted_share"), "excess": x.value, "ci": [x.lo, x.hi]}, n=x.n) for x in sibs]
        notes.append("Each person is compared with their own other skills, so skills are not confounded with who does them.")
    elif k == "onboarding_speed" and role:
        d = A.onboarding_detail(view, role)
        if not d.get("reason"):
            cols = [{"key": "reached", "label": "Reached independence", "unit": "share"}, {"key": "lo", "label": "Low", "unit": "share"}, {"key": "hi", "label": "High", "unit": "share"},
                    {"key": "at_risk", "label": "People still followed", "unit": "people"}]
            rows = [_row(f"By {pt['x']} occurrences", {"reached": pt["y"], "lo": pt["lo"], "hi": pt["hi"], "at_risk": pt["n_at_risk"]}) for pt in d["km"] if pt["x"] % 20 == 0]
            series = [{"label": "Kaplan-Meier: reached independence", "points": [{"x": pt["x"], "y": pt["y"], "lo": pt["lo"], "hi": pt["hi"]} for pt in d["km"]]},
                      {"label": "Independence by occurrence block", "points": d["curve"]}]
            notes += ["Time is occurrences, with censoring for people who have not reached the line yet.", "The target is a design target the firm sets, not a measured standard."]
    elif k == "unit_attention" and role:
        cols = [{"key": "diff", "label": "Independence difference", "unit": "share"}, {"key": "ci", "label": "Interval", "unit": "share"}]
        rows = [_row(f"{str(c.extras.get('unit', '')).replace('_', ' ')} against the rest of the role", {"diff": c.value, "ci": [c.lo, c.hi]}, n=c.n)]
        notes.append("Compared on the role's skill mix. Groups under 5 people are not compared. This is where onboarding support may help.")
    elif k == "automation_value":
        cols = [{"key": "value", "label": "Value"}]
        rows = [_row("Hours handled in four weeks", {"value": c.value}, n=c.n), _row("Approved routines", {"value": c.split.get("approved_routines")}),
                _row("Shadow matches", {"value": c.split.get("shadow_matches")}, n=c.split.get("shadow_runs")), _row("Shadow lower bound", {"value": c.split.get("shadow_lower")})]
        notes.append("Hours are agent minutes on approved routines, a proxy for time handed over, not a measured saving.")
    elif k == "automation_pending":
        cols = [{"key": "value", "label": "Value"}]
        rows = [_row("Proposals waiting", {"value": c.n}), _row("People with a proposal", {"value": c.split.get("people")}), _row("Hours over four weeks (lower bounds)", {"value": c.value})]
        notes.append("Only the worker can approve a routine.")
    elif k == "risk_signal":
        cols = [{"key": "value", "label": "Value"}]
        rows = [_row(str(c.slots.get("signal", "")).replace("_", " "), {"value": c.value}, n=c.n)]
        notes.append("Counts and ages only; no content from any run or approval.")
    elif k == "coverage":
        cov = view.coverage()
        cols = [{"key": "users", "label": "People", "unit": "people"}, {"key": "enough", "label": "With enough data", "unit": "people"}]
        rows = [_row(r["name"], {"users": r["users"], "enough": r["enough_data"]}) for r in cov["roles"]]
        notes.append(f"Enough data means at least {view.p.enough_n} occurrences in the last 12 weeks.")
    else:
        cols = [{"key": "value", "label": "Value"}]
        rows = [_row(k.replace("_", " "), {"value": c.value}, n=c.n)]
    notes += [f"Data: {c.badge}. {V.STATEMENT}"]
    return {"id": c.id, "headline": headline, "kind": k, "columns": cols, "rows": rows, "series": series, "tables": tables, "notes": notes,
            "method": f"{view.p.n_boot} person-level bootstrap draws where an interval is a bootstrap; 3-week windows; seeds come from ids."}
