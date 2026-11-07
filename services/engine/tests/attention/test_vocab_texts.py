"""The closed vocabularies are consistent, and every word the layer says passes the house style."""
from __future__ import annotations

import json

import pytest

from understudy_engine.attention import digest as D
from understudy_engine.attention import paths as P
from understudy_engine.attention import texts as X
from understudy_engine.attention import vocab as V
from understudy_engine.attention.events import Item

from .conftest import T0, ev


def test_every_type_has_a_consistent_ladder_floor_and_modes():
    for t, sp in V.TYPES.items():
        assert sp.ladder[-1] == sp.floor, t                                   # the ladder ends at the floor
        for mode, (chan, deliver) in sp.modes.items():
            assert chan in sp.ladder, (t, mode)
            assert deliver in V.DELIVER_AT
        assert set(sp.modes) == set(V.MODES)
        assert sp.cls in V.CLASSES and sp.ttl_s > 0
        assert V.RANK[sp.floor] >= 0


def test_safety_rows_are_identical_in_all_four_modes_and_floor_at_toast():
    for t, sp in V.TYPES.items():
        if sp.cls == V.SAFETY:
            assert len({sp.modes[m] for m in V.MODES}) == 1 and sp.modes["normal"] == (V.TOAST, V.NOW)
            assert sp.ladder == (V.TOAST,) and sp.floor == V.TOAST and sp.needs_you and not sp.reminders


def test_time_types_floor_at_badge_and_have_one_reminder_kind():
    for t, sp in V.TYPES.items():
        if sp.cls == V.TIME:
            assert sp.floor == V.BADGE and sp.reminders and sp.needs_you
    assert V.TYPES["approval_waiting"].floor == V.BADGE


def test_only_chip_and_above_interrupt_and_there_is_no_phone_channel():
    assert V.INTERRUPTING == {V.CHIP, V.TOAST, V.QUESTION, V.VOICE}
    assert not {c for c in V.CHANNELS if "phone" in c or "sms" in c or "push" in c}


def test_no_marker_is_an_event_type():
    for name in ("agent_acting", "stop_all", "stop_pill", "glance_in_flight", "kill_state", "paused"):
        assert name not in V.TYPES                                           # state, drawn by its owner; never delayed here


def test_schema_enum_matches_the_submittable_types():
    schema = json.loads(P.schema_path().read_text())
    assert set(schema["properties"]["type"]["enum"]) == set(V.SUBMITTABLE)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["op"]["enum"]) == set(V.OPS)
    assert set(schema["properties"]["risk_class"]["enum"]) == set(V.RISK_CLASSES)
    assert set(schema["properties"]["outcome"]["enum"]) == set(V.OUTCOMES)
    assert set(schema["properties"]["run_mode"]["enum"]) == set(V.RUN_MODES)
    assert set(schema["properties"]["service"]["enum"]) == set(V.SERVICES)


def test_every_non_passthrough_type_has_a_template_and_every_template_lints():
    for t, sp in V.TYPES.items():
        if t == "attention_digest" or sp.passthrough or t == "kill_cleared":
            continue
        assert t in X.TEMPLATES, t
    sample = dict(count=3, minutes=45, run_mode="overnight", service="agent", deadline_in_s=2700, payload={"ran": 3, "needs_you": 1, "can_ignore": 4})
    for tid in X.TEMPLATES:
        title, body = X.render(tid, **sample)
        assert X.lint(title, body) == [], (tid, X.lint(title, body), title, body)
        for count in (1, 2, 12):
            title, body = X.render(tid, **{**sample, "count": count, "payload": {"ran": 0, "needs_you": count, "can_ignore": 0}})
            assert X.lint(title, body) == [], (tid, count)


def test_every_reason_line_lints_and_every_router_reason_has_one():
    for code, line in X.REASONS.items():
        assert X.lint(None, line, reason=True) == [], (code, line)
    # every reason code the router can emit has a line (the router's literals plus the quiet states)
    emitted = {"shown_safety", "safety_on_return", "shown_now", "shown_break", "shown_asked", "shown_reminder", "shown_digest", "held_lock",
               "held_spacing", "held_state_unknown", "held_away", "held_typing", "held_deep_work", "held_not_a_break", "passive_badge",
               "passive_banner", "passive_digest", "passive_budget", "passive_learned", "passive_mode", "dropped_resolved", "dropped_expired",
               "dropped_superseded", "dropped_never_subject", "dropped_flow", "dropped_lock", "dropped_spacing", "dropped_budget", "dropped_mode",
               "dropped_learned", "dropped_state_unknown", "dropped_away", "log_only"}
    emitted |= {f"{p}_{q}" for p in ("held", "dropped") for q in ("dnd", "screen_sharing", "on_call", "in_meeting")}
    assert emitted <= set(X.REASONS), emitted - set(X.REASONS)


@pytest.mark.parametrize("bad", [
    "Act now!", "Just a quick note.", "Heads up: a run paused.", "Reminder: approve this.", "Don't forget to approve.", "You forgot an approval.",
    "This is urgent.", "Hurry and decide.", "Oops, something broke.", "You should open it.", "Welcome back.", "Right now matters.", "You missed it.",
])
def test_the_linter_catches_urgency_guilt_and_stock_phrases(bad):
    assert X.lint("Title", f"Understudy: {bad}"), bad


def test_the_linter_checks_length_source_case_and_full_stop():
    assert "title:too_long" in X.lint("one two three four five six seven eight nine", "Understudy: ok.")
    assert "body:too_long" in X.lint("Title", "Understudy: " + " ".join(["word"] * 30) + ".")
    assert "source:missing" in X.lint("Title", "Something happened.")
    assert "body:no_full_stop" in X.lint("Title", "Understudy: no stop")
    assert "title:not_sentence_case" in X.lint("lower title", "Understudy: fine.")
    assert X.lint("Everything is stopped", "Understudy: nothing is running.") == []


def test_every_notification_names_its_source_from_the_fixed_set():
    for tid in X.TEMPLATES:
        title, body = X.render(tid, count=2, run_mode="background", service="model", deadline_in_s=600, payload={"ran": 2, "needs_you": 2, "can_ignore": 1})
        assert any(s in f"{title} {body}" for s in V.SOURCES), tid


def test_slots_never_carry_free_text_and_minutes_are_rounded_to_five():
    assert X.phrase_minutes(47) == "in 45 minutes" and X.phrase_minutes(3) == "in less than 5 minutes" and X.phrase_minutes(180) == "in 3 hours"
    assert X.phrase_minutes(60 * 30) == "in more than a day"
    assert "in 45 minutes" in X.render("calendar_deadline", deadline_in_s=47 * 60)[1]


def test_passthrough_types_have_no_words_of_ours():
    for t in ("cue_cue", "cue_ask", "cue_offer", "voice_line", "help_level_changed"):
        it = Item.from_event(ev(t), "i_x", T0)
        r = X.render_item(it, now=T0)
        assert r["text_id"] == X.PASSTHROUGH and r["title"] is None and r["body"] is None


def test_digest_lines_lint_and_are_capped_and_ordered_by_urgency():
    items = []
    for i, t in enumerate(("approval_waiting", "irreversible_decision", "run_blocked_target", "calendar_deadline", "injection_pause", "approval_blocking",
                           "kill_engaged")):
        it = Item.from_event(ev(t, f"s{i}", count=2), f"i_{i}", T0)
        items.append(it)
    items.append(Item.from_event(ev("run_finished", "r1", count=3, outcome="done"), "i_r", T0))
    items.append(Item.from_event(ev("briefing_ready", "b1", count=4), "i_b", T0))
    pl = D.summarise(items, "morning", T0)
    assert len(pl["lines"]) <= 7 and D.lint_lines(pl) == []
    first = pl["lines"][0]
    assert "stopped" in first or "paused" in first or "cannot be undone" in first       # safety first
    assert pl["needs_you_items"][0]["type"] in ("kill_engaged", "injection_pause", "irreversible_decision")
    assert pl["ran"] == 3 and pl["can_ignore"] == 4
