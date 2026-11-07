from __future__ import annotations

import json

import jsonschema
import pytest

from understudy_engine.attention import paths as P
from understudy_engine.attention import vocab as V
from understudy_engine.attention.events import EventError, parse_event
from understudy_engine.attention.learning import Acceptance, Label, hour_kernel, label_of, label_weights
from understudy_engine.attention.state import DEFAULT, parse_state

from .conftest import T0

GOOD = {"type": "approval_blocking", "person": "p_ada", "subject": "q_12", "count": 2, "risk_class": "irreversible", "blocks_run": True}


def test_a_good_event_parses_and_agrees_with_the_json_schema():
    schema = json.loads(P.schema_path().read_text())
    jsonschema.validate({k: v for k, v in GOOD.items() if k != "person"}, schema)
    e = parse_event(GOOD)
    assert e.type == "approval_blocking" and e.dedup_key == "approval:q_12" and e.count == 2


@pytest.mark.parametrize("patch", [
    {"type": "attention_digest"}, {"type": "made_up"}, {"subject": "Has Spaces"}, {"subject": "x" * 65}, {"subject": ""}, {"person": "ada"},
    {"count": 0}, {"count": 1000}, {"count": True}, {"risk_class": "scary"}, {"outcome": "great"}, {"expires_in_s": 0}, {"minutes": -1},
    {"blocks_run": "yes"}, {"title": "free text"}, {"body": "free text"}, {"text": "x"}, {"op": "delete"}, {"origin": "model"},
])
def test_bad_events_are_refused_and_the_schema_agrees_on_the_enum_cases(patch):
    d = {**GOOD, **patch}
    with pytest.raises(EventError):
        parse_event(d)


def test_unknown_fields_are_refused_both_ways():
    schema = json.loads(P.schema_path().read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"type": "run_finished", "subject": "r1", "title": "My secret run"}, schema)
    with pytest.raises(EventError):
        parse_event({"type": "run_finished", "person": "p_a", "subject": "r1", "title": "My secret run"})


def test_service_degraded_needs_a_service_and_deadline_needs_its_time():
    with pytest.raises(EventError):
        parse_event({"type": "service_degraded", "person": "p_a", "subject": "svc"})
    with pytest.raises(EventError):
        parse_event({"type": "calendar_deadline", "person": "p_a", "subject": "d1"})
    assert parse_event({"type": "calendar_deadline", "person": "p_a", "subject": "d1", "deadline_in_s": 600}).deadline_in_s == 600


def test_a_blocking_waiting_approval_is_upgraded_and_only_cues_can_be_asked_for():
    assert parse_event({"type": "approval_waiting", "person": "p_a", "subject": "q1", "blocks_run": True}).type == "approval_blocking"
    assert parse_event({"type": "run_finished", "person": "p_a", "subject": "r1", "asked": True}).asked is False
    assert parse_event({"type": "cue_cue", "person": "p_a", "subject": "e1", "asked": True}).asked is True


def test_parse_state_unknown_when_empty_or_stale_and_reads_flags():
    assert parse_state({}, T0).known is False
    assert parse_state({"typing": "1"}, T0).known is False                      # `typing` is the route's alias; the route maps it
    s = parse_state({"typing_burst": "true", "quiet_s": "0.5", "dnd": "1", "local_hour": "9"}, T0)
    assert s.known and s.typing_burst and s.dnd and s.quiet_s == 0.5 and s.local_hour == 9 and s.hard_quiet() == "dnd"
    stale = parse_state({"quiet_s": "5", "t": T0 - 11}, T0, DEFAULT)
    assert stale.known is False                                                  # older than the freshness row (10 s): unknown
    assert parse_state({"quiet_s": "5", "t": T0 - 5}, T0, DEFAULT).known is True


def test_hard_quiet_precedence():
    s = parse_state({"screen_sharing": "1", "in_meeting": "1", "on_call": "1"}, T0)
    assert s.hard_quiet() == "screen_sharing"


# -------------------------------------------------------------------------------------------------- learning
def test_labels_follow_the_windows():
    assert label_of("followed", 3) == "followed" and label_of("opened", 40) == "followed"
    assert label_of("dismissed", 3.9) == "dismissed_fast" and label_of("dismissed", 4.5) == "dismissed"
    assert label_of("ignored", None) == "ignored" and label_of("never", None) == "never" and label_of("shown", 1) is None
    assert label_weights("followed", 5) == (1.0, 0.0) and label_weights("followed", 30) == (0.5, 0.0)


def test_kernel_is_circular():
    assert hour_kernel(23, 0) == 0.5 and hour_kernel(0, 22) == 0.25 and hour_kernel(3, 3) == 1.0 and hour_kernel(0, 12) == 0.1


def mk(type_id, hour, label, n, **kw):
    return [Label(type_id, hour, label, kw.get("seconds"), kw.get("subject"), 0.0) for _ in range(n)]


def test_no_drop_without_enough_evidence_and_never_negative():
    acc = Acceptance(mk("routine_proposal", 10, "dismissed_fast", 3))
    assert acc.learned_drop("routine_proposal", 10) == 0                         # n_eff below n_min: the prior holds
    for h in range(24):
        assert acc.learned_drop("routine_proposal", h) >= 0


def test_rejections_quieten_one_then_two_rungs():
    one = Acceptance(mk("routine_proposal", 10, "dismissed_fast", 8, seconds=1))
    assert one.learned_drop("routine_proposal", 10) == 1                          # p = 2 / (4 + 8) = 0.17
    acc = Acceptance(mk("routine_proposal", 10, "dismissed_fast", 14, seconds=1))
    assert acc.learned_drop("routine_proposal", 10) == 2                          # p = 2 / (4 + 14) = 0.11
    mild = Acceptance(mk("routine_proposal", 10, "dismissed", 4, seconds=8) + mk("routine_proposal", 10, "followed", 1, seconds=3) + mk("routine_proposal", 10, "ignored", 3))
    p, n = mild.estimate("routine_proposal", 10)
    assert n >= DEFAULT.n_min and 0.12 < p <= 0.40
    assert mild.learned_drop("routine_proposal", 10) in (0, 1)


def test_acceptance_never_quietens_safety_or_blocking_approvals_or_anything_unknown():
    acc = Acceptance(mk("approval_blocking", 10, "never", 20, subject="s") + mk("injection_pause", 10, "dismissed_fast", 20) + mk("kill_engaged", 10, "never", 20))
    for t in ("approval_blocking", "injection_pause", "kill_engaged", "made_up", "run_blocked_target", "calendar_deadline"):
        assert acc.learned_drop(t, 10) == 0


def test_followed_labels_keep_a_type_loud():
    acc = Acceptance(mk("briefing_ready", 10, "followed", 20, seconds=2))
    assert acc.learned_drop("briefing_ready", 10) == 0 and acc.estimate("briefing_ready", 10)[0] > 0.8


def test_hours_borrow_from_neighbours_but_not_from_far_away():
    acc = Acceptance(mk("routine_proposal", 14, "dismissed_fast", 14, seconds=1))
    assert acc.learned_drop("routine_proposal", 14) == 2 and acc.learned_drop("routine_proposal", 15) >= 1
    assert acc.learned_drop("routine_proposal", 2) == 0                           # twelve hours away: the far-hour kernel is 0.1 each


def test_three_nevers_on_distinct_subjects_move_a_type_to_its_maximum():
    labels = [Label("briefing_ready", 9, "never", None, f"b{i}", 0.0) for i in range(3)]
    assert Acceptance(labels).learned_drop("briefing_ready", 9) == 2
    same = [Label("briefing_ready", 9, "never", None, "b0", 0.0) for _ in range(3)]
    assert Acceptance(same).learned_drop("briefing_ready", 9) == 0                 # one subject three times is not three subjects


def test_reset_clears_the_estimates_and_window_is_capped():
    acc = Acceptance(mk("routine_proposal", 10, "dismissed_fast", 10, seconds=1))
    acc.reset(["routine_proposal"])
    assert acc.learned_drop("routine_proposal", 10) == 0
    many = Acceptance(mk("routine_proposal", 10, "dismissed_fast", 500, seconds=1))
    assert len(many.labels()) == DEFAULT.label_window
