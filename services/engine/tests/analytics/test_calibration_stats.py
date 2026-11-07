import json
import math

import numpy as np
import pytest

from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust import calibration as cal
from understudy_engine.trust import stats


def test_wilson_matches_known_values():
    assert stats.wilson_lower(20, 20) == pytest.approx(0.8389, abs=1e-3)   # the spec's "about 0.84"
    assert stats.wilson_lower(73, 73) >= 0.95 > stats.wilson_lower(72, 72)  # 73 clean runs reach A3's bar
    lo, hi = stats.wilson_interval(0, 10)
    assert lo == 0.0 and 0.2 < hi < 0.4
    assert stats.wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = stats.wilson_interval(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    with pytest.raises(ValueError):
        stats.wilson_lower(5, 3)


def test_wilson_lower_monotone():
    # more successes at fixed n -> larger bound; more clean trials at fixed rate -> larger bound
    assert all(stats.wilson_lower(k, 30) < stats.wilson_lower(k + 1, 30) for k in range(30))
    assert stats.wilson_lower(10, 10) < stats.wilson_lower(30, 30)


def test_clopper_pearson_exact_cases():
    # k = 0: upper one-sided bound is 1 - alpha^(1/n)
    assert stats.clopper_pearson_upper(0, 29, 0.05) == pytest.approx(1 - 0.05 ** (1 / 29), abs=1e-9)
    assert stats.clopper_pearson_upper(0, 0) == 1.0
    lo, hi = stats.clopper_pearson(5, 20)
    assert lo < 0.25 < hi and lo == pytest.approx(0.0866, abs=2e-3) and hi == pytest.approx(0.4910, abs=2e-3)
    assert stats.clopper_pearson(0, 10)[0] == 0.0 and stats.clopper_pearson(10, 10)[1] == 1.0


def test_clopper_pearson_coverage_is_at_least_nominal():
    rng = np.random.default_rng(0)
    p, n, alpha, reps = 0.1, 40, 0.10, 3000
    k = rng.binomial(n, p, size=reps)
    ub = np.array([stats.clopper_pearson_upper(int(x), n, alpha) for x in k])
    assert (ub >= p).mean() >= 1 - alpha - 0.01  # exact bound is conservative


def test_log_loss_brier_ece_known_values():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.9, 0.1, 0.9, 0.1])
    assert cal.log_loss(y, p) == pytest.approx(-math.log(0.9))
    assert cal.brier(y, p) == pytest.approx(0.01)
    assert cal.ece(y, p) == pytest.approx(0.1)


def test_ece_near_zero_for_calibrated_predictions():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 40000)
    y = (rng.uniform(0, 1, p.size) < p).astype(int)
    assert cal.ece(y, p) < 0.02
    assert cal.ece(y, 1 - p) > 0.3  # a reversed forecaster is badly calibrated
    bins = cal.reliability_bins(y, p)
    assert sum(b["n"] for b in bins) == p.size
    assert all(set(b) >= {"p_mean", "freq", "n"} for b in bins)


def test_platt_and_isotonic_fix_overconfident_scores():
    rng = np.random.default_rng(2)
    z = rng.normal(0, 1.5, 6000)
    true_p = cal.sigmoid(z)
    y = (rng.uniform(size=z.size) < true_p).astype(int)
    over = cal.sigmoid(3.0 * z)  # overconfident forecast
    tr, te = slice(0, 3000), slice(3000, None)
    base = cal.ece(y[te], over[te])
    pl = cal.PlattScaler().fit(over[tr], y[tr])
    iso = cal.IsotonicCalibrator().fit(over[tr], y[tr])
    assert pl.a == pytest.approx(1 / 3, abs=0.08)
    assert cal.ece(y[te], pl.transform(over[te])) < base / 2
    assert cal.ece(y[te], iso.transform(over[te])) < base / 2
    xs = np.linspace(0, 1, 50)
    assert np.all(np.diff(iso.transform(xs)) >= -1e-12)  # monotone


def test_isotonic_pav_is_exact_on_small_case():
    iso = cal.IsotonicCalibrator().fit(np.array([0.1, 0.2, 0.3, 0.4]), np.array([0, 1, 0, 1]))
    out = iso.transform(np.array([0.1, 0.2, 0.3, 0.4]))
    assert out.tolist() == pytest.approx([0.0, 0.5, 0.5, 1.0])


def test_logistic_regression_recovers_coefficients():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(20000, 3))
    w = np.array([1.5, -2.0, 0.0])
    y = (rng.uniform(size=X.shape[0]) < cal.sigmoid(X @ w - 0.5)).astype(int)
    m = LogisticModel(l2=1e-3).fit(X, y)
    # coefficients are on the raw scale after un-standardising
    raw = m.coef_ / m.scale_
    assert raw == pytest.approx(w, abs=0.1)
    p = m.predict_proba(X)
    assert cal.ece(y, p) < 0.02


def test_cluster_bootstrap_interval_contains_point_estimate_and_is_seeded():
    rng = np.random.default_rng(4)
    n = 4000
    p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < p).astype(int)
    clusters = rng.integers(0, 80, n)
    a = cal.cluster_bootstrap_scores(y, p, clusters, n_boot=200, seed=7)
    b = cal.cluster_bootstrap_scores(y, p, clusters, n_boot=200, seed=7)
    assert a == b
    ll = cal.log_loss(y, p)
    assert a["log_loss"][0] < ll < a["log_loss"][1]
    json.dumps(a)
