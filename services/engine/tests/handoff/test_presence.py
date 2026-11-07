"""ANA-12, OFF-1, OFF-3: presence map, intervals, idle capacity, return-time survival, decision rule, evaluation."""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pytest

from understudy_engine.presence import (
    ACTIVE, IDLE, OFF, PresenceModel, PriorHours, ReturnTimeModel, Smoothing, Spell, day_states_from_events, decide,
    evaluate_presence, loss_for_cap, spells_from_events, threshold,
)
from understudy_engine.presence.survival import SurvivalEstimate

from .gen import presence_events, truth_active_matrix

UTC = timezone.utc


def _fit(persona, days=21, seed=2, prior=None, with_sleep=True):
    ev, _ = presence_events(persona, days, seed=seed, with_sleep=with_sleep)
    obs = day_states_from_events(ev)
    return PresenceModel(prior or PriorHours()).fit(obs), obs, ev


# ----------------------------------------------------------------------------- timeline
def test_bins_from_hand_made_events_and_agent_events_are_ignored():
    d = datetime(2026, 11, 2, tzinfo=UTC)  # Monday
    ev = [
        {"t": d.replace(hour=9, minute=1), "type": "click", "actor": "human"},
        {"t": d.replace(hour=9, minute=14), "type": "scroll", "actor": "human"},
        {"t": d.replace(hour=10, minute=0), "type": "sleep", "actor": "human"},
        {"t": d.replace(hour=11, minute=0), "type": "agent_step", "actor": "agent"},   # not presence
        {"t": d.replace(hour=12, minute=5), "type": "resume", "actor": "human"},
    ]
    (day,) = day_states_from_events(ev)
    assert day.states[36] == ACTIVE                      # 09:00 bin
    assert day.states[37] == IDLE                        # 09:15, awake, no input
    assert day.states[40] == OFF and day.states[47] == OFF  # asleep from 10:00 until the next event
    assert day.states[44] == OFF                          # the agent step at 11:00 did not wake anything
    assert day.states[48] == ACTIVE                       # 12:00 bin has the resume


def test_spells_are_gaps_between_inputs_and_open_spell_is_censored():
    d = datetime(2026, 11, 2, 9, 0, tzinfo=UTC).timestamp()
    ev = [{"t": d + s, "type": "click", "actor": "human"} for s in (0, 60, 60 * 9, 60 * 10)]
    ev.append({"t": d + 70, "type": "lock", "actor": "human"})  # lock is not an input
    sp = spells_from_events(ev)
    assert [round(s.duration_min) for s in sp] == [8]
    sp = spells_from_events(ev, censor_at=d + 60 * 60)
    assert sp[-1].ended is False and round(sp[-1].duration_min) == 50


# ----------------------------------------------------------------------------- the map
def test_map_recovers_the_planted_schedule_with_intervals():
    model, _, _ = _fit("nine_to_five")
    p = model.p_active()
    truth = truth_active_matrix("nine_to_five")
    assert p[truth].mean() > 0.75                      # inside the planted blocks
    assert p[~truth].mean() < 0.08                     # nights and weekends
    # a Tuesday 03:00 bin and a Tuesday 10:00 bin
    assert p[1, 12] < 0.1 < 0.8 < p[1, 40]
    lo, hi = model.active_interval()
    assert np.all(lo <= p) and np.all(p <= hi)
    assert (hi - lo).mean() < 0.35
    hm = model.heatmap()
    assert len(hm) == 672 and {"dow", "slot", "p", "lo", "hi"} == set(hm[0])


def test_data_overrides_a_wrong_pack_prior():
    # the pack says nine to five; the worker is a night owl; after three weeks the map follows the worker
    model, _, _ = _fit("night_owl", prior=PriorHours())
    p = model.p_active()
    truth = truth_active_matrix("night_owl")
    assert p[truth].mean() > 0.6 and p[~truth].mean() < 0.2
    assert p[2, 40] < 0.35 or p[2, 40] < p[2, 64]       # Wed 10:00 is not their active time; 16:00 is


def test_more_days_give_narrower_intervals():
    ev, _ = presence_events("nine_to_five", 21, seed=4)
    obs = day_states_from_events(ev)
    narrow = PresenceModel(PriorHours()).fit(obs)
    wide = PresenceModel(PriorHours()).fit(obs[:7])
    nl, nh = narrow.active_interval()
    wl, wh = wide.active_interval()
    assert (nh - nl).mean() < (wh - wl).mean()


def test_smoothing_helps_on_held_out_days_and_borrowed_counts_are_fractional():
    ev, _ = presence_events("nine_to_five", 21, seed=5)
    obs = day_states_from_events(ev)
    train, test = obs[:14], obs[14:]
    smooth = PresenceModel(PriorHours()).fit(train)
    raw = PresenceModel(PriorHours(), Smoothing(0, 0, 0, 0, prior_strength=0.5)).fit(train)
    assert smooth.log_loss_active(test) < raw.log_loss_active(test)
    # a bin with no observations of its own still gets a finite, non-degenerate posterior with a wide interval
    m = PresenceModel(PriorHours()).fit(obs[:2])
    lo, hi = m.active_interval()
    assert np.all((0 < lo) & (hi < 1))


def test_idle_capacity_has_an_interval_and_quiet_days_are_off_not_idle():
    with_sleep, obs, _ = _fit("nine_to_five", with_sleep=True)
    no_sleep, obs2, _ = _fit("nine_to_five", with_sleep=False)
    for m in (with_sleep, no_sleep):
        a = m.idle_capacity_interval()
        assert a["lo"] <= a["mean"] <= a["hi"] and a["hi"] - a["lo"] > 0
        assert 0 < a["mean"] < 168 - m.active_hours_per_week()
    # no sleep events at all: a day with no events is still off (auto-sleep after the grace period), never 24 h idle
    weekend = [d for d in obs2 if d.day.weekday() == 5][0]
    assert (weekend.states == OFF).mean() > 0.95
    assert no_sleep.idle_capacity_interval()["mean"] < 40


def test_quiet_window_mask_wraps_midnight():
    from understudy_engine.presence import window_mask

    m = window_mask({"start": "22:00", "end": "06:00", "days": ["mon"]})
    assert m[0, 90] and not m[0, 20] and m[1, 10] and not m[1, 30]    # Mon 22:30 yes; Tue 02:30 (wrap) yes; Tue 07:30 no


# ----------------------------------------------------------------------------- return-time hazard
def test_survival_depends_on_time_of_week_and_is_smooth_and_decreasing():
    ev, _ = presence_events("nine_to_five", 21, seed=2)
    rt = ReturnTimeModel(spells_from_events(ev))
    tue = 1 * 1440
    evening = rt.survival(120, tue + 19 * 60, 45)        # Tuesday 19:00, idle for 45 min: the day is over
    midday = rt.survival(120, tue + 11 * 60, 5)          # Tuesday 11:00, five minutes into a mid-block pause
    assert evening.survival > 0.8 > 0.2 > midday.survival
    ds = [15, 30, 60, 120, 240, 480]
    vals = [rt.survival(d, tue + 19 * 60, 45).survival for d in ds]
    assert all(a >= b - 1e-9 for a, b in zip(vals, vals[1:]))
    fine = [rt.survival(d, tue + 11 * 60, 5).survival for d in np.arange(5, 60, 2.0)]
    assert max(abs(a - b) for a, b in zip(fine, fine[1:])) < 0.2          # no staircase
    est = rt.survival(60, tue + 19 * 60, 45)
    assert est.lo <= est.survival <= est.hi and est.n_eff > 1
    out = rt.forecast(tue + 19 * 60, 45)
    assert [r["d_min"] for r in out] == [5, 15, 30, 60, 120, 240, 480]


def test_survival_with_no_history_says_wait():
    rt = ReturnTimeModel([])
    est = rt.survival(30, 100, 5)
    d = decide(est, 30, gain=1, loss=4)
    assert est.survival == 0 and not d.go and "no history" in d.reason


def test_survival_conditions_on_time_already_idle():
    sp = [Spell(0.0, d, 600.0, 1) for d in [10, 12, 15, 300, 320, 340]]   # short gaps or long gaps, nothing between
    rt = ReturnTimeModel(sp)
    early = rt.survival(60, 1440 + 600, 5).survival          # right after leaving: half are long
    later = rt.survival(60, 1440 + 600 + 60, 60).survival    # an hour in: only long ones remain
    assert later > early + 0.2


# ----------------------------------------------------------------------------- decision rule
def test_threshold_is_the_critical_fractile():
    assert threshold(1, 9) == pytest.approx(0.9)
    assert threshold(3, 1) == pytest.approx(0.25)
    assert loss_for_cap(1, 0.10) == pytest.approx(9.0) and threshold(1, loss_for_cap(1, 0.1)) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        threshold(0, 0)
    with pytest.raises(ValueError):
        threshold(-1, 1)


def test_decide_goes_only_above_the_threshold_and_refuses_locked_or_asleep():
    est = SurvivalEstimate(0.85, 0.7, 0.95, 40.0, 40)
    assert decide(est, 60, gain=1, loss=4).go                     # 0.85 > 0.8
    assert not decide(est, 60, gain=1, loss=9).go                 # 0.85 < 0.9
    assert not decide(SurvivalEstimate(0.9, 0.8, 0.95, 40.0, 40), 60, gain=1, loss=9).go   # equal does not beat it
    d = decide(est, 60, 1, 4, locked=True)
    assert not d.go and d.locked and "locked" in d.reason
    assert not decide(est, 60, 1, 4, asleep=True).go
    assert "below" in decide(est, 60, 1, 9).reason and "above" in decide(est, 60, 1, 4).reason


# ----------------------------------------------------------------------------- held-out evaluation
@pytest.mark.parametrize("persona", ["nine_to_five", "night_owl", "shift"])
def test_evaluation_on_held_out_days_beats_the_baselines(persona):
    ev, _ = presence_events(persona, 21, seed=2)
    obs = day_states_from_events(ev)
    spells = spells_from_events(ev)
    rep = evaluate_presence(obs, spells, PriorHours(), cap=0.10)
    assert rep["origin"] == "synthetic" and rep["n_unit"] == "days" and "forward" in rep["by_split"]
    for mode, part in rep["by_split"].items():
        m, w, d = part["map"], part["window"], part["decision"]
        # 1. map: better than the pack prior and than one global rate on held-out days
        assert m["model"]["brier"] < m["prior_only"]["brier"] and m["model"]["brier"] < m["global_rate"]["brier"]
        assert m["ece"] < 0.15
        # 2. window forecast: better than a memoryless baseline, no worse than pooled survival, calibrated
        assert w["model"]["brier"] < w["exponential"]["brier"]
        assert w["model"]["brier"] <= w["pooled"]["brier"] * 1.02
        assert w["ece"] < 0.12
        # 3. decisions: interruption rate at or under the cap (with a small margin), far below idle-5-min,
        #    and more idle time used than the fixed overnight window
        rule, always, fixed = d["rule"], d["run_whenever_idle_5min"], d["fixed_overnight"]
        assert rule["interruption_rate"] <= 0.10 + 0.05, (mode, rule)
        assert rule["interruption_rate"] < always["interruption_rate"]
        assert rule["share_idle_used"] > fixed["share_idle_used"]
        assert rule["interruption_ci"][0] <= rule["interruption_rate"] <= rule["interruption_ci"][1]
    assert rep["metrics"]["decision"]["threshold"] == pytest.approx(0.9, abs=1e-3)


def test_fixed_overnight_window_collides_for_a_night_owl_and_the_rule_does_not():
    ev, _ = presence_events("night_owl", 21, seed=2)
    rep = evaluate_presence(day_states_from_events(ev), spells_from_events(ev), PriorHours(), cap=0.10)
    d = rep["by_split"]["interleaved"]["decision"]
    assert d["fixed_overnight"]["interruption_rate"] > 0.25
    assert d["rule"]["interruption_rate"] < 0.10
