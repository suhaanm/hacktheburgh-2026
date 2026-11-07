import numpy as np

from understudy_engine.hazard.events import choose_config, score_rows
from understudy_engine.mlv2.alarms import (
    build_layout, choose_config_fast, person_event_counts, pooled, score_grid, threshold_grid,
)


def _random_p(tab, seed=0):
    rng = np.random.default_rng(seed)
    base = 1 / (1 + np.exp(-(tab.dense[:, 3] - 3.5)))      # rises with log time-since-progress
    return np.clip(base * 0.6 + rng.uniform(0, 0.5, tab.n), 0, 1)


def test_grid_matches_v1_scoring_exactly(sim_tab):
    tab = sim_tab
    lay = build_layout(tab)
    p = _random_p(tab)
    eps = list(range(len(tab.ep_person)))
    thr = np.array([0.3, 0.5, 0.62, 0.8, 1.01])
    for conf in (1, 2):
        gs = score_grid(lay, p, thr, conf)
        pl = pooled(lay, gs, np.array(eps))
        for j, th in enumerate(thr):
            res, per = score_rows(tab, p, eps, float(th), confirm_bins=conf)
            assert res.false_alarms == int(pl["fa"][j])
            assert res.true_alarms == int(pl["ta"][j])
            assert res.detected == int(pl["det"][j])
            assert res.n_events == int(pl["n_events"])
            assert abs(res.non_event_h - pl["non_event_h"]) < 1e-9
            for e in (0, 5, 17):
                assert per[e].false_alarms == gs.false_alarms[e, j]
                assert per[e].detected == gs.detected[e, j]


def test_choose_config_matches_v1(sim_tab):
    tab = sim_tab
    lay = build_layout(tab)
    p = _random_p(tab, 1)
    eps = [e for e, q in enumerate(tab.ep_person) if q != tab.ep_person[0]]
    for budget in (0.5, 1.0, 3.0):
        v1 = choose_config(tab, p, eps, budget)
        v2 = choose_config_fast(lay, p, np.array(eps), budget)
        for k in ("threshold", "confirm_bins", "budget_met"):
            assert v1[k] == v2[k], (budget, k, v1, v2)
        assert abs(v1["train_fa_per_hour"] - v2["train_fa_per_hour"]) < 1e-9
        assert abs(v1["train_detection_rate"] - v2["train_detection_rate"]) < 1e-9


def test_subset_of_episodes_leaves_others_zero(sim_tab):
    lay = build_layout(sim_tab)
    p = _random_p(sim_tab)
    gs = score_grid(lay, p, np.array([0.5]), 1, episodes=np.array([3, 4]))
    other = np.setdiff1d(np.arange(lay.n_ep), [3, 4])
    assert gs.false_alarms[other].sum() == 0 and gs.detected[other].sum() == 0
    cnt = person_event_counts(lay, p, 0.5, 1, np.array([3, 4]))
    assert cnt["false_alarms"] == gs.false_alarms[[3, 4], 0].sum()


def test_threshold_grid_ends_with_never():
    g = threshold_grid(np.linspace(0, 1, 500))
    assert g[-1] == 1.01 and np.all(np.diff(g) > 0)
