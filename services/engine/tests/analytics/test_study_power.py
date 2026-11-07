import hashlib
import json
import random

import numpy as np
import pytest

from understudy_engine.store.paths import repo_root
from understudy_engine.study_power import evaluate_study_power
from understudy_engine.study_power import model as M

ANALYZE = repo_root() / "evals" / "study" / "analyze.py"
pytestmark = pytest.mark.skipif(not ANALYZE.is_file(), reason="pre-registered analysis not present")


def test_the_preregistered_analysis_is_imported_and_left_untouched():
    before = hashlib.sha256(ANALYZE.read_bytes()).hexdigest()
    an = M.load_analysis()
    assert callable(an.t_interval) and callable(an.sign_flip_p) and an.POSSIBLE == M.POSSIBLE
    evaluate_study_power(fast=True)
    assert hashlib.sha256(ANALYZE.read_bytes()).hexdigest() == before


def test_vectorised_sign_flip_equals_the_plans_exact_function():
    an = M.load_analysis()
    rng = random.Random(0)
    for n in (1, 2, 3, 4, 5, 6, 8, 10, 12):
        rows = [[rng.choice((-1.0, -0.5, 0.0, 0.5, 1.0)) for _ in range(n)] for _ in range(25)]
        got = M.sign_flip_p_vec(np.array(rows))
        for r, g in zip(rows, got):
            assert an.sign_flip_p(r) == pytest.approx(g, abs=1e-12)
    with pytest.raises(ValueError):
        M.sign_flip_p_vec(np.array([[0.3, 0.2]]))


def test_vectorised_t_interval_equals_the_plans_function():
    an = M.load_analysis()
    rng = np.random.default_rng(1)
    D = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], size=(60, 7))
    mean, lo, hi = M.t_interval_vec(D)
    for i in range(60):
        m, l, h = an.t_interval([float(x) for x in D[i]])
        assert (m, l, h) == pytest.approx((mean[i], lo[i], hi[i]), abs=1e-12)


def test_design_is_the_exact_counterbalance_and_n_must_be_balanced():
    seqs = M.sequences()
    assert set(seqs) == {"S1", "S2", "S3", "S4"}
    assert seqs["S1"] == [("cliff", "coached"), ("reconcile", "uncoached")]
    assert seqs["S4"] == [("reconcile", "uncoached"), ("cliff", "coached")]
    for skill in ("cliff", "reconcile"):                   # each skill coached for two sequences, first and second block alike
        assert sum(1 for s in seqs.values() for sk, c in s if sk == skill and c == "coached") == 2
    assert sum(1 for s in seqs.values() if s[0][1] == "coached") == 2
    with pytest.raises(ValueError):
        M.simulate_differences(6, 10, 0.0, 0.0, 0.0)


def test_scores_are_the_real_discrete_values_and_seeded():
    D = M.simulate_differences(8, 400, 1.0, 0.0, 0.0, seed=3)
    assert D.shape == (400, 8) and set(np.unique(D)) <= {-1.0, -0.5, 0.0, 0.5, 1.0}
    assert np.array_equal(D, M.simulate_differences(8, 400, 1.0, 0.0, 0.0, seed=3))
    assert not np.array_equal(D, M.simulate_differences(8, 400, 1.0, 0.0, 0.0, seed=4))


def test_true_effect_in_probability_points():
    assert M.true_effect(0.0) == pytest.approx(0.0, abs=1e-12)
    pp = [100 * M.true_effect(g) for g in (0.5, 1.0, 2.0)]
    assert pp == sorted(pp) and 8 < pp[0] < 13 and 17 < pp[1] < 25 and 33 < pp[2] < 45


def test_skill_difficulty_cancels_in_the_balanced_design():
    # very different baselines for the two skills; no coaching effect: the mean difference is still about zero
    pop = M.Population(mu_cliff=-2.0, mu_reconcile=1.0)
    D = M.simulate_differences(4, 20000, 0.0, 0.0, 0.0, pop=pop, seed=5)
    assert abs(D.mean()) < 0.01
    # but individual differences are large: that variance is what costs power
    assert D.std() > 0.5


def test_balanced_design_protects_against_generic_carryover_and_fatigue_but_not_spillover():
    n, reps = 24, 6000
    base = M.simulate_differences(n, reps, 0.0, 0.0, 0.0, seed=7).mean()
    nuis = M.simulate_differences(n, reps, 0.0, 1.0, -0.7, seed=7).mean()
    assert abs(nuis - base) < 0.012 and abs(nuis) < 0.012            # under no effect, nuisances do not move the estimate
    tau = M.true_effect(1.0)
    clean = M.simulate_differences(n, reps, 1.0, 0.0, 0.0, seed=8).mean()
    spill = M.simulate_differences(n, reps, 1.0, 1.0, 0.0, seed=8).mean()
    assert clean == pytest.approx(tau, abs=0.012)                    # unbiased with no nuisance
    assert spill < tau - 0.05                                        # spill-over dilutes the contrast: negative bias


def test_false_positive_rate_stays_near_nominal_under_nuisance():
    for kappa, omega in ((0.0, 0.0), (1.0, 0.0), (0.0, -0.7), (1.0, -0.7)):
        D = M.simulate_differences(24, 6000, 0.0, kappa, omega, seed=11)
        _, lo, hi = M.t_interval_vec(D)
        fp = ((lo > 0) | (hi < 0)).mean()
        assert 0.03 < fp < 0.075, (kappa, omega, fp)


def test_exact_enumeration_for_n4_says_only_uniform_large_differences_can_show():
    ex = evaluate_study_power(fast=True)["needed_difference_n4"]["exact_enumeration"]
    assert ex["ordered_patterns"] == 625 and ex["patterns_with_ci_above_zero"] == 16
    assert ex["every_difference_must_be_at_least"] == 0.5
    assert ex["smallest_mean_with_ci_above_zero_and_spread"] == pytest.approx(0.625)
    for e in ex["examples_ci_above_zero"]:
        assert min(e["d_sorted"]) >= 0.5 and e["ci"][0] > 0


def test_evaluate_study_power_shape_and_the_n4_facts():
    r = evaluate_study_power(fast=True)
    json.dumps(r, default=str)
    assert len(r["rows"]) == 5 * 4 * 3 * 2
    need = {"n", "true_effect_pp", "carryover", "order_effect", "power_ci", "power_p05", "bias", "coverage", "false_positive"}
    assert all(need <= set(row) for row in r["rows"])
    assert r["min_p_by_n"]["4"] == 0.125 and r["min_p_by_n"]["8"] == pytest.approx(2 / 256)
    n4 = [row for row in r["rows"] if row["n"] == 4]
    assert all(row["power_p05"] == 0.0 for row in n4)                # p < 0.05 is impossible at n = 4
    assert max(row["power_ci"] for row in n4) < 0.3                  # and even a large effect is rarely seen
    assert r["meta"]["origin"] == "synthetic" and r["meta"]["n_unit"] == "replications"
    assert r["limitations"] and all(set(x) == {"id", "text", "severity"} for x in r["limitations"])
    assert any("only shows" in x["text"] or "only" in x["text"] for x in r["limitations"])
    assert "impossible" in r["note"] and r["analysis_fidelity"]["max_abs_diff_ci"] < 1e-9
    assert r["analysis_fidelity"]["max_abs_diff_p"] == 0.0
    pp = [e["true_effect_pp"] for e in r["effects"]]
    assert pp == sorted(pp) and pp[0] == 0.0


def test_power_rises_with_n_and_with_effect_and_false_positives_stay_small():
    r = evaluate_study_power(fast=True, reps=1500)
    base = {(row["n"], row["effect_label"]): row for row in r["rows"] if row["carryover"] == 0.0 and row["order_effect"] == 0.0}
    large = [base[(n, "large")]["power_ci"] for n in (4, 8, 12, 16, 24)]
    assert large == sorted(large) and large[-1] > 0.8 and large[0] < 0.3
    n24 = [base[(24, e)]["power_ci"] for e in ("none", "small", "medium", "large")]
    assert n24 == sorted(n24)
    for n in (4, 8, 12, 16, 24):
        assert base[(n, "none")]["false_positive"] < 0.09
    assert all(0.85 < row["coverage"] <= 1.0 for row in base.values())


def test_deterministic_and_full_mode_uses_at_least_5000_replications():
    a = evaluate_study_power(fast=True)
    b = evaluate_study_power(fast=True)
    for x in (a, b):
        x["meta"].pop("generated_at")
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    full = evaluate_study_power()
    assert full["grid"]["replications_per_cell"] >= 5000 and full["meta"]["n"] >= 5000
    assert all(row["replications"] >= 5000 for row in full["rows"])
    n4 = [row for row in full["rows"] if row["n"] == 4]
    assert all(row["power_p05"] == 0.0 for row in n4)
