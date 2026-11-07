"""The pre-registered analysis of the role studies (PLAN.md section 7). Reuses ``evals/study/analyze.py`` (t interval, exact sign-flip p, ``paired``) and the generic parts of
``evals/study_sim/analysis.py`` by import, on CSV rows in the human format plus this design's columns. Every number carries its n. Plain functions, tested on made-up numbers.

The primary outcome: per participant, the ORACLE POINTS (0 wrong or claimed-done-wrong, 1 partial, 2 correct) of the unassisted post-test of the coached skill minus the
uncoached skill; the mean of those differences over the coached-arm participants, with the t interval and the exact sign-flip p. Everything else is secondary and descriptive.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter

from evals.study_sim import analysis as sim
from evals.study_sim.analysis_io import STUDY

from .design import assignments_for_design_check, build_participants
from .roles import cfg

sys.path.insert(0, str(STUDY))
import analyze as A  # noqa: E402

OUTCOMES = ("correct", "partial", "wrong", "claimed_done_wrong")
# the feasibility pilot (declared in advance): a participant option is USABLE when all hold, over the UNASSISTED cases of the pilot (pre-test and post-test of each block of 3 A/A participants: 12 cases)
PILOT_MAX_SHARE_ZERO = 0.5            # FLOOR: at most half of the unassisted cases score 0 points
PILOT_MAX_SHARE_FULL = 0.8            # CEILING: at most 80% score the full 2 points (a coach needs room to help)
PILOT_MAX_SHARE_CAP_BOUND = 0.25      # CAP: at most a quarter end by the action cap (or the wall cap) or use at least 95% of their cap
CAP_USED_SHARE = 0.95
MIN_UNITS = 2                         # fewer than 2 affordable units (8 participants each) and a role is not run
COST_SAFETY = 1.3                     # the estimate of a participant's cost is the pilot mean times this ...
STUDY_VS_PILOT = 1.5                  # ... times 1.5 (a pilot participant works 4 unassisted cases; a study participant 6 cases plus two notes)


def split_arms(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    return ([r for r in rows if r.get("arm") == "coached"], [r for r in rows if r.get("arm") == "aa"], [r for r in rows if r.get("arm") == "pilot"])


def points(r: dict, which: str) -> float:
    return {"post": r["post_checks_done"], "pre": r["pre_points"], "practice": r["practice_points"]}[which]


def change_diffs(rows: list[dict]) -> dict[str, float]:
    """participant -> change(pre -> post, in points / 2) of the coached skill minus the same change of the uncoached skill."""
    inc = sim._included(rows)
    return A.paired(inc, lambda r: (r["post_checks_done"] - r["pre_points"]) / 2.0)


def change_section(rows: list[dict]) -> dict:
    d = change_diffs(rows)
    out = sim.interval([d[p] for p in sorted(d)])
    out["per_participant_difference"] = {p: round(d[p], 3) for p in sorted(d)}
    out["note"] = "secondary: (post minus pre) of the coached skill minus (post minus pre) of the uncoached skill, in fractions of the 2 points"
    return out


def outcome_counts(rows: list[dict], which: str, by_condition: bool = True) -> dict:
    inc = sim._included(rows)
    key = {"pre": "pre_outcome", "post": "post_outcome", "practice": "practice_outcome"}[which]
    cond = {"pre": "actual_condition", "post": "condition", "practice": "actual_condition"}[which]
    out: dict = {}
    for r in inc:
        k = r[cond] if by_condition else "all"
        out.setdefault(k, Counter())[r[key]] += 1
    return {k: {o: int(c.get(o, 0)) for o in OUTCOMES} | {"n": sum(c.values())} for k, c in out.items()}


def per_skill(role: str, rows: list[dict]) -> dict:
    """Per skill: baseline (pre-test mean points, share at the floor and at the ceiling), post-test mean where it was coached vs not (different people, same skill) with a percentile
    bootstrap interval on the difference, skill-check-done shares, and the claimed-done-but-wrong share. Descriptive: no p-value."""
    inc = sim._included(rows)
    out = {}
    for skill in cfg(role).skills:
        rs = [r for r in inc if r["skill"] == skill]
        c = [A.skill_score(r) for r in rs if r["condition"] == "coached"]
        u = [A.skill_score(r) for r in rs if r["condition"] == "uncoached"]
        pre = [r["pre_points"] for r in rs]
        out[skill] = {
            "n_blocks": len(rs), "n_coached": len(c), "n_uncoached": len(u),
            "baseline_pre_mean_points": round(statistics.fmean(pre), 3) if pre else None, "baseline_share_zero": round(sum(1 for x in pre if x == 0) / len(pre), 3) if pre else None,
            "baseline_share_full": round(sum(1 for x in pre if x == 2) / len(pre), 3) if pre else None,
            "post_mean_coached": round(statistics.fmean(c) * 2, 3) if c else None, "post_mean_uncoached": round(statistics.fmean(u) * 2, 3) if u else None,
            "difference_points": round((statistics.fmean(c) - statistics.fmean(u)) * 2, 3) if c and u else None,
            "ci95_bootstrap_points": [None if x is None else round(x * 2, 3) for x in sim._boot_mean_diff(c, u)], "ci_method": f"percentile bootstrap, {sim.BOOT} resamples, seed {sim.SEED}",
            "skill_check_done_pre": round(statistics.fmean(r["pre_skill_check"] for r in rs), 3) if rs else None,
            "skill_check_done_post_coached": round(statistics.fmean(r["post_skill_check"] for r in rs if r["condition"] == "coached"), 3) if c else None,
            "skill_check_done_post_uncoached": round(statistics.fmean(r["post_skill_check"] for r in rs if r["condition"] == "uncoached"), 3) if u else None,
            "claimed_done_wrong_pre": int(sum(r["pre_claimed_done_wrong"] for r in rs)), "claimed_done_wrong_post": int(sum(r["post_claimed_done_wrong"] for r in rs)),
        }
    return out


def false_claims(rows: list[dict]) -> dict:
    inc = sim._included(rows)
    n = len(inc)
    return {"blocks": n, "claimed_done_wrong_pre": int(sum(r["pre_claimed_done_wrong"] for r in inc)), "claimed_done_wrong_post": int(sum(r["post_claimed_done_wrong"] for r in inc)),
            "post_edge_cases_missed_when_done": int(sum(r["post_edge_missed"] for r in inc)),
            "note": "claimed_done_wrong: the participant declared the work done (Mark done, or an answer with status checked or handled) while the oracle says it is wrong"}


def design_check(rows: list[dict], role: str) -> list[str]:
    """Structural checks against the fixed design (run before any number is computed); problems are listed, never silently fixed."""
    problems: list[str] = []
    design = assignments_for_design_check(build_participants(role))
    by_p: dict[str, list[dict]] = {}
    for r in rows:
        by_p.setdefault(r["participant"], []).append(r)
    for p, rs in by_p.items():
        plan = design.get(p)
        if not plan:
            problems.append(f"{p}: not in the design")
            continue
        if sorted(int(r["block"]) for r in rs) != [1, 2]:
            problems.append(f"{p}: needs exactly blocks 1 and 2")
        conds = sorted(r["condition"] for r in rs)
        if conds != ["coached", "uncoached"]:
            problems.append(f"{p}: needs one coached and one uncoached block, has {conds}")
        for r in rs:
            b = plan["blocks"].get(int(r["block"]))
            exp = (b["skill"], b["condition"], f"{b['pre'][0]}/v{b['pre'][1]}", f"{b['practice'][0]}/v{b['practice'][1]}", f"{b['post'][0]}/v{b['post'][1]}") if b else None
            got = (r["skill"], r["condition"], r["pre_case"], r["practice_case"], r["post_case"])
            if exp != got:
                problems.append(f"{p} block {int(r['block'])}: differs from the fixed design ({got} vs {exp})")
    return problems


def _flip_p(d: list[float]) -> float:
    """Exact two-sided sign-flip p over all 2^n sign patterns (vectorised; ``analyze.sign_flip_p`` is the reference and gives the same number)."""
    import numpy as np

    n = len(d)
    signs = (((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1) * 2 - 1).astype(float)
    return float((np.abs(signs @ np.array(d, float)) >= abs(sum(d)) - 1e-12).mean())


def aa_relabelling(role: str, aa_rows: list[dict]) -> dict:
    """The A/A false-positive rate of the pre-registered analysis, conditional on the A/A scores (exact, no sampling). An A/A participant has two skill scores and no coaching at all, so
    which skill is 'nominally coached' is arbitrary. Each participant's base difference is score(first skill of its pair) minus score(second); every balanced relabelling (half the
    participants keep the sign, half flip it) is analysed like the headline: the share with sign-flip p below 0.05 and the share whose t interval excludes 0 are the empirical
    false-positive rates on these scores."""
    import itertools
    import math

    inc = sim._included(aa_rows)
    pair_of = {s.pid: s.pair for s in build_participants(role)}
    by: dict[str, dict[str, float]] = {}
    for r in inc:
        by.setdefault(r["participant"], {})[r["skill"]] = A.skill_score(r)
    ids = sorted(p for p, v in by.items() if p in pair_of and set(v) == set(pair_of[p]))
    n = len(ids)
    if n < 4 or n % 2:
        return {"n": n, "note": "needs an even number of A/A participants (at least 4)"}
    base = {p: by[p][pair_of[p][0]] - by[p][pair_of[p][1]] for p in ids}
    fp_p = fp_ci = total = 0
    for keep in itertools.combinations(ids, n // 2):
        d = [base[p] if p in keep else -base[p] for p in ids]
        total += 1
        fp_p += _flip_p(d) < 0.05
        m, lo, hi = A.t_interval(d)
        fp_ci += (not math.isnan(lo)) and (lo > 0 or hi < 0)
    return {"n": n, "relabellings": total, "share_sign_flip_p_below_05": round(fp_p / total, 4), "share_ci_excludes_zero": round(fp_ci / total, 4),
            "note": "conditional on these A/A scores; the nominal rate is 0.05. A rate above that means the analysis would raise false alarms on this measurement chain."}


def aa_block(role: str, aa_rows: list[dict], coached_rows: list[dict]) -> dict:
    out = sim.aa_section(aa_rows, coached_rows)
    out["relabelling"] = aa_relabelling(role, aa_rows)
    return out


def analyse_role(role: str, rows: list[dict]) -> dict:
    coached, aa, pilot = split_arms(rows)
    return {
        "role": role,
        "headline": sim.headline(coached) if coached else {"n": 0},
        "change_pre_to_post": change_section(coached) if coached else {"n": 0},
        "design_problems": design_check(coached + aa, role),
        "excluded_participants": sim.excluded_ids(coached + aa),
        "per_skill": per_skill(role, coached) if coached else {},
        "outcomes": {"pre": outcome_counts(coached, "pre"), "post": outcome_counts(coached, "post"), "practice": outcome_counts(coached, "practice")},
        "false_claims": false_claims(coached) if coached else None,
        "aa": aa_block(role, aa, coached) if aa else {"n": 0},
        "aa_per_skill": per_skill(role, aa) if aa else {},
        "effort": sim.effort(coached) if coached else None, "effort_aa": sim.effort(aa) if aa else None,
        "nudges": sim.nudges(coached) if coached else None,
        "n_pilot_rows_discarded": len(pilot),
    }


# ------------------------------------------------------------------------------------------------ the feasibility pilot (declared in advance)
def _yes(v) -> bool:
    return v is True or str(v).strip().lower() in ("yes", "true", "1", "1.0")


def unassisted_cases(rows: list[dict]) -> list[dict]:
    """The pre-test and the post-test of every block row, as {points, actions, cap, capped}."""
    out = []
    for r in rows:
        out.append({"points": float(r["pre_points"]), "actions": float(r["pre_actions"]), "cap": float(r.get("pre_cap") or 0), "capped": _yes(r.get("pre_capped"))})
        out.append({"points": float(r["post_checks_done"]), "actions": float(r["post_actions"]), "cap": float(r.get("post_cap") or 0), "capped": _yes(r.get("post_capped"))})
    return out


def pilot_verdict(rows: list[dict], costs_per_participant: list[float]) -> dict:
    """Is this participant option usable? ``rows`` are the pilot CSV rows (A/A arm only, 3 participants x 2 blocks). Criteria, all decided here in code (the PILOT_* constants):
    floor (share of unassisted cases scoring 0), ceiling (share fully correct), cap-binding (share that end by cap or use at least 95% of their cap), no harness exclusion."""
    cases = unassisted_cases(rows)
    n = len(cases)
    excluded = sorted({r["participant"] for r in rows if str(r.get("exclusion", "")).strip()})
    zero = sum(1 for c in cases if c["points"] <= 0) / n if n else 1.0
    full = sum(1 for c in cases if c["points"] >= 2) / n if n else 0.0
    bound = sum(1 for c in cases if c["capped"] or (c["cap"] and c["actions"] >= CAP_USED_SHARE * c["cap"])) / n if n else 1.0
    reasons = []
    if not n:
        reasons.append("no pilot rows")
    if zero > PILOT_MAX_SHARE_ZERO:
        reasons.append(f"floor: {zero:.0%} of the unassisted pilot cases scored 0 (at most {PILOT_MAX_SHARE_ZERO:.0%})")
    if full > PILOT_MAX_SHARE_FULL:
        reasons.append(f"ceiling: {full:.0%} of the unassisted pilot cases were fully correct (at most {PILOT_MAX_SHARE_FULL:.0%}): no room for a coach to help")
    if bound > PILOT_MAX_SHARE_CAP_BOUND:
        reasons.append(f"cap: {bound:.0%} of the unassisted pilot cases ended by the cap or used at least {CAP_USED_SHARE:.0%} of it (at most {PILOT_MAX_SHARE_CAP_BOUND:.0%}): the cap binds before the skills are reached")
    if excluded:
        reasons.append(f"harness exclusions in the pilot: {excluded}")
    cost = statistics.fmean(costs_per_participant) if costs_per_participant else None
    return {"usable": not reasons, "reasons": reasons, "n_unassisted_cases": n, "share_zero": round(zero, 3), "share_full": round(full, 3), "share_cap_bound": round(bound, 3),
            "mean_cost_per_participant_usd": None if cost is None else round(cost, 4), "points": [c["points"] for c in cases],
            "criteria": {"max_share_zero": PILOT_MAX_SHARE_ZERO, "max_share_full": PILOT_MAX_SHARE_FULL, "max_share_cap_bound": PILOT_MAX_SHARE_CAP_BOUND, "cap_used_share": CAP_USED_SHARE}}


def plan_units(mean_cost: float | None, budget_left: float, roles_left: int, *, max_units: int = 3) -> dict:
    """How many whole UNITS (8 participants each: 4 coached + 4 A/A, balanced within a pair of skills) a role can afford: the largest u (at most 3) with
    u * 8 * mean_cost * COST_SAFETY <= budget_left / roles_left. Fewer than MIN_UNITS: the role is not run (it could not say anything). The cost of a role participant is the
    pilot's per-participant cost times STUDY_VS_PILOT and COST_SAFETY."""
    if not mean_cost or mean_cost <= 0:
        return {"units": 0, "run": False, "why": "no measured pilot cost"}
    share = budget_left / max(roles_left, 1)
    unit_cost = 8 * mean_cost * STUDY_VS_PILOT * COST_SAFETY
    u = min(max_units, int(share // unit_cost))
    return {"units": u, "participants": 8 * u, "coached": 4 * u, "aa": 4 * u, "estimated_cost_usd": round(u * unit_cost, 2), "unit_cost_usd": round(unit_cost, 2), "budget_share_usd": round(share, 2),
            "run": u >= MIN_UNITS, "why": "" if u >= MIN_UNITS else f"fewer than {MIN_UNITS} units affordable: the study would be too small to say anything"}
