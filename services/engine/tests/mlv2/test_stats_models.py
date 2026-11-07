import numpy as np
import pytest

from understudy_engine.mlv2 import models as MD
from understudy_engine.mlv2 import stats as S
from understudy_engine.mlv2.controls import beats_base_rate, shuffle_labels
from understudy_engine.trust.calibration import brier, ece, log_loss


def test_cluster_bootstrap_point_matches_direct_metrics():
    rng = np.random.default_rng(0)
    n = 600
    person = np.repeat([f"p{i}" for i in range(6)], 100)
    p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < p).astype(float)
    cl = S.Clusters.from_labels(person)
    parts = S.score_parts(y, p, cl)
    pts = S.metric_points(parts)
    assert abs(pts["log_loss"] - log_loss(y, p)) < 1e-12
    assert abs(pts["brier"] - brier(y, p)) < 1e-12
    assert abs(pts["ece"] - ece(y, p)) < 1e-12
    from scipy.stats import rankdata
    pos = y == 1
    auc = (rankdata(p)[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
    assert abs(pts["auc"] - auc) < 1e-12


def test_bootstrap_resamples_people_not_rows_and_pairing_cancels_shared_noise():
    rng = np.random.default_rng(1)
    person = np.repeat([f"p{i}" for i in range(8)], 50)
    y = (rng.uniform(size=400) < 0.3).astype(float)
    p_a = np.full(400, 0.3)
    p_b = np.clip(p_a + 0.0, 1e-6, 1 - 1e-6)
    cl = S.Clusters.from_labels(person)
    M = S.boot_multiplicities(cl.C, 500, 3)
    assert np.all(M.sum(axis=1) == cl.C)          # a resample of people has as many people as the sample
    da = S.metric_draws(S.score_parts(y, p_a, cl), M)
    db = S.metric_draws(S.score_parts(y, p_b, cl), M)
    lo, hi = S.interval(da["log_loss"] - db["log_loss"], 0.95)
    assert lo == hi == 0.0                          # identical predictions: the paired interval has zero width


def test_adjusted_level_and_interval():
    assert abs(S.adjusted_level(7) - (1 - 0.05 / 7)) < 1e-12
    d = np.linspace(0, 1, 1001)
    lo, hi = S.interval(d, 0.9)
    assert abs(lo - 0.05) < 1e-9 and abs(hi - 0.95) < 1e-9


def test_gbm_is_monotone_in_time_since_progress_and_dwell(sim_tab):
    tab = sim_tab
    rows = tab.rows_of(tab.people)
    g = MD.GbmHazard().fit(tab, rows)
    base_idx = rows[:200]
    from understudy_engine.hazard.features import DENSE_NAMES
    import dataclasses
    for cols, deltas in ((("log_tsp", "tsp_lin"), (0.0, 0.5, 1.0, 2.0)), (("log_dwell",), (0.0, 0.5, 1.0, 2.0))):
        outs = []
        for d in deltas:
            dense = tab.dense.copy()
            for c in cols:
                dense[:, DENSE_NAMES.index(c)] += d
            t2 = dataclasses.replace(tab, dense=dense)
            outs.append(g.predict(t2, base_idx))
        outs = np.array(outs)
        assert np.all(np.diff(outs, axis=0) >= -1e-9), cols


def test_calibrators_are_monotone_and_fit_on_training_only():
    rng = np.random.default_rng(2)
    p = rng.uniform(0.02, 0.98, 2000)
    y = (rng.uniform(size=2000) < p ** 1.5).astype(float)     # miscalibrated: true rate is lower than p
    for kind in ("platt", "isotonic"):
        c = MD.Calibrator(kind).fit(p, y)
        g = np.linspace(0.02, 0.98, 50)
        assert np.all(np.diff(c.transform(g)) >= -1e-9)
        assert ece(y, c.transform(p)) < ece(y, p)


def test_personal_shift_has_no_effect_without_history_and_uses_only_earlier_episodes(sim_tab):
    tab = sim_tab
    q = tab.people[0]
    rows = tab.rows_of([q])
    p = np.full(tab.n, 0.3)
    prior = (2.0, 8.0)
    out = MD.apply_personal_shift(tab, p, rows, prior)
    first_ep = tab.episode[rows] == tab.episode[rows][0]
    assert np.allclose(out[first_ep], 0.3)                       # no history: no shift
    # change the labels of the LAST episode of this person: earlier episodes' shifted predictions must not move
    import dataclasses
    y2 = tab.y.copy()
    last = rows[tab.episode[rows] == tab.episode[rows][-1]]
    y2[last] = 1 - y2[last]
    out2 = MD.apply_personal_shift(dataclasses.replace(tab, y=y2), p, rows, prior)
    n_before = rows.size - last.size
    assert np.allclose(out[:n_before], out2[:n_before])
    # a person who is stuck more often than the prior mean gets pushed up
    y3 = np.ones(tab.n, dtype=tab.y.dtype)
    out3 = MD.apply_personal_shift(dataclasses.replace(tab, y=y3), p, rows, prior)
    assert out3[-1] > 0.3


def test_shuffled_labels_keep_marginals_and_break_the_link(sim_tab):
    sh = shuffle_labels(sim_tab, 1)
    assert sh.y.sum() == sim_tab.y.sum() and not np.array_equal(sh.y, sim_tab.y)
    sp = shuffle_labels(sim_tab, 1, scope="person")
    for q in sim_tab.people:
        r = sim_tab.rows_of([q])
        assert sp.y[r].sum() == sim_tab.y[r].sum()
    assert not np.array_equal(sp.y, sim_tab.y)
    assert beats_base_rate(0.40, 0.50) and not beats_base_rate(0.499, 0.50)
