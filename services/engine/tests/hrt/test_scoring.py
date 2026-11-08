"""Proper scoring rules, calibration and the paired person-cluster bootstrap (PLAN.md sections 3.3 and 6)."""
from __future__ import annotations

import numpy as np

from understudy_engine.hrt import scoring as sc


def _world(n_people: int = 20, per: int = 150, seed: int = 0, slope: float = 1.0, shift: float = 0.0):
    rng = np.random.default_rng(seed)
    person = np.repeat(np.arange(n_people), per)
    z = rng.normal(-0.8, 1.2, n_people * per)
    p_true = 1 / (1 + np.exp(-z))
    y = (rng.random(z.size) < p_true).astype(float)
    p_forecast = 1 / (1 + np.exp(-(slope * z + shift)))
    return person.astype(str), y, p_true, p_forecast


def test_log_loss_and_brier_match_hand_values():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p = np.array([0.8, 0.2, 0.5, 0.5])
    assert np.isclose(sc.log_losses(y, p).mean(), -(np.log(0.8) + np.log(0.8) + 2 * np.log(0.5)) / 4)
    assert np.isclose(sc.brier_losses(y, p).mean(), (0.04 + 0.04 + 0.25 + 0.25) / 4)


def test_probabilities_are_clipped_so_one_bin_costs_at_most_4_6_nats():
    assert np.isclose(sc.B_LOSS, 4.60517, atol=1e-4)
    assert sc.log_losses(np.array([1.0]), np.array([0.0]))[0] <= sc.B_LOSS + 1e-12
    assert sc.log_losses(np.array([0.0]), np.array([1.0]))[0] <= sc.B_LOSS + 1e-12


def test_proper_scoring_rule_truth_beats_a_distorted_forecast():
    _, y, p_true, _ = _world(40, 300, 1)
    distorted = 1 / (1 + np.exp(-(2.0 * np.log(p_true / (1 - p_true)))))
    assert sc.log_losses(y, p_true).mean() < sc.log_losses(y, distorted).mean()
    assert sc.brier_losses(y, p_true).mean() < sc.brier_losses(y, distorted).mean()
    assert sc.log_losses(y, p_true).mean() < sc.log_losses(y, np.full_like(y, y.mean())).mean()


def test_calibration_slope_is_near_one_for_a_calibrated_forecast_and_below_one_when_overconfident():
    _, y, p_true, _ = _world(40, 400, 2)
    a, b = sc.calibration_fit(y, p_true)
    assert abs(b - 1.0) < 0.12 and abs(a) < 0.12
    over = 1 / (1 + np.exp(-(2.5 * np.log(p_true / (1 - p_true)))))
    a2, b2 = sc.calibration_fit(y, over)
    assert b2 < 0.6


def test_ece_and_reliability_table_for_a_perfectly_flat_forecast():
    y = np.array([1.0] * 3 + [0.0] * 7)
    p = np.full(10, 0.3)
    t = sc.reliability_table(y, p)
    assert len(t) == 1 and t[0]["n"] == 10 and np.isclose(t[0]["freq"], 0.3) and t[0]["freq_lo"] < 0.3 < t[0]["freq_hi"]
    assert np.isclose(sc.ece(y, p), 0.0)


def test_paired_bootstrap_shares_resamples_and_is_reproducible():
    person, y, p_true, _ = _world(30, 120, 3)
    base = np.full_like(y, y.mean())
    cl = sc.Clusters.from_labels(person)
    M = sc.multiplicities(cl.C, 400, 7)
    d1 = sc.paired_difference(sc.log_losses(y, p_true), sc.log_losses(y, base), cl, M)
    d2 = sc.paired_difference(sc.log_losses(y, p_true), sc.log_losses(y, base), cl, sc.multiplicities(cl.C, 400, 7))
    assert d1 == d2
    assert d1["est"] < 0 and d1["ci"][1] < 0 and d1["verdict"] == "a better"
    # a predictor against itself: a difference of exactly zero with a zero-width interval
    z = sc.paired_difference(sc.log_losses(y, p_true), sc.log_losses(y, p_true), cl, M)
    assert z["est"] == 0.0 and z["ci"] == [0.0, 0.0] and z["verdict"] == "no clear difference"


def test_the_interval_resamples_people_so_it_is_wider_than_one_that_resamples_bins():
    # people differ in base rate: bins within a person are not independent, so the person bootstrap must be wider
    rng = np.random.default_rng(5)
    people = 12
    person = np.repeat(np.arange(people), 400).astype(str)
    rate = rng.uniform(0.05, 0.6, people)
    y = (rng.random(people * 400) < np.repeat(rate, 400)).astype(float)
    p = np.full_like(y, y.mean())
    losses = sc.log_losses(y, p)
    cl = sc.Clusters.from_labels(person)
    wide = sc.mean_with_interval(losses, cl, sc.multiplicities(cl.C, 1000, 1))["ci"]
    rows = sc.Clusters.from_labels(np.arange(y.size).astype(str))
    narrow = sc.mean_with_interval(losses, rows, sc.multiplicities(rows.C, 200, 1))["ci"]
    assert (wide[1] - wide[0]) > 2 * (narrow[1] - narrow[0])


def test_score_binary_reports_every_predictor_and_pairs_the_primary():
    person, y, p_true, _ = _world(24, 150, 4)
    out = sc.score_binary(y, {"model": p_true, "base": np.full_like(y, y.mean())}, person, primary="model", B=300, calibration_draws=60)
    assert set(out["predictors"]) == {"model", "base"} and set(out["paired_log_loss_vs"]) == {"base"}
    cal = out["predictors"]["model"]["calibration"]
    assert cal["slope_contains_1"] and cal["intercept_contains_0"]
    assert out["paired_log_loss_vs"]["base"]["verdict"] == "a better"
    assert out["n_clusters"] == 24 and out["bootstrap"]["unit"] == "people"


def test_truncated_crps_handles_censoring_without_imputing():
    K = 4
    cdf = np.array([[0.25, 0.5, 0.75, 1.0], [0.25, 0.5, 0.75, 1.0], [0.0, 0.0, 0.0, 0.0]])
    # row 0: event in step 2 (observed all 4 steps); row 1: censored after 2 steps with no event; row 2: no event in 4 steps against a CDF of 0 (perfect)
    event = np.array([2, -1, -1])
    obs = np.array([4, 2, 4])
    out = sc.truncated_crps(cdf, event, obs, step_s=30.0)
    assert np.isclose(out[0], np.mean([(0.25 - 0) ** 2, (0.5 - 1) ** 2, (0.75 - 1) ** 2, (1.0 - 1) ** 2]) * 30.0)
    assert np.isclose(out[1], np.mean([0.25 ** 2, 0.5 ** 2]) * 30.0)          # only the 2 observed steps count
    assert out[2] == 0.0
    # a sharper correct CDF scores better than a vague one
    sharp = np.array([[0.0, 1.0, 1.0, 1.0]])
    vague = np.array([[0.25, 0.5, 0.75, 1.0]])
    e, o = np.array([2]), np.array([4])
    assert sc.truncated_crps(sharp, e, o, 30.0)[0] < sc.truncated_crps(vague, e, o, 30.0)[0]


def test_calibration_fit_converges_for_an_anti_informative_and_a_saturated_forecast():
    rng = np.random.default_rng(11)
    n = 6000
    p_true = rng.uniform(0.1, 0.9, n)
    y = (rng.random(n) < p_true).astype(float)
    flipped = 1.0 - p_true                      # a forecast that says the opposite: the slope is about -1
    a, b = sc.calibration_fit(y, flipped)
    assert -1.3 < b < -0.7 and abs(a) < 1.0
    saturated = np.where(rng.random(n) < 0.5, 0.0, 1.0)      # clipped to 0.01 and 0.99, unrelated to y
    a2, b2 = sc.calibration_fit(y, saturated)
    assert np.isfinite(a2) and np.isfinite(b2) and abs(b2) < 1.0
    w = rng.integers(0, 3, n).astype(float)     # weights (bootstrap multiplicities) work the same
    a3, b3 = sc.calibration_fit(y, p_true, weights=w)
    assert abs(b3 - 1.0) < 0.2
