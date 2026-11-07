from __future__ import annotations

import math

import numpy as np
from understudy_engine.insights import stats as S


def test_welch_and_one_sample_agree_with_scipy():
    from scipy import stats

    x, y = [5.0, 7.0, 6.0, 9.0, 8.0, 7.5], [3.0, 4.0, 2.5, 5.0, 3.5]
    e = S.welch(x, y)
    ref = stats.ttest_ind(x, y, equal_var=False)
    assert abs(e.p - ref.pvalue) < 1e-9 and abs(e.value - (np.mean(x) - np.mean(y))) < 1e-12 and e.lo < e.value < e.hi
    o = S.one_sample(x)
    assert abs(o.p - stats.ttest_1samp(x, 0.0).pvalue) < 1e-9


def test_small_samples_give_none_not_a_made_up_interval():
    assert S.one_sample([1.0]) is None and S.welch([1.0], [2.0, 3.0]) is None and S.newcombe(1, 0, 1, 5) is None


def test_constant_data_does_not_divide_by_zero():
    e = S.one_sample([3.0] * 8)
    assert e.p == 0.0 or e.p < 1e-12
    assert S.one_sample([0.0] * 8).p == 1.0


def test_newcombe_interval_contains_the_difference_and_the_p_is_sane():
    d, lo, hi, p = S.newcombe(18, 20, 6, 20)
    assert abs(d - 0.6) < 1e-12 and lo < d < hi and lo > 0 and p < 0.001
    d, lo, hi, p = S.newcombe(10, 20, 10, 20)
    assert d == 0 and lo < 0 < hi and p == 1.0


def test_bonferroni_multiplier_grows_with_the_family():
    assert abs(S.bonferroni_z(0.05, 1) - 1.959964) < 1e-5
    assert S.bonferroni_z(0.05, 10) > S.bonferroni_z(0.05, 5) > S.bonferroni_z(0.05, 1)
    assert abs(S.bonferroni_z(0.05, 0) - S.bonferroni_z(0.05, 1)) < 1e-12


def test_seed_from_is_stable_across_calls():
    assert S.seed_from("a", 1) == S.seed_from("a", 1) and S.seed_from("a", 1) != S.seed_from("a", 2)


def test_kaplan_meier_matches_a_hand_computation_and_handles_censoring():
    times, events = [3, 5, 5, 8, 10, 10], [True, True, False, True, False, True]
    pts = S.km(times, events, [3, 5, 8, 10])
    s = {p.x: p.s for p in pts}
    assert abs(s[3] - 5 / 6) < 1e-12 and abs(s[5] - 5 / 6 * 4 / 5) < 1e-12          # at t = 5: five at risk, one event (the other 5 is censored)
    assert abs(s[8] - 5 / 6 * 4 / 5 * 2 / 3) < 1e-12 and abs(s[10] - 5 / 6 * 4 / 5 * 2 / 3 * 1 / 2) < 1e-12
    assert S.km_median(times, events) == 8
    assert S.km_median([5, 6, 7], [False, False, False]) is None


def test_km_interval_never_collapses_to_a_point_when_nobody_has_had_the_event():
    pts = S.km([30, 40, 50, 60, 70, 80], [False] * 6, [60])
    assert pts[0].s == 1.0 and pts[0].lo < pts[0].hi


def test_greenwood_interval_brackets_the_estimate():
    pts = S.km([10, 20, 30, 40, 50, 60, 70, 80], [True, True, False, True, False, True, False, False], [45])
    p = pts[0]
    assert 0 < p.lo <= p.s <= p.hi < 1 and math.isfinite(p.lo)
