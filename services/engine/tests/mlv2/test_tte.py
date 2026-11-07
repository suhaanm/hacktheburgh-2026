import numpy as np

from understudy_engine.core import Cog, Episode
from understudy_engine.hazard.features import build_bins
from understudy_engine.mlv2 import tte as T


def _ep(progress, t1, person="p_a", tid="t1", t0=1000.0):
    cogs = [Cog(t0, t1, "READ")]
    return Episode(task_id=tid, person=person, role="r", origin="synthetic", t0=t0, t1=t1, cogs=cogs, progress_t=list(progress))


def test_tte_outcomes_agree_with_the_v1_label(sim_episodes, sim_tab):
    d = T.build_tte(sim_episodes, sim_tab)
    y_from_tte = ((d.time_s > 60.0) | (d.event == 0)).astype(int)
    assert np.array_equal(y_from_tte, sim_tab.y.astype(int))


def test_person_period_expansion_on_a_handmade_episode():
    # progress at +40 and +200; episode ends at +300. bins at 0, 30, ... while b + 60 <= 300
    ep = _ep([1040.0, 1200.0], 1300.0)
    tab = build_bins([ep])
    d = T.build_tte([ep], tab)
    # origin 0 (b = 1000): next progress at +40 -> step 2, event
    assert d.event[0] == 1 and abs(d.time_s[0] - 40) < 1e-9
    origin, step, ev = T.person_period(d, np.array([0]))
    assert step.tolist() == [1, 2] and ev.tolist() == [0.0, 1.0]
    # origin 2 (b = 1060): next progress at +140 -> step 5
    i = list(tab.t).index(1060.0)
    origin, step, ev = T.person_period(d, np.array([i]))
    assert step.tolist() == [1, 2, 3, 4, 5] and ev.tolist() == [0, 0, 0, 0, 1.0]
    # last origin: b = 1240, no later progress: censored, 2 observed steps (60 s) -> two zero rows
    j = len(tab.t) - 1
    assert d.event[j] == 0
    origin, step, ev = T.person_period(d, np.array([j]))
    assert ev.sum() == 0 and step.size == d.steps_obs[j]


def test_survival_is_monotone_and_s60_matches_two_steps(sim_episodes, sim_tab):
    d = T.build_tte(sim_episodes, sim_tab)
    people = sim_tab.people
    tr, te = sim_tab.rows_of(people[1:]), sim_tab.rows_of(people[:1])
    m = T.DiscreteTimeModel("full").fit(sim_tab, d, tr)
    S = m.survival(sim_tab, te)
    assert np.all(np.diff(S, axis=1) <= 1e-12) and np.allclose(S[:, 0], 1.0)
    h = m.hazards(sim_tab, te)
    assert np.allclose(m.prob_no_progress_60s(sim_tab, te), (1 - h[:, 0]) * (1 - h[:, 1]))
    mins = m.expected_minutes(sim_tab, te)
    assert np.all(mins > 0) and np.all(mins <= 5.0 + 1e-9)


def test_head_beats_constant_on_concordance_and_s60_log_loss(sim_episodes, sim_tab):
    from understudy_engine.trust.calibration import log_loss

    d = T.build_tte(sim_episodes, sim_tab)
    o = T.oof_tte(sim_tab, d)
    y = sim_tab.y.astype(float)
    assert np.all(np.isfinite(o.s60)) and np.all(np.isfinite(o.minutes))
    base = np.full(sim_tab.n, y.mean())
    assert log_loss(y, o.s60) < log_loss(y, base)
    c = T.concordance(d.time_s, d.event, -o.minutes * -1)      # larger expected minutes should mean longer waits
    assert c is not None and c > 0.5


def test_km_restricted_mean_basics():
    # no censoring: all progress at 60 s -> restricted mean 1 minute
    assert abs(T.km_restricted_mean(np.full(10, 60.0), np.ones(10)) - 1.0) < 1e-9
    # everyone censored at 400 s: S stays 1 until the cap of 300 s -> 5 minutes
    assert abs(T.km_restricted_mean(np.full(10, 400.0), np.zeros(10)) - 5.0) < 1e-9
    # half the origins progress at 30 s, half at 90 s
    v = T.km_restricted_mean(np.array([30.0, 90.0]), np.array([1, 1]))
    assert abs(v - ((1 * 30 + 0.5 * 60 + 0 * 210) / 60.0)) < 1e-9
