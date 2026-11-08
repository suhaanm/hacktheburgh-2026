import json

import numpy as np
import pytest

from understudy_engine.routing import control as C
from understudy_engine.routing.cases import FEATURES, simulate_cases, split_indices
from understudy_engine.routing.evaluate import _one_resplit, evaluate_routing, evaluate_routing_synthetic
from understudy_engine.routing.model import RoutingModel
from understudy_engine.trust.stats import clopper_pearson_upper


def test_case_generator_is_deterministic_and_has_a_sensible_error_rate():
    a, b = simulate_cases(1500, seed=3), simulate_cases(1500, seed=3)
    assert np.array_equal(a.X, b.X) and np.array_equal(a.y, b.y)
    assert 0.07 < a.y.mean() < 0.20
    assert a.X.shape[1] == len(FEATURES) and "p_true" not in FEATURES and "y" not in FEATURES
    # the observable signals carry information, as designed
    assert a.col("disagree")[a.y == 1].mean() > a.col("disagree")[a.y == 0].mean()
    assert a.col("agent_confidence")[a.y == 1].mean() < a.col("agent_confidence")[a.y == 0].mean()
    assert abs(a.p_true.mean() - a.y.mean()) < 0.02


def test_splits_partition_the_cases():
    tr, ca, te = split_indices(1000, 0)
    assert len(set(tr) | set(ca) | set(te)) == 1000 and not (set(tr) & set(ca)) and not (set(ca) & set(te))


def test_platt_calibration_never_changes_the_order_of_cases():
    c = simulate_cases(3000, seed=1)
    tr, ca, te = split_indices(c.n, 1)
    m = RoutingModel().fit(c.X[tr], c.y[tr]).calibrate(c.X[ca], c.y[ca])
    raw, cal = m.raw(c.X[te]), m.predict(c.X[te])
    assert np.array_equal(np.argsort(raw, kind="stable"), np.argsort(cal, kind="stable"))


def test_risk_control_picks_the_largest_set_whose_bound_is_under_alpha():
    n = 1000
    risk = np.linspace(0, 1, n)
    y = np.zeros(n, int)
    y[900:] = 1                                  # the riskiest 10% always err, the rest never
    r = C.risk_control(risk, y, alpha=0.05, delta=0.05, n_grid=20, correction="none")
    assert r["feasible"] and r["errors"] == 0
    # error-free prefix of 900 cases: its bound is tiny; adding the error-heavy tail breaks it. The chosen set stops at the tail.
    assert 0.85 <= r["coverage"] <= 0.90
    assert r["upper_bound"] <= 0.05
    assert clopper_pearson_upper(0, r["k"], 0.05) == pytest.approx(r["upper_bound"])


def test_bonferroni_is_never_larger_than_naive_and_tighter_alpha_means_smaller_sets():
    c = simulate_cases(4000, seed=0)
    tr, ca, te = split_indices(c.n, 0)
    m = RoutingModel().fit(c.X[tr], c.y[tr]).calibrate(c.X[ca], c.y[ca])
    rc = m.predict(c.X[ca])
    cov = {}
    for alpha in (0.03, 0.05, 0.10):
        b = C.risk_control(rc, c.y[ca], alpha, correction="bonferroni")["coverage"]
        n_ = C.risk_control(rc, c.y[ca], alpha, correction="none")["coverage"]
        assert b <= n_
        cov[alpha] = b
    assert cov[0.03] <= cov[0.05] <= cov[0.10]


def test_infeasible_alpha_certifies_nothing_and_approves_nothing():
    risk = np.linspace(0, 1, 200)
    y = np.ones(200, int)
    r = C.risk_control(risk, y, alpha=0.05)
    assert not r["feasible"] and r["coverage"] == 0.0 and r["threshold"] == -np.inf
    chk = C.check_heldout(r["threshold"], risk, y, 0.05)
    assert chk["approved"] == 0 and chk["error_rate"] is None and not chk["violated"]


def test_check_heldout_flags_a_real_violation():
    risk = np.linspace(0, 1, 1000)
    y = np.zeros(1000, int); y[:400] = (np.arange(400) % 4 == 0)   # 25% errors among the approved
    chk = C.check_heldout(0.4, risk, y, alpha=0.05)
    assert chk["violated"] and not chk["observed_within_alpha"] and chk["ci"][0] > 0.05


def test_risk_coverage_curve_shape_and_ordering_of_rankers():
    c = simulate_cases(4000, seed=2)
    tr, ca, te = split_indices(c.n, 2)
    m = RoutingModel().fit(c.X[tr], c.y[tr]).calibrate(c.X[ca], c.y[ca])
    curve = C.risk_coverage_curve(m.predict(c.X[te]), c.y[te])
    assert curve[-1]["coverage"] == pytest.approx(1.0) and curve[-1]["error_rate"] == pytest.approx(c.y[te].mean())
    assert all(p["ci"][0] <= p["error_rate"] <= p["ci"][1] for p in curve)
    # model beats random review and the confidence-only ranking. The true PRIOR probability ranks worse than the model
    # because disagreement and confidence carry information about the realised outcome.
    a_model = C.aurc(curve)
    a_conf = C.aurc(C.risk_coverage_curve(1 - c.col("agent_confidence")[te], c.y[te]))
    a_rand = C.aurc(C.risk_coverage_curve(np.random.default_rng(0).random(te.size), c.y[te]))
    a_orac = C.aurc(C.risk_coverage_curve(c.p_true[te], c.y[te]))
    assert a_model < a_conf < a_rand and a_model < a_orac < a_rand


def test_the_bound_holds_on_held_out_cases_across_fresh_draws():
    """The headline check for ANA-8: choose the set on calibration, then look at cases the choice never saw."""
    rows = [_one_resplit(100 + i, 3000, alpha=0.05, delta=0.05, correction="bonferroni") for i in range(30)]
    assert np.mean([r["violated"] for r in rows]) <= 0.10          # claimed delta is 0.05
    errs = [r["error"] for r in rows if r["error"] is not None]
    assert np.mean(errs) <= 0.05
    assert np.mean([r["feasible"] for r in rows]) >= 0.5           # and it is not vacuous: most draws certify some set
    assert np.mean([r["coverage"] for r in rows]) > 0.25


def test_evaluate_routing_output_contract_and_determinism():
    a = evaluate_routing_synthetic(n_cases=3000, seed=5, n_resplits=6, resplit_n=2000)
    b = evaluate_routing_synthetic(n_cases=3000, seed=5, n_resplits=6, resplit_n=2000)
    a["meta"].pop("generated_at"); b["meta"].pop("generated_at")
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    for k in ("alpha", "curve", "held_out_error", "held_out_ci", "bound_held", "expert_minutes_per_case"):
        assert k in a
    assert set(a["curve"][0]) >= {"coverage", "risk", "ci"} and len(a["curve"][0]["ci"]) == 2
    assert a["bound_held"] in (True, False) and a["meta"]["n_unit"] == "households" and a["origin"] == "synthetic"
    assert a["expert_minutes_per_case"] == pytest.approx((1 - a["held_out"]["coverage"]) * a["review_minutes_assumed_per_case"])
    assert a["expert_minutes_per_case"] < a["expert_minutes_review_all"]
    assert a["caveats"]
    # baselines: the model certifies at least as much as the single-signal rankers
    assert a["held_out"]["coverage"] >= a["baselines"]["agent_confidence_only"]["held_out_coverage"]
    assert a["baselines"]["random"]["held_out_coverage"] == 0.0
    # fixed review budget: the share reviewed is the budget and the escaping-error rate is reported with its interval
    fb = a["fixed_review_budget"]
    assert fb["reviewed"] / (fb["reviewed"] + fb["auto_approved"]) == pytest.approx(0.30, abs=0.01)
    assert fb["share_of_errors_caught"] > 0.5 and len(fb["held_out_ci"]) == 2
    assert a["resplits"]["bonferroni"]["violation_rate"] <= a["resplits"]["none"]["violation_rate"] + 0.2


def test_review_budget_beats_random_review_at_the_same_budget():
    a = evaluate_routing_synthetic(n_cases=4000, seed=1, n_resplits=0)
    fb = a["fixed_review_budget"]
    random_caught = 0.30     # random review catches 30% of errors in expectation
    assert fb["share_of_errors_caught"] > random_caught + 0.25


# ---------------- A4: cases from the sandbox households ----------------
sandbox = pytest.importorskip("understudy_agent.sandbox_sites.oracle", reason="agent package not importable")


def test_sandbox_cases_label_and_features_follow_the_definition():
    from understudy_agent.sandbox_sites import oracle
    from understudy_agent.sandbox_sites.households import generate_households
    from understudy_engine.routing.sandbox import agent_answer, sandbox_cases
    c = sandbox_cases(240, seed=7)
    hs = generate_households(240, 7)
    assert c.n == 240 and c.X.shape == (240, len(c.features)) and c.origin == "synthetic"
    for i in (0, 15, 100, 239):
        answers = [oracle.site_expected(s, hs[i])["uc_monthly"] for s in "abc"]
        ref = oracle.score(hs[i])["uc_monthly"]
        assert c.y[i] == int(abs(agent_answer(answers) - ref) > 1.0)
    # no oracle value or label hides in the features
    assert "oracle" not in " ".join(c.features) and "label" not in " ".join(c.features)
    for j in range(c.X.shape[1]):
        assert not (c.X[:, j].std() > 0 and np.array_equal(c.X[:, j], c.y.astype(float)) and c.y.any())


def test_stated_confidence_depends_only_on_disagreement():
    from understudy_engine.routing.sandbox import stated_confidence
    assert stated_confidence([100.0, 100.4, 99.8], [True] * 3)[0] == pytest.approx(0.98, abs=0.01)      # all within a pound
    conf, pairs, distinct = stated_confidence([0.0, 174.0, 348.0], [False, True, True])
    assert pairs == 3 and distinct == 2 and conf < 0.6
    # identical disagreement pattern, different absolute level -> same confidence
    assert stated_confidence([10.0, 10.0, 60.0], [True] * 3)[0] == stated_confidence([500.0, 500.0, 550.0], [True] * 3)[0]


def test_stand_in_agents_behave_as_described():
    from understudy_engine.routing.sandbox import sandbox_cases
    med = sandbox_cases(300, 7, "median_of_three")
    assert med.y.sum() == 0                                  # the median of three always recovers the oracle here
    maj = sandbox_cases(600, 7, "majority_else_mean")
    errs = maj.extra["errors_by_archetype"]
    assert {a for a, v in errs.items() if v["errors"]} == {"savings_cliff_16k"}
    assert 0.02 < maj.y.mean() < 0.08
    assert sandbox_cases(300, 7, "mean_of_three").y.mean() > 0.15
    with pytest.raises(ValueError):
        sandbox_cases(30, 1, "vibes")


def test_sandbox_routing_headline_contract_bound_and_honest_notes():
    a = evaluate_routing(n_cases=600, seed=3, n_resplits=5, resplit_n=400)
    b = evaluate_routing(n_cases=600, seed=3, n_resplits=5, resplit_n=400)
    for r in (a, b):
        r["meta"].pop("generated_at"); r["secondary"]["meta"].pop("generated_at")
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    for k in ("alpha", "curve", "held_out_error", "held_out_ci", "bound_held", "expert_minutes_per_case"):
        assert k in a
    assert a["meta"]["n_unit"] == "households" and a["meta"]["origin"] == "synthetic"
    assert "sandbox" in a["headline_source"] and "simplified" in a["meta"]["note"]
    assert any("CIRCULARITY" in c for c in a["caveats"]) and any("simplified internal rule set" in c for c in a["caveats"])
    assert a["bound_held"] and a["held_out"]["coverage"] > 0.8
    assert a["expert_minutes_per_case"] < a["expert_minutes_review_all"] / 2
    assert a["resplits"]["bonferroni"]["violation_rate"] == 0.0
    assert a["secondary"]["meta"]["n_unit"] == "households" and "pure generator" in a["secondary"]["source"]
    assert {x["stand_in"] for x in a["stand_ins"]} == {"majority_else_mean", "mean_of_three", "median_of_three"}
    assert a["case_set"]["errors_by_archetype"]["savings_cliff_16k"]["errors"] > 0
    json.dumps(a, default=str)


def test_sandbox_routing_fast_is_quick():
    import time
    t = time.time()
    r = evaluate_routing(fast=True)
    assert time.time() - t < 30 and r["resplits"]["bonferroni"]["n_resplits"] == 10 and "stand_ins" not in r
