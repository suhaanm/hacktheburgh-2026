"""The router's rules, one by one. Pure: every test builds an event, a worker state and a history and reads the Decision."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from understudy_engine.attention import vocab as V
from understudy_engine.attention.events import Item
from understudy_engine.attention.router import AttentionRouter, is_natural_break
from understudy_engine.attention.state import DEFAULT, History, Lock, Settings

from .conftest import T0, busy, ev, ws

R = AttentionRouter()
SAFETY = [t for t, s in V.TYPES.items() if s.cls == V.SAFETY]
HARD = ("dnd", "screen_sharing", "on_call", "in_meeting")


def hist(**kw) -> History:
    return History(**kw)


def item(type_: str, subject: str = "s1", first_t: float = T0, **kw) -> Item:
    it = Item.from_event(ev(type_, subject, **kw), "i_t", first_t)
    return it


def decide(type_: str, w=None, h=None, **kw):
    return R.decide(item(type_, **kw), w or ws(), h or hist())


# ------------------------------------------------------------------------------------------------ safety
@pytest.mark.parametrize("t", SAFETY)
@pytest.mark.parametrize("state", [
    dict(dnd=True), dict(screen_sharing=True), dict(on_call=True), dict(in_meeting=True), dict(typing_burst=True, quiet_s=0.1), dict(deep_work=True, quiet_s=1),
    dict(task_in_progress=True, quiet_s=1), dict(known=False),
])
def test_safety_is_never_suppressed_never_batched_never_held(t, state):
    d = decide(t, ws(**state))
    assert d.channel == V.TOAST and d.deliver_at == V.NOW and d.reason_code == "shown_safety" and d.badge and d.preempt


@pytest.mark.parametrize("t", SAFETY)
def test_safety_ignores_budget_spacing_mode_learning_and_never(t):
    h = hist(budget_used=999, wait_toasts=99, last_interruption_t=T0 - 1, settings=Settings(modes={t: "digest"}, budget_per_day=0),
             never_subjects=frozenset({"s1"}), learned_drop=lambda *_: 2)
    d = decide(t, h=h)
    assert d.channel == V.TOAST and d.deliver_at == V.NOW and d.reason_code == "shown_safety"


@pytest.mark.parametrize("t", SAFETY)
def test_safety_away_is_marked_now_and_first_on_return(t):
    d = decide(t, ws(away=True, away_s=600))
    assert d.channel == V.TOAST and d.deliver_at == V.RETURN and d.reason_code == "safety_on_return" and d.badge
    d2 = decide(t, ws(locked=True))
    assert d2.deliver_at == V.RETURN


def test_safety_is_shown_once_and_has_no_reminder():
    it = item("injection_pause")
    it.state, it.interrupted, it.shown_t = "shown", True, T0
    assert R.reminder(it, ws(T0 + 99999), hist()) is None


def test_safety_waits_only_for_another_safety_toast_on_screen_never_for_a_cue():
    cue_lock = Lock("i_c", "cue", "cue:e1", T0 + 10)
    assert decide("kill_engaged", h=hist(lock=cue_lock)).preempt is True
    other = Lock("i_s", "safety", "run:r9", T0 + 10)
    d = decide("injection_pause", h=hist(lock=other))
    assert d.reason_code == "held_lock" and d.deliver_at == V.BREAK and d.badge          # seconds, not suppression
    assert decide("injection_pause", ws(T0 + 11), hist(lock=other)).reason_code == "shown_safety"


# ------------------------------------------------------------------------------------------------ time-sensitive
def test_time_sensitive_has_a_badge_from_birth_and_waits_for_a_break_while_typing():
    d = decide("approval_blocking", busy())
    assert d.channel == V.TOAST and d.deliver_at == V.BREAK and d.reason_code == "held_typing" and d.badge
    d2 = decide("approval_blocking")            # quiet 60 s, no task: a natural break
    assert d2.deliver_at == V.NOW and d2.reason_code == "shown_break"


def test_time_sensitive_hold_is_capped_then_released_when_not_typing():
    held = ws(quiet_s=5, task_in_progress=True)              # not a break (a task is in progress, quiet < 90 s)
    assert decide("run_blocked_target", held).reason_code == "held_not_a_break"
    later = ws(T0 + DEFAULT.max_hold_soft_s + 1, quiet_s=5, task_in_progress=True)
    d = R.decide(item("run_blocked_target"), later, hist())
    assert d.deliver_at == V.NOW
    still_typing = ws(T0 + DEFAULT.max_hold_soft_s + 1, typing_burst=True, quiet_s=0.5)
    assert R.decide(item("run_blocked_target"), still_typing, hist()).reason_code == "held_typing"


@pytest.mark.parametrize("flag", HARD)
def test_hard_quiet_holds_time_items_drops_cues_and_leaves_passive_alone(flag):
    d = decide("approval_blocking", ws(**{flag: True}))
    assert d.deliver_at == V.BREAK and d.reason_code == f"held_{flag}" and d.badge
    c = decide("cue_cue", ws(**{flag: True}))
    assert c.channel == V.LOG and c.reason_code == f"dropped_{flag}"
    p = decide("service_degraded", ws(**{flag: True}), service="agent")
    assert p.channel == V.BANNER and p.deliver_at == V.NOW                                  # a banner is passive: never held


def test_unknown_worker_is_held_never_interrupted_except_safety():
    u = ws(known=False)
    assert decide("approval_blocking", u).reason_code == "held_state_unknown"
    assert decide("cue_ask", u).reason_code == "dropped_state_unknown"
    assert decide("routine_proposal", u).reason_code == "held_state_unknown"
    assert decide("kill_engaged", u).deliver_at == V.NOW


def test_away_time_waits_for_return_wait_folds_into_the_digest_cues_pass():
    a = ws(away=True, away_s=900)
    assert decide("run_blocked_error", a).deliver_at == V.RETURN
    d = decide("routine_proposal", a)
    assert d.deliver_at == V.DIGEST and d.channel == V.BANNER and d.reason_code == "held_away"
    assert decide("cue_offer", a).reason_code == "dropped_away"


def test_deep_work_holds_until_a_real_pause():
    assert decide("approval_blocking", ws(deep_work=True, quiet_s=20)).reason_code == "held_deep_work"
    assert decide("approval_blocking", ws(deep_work=True, quiet_s=100)).deliver_at == V.NOW


# ------------------------------------------------------------------------------------------------ helpful-now
def test_a_cue_is_shown_when_nothing_is_in_the_way_and_can_only_be_silenced_never_caused():
    assert decide("cue_cue", ws(quiet_s=3)).deliver_at == V.NOW
    assert decide("cue_cue", busy()).reason_code == "dropped_flow"                          # a backstop to Cue's own flow gate
    assert decide("cue_cue", ws(quiet_s=1.0)).reason_code == "dropped_flow"


def test_one_voice_cue_dropped_while_anything_else_is_up_but_its_own_escalation_continues():
    lock = Lock("i_x", "cue", "cue:e2", T0 + 8)
    assert decide("cue_cue", h=hist(lock=lock), subject="e1").reason_code == "dropped_lock"
    assert decide("cue_cue", h=hist(lock=lock), subject="e2").reason_code == "shown_now"      # same episode: a continuation
    expired = Lock("i_x", "cue", "cue:e2", T0 - 1)
    assert decide("cue_cue", h=hist(lock=expired), subject="e1").reason_code == "shown_now"
    toast = Lock("i_t", "decision", "approval:q1", T0 + 15)
    assert decide("cue_ask", h=hist(lock=toast)).reason_code == "dropped_lock"
    assert decide("approval_blocking", h=hist(lock=Lock("i_c", "cue", "cue:e1", T0 + 9)), subject="q2").reason_code == "held_lock"
    assert decide("routine_proposal", h=hist(lock=toast)).reason_code == "held_lock"


def test_spacing_applies_to_new_cues_not_to_time_items_or_continuations():
    h = hist(last_interruption_t=T0 - 30)
    assert decide("cue_cue", h=h, subject="e5").reason_code == "dropped_spacing"
    assert decide("approval_blocking", h=h).deliver_at == V.NOW
    assert decide("routine_proposal", h=h).reason_code == "held_spacing"
    ok = hist(last_interruption_t=T0 - 91)
    assert decide("cue_cue", h=ok).reason_code == "shown_now"


def test_budget_drops_cues_and_folds_can_wait_into_the_digest_but_never_touches_time_or_safety():
    h = hist(budget_used=10)
    assert decide("cue_cue", h=h).reason_code == "dropped_budget"
    d = decide("routine_proposal", h=h)
    assert d.deliver_at == V.DIGEST and d.channel == V.BANNER and d.reason_code == "passive_budget"
    assert decide("approval_blocking", h=h).deliver_at == V.NOW
    assert decide("irreversible_decision", h=h).deliver_at == V.NOW
    assert decide("cue_cue", h=hist(budget_used=10, settings=Settings(budget_per_day=14))).reason_code == "shown_now"
    assert decide("cue_cue", h=hist(budget_used=7, settings=Settings(modes={"cue_cue": "quiet"}, budget_per_day=10))).reason_code == "dropped_budget"   # x0.5
    assert decide("cue_cue", h=hist(budget_used=12, settings=Settings(modes={"cue_cue": "loud"}, budget_per_day=10))).reason_code == "shown_now"      # x1.5


def test_wait_toasts_per_day_cap():
    assert decide("routine_proposal", h=hist(wait_toasts=3)).reason_code == "passive_budget"


def test_the_workers_ask_bypasses_quiet_budget_spacing_and_learning_but_not_consent_style_gates():
    h = hist(budget_used=99, last_interruption_t=T0 - 2, learned_drop=lambda *_: 2, settings=Settings(modes={"cue_ask": "digest"}))
    for state in (busy(), ws(dnd=True), ws(screen_sharing=True), ws(known=False)):
        d = R.decide(item("cue_ask", asked=True), state, h)
        assert d.channel == V.QUESTION and d.deliver_at == V.NOW and d.reason_code == "shown_asked"
    assert R.decide(item("cue_ask", subject="e9", asked=True), ws(), hist(lock=Lock("i", "cue", "cue:e1", T0 + 9))).preempt is True
    assert R.decide(item("cue_ask", subject="e9", asked=True), ws(), hist(lock=Lock("i", "decision", "approval:q", T0 + 9))).reason_code == "dropped_lock"
    assert R.decide(item("cue_ask", asked=True), ws(), hist(never_subjects=frozenset({"s1"}))).reason_code == "dropped_never_subject"


# ------------------------------------------------------------------------------------------------ can-wait and info
def test_can_wait_defaults_go_to_the_digest_as_passive_notes():
    for t, ch in (("briefing_ready", V.BANNER), ("run_finished", V.BANNER), ("morning_report", V.BANNER), ("approval_waiting", V.BADGE)):
        d = decide(t)
        assert d.channel == ch and d.deliver_at == V.DIGEST and d.reason_code == "passive_digest", t
    p = decide("routine_proposal")
    assert p.channel == V.TOAST and p.deliver_at == V.NOW and p.reason_code == "shown_break"
    assert decide("routine_proposal", ws(quiet_s=5, task_in_progress=True)).reason_code == "held_not_a_break"
    assert decide("routine_proposal", busy()).reason_code == "held_typing"


def test_service_note_is_a_passive_banner_never_an_interruption():
    for state in (ws(), busy(), ws(away=True), ws(dnd=True), ws(known=False)):
        d = R.decide(item("service_degraded", service="model"), state, hist())
        assert d.channel == V.BANNER and d.deliver_at == V.NOW and not d.interrupting


@pytest.mark.parametrize("mode,chan,deliver", [("loud", V.TOAST, V.NOW), ("normal", V.BANNER, V.DIGEST), ("quiet", V.BANNER, V.DIGEST), ("digest", V.BANNER, V.DIGEST)])
def test_modes_for_a_can_wait_item(mode, chan, deliver):
    d = decide("run_finished", h=hist(settings=Settings(modes={"run_finished": mode})))
    assert d.channel == chan and d.deliver_at == deliver


def test_modes_for_time_items_quiet_is_badge_only_for_blocked_runs_and_one_toast_for_approvals():
    q = hist(settings=Settings(modes={"run_blocked_target": "quiet", "approval_blocking": "quiet", "calendar_deadline": "digest"}))
    assert decide("run_blocked_target", h=q).channel == V.BADGE
    assert decide("approval_blocking", h=q).channel == V.TOAST
    assert decide("calendar_deadline", h=q, deadline_in_s=3600).channel == V.BADGE
    assert decide("run_blocked_target", h=q).badge


def test_informational_is_silent_log_only_and_the_level_glance_is_a_free_two_second_chip():
    d = decide("kill_cleared")
    assert d.channel == V.LOG and d.reason_code == "log_only" and not d.badge
    g = decide("help_level_changed", ws(quiet_s=3))
    assert g.channel == V.CHIP and g.deliver_at == V.NOW


def test_level_glance_can_be_switched_off_by_setting_or_environment(monkeypatch):
    off = hist(settings=Settings(level_glance=False))
    assert decide("help_level_changed", h=off).reason_code == "dropped_mode"
    assert decide("help_level_changed", h=hist(level_glance_env_off=True)).reason_code == "dropped_mode"
    assert decide("help_level_changed", h=hist(settings=Settings(modes={"help_level_changed": "quiet"}))).channel == V.LOG


def test_level_glance_is_limited_to_twice_an_hour_needs_a_free_screen_and_spends_no_budget():
    two = hist(level_glances=(T0 - 600, T0 - 60))
    assert decide("help_level_changed", h=two).reason_code == "dropped_budget"
    assert decide("help_level_changed", h=hist(level_glances=(T0 - 4000, T0 - 60))).channel == V.CHIP
    assert decide("help_level_changed", busy()).reason_code == "dropped_flow"
    assert decide("help_level_changed", h=hist(lock=Lock("i", "cue", "cue:e", T0 + 5))).reason_code == "dropped_lock"
    assert decide("help_level_changed", h=hist(budget_used=99, last_interruption_t=T0 - 5)).channel == V.CHIP


def test_voice_never_starts_on_its_own():
    assert decide("voice_line").channel == V.CHIP
    assert decide("voice_line", ws(voice_session=True)).channel == V.VOICE
    assert R.decide(item("voice_line", asked=True), ws(), hist()).channel == V.VOICE
    assert decide("voice_line", h=hist(settings=Settings(modes={"voice_line": "quiet"}))).channel == V.LOG


# ------------------------------------------------------------------------------------------------ learning, never, expiry
def test_learning_lowers_rungs_but_not_below_the_floor_and_not_for_safety_or_blocking_approvals():
    drop2 = lambda *_: 2  # noqa: E731
    h = hist(learned_drop=drop2)
    d = decide("routine_proposal", h=h)
    assert d.channel == V.LOG and d.reason_code == "dropped_learned"
    d1 = decide("routine_proposal", h=hist(learned_drop=lambda *_: 1))
    assert d1.channel == V.BANNER and d1.deliver_at == V.DIGEST and d1.reason_code == "passive_learned"
    assert decide("cue_ask", h=h).reason_code == "dropped_learned"
    aw = decide("approval_waiting", h=h)
    assert aw.channel == V.BADGE and aw.badge                                    # the floor keeps an approval visible
    assert decide("approval_blocking", h=h).channel == V.TOAST
    for t in SAFETY:
        assert decide(t, h=h).channel == V.TOAST
    for t in ("run_blocked_target", "run_blocked_error", "calendar_deadline"):
        assert decide(t, h=h, deadline_in_s=3600).channel == V.TOAST            # time types are not learnable


def test_learning_can_never_raise_a_channel_above_its_table_value():
    for t, sp in V.TYPES.items():
        base = R.decide(item(t, service="agent", deadline_in_s=3600), ws(), hist())
        for drop in (0, 1, 2):
            d = R.decide(item(t, service="agent", deadline_in_s=3600), ws(), hist(learned_drop=lambda *_, k=drop: k))
            assert V.RANK[d.channel] <= V.RANK[base.channel], (t, drop)
            assert V.RANK[d.channel] >= V.RANK[sp.floor] or d.channel == V.LOG and sp.floor == V.LOG


def test_never_for_this_drops_the_subject_but_not_safety_or_a_blocking_approval():
    h = hist(never_subjects=frozenset({"s1"}))
    assert decide("routine_proposal", h=h).reason_code == "dropped_never_subject"
    assert decide("approval_blocking", h=h).deliver_at == V.NOW
    assert decide("injection_pause", h=h).channel == V.TOAST
    assert decide("routine_proposal", h=h, subject="other").channel == V.TOAST


def test_resolved_and_expired_items_are_dropped_without_bothering_anyone():
    it = item("approval_blocking")
    assert R.decide(it, ws(T0 + 86400 + 1), hist()).reason_code == "dropped_expired"
    r = replace(it, op="resolve")
    assert R.decide(r, ws(), hist()).reason_code == "dropped_resolved" and not R.decide(r, ws(), hist()).badge
    short = item("approval_blocking", expires_in_s=30)
    assert R.decide(short, ws(T0 + 31), hist()).channel == V.LOG


def test_a_producer_may_shorten_an_expiry_but_never_lengthen_it():
    assert item("cue_cue", expires_in_s=12).expires_at == T0 + 12
    assert item("cue_cue", expires_in_s=9999).expires_at == T0 + V.TYPES["cue_cue"].ttl_s
    assert item("calendar_deadline", deadline_in_s=7200).expires_at == T0 + 7200


# ------------------------------------------------------------------------------------------------ reminders
def shown(type_: str, **kw) -> Item:
    it = item(type_, **kw)
    it.state, it.interrupted, it.shown_t, it.until = "shown", True, T0, T0 + 20
    return it


def test_exactly_one_reminder_after_twenty_minutes_at_a_break_then_nothing():
    it = shown("approval_blocking")
    assert R.reminder(it, ws(T0 + 1199), hist()) is None
    r = R.reminder(it, ws(T0 + 1200), hist())
    assert r is not None and r.channel == V.TOAST and r.reason_code == "shown_reminder" and r.text_id == "approval_reminder"
    it.reminders, it.state = 1, "reminded"
    assert R.reminder(it, ws(T0 + 99999), hist()) is None
    it.state = "shown"
    assert R.reminder(it, ws(T0 + 99999), hist()) is None                       # the cap is a count, not a state


def test_reminder_is_ten_minutes_when_loud_and_never_when_quiet_or_digest():
    it = shown("run_blocked_target")
    loud = hist(settings=Settings(modes={"run_blocked_target": "loud"}))
    assert R.reminder(it, ws(T0 + 600), loud) is not None
    for mode in ("quiet", "digest"):
        assert R.reminder(it, ws(T0 + 99999), hist(settings=Settings(modes={"run_blocked_target": mode}))) is None
    it2 = shown("approval_blocking")
    assert R.reminder(it2, ws(T0 + 99999), hist(settings=Settings(modes={"approval_blocking": "quiet"}))) is None


def test_no_reminder_after_the_worker_reacted_or_for_unshown_or_wrong_types_and_it_obeys_quiet_rules():
    it = shown("approval_blocking")
    it.state = "acted"
    assert R.reminder(it, ws(T0 + 2000), hist()) is None
    it.state = "dismissed"
    assert R.reminder(it, ws(T0 + 2000), hist()) is None
    assert R.reminder(item("approval_blocking"), ws(T0 + 2000), hist()) is None
    w = shown("routine_proposal")
    assert R.reminder(w, ws(T0 + 99999), hist()) is None
    assert R.reminder(shown("approval_blocking"), busy(T0 + 2000), hist()) is None
    assert R.reminder(shown("approval_blocking"), ws(T0 + 2000, dnd=True), hist()) is None
    assert R.reminder(shown("approval_blocking"), ws(T0 + 2000, away=True), hist()) is None


def test_deadline_reminder_only_while_the_deadline_is_still_ten_minutes_away():
    it = shown("calendar_deadline", deadline_in_s=3600)
    assert R.reminder(it, ws(T0 + 1300), hist()) is not None
    near = shown("calendar_deadline", deadline_in_s=1500)
    assert R.reminder(near, ws(T0 + 1300), hist()) is None                       # 200 s left


# ------------------------------------------------------------------------------------------------ natural break and purity
@pytest.mark.parametrize("state,expected", [
    (dict(quiet_s=60), True), (dict(quiet_s=14), False), (dict(quiet_s=15), True), (dict(typing_burst=True, quiet_s=60), False),
    (dict(task_in_progress=True, quiet_s=60), False), (dict(task_in_progress=True, quiet_s=90), True),
    (dict(task_marker_s=30, quiet_s=3), True), (dict(task_marker_s=30, quiet_s=2), False), (dict(task_marker_s=120, quiet_s=3), False),
    (dict(dashboard_focused=True, quiet_s=0), True), (dict(returned_s=30, quiet_s=0), True), (dict(returned_s=500, quiet_s=0), False),
    (dict(deep_work=True, quiet_s=30), False), (dict(deep_work=True, quiet_s=95), True), (dict(away=True), False), (dict(locked=True), False),
    (dict(known=False), False),
])
def test_natural_break_table(state, expected):
    assert is_natural_break(ws(**state)) is expected


def test_decide_is_a_pure_function_and_mutates_nothing():
    it = item("approval_blocking")
    w, h = busy(), hist(budget_used=3)
    before = (copy.deepcopy(it), copy.deepcopy(w), copy.deepcopy(h))
    d1, d2 = R.decide(it, w, h), R.decide(it, w, h)
    assert d1 == d2 and (it, w, h) == before
    ev_only = ev("approval_blocking", "s1")
    assert R.decide(ev_only, w, h) == R.decide(ev_only, w, h)


def test_every_decision_carries_a_known_reason_with_fixed_text():
    from understudy_engine.attention.texts import REASONS

    states = [ws(), busy(), ws(away=True), ws(dnd=True), ws(known=False), ws(quiet_s=5, task_in_progress=True), ws(deep_work=True, quiet_s=5)]
    hs = [hist(), hist(budget_used=99), hist(last_interruption_t=T0 - 5), hist(lock=Lock("i", "cue", "cue:z", T0 + 9)), hist(never_subjects=frozenset({"s1"})),
          hist(learned_drop=lambda *_: 2)]
    for t in V.EVENT_TYPES:
        for w in states:
            for h in hs:
                d = R.decide(item(t, service="agent", deadline_in_s=3600), w, h)
                assert d.reason_code in REASONS, (t, d.reason_code)
                assert d.channel in V.CHANNELS and d.deliver_at in V.DELIVER_AT
