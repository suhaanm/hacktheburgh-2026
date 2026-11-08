"""The analysis on made-up numbers (never on model output): headline, A/A, design check, pilot verdict, unit planning, report and section."""
from __future__ import annotations

import json

import pytest

from evals.study_roles import LABEL
from evals.study_roles import analysis as AN
from evals.study_roles import analysis_rows as AR
from evals.study_roles import report
from evals.study_roles.section import evaluate_study_roles

from .conftest import made_up_rows


def test_headline_is_the_mean_of_coached_minus_uncoached_post_points_over_two(specs):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 1)
    a = AN.analyse_role(specs[0].role, rows)
    h = a["headline"]
    assert h["n"] == 12 and h["mean_difference"] == 0.5 and h["ci_degenerate"] is True and h["sign_flip_p_two_sided"] == round(2 / 2 ** 12, 6)
    assert a["design_problems"] == [] and a["aa"]["n"] == 12 and a["n_pilot_rows_discarded"] == 0


def test_no_difference_when_coaching_does_nothing_and_aa_is_zero_by_construction(specs):
    rows = made_up_rows(specs, lambda s, b: 1)
    a = AN.analyse_role(specs[0].role, rows)
    assert a["headline"]["mean_difference"] == 0.0 and a["aa"]["mean_difference"] == 0.0
    rel = a["aa"]["relabelling"]
    assert rel["n"] == 12 and rel["relabellings"] == 924 and rel["share_sign_flip_p_below_05"] == 0.0
    rows2 = made_up_rows(specs, lambda s, b: 1, aa_post_fn=lambda s, b: 2 if (b.skill == s.pair[0]) == (s.index % 2 == 1) else 0)   # half the A/A people score +1, half -1
    rel2 = AN.analyse_role(specs[0].role, rows2)["aa"]["relabelling"]
    assert rel2["share_sign_flip_p_below_05"] > 0.0 and rel2["n"] == 12


def test_pre_to_post_change_contrast_removes_a_baseline_difference(specs):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 1, pre_fn=lambda s, b: 1 if b.nominal_condition == "coached" else 0)
    a = AN.analyse_role(specs[0].role, rows)
    assert a["headline"]["mean_difference"] == 0.5
    assert a["change_pre_to_post"]["mean_difference"] == 0.0           # (2-1)/2 - (1-0)/2


def test_a_design_deviation_is_listed_not_hidden(specs):
    rows = made_up_rows(specs, lambda s, b: 1)
    rows[0]["post_case"] = "somewhere/v9"
    rows[1]["condition"] = "coached"
    probs = AN.design_check(rows, specs[0].role)
    assert any("differs from the fixed design" in p for p in probs) and any("one coached and one uncoached" in p for p in probs)


def test_excluded_participants_drop_out_entirely(specs):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 0)
    for r in rows:
        if r["participant"] == specs[0].pid and r["block"] == 2.0:
            r["exclusion"] = "harness error"
    a = AN.analyse_role(specs[0].role, rows)
    assert a["headline"]["n"] == 11 and specs[0].pid in a["excluded_participants"]


def test_pilot_rows_never_enter_the_analysis(specs):
    rows = made_up_rows(specs, lambda s, b: 1)
    for r in rows[:4]:
        r["arm"] = "pilot"
    a = AN.analyse_role(specs[0].role, rows)
    assert a["n_pilot_rows_discarded"] == 4 and a["headline"]["n"] + a["aa"]["n"] <= 24


def test_per_skill_reports_baseline_floor_and_ceiling(specs, role):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 1, pre_fn=lambda s, b: 2)
    ps = AN.analyse_role(role, rows)["per_skill"]
    assert set(ps) == set(__import__("evals.study_roles.roles", fromlist=["cfg"]).cfg(role).skills)
    assert all(v["baseline_share_full"] == 1.0 and v["baseline_share_zero"] == 0.0 for v in ps.values())


def _pilot_rows(pre, post=None, capped="no", actions=10, cap=40):
    post = post if post is not None else pre
    return [{"participant": f"p{i}", "pre_points": float(x), "post_checks_done": float(post[i]), "pre_actions": float(actions), "post_actions": float(actions), "pre_cap": float(cap), "post_cap": float(cap),
             "pre_capped": capped, "post_capped": capped, "exclusion": ""} for i, x in enumerate(pre)]


def test_pilot_floor_ceiling_cap_binding_and_exclusion_criteria():
    ok = AN.pilot_verdict(_pilot_rows([0, 1, 1, 2, 0, 1], [1, 1, 0, 1, 2, 1]), [0.1, 0.15, 0.12])
    assert ok["usable"] and ok["n_unassisted_cases"] == 12 and ok["share_zero"] == round(3 / 12, 3) and ok["mean_cost_per_participant_usd"] == 0.1233
    floor = AN.pilot_verdict(_pilot_rows([0, 0, 0, 1, 0, 0], [0, 0, 0, 0, 1, 0]), [0.3])
    assert not floor["usable"] and floor["reasons"][0].startswith("floor") and floor["share_zero"] == round(10 / 12, 3)
    ceil = AN.pilot_verdict(_pilot_rows([2, 2, 2, 2, 2, 1], [2, 2, 2, 2, 2, 2]), [0.3])
    assert not ceil["usable"] and any("ceiling" in r for r in ceil["reasons"])
    capped = AN.pilot_verdict(_pilot_rows([1, 1, 1, 1, 1, 1], capped="yes"), [0.3])
    assert not capped["usable"] and any(r.startswith("cap") for r in capped["reasons"]) and capped["share_cap_bound"] == 1.0
    used95 = AN.pilot_verdict(_pilot_rows([1, 1, 1, 1, 1, 1], actions=38, cap=40), [0.3])                 # 38 of 40 = 95%: the cap binds even without a cap flag
    assert not used95["usable"] and used95["share_cap_bound"] == 1.0
    some = AN.pilot_verdict(_pilot_rows([1, 1, 1, 1, 1, 1], actions=37, cap=40), [0.3])                   # 92.5%: not bound
    assert some["usable"] and some["share_cap_bound"] == 0.0
    rows = _pilot_rows([1, 1, 1, 1, 1, 1])
    rows[0]["exclusion"] = "harness error"
    assert not AN.pilot_verdict(rows, [0.3])["usable"]
    assert not AN.pilot_verdict([], [])["usable"]
    # the cap binding and the floor are both judged on the same unassisted cases, and the thresholds are the ones declared in the plan
    assert (AN.PILOT_MAX_SHARE_ZERO, AN.PILOT_MAX_SHARE_FULL, AN.PILOT_MAX_SHARE_CAP_BOUND, AN.CAP_USED_SHARE) == (0.5, 0.8, 0.25, 0.95)


def test_unit_planning_from_the_measured_pilot_cost():
    p = AN.plan_units(0.05, 7.0, 2)                      # a role may spend 3.5; one unit costs 8 * 0.05 * 1.5 * 1.3 = 0.78
    assert p["units"] == 3 and p["run"] and p["participants"] == 24 and p["coached"] == p["aa"] == 12 and p["unit_cost_usd"] == 0.78
    p = AN.plan_units(0.15, 7.0, 2)                      # one unit 2.34 -> 1 unit: the role is not run
    assert p["units"] == 1 and not p["run"] and "fewer than 2" in p["why"]
    p = AN.plan_units(0.10, 7.0, 2)                      # one unit 1.56 -> 2 units
    assert p["units"] == 2 and p["run"] and p["estimated_cost_usd"] == 3.12
    p = AN.plan_units(0.10, 7.0, 1)                      # the second role gets all that is left
    assert p["units"] == 3 and p["run"]
    assert not AN.plan_units(None, 7.0, 2)["run"] and AN.plan_units(0.001, 100.0, 1)["units"] == 3


def test_csv_round_trip_and_report(tmp_path, specs, role):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 1)
    out = tmp_path / "res"
    out.mkdir()
    AR.write_csv(out / "participants.csv", rows)
    back = AR.load_rows(out / "participants.csv")
    assert len(back) == len(rows) and back[0]["post_checks_done"] == rows[0]["post_checks_done"] and back[0]["pre_points"] == rows[0]["pre_points"]
    s = report.write_all(role, out)
    assert s["status"] == "ok" and s["headline"]["n"] == 12 and s["label"] == LABEL == "language-model participants, not people"   # the D57 wording: never "simulated" in a string a person reads
    md = (out / "REPORT.md").read_text()
    assert "not people" in md and "Primary outcome" in md and "Limits" in md
    assert json.loads((out / "summary.json").read_text())["role"] == role
    assert (out / "PROVENANCE.json").exists()


def test_section_is_not_run_without_results_and_never_the_live_study(tmp_path):
    s = evaluate_study_roles(tmp_path)
    assert s["status"] == "not_run" and "not been run" in s["reason"] and s["roles"] == {} and "never feeds the live" in s["meta"]["note"].lower()
    assert "not people" in s["label"]


def test_section_reads_results_when_they_exist(tmp_path, specs, role):
    rows = made_up_rows(specs, lambda s, b: 2 if b.nominal_condition == "coached" else 1)
    d = tmp_path / role
    d.mkdir()
    AR.write_csv(d / "participants.csv", rows)
    report.write_all(role, d)
    (d / "PILOT_fast.json").write_text(json.dumps({"usable": True}))
    s = evaluate_study_roles(tmp_path)
    assert s["status"] in ("ok", "partial") and role in s["roles"] and s["roles"][role]["headline"]["n"] == 12 and f"{role}/PILOT_fast" in s["pilots"]


def test_fast_sign_flip_equals_the_reference():
    import random
    from evals.study_roles.analysis import A, _flip_p
    rng = random.Random(1)
    for n in (4, 7, 10):
        d = [rng.choice([-1, 0, 0.5, 1, 2]) for _ in range(n)]
        assert abs(_flip_p(d) - A.sign_flip_p(d)) < 1e-12


def test_excluded_pilot_participants_are_not_counted_as_zeros_but_make_the_pilot_unusable():
    rows = _pilot_rows([2, 2, 1, 2, 2, 1], [2, 2, 1, 2, 2, 1])
    for r in rows[:2]:
        r["exclusion"] = "harness error"
        r["pre_points"], r["post_checks_done"] = 0.0, 0.0                   # what an unfinished participant leaves behind
    v = AN.pilot_verdict(rows, [0.13])
    assert not v["usable"] and v["n_unassisted_cases"] == 8 and v["share_zero"] == 0.0 and any("harness exclusions" in r for r in v["reasons"]) and not any(r.startswith("floor") for r in v["reasons"])
