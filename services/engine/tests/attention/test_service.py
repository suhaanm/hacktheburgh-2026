"""The service keeps the books: coalescing, superseding, expiry, the one voice, reminders, digests, markers, labels, settings, privacy."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from understudy_engine.attention import vocab as V
from understudy_engine.attention.events import EventError, Item
from understudy_engine.attention.service import AttentionService, local_day
from understudy_engine.attention.state import DEFAULT, Params
from understudy_engine.attention.store import AttentionStore

from .conftest import P, T0, busy, ev, ws


def nxt(svc, w):
    return svc.next(P, w)


def item_of(out):
    return out["item"]


# ------------------------------------------------------------------------------------------------ coalescing, superseding, expiry
def test_the_same_subject_is_one_item_with_a_count_never_two(svc):
    a = svc.submit(ev("briefing_ready", "gen1", count=2), ws())
    b = svc.submit(ev("briefing_ready", "gen1", count=3), ws(T0 + 5))
    c = svc.submit(ev("briefing_ready", "gen1", count=3), ws(T0 + 9))
    assert a["item_id"] == b["item_id"] == c["item_id"] and b["coalesced"] and c["coalesced"]
    ps = svc.store.person(P)
    assert len(ps.items) == 1
    it = next(iter(ps.items.values()))
    assert it.count == 3 and it.occurrences == 3


def test_a_newer_decision_replaces_an_older_unseen_one(svc):
    a = svc.submit(ev("approval_waiting", "q1"), busy())
    b = svc.submit(ev("approval_blocking", "q1"), busy())
    ps = svc.store.person(P)
    assert ps.items[a["item_id"]].state == "suppressed" and ps.items[a["item_id"]].reason_code == "dropped_superseded"
    assert ps.items[b["item_id"]].state in ("held", "shown")
    assert svc.badges(P)["badges"]["needs_you"] == 1                               # the story is counted once


def test_a_shown_item_is_replaced_by_the_newer_one_of_its_family_as_resolved(svc):
    svc.submit(ev("run_blocked_target", "r1"), ws())
    out = nxt(svc, ws())
    assert item_of(out)["type"] == "run_blocked_target"
    svc.submit(ev("injection_pause", "r1"), ws(T0 + 30))
    ps = svc.store.person(P)
    states = {i.type: i.state for i in ps.items.values()}
    assert states["run_blocked_target"] == "resolved" and states["injection_pause"] == "held"


def test_expired_items_vanish_without_bothering_anyone(svc):
    svc.submit(ev("approval_blocking", "q1", expires_in_s=60), busy())
    assert svc.badges(P)["badges"]["needs_you"] == 1
    out = nxt(svc, ws(T0 + 61))
    assert out["item"] is None and out["badges"]["needs_you"] == 0
    assert svc.store.person(P).items and all(i.state == "expired" for i in svc.store.person(P).items.values())


def test_resolve_drops_the_item_and_any_story_member(svc):
    svc.submit(ev("approval_blocking", "q9"), busy())
    r = svc.submit(ev("approval_blocking", "q9", op="resolve"), busy())
    assert r["resolved"] == 1 and svc.badges(P)["badges"]["needs_you"] == 0
    assert nxt(svc, ws())["item"] is None


# ------------------------------------------------------------------------------------------------ time-sensitive: one toast, one reminder, nothing
def test_time_sensitive_walk_badge_then_one_toast_then_one_reminder_then_nothing(svc):
    svc.submit(ev("approval_blocking", "q1"), busy())
    out = nxt(svc, busy(T0 + 1))
    assert out["item"] is None and out["badges"]["needs_you"] == 1 and out["badges"]["marker"] == "needs_you"     # a badge from birth, nothing on screen
    out = nxt(svc, ws(T0 + 30))
    it = item_of(out)
    assert it["type"] == "approval_blocking" and it["channel"] == "toast" and it["reason_code"] == "shown_break" and it["title"] == "An approval is waiting"
    assert nxt(svc, ws(T0 + 31))["item"] is None                                    # on screen: nothing new
    out = nxt(svc, ws(T0 + 30 + 1200))                                              # the lock and display are long over
    rem = item_of(out)
    assert rem and rem["reminder"] is True and rem["title"] == "An approval is still waiting" and "only reminder" in rem["body"]
    for dt in (1500, 4000, 20000, 80000):
        assert nxt(svc, ws(T0 + dt))["item"] is None                                # never nagged again
    assert nxt(svc, ws(T0 + 80000))["badges"]["needs_you"] == 1                     # the passive badge stays until it is resolved or expires


def test_a_reacted_item_gets_no_reminder_but_stays_counted(svc):
    r = svc.submit(ev("approval_blocking", "q1"), ws())
    it = item_of(nxt(svc, ws()))
    svc.feedback(P, it["id"], "dismissed", seconds=6, now=T0 + 6)
    assert nxt(svc, ws(T0 + 5000))["item"] is None
    assert svc.badges(P)["badges"]["needs_you"] == 1 and r["item_id"] == it["id"]


# ------------------------------------------------------------------------------------------------ one voice
def test_a_cue_and_a_toast_never_coexist_and_safety_preempts(svc):
    cue = svc.submit(ev("cue_ask", "e1", expires_in_s=12), ws(quiet_s=5))
    assert cue["show"] is True
    svc.submit(ev("approval_blocking", "q1"), ws())
    held = nxt(svc, ws(T0 + 1, quiet_s=30))
    assert held["item"] is None and held["active"]["type"] == "cue_ask"
    assert svc.why(svc.store.person(P).items[[k for k, v in svc.store.person(P).items.items() if v.type == "approval_blocking"][0]].id)["reason_code"] == "held_lock"
    again = svc.submit(ev("cue_cue", "e2", expires_in_s=12), ws(T0 + 2, quiet_s=5))
    assert again["show"] is False and again["decision"]["reason_code"] == "dropped_lock"
    after = nxt(svc, ws(T0 + 13))                                                   # the question's 12 s are over
    assert item_of(after)["type"] == "approval_blocking"
    svc.submit(ev("injection_pause", "r7"), ws(T0 + 14))
    pre = item_of(nxt(svc, ws(T0 + 15)))
    assert pre["type"] == "injection_pause" and pre["preempt"] is True and pre["channel"] == "toast"


def test_two_deliverable_items_are_shown_one_at_a_time(svc):
    svc.submit(ev("approval_blocking", "q1"), busy())
    svc.submit(ev("run_blocked_error", "r1"), busy())
    first = item_of(nxt(svc, ws(T0 + 5)))
    assert first
    assert nxt(svc, ws(T0 + 6))["item"] is None
    second = item_of(nxt(svc, ws(T0 + 5 + 21)))
    assert second and second["id"] != first["id"]
    assert {first["type"], second["type"]} == {"approval_blocking", "run_blocked_error"}


def test_a_cue_escalation_is_a_continuation_and_extends_the_display(svc):
    a = svc.submit(ev("cue_cue", "e1", expires_in_s=12), ws(quiet_s=5))
    b = svc.submit(ev("cue_cue", "e1", expires_in_s=12), ws(T0 + 6, quiet_s=5))
    assert a["show"] and b["coalesced"] and b["show"] is True
    assert svc.store.person(P).lock["until"] >= T0 + 6 + 12 - 1e-6


def test_admission_uses_the_last_polled_state_and_fails_closed_when_it_is_stale(svc):
    nxt(svc, busy())                                                                # the adapter polled: the worker is typing
    out = svc.submit(ev("cue_cue", "e1"), None, now=T0 + 3)
    assert out["show"] is False and out["decision"]["reason_code"] == "dropped_flow"
    stale = svc.submit(ev("cue_cue", "e2"), None, now=T0 + 60)                       # no poll for a minute: unknown, never interrupt
    assert stale["show"] is False and stale["decision"]["reason_code"] == "dropped_state_unknown"
    fresh = svc.submit(ev("cue_cue", "e3"), ws(T0 + 200, quiet_s=4))
    assert fresh["show"] is True


# ------------------------------------------------------------------------------------------------ roll-up and digests
def test_several_can_wait_items_at_one_break_become_one_summary(svc):
    for t in ("briefing_ready", "run_finished", "morning_report"):
        svc.submit(ev(t, f"{t}1", outcome="done" if t == "run_finished" else None), ws())
    s = svc.store
    s.person(P).settings = {"modes": {"briefing_ready": "loud", "run_finished": "loud", "morning_report": "loud"}}
    out = nxt(svc, ws(T0 + 10))
    it = item_of(out)
    assert it and it["type"] == "attention_digest" and it["text_id"] == "digest_rollup"
    assert nxt(svc, ws(T0 + 40))["item"] is None
    folded = [i for i in svc.store.person(P).items.values() if i.state == "digested"]
    assert len(folded) == 3 and all(i.folded_into == it["id"] for i in folded)


def test_a_morning_digest_is_one_toast_only_if_something_needs_the_worker_else_a_banner(svc):
    svc.submit(ev("run_finished", "r1", outcome="done", run_mode="overnight", count=3), ws(T0 - 3600 * 9, local_hour=1))
    svc.submit(ev("briefing_ready", "b1", count=4), ws(T0 - 3600 * 9, local_hour=1))
    # the worker is away overnight
    nxt(svc, ws(T0 - 3600 * 9, away=True, away_s=0, local_hour=1))
    nxt(svc, ws(T0 - 3600 * 4, away=True, away_s=18000, local_hour=6))
    out = nxt(svc, ws(T0 - 10, quiet_s=0.5, local_hour=9))                            # back at their desk
    assert out["digest_ready"] is True
    out2 = nxt(svc, ws(T0, quiet_s=0.5, local_hour=10))
    d = svc.digest(P, "morning")
    assert d["kind"] == "morning" and d["ran"] == 3 and d["can_ignore"] == 4 and d["needs_you"] == 0
    it = item_of(out) or item_of(out2)
    assert it is None                                                                 # nothing needs them: the digest is a banner, not a toast
    ps = svc.store.person(P)
    dig = [i for i in ps.items.values() if i.type == "attention_digest"]
    assert len(dig) == 1 and dig[0].state == "shown" and dig[0].channel == V.BANNER
    assert all(i.state == "digested" for i in ps.items.values() if i.type in ("run_finished", "briefing_ready"))


def test_a_digest_with_a_needs_you_item_is_one_toast_and_the_item_is_not_announced_twice(svc):
    svc.submit(ev("approval_blocking", "q1"), ws(T0 - 7200, away=True))
    svc.submit(ev("run_finished", "r1", outcome="failed", count=1), ws(T0 - 7200, away=True))
    nxt(svc, ws(T0 - 7200, away=True, away_s=0))
    nxt(svc, ws(T0 - 3600, away=True, away_s=3600))
    first = item_of(nxt(svc, ws(T0, quiet_s=0.5)))                                    # back: the approval, first
    assert first and first["type"] == "approval_blocking"
    nxt(svc, ws(T0 + 21, quiet_s=0.5))
    types = {i.type: i for i in svc.store.person(P).items.values()}
    dig = types["attention_digest"]
    assert dig.needs_you_n == 0                                                         # it was shown on its own: the summary is a banner, not a second toast
    assert dig.channel in (V.BANNER, V.TOAST)


def test_nothing_to_say_is_silence_not_a_summary(svc):
    nxt(svc, ws(T0 - 5000, away=True, away_s=0))
    nxt(svc, ws(T0, quiet_s=1))
    assert not [i for i in svc.store.person(P).items.values() if i.type == "attention_digest"]
    assert svc.digest(P, "return")["lines"] == []


def test_digests_are_spaced_by_the_gap(svc):
    def go(t0):
        svc.submit(ev("briefing_ready", f"b{int(t0)}"), ws(t0 - 4100))
        nxt(svc, ws(t0 - 4000, away=True, away_s=0))
        nxt(svc, ws(t0 - 50, away=True, away_s=3950))
        nxt(svc, ws(t0, quiet_s=1))
    go(T0)
    go(T0 + 4000)                                                                       # less than the 3 h gap
    assert len([i for i in svc.store.person(P).items.values() if i.type == "attention_digest"]) == 1
    go(T0 + 4000 + 11000)
    assert len([i for i in svc.store.person(P).items.values() if i.type == "attention_digest"]) == 2


def test_digest_preview_folds_nothing(svc):
    svc.submit(ev("briefing_ready", "b1", count=2), ws())
    before = {k: v.state for k, v in svc.store.person(P).items.items()}
    pv = svc.digest(P, "now", T0 + 5)
    assert pv["can_ignore"] == 2 and pv["lines"] and {k: v.state for k, v in svc.store.person(P).items.items()} == before


# ------------------------------------------------------------------------------------------------ markers are state, never delayed
@pytest.mark.parametrize("state", [dict(dnd=True), dict(screen_sharing=True), dict(on_call=True), dict(in_meeting=True), dict(away=True), dict(locked=True),
                                   dict(typing_burst=True, quiet_s=0.2), dict(deep_work=True, quiet_s=2), dict(known=False)])
def test_the_stopped_marker_is_never_delayed_by_any_quiet_state_or_the_lock(svc, state):
    svc.submit(ev("cue_ask", "e1"), ws(quiet_s=5))                                      # a question card holds the lock
    svc.submit(ev("kill_engaged", "kill1"), ws(**state))
    out = nxt(svc, ws(T0 + 1, **state))
    assert out["badges"]["marker"] == "stopped" and out["badges"]["stopped"] is True    # from open items alone: no worker state, no lock, no budget
    svc.submit(ev("kill_cleared", "kill1"), ws(T0 + 2))
    assert nxt(svc, ws(T0 + 3))["badges"]["marker"] == "none"


def test_the_kill_notice_itself_is_shown_at_once_unless_the_worker_is_away(svc):
    svc.submit(ev("kill_engaged", "k1"), busy())
    it = item_of(nxt(svc, busy(T0 + 1)))
    assert it and it["type"] == "kill_engaged" and it["title"] == "Everything is stopped"
    away = AttentionService(AttentionStore(), clock=lambda: T0)
    away.submit(ev("kill_engaged", "k1"), ws(away=True))
    assert item_of(away.next(P, ws(T0 + 1, away=True))) is None
    assert away.next(P, ws(T0 + 2, away=True))["badges"]["marker"] == "stopped"
    assert item_of(away.next(P, ws(T0 + 3)))["type"] == "kill_engaged"                   # first thing on return


def test_agent_acting_and_the_stop_pill_have_no_way_through_this_layer(svc):
    for name in ("agent_acting", "stop_pill", "stop_all", "glance_in_flight"):
        with pytest.raises(EventError):
            from understudy_engine.attention.events import parse_event
            parse_event({"type": name, "person": P, "subject": "x"})


# ------------------------------------------------------------------------------------------------ feedback and learning
def test_never_for_this_suppresses_the_subject_and_reaches_the_estimates(svc):
    svc.submit(ev("routine_proposal", "calc-entry"), ws())
    it = item_of(nxt(svc, ws()))
    assert it["type"] == "routine_proposal"
    out = svc.feedback(P, it["id"], "never", now=T0 + 3)
    assert out["label"] == "never" and out["state"] == "suppressed"
    again = svc.submit(ev("routine_proposal", "calc-entry"), ws(T0 + 5000))
    assert again["state"] == "suppressed" and again["decision"]["reason_code"] == "dropped_never_subject"
    assert svc.submit(ev("routine_proposal", "other"), ws(T0 + 5000))["state"] != "suppressed"


def test_a_worker_who_dismisses_everything_gets_a_quieter_router_but_approvals_stay_visible(svc):
    t = T0
    for i in range(30):                                                                 # thirty proposals, each closed within a second
        t += 4000
        r = svc.submit(ev("routine_proposal", f"rt{i}"), ws(t))
        out = nxt(svc, ws(t + 1))
        it = item_of(out)
        if it and it["type"] == "routine_proposal":
            svc.feedback(P, it["id"], "dismissed", seconds=1.0, now=t + 2)
    drop = svc.store.person(P).acc.learned_drop("routine_proposal", 10)
    assert drop >= 1
    shown_late = [i for i in svc.store.person(P).items.values() if i.type == "routine_proposal" and i.interrupted]
    assert 4 <= len(shown_late) < 30                                                    # it learned: later proposals were not toasts
    # approvals still reach them, through a toast, because the floor keeps them visible
    svc.submit(ev("approval_blocking", "qq"), ws(t + 9000))
    assert item_of(nxt(svc, ws(t + 9000)))["type"] == "approval_blocking"
    svc.submit(ev("approval_waiting", "q2"), ws(t + 9100))
    assert svc.badges(P)["badges"]["needs_you"] >= 2


def test_an_ignored_toast_is_labelled_by_the_display_timing_out(svc):
    svc.submit(ev("routine_proposal", "rp1"), ws())
    it = item_of(nxt(svc, ws()))
    assert it
    nxt(svc, ws(T0 + 60))                                                              # twenty seconds were up, nobody touched it
    ps = svc.store.person(P)
    assert ps.labels and ps.labels[-1]["label"] == "ignored"
    assert ps.items[it["id"]].state == "dismissed"                                      # a can-wait toast does not come back


def test_feedback_validates_event_and_item(svc):
    svc.submit(ev("routine_proposal", "rp1"), ws())
    with pytest.raises(EventError):
        svc.feedback(P, "i_nope", "followed")
    it = item_of(nxt(svc, ws()))
    with pytest.raises(EventError):
        svc.feedback(P, it["id"], "exploded")
    assert svc.feedback(P, it["id"], "followed", seconds=3, now=T0 + 3)["label"] == "followed"
    assert svc.feedback(P, it["id"], "shown")["label"] is None


# ------------------------------------------------------------------------------------------------ transparency and settings
def test_why_gives_a_fixed_one_line_reason_and_the_transitions(svc):
    r = svc.submit(ev("approval_blocking", "q1"), busy())
    w = svc.why(r["item_id"])
    assert w["reason_code"] == "held_typing" and w["reason_text"] == "Held because you were typing. Shown at your next pause."
    nxt(svc, ws(T0 + 40))
    w2 = svc.why(r["item_id"])
    assert w2["state"] == "shown" and [x["state"] for x in w2["transitions"]][-1] == "shown" and w2["budget"]["per_day"] == 10
    assert svc.why("i_missing") is None


def test_settings_validate_and_safety_cannot_be_turned_down(svc):
    out = svc.set_settings(P, modes={"routine_proposal": "digest", "approval_blocking": "quiet"}, budget_per_day=6, level_glance=False)
    modes = {t["type"]: t["mode"] for t in out["types"]}
    assert modes["routine_proposal"] == "digest" and out["budget_per_day"] == 6 and out["level_glance"] is False
    with pytest.raises(EventError) as e:
        svc.set_settings(P, modes={"injection_pause": "quiet"})
    assert e.value.code == "safety_fixed"
    for bad in ({"modes": {"made_up": "quiet"}}, {"modes": {"run_finished": "silent"}}, {"budget_per_day": 41}, {"budget_per_day": -1}, {"budget_per_day": True}):
        with pytest.raises(EventError):
            svc.set_settings(P, **bad)
    assert any(f["type"] == "injection_pause" for f in out["floors"]) and any(f["type"] == "approval_blocking" for f in out["floors"])
    svc.set_settings(P, modes={"routine_proposal": "normal"})
    assert "routine_proposal" not in svc.store.person(P).settings["modes"]


def test_the_worker_can_turn_the_level_glance_fully_off(svc, monkeypatch):
    assert svc.submit(ev("help_level_changed", "lv1", expires_in_s=60), ws(quiet_s=5))["show"] is True
    svc.set_settings(P, level_glance=False)
    off = svc.submit(ev("help_level_changed", "lv2", expires_in_s=60), ws(T0 + 5000, quiet_s=5))
    assert off["show"] is False and off["decision"]["reason_code"] == "dropped_mode"
    svc.set_settings(P, level_glance=True)
    monkeypatch.setenv("UNDERSTUDY_ATTENTION_LEVEL_GLANCE", "0")
    env = svc.submit(ev("help_level_changed", "lv3", expires_in_s=60), ws(T0 + 9000, quiet_s=5))
    assert env["show"] is False and env["decision"]["reason_code"] == "dropped_mode"


def test_reset_learned_clears_the_labels(svc):
    t = T0
    for i in range(16):
        t += 4000
        svc.submit(ev("routine_proposal", f"r{i}"), ws(t))
        it = item_of(nxt(svc, ws(t + 1)))
        if it:
            svc.feedback(P, it["id"], "dismissed", seconds=1, now=t + 2)
    assert svc.store.person(P).acc.learned_drop("routine_proposal", 10) >= 1
    svc.set_settings(P, reset_learned=True)
    assert svc.store.person(P).acc.learned_drop("routine_proposal", 10) == 0 and not svc.store.person(P).labels


# ------------------------------------------------------------------------------------------------ persistence and privacy
def test_state_round_trips_through_the_file_and_holds_only_metadata(tmp_path):
    path, log = tmp_path / "attention" / "state.json", tmp_path / "attention" / "log.jsonl"
    a = AttentionService(AttentionStore(path, log), clock=lambda: T0)
    a.submit(ev("approval_blocking", "q_12", count=2, risk_class="irreversible"), busy())
    a.next(P, ws(T0 + 40))
    b = AttentionService(AttentionStore(path, log), clock=lambda: T0)
    ps = b.store.person(P)
    assert len(ps.items) == 1 and next(iter(ps.items.values())).state == "shown" and ps.lock is not None
    raw = path.read_text() + log.read_text()
    assert "q_12" in raw
    doc = json.loads(path.read_text())
    assert doc["version"] == 1
    assert oct(log.stat().st_mode & 0o777) == "0o600"


def test_a_planted_string_cannot_reach_the_store_or_the_log(tmp_path):
    path, log = tmp_path / "s.json", tmp_path / "l.jsonl"
    s = AttentionService(AttentionStore(path, log), clock=lambda: T0)
    from understudy_engine.attention.events import parse_event
    for bad in ({"type": "run_finished", "person": P, "subject": "r1", "title": "PLANTED-SECRET-123"},
                {"type": "run_finished", "person": P, "subject": "PLANTED SECRET 123"},
                {"type": "run_finished", "person": P, "subject": "r1", "outcome": "PLANTED-SECRET-123"}):
        with pytest.raises(EventError):
            parse_event(bad)
    s.submit(ev("run_finished", "r1", outcome="done"), ws())
    nxt(s, ws(T0 + 100))
    assert "PLANTED" not in path.read_text() + (log.read_text() if log.exists() else "")


def test_export_and_delete_are_the_workers(svc):
    svc.submit(ev("approval_blocking", "q1"), ws())
    doc = svc.store.export(P)
    assert doc["metadata_only"] is True and doc["state"]["items"]
    assert svc.store.delete(P) == 1 and svc.store.person(P).items == {}


def test_local_day_follows_the_workers_hour():
    assert local_day(T0, 10) == local_day(T0 + 3600, 11) and local_day(T0, 10) != local_day(T0 + 15 * 3600, 1)
    assert local_day(T0, 10) == local_day(T0, 10)


# ------------------------------------------------------------------------------------------------ deferral (the desktop could not draw it)
def test_a_deferred_item_goes_back_to_held_with_no_label_and_the_counters_return(svc):
    svc.submit(ev("routine_proposal", "rp1"), ws())
    it = item_of(nxt(svc, ws()))
    ps = svc.store.person(P)
    assert ps.budget_used == 1 and ps.wait_toasts == 1 and ps.last_interruption_t == T0
    out = svc.feedback(P, it["id"], "deferred", now=T0 + 1)
    assert out["state"] == "held" and out["label"] is None and not ps.labels
    assert ps.budget_used == 0 and ps.wait_toasts == 0 and ps.last_interruption_t is None and ps.lock is None
    again = item_of(nxt(svc, ws(T0 + 2)))
    assert again and again["id"] == it["id"]                                         # offered again, as if nothing had happened


def test_a_deferred_reminder_gives_the_reminder_back(svc):
    svc.submit(ev("approval_blocking", "q1"), ws())
    nxt(svc, ws())
    rem = item_of(nxt(svc, ws(T0 + 1300)))
    assert rem and rem["reminder"] is True
    svc.feedback(P, rem["id"], "deferred", now=T0 + 1301)
    it = svc.store.person(P).items[rem["id"]]
    assert it.reminders == 0 and it.state == "shown"
    assert item_of(nxt(svc, ws(T0 + 1400)))["reminder"] is True


def test_the_digest_preview_gives_screens_ids_and_worded_rows(svc):
    svc.submit(ev("approval_blocking", "q1"), busy())
    svc.submit(ev("approval_blocking", "q2"), busy())
    svc.submit(ev("run_finished", "r1", outcome="done"), ws())
    svc.submit(ev("cue_cue", "e1"), busy())                                            # dropped: the worker was typing
    pv = svc.digest(P, "now", T0 + 1)
    first = pv["needs_you_items"][0]
    assert first["type"] == "approval_blocking" and first["count"] == 2 and first["id"] in first["ids"] and len(first["ids"]) == 2
    assert svc.why(first["id"])["reason_text"]
    rows = {(r["state"], r["code"]): r for r in pv["today_detail"]}
    assert rows[("held", "held_typing")]["n"] == 2 and rows[("held", "held_typing")]["reason_text"] == "Held because you were typing. Shown at your next pause."
    assert rows[("dropped", "dropped_flow")]["n"] == 1
    assert all(r["reason_text"] for r in pv["today_detail"])
