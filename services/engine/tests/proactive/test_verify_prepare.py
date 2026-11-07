"""Verify drops stale cards (and only those); prepare builds editable content from templates."""
from __future__ import annotations

from datetime import timedelta

import pytest

from understudy_engine.proactive.candidates import Ctx, collect
from understudy_engine.proactive.cards import new_card
from understudy_engine.proactive.prepare import prepare
from understudy_engine.proactive.verify import verify_one

from .conftest import NOW, P, cal_row, git_row, make_readers, routine_row, run_row, skill_row

CTX = Ctx(person=P, now=NOW)


def _first(readers, kind):
    return next(c for c in collect(CTX, readers).candidates if c.kind == kind)


def _verdict(cand, readers, **kw):
    return verify_one(cand, collect(CTX, readers), CTX, **kw)


# ----------------------------------------------------------------------------------------------- stale
@pytest.mark.parametrize("change,why", [({"status": "shadow"}, "switched"), ({"status": "approval"}, "switched"),
                                        ({"status": "declined"}, "no"), ({"status": "never"}, "no"), ({"proposable": False}, "not ready")])
def test_automate_goes_stale_when_the_routine_is_already_on_or_declined(change, why):
    cand = _first(make_readers(routines=[routine_row()]), "automate")
    v = _verdict(cand, make_readers(routines=[routine_row(**change)]))
    assert v.verdict == "stale" and why in v.note.lower() and v.checked


def test_automate_stale_when_the_routine_vanished():
    cand = _first(make_readers(routines=[routine_row()]), "automate")
    assert _verdict(cand, make_readers(routines=[])).verdict == "stale"


def test_practice_stale_once_the_skill_reaches_level_4():
    cand = _first(make_readers(skills=[skill_row()]), "practice")
    v = _verdict(cand, make_readers(skills=[skill_row(level=4, mastery=0.95)]))
    assert v.verdict == "stale" and "level 4" in v.note


def test_focus_block_stale_when_the_calendar_no_longer_suggests_it():
    cand = _first(make_readers(calendar=[cal_row()]), "focus_block")
    assert _verdict(cand, make_readers(calendar=[])).verdict == "stale"
    assert _verdict(cand, make_readers(calendar=[cal_row()])).verdict == "confirmed"


def test_git_habit_stale_when_it_falls_inside_the_noise():
    cand = _first(make_readers(git=[git_row()]), "git_habit")
    assert _verdict(cand, make_readers(git=[git_row(ci=[-10.0, 80.0])])).verdict == "stale"


def test_agent_result_stale_once_viewed_or_gone():
    cand = _first(make_readers(runs=[run_row()]), "agent_result")
    assert _verdict(cand, make_readers(runs=[run_row(viewed=True)])).verdict == "stale"
    assert _verdict(cand, make_readers(runs=[])).verdict == "stale"


def test_a_card_waiting_in_the_queue_is_stale_not_duplicated():
    readers = make_readers(routines=[routine_row()], in_flight=lambda key: key.startswith("briefing:"))
    cand = _first(readers, "automate")
    v = _verdict(cand, readers, in_flight=readers.in_flight)
    assert v.verdict == "stale" and "queue" in v.note


def test_an_expired_card_is_stale():
    readers = make_readers(routines=[routine_row()])
    cand = _first(readers, "automate")
    card = new_card(cand, {"text": "x"}, now_ts=(NOW - timedelta(days=10)).timestamp(), score=0.5, ranking={})
    v = _verdict(cand, readers, card=card)
    assert v.verdict == "stale" and "timed out" in v.note


# ----------------------------------------------------------------------------------------------- unchecked and updated
def test_an_unreadable_source_neither_confirms_nor_refutes():
    cand = _first(make_readers(calendar=[cal_row()]), "focus_block")
    v = _verdict(cand, make_readers(calendar=[], available={"calendar": False}))
    assert v.verdict == "confirmed" and v.checked is False and "not re-checked" in v.note.lower()


def test_updated_when_the_numbers_move_but_not_for_a_day_passing():
    cand = _first(make_readers(routines=[routine_row()]), "automate")
    v = _verdict(cand, make_readers(routines=[routine_row(episodes=21, minutes_per_week=140.0, hours_lo=4.5, hours_hi=7.6)]))
    assert v.verdict == "updated" and v.candidate.numbers["episodes"] == 21
    same = _verdict(cand, make_readers(routines=[routine_row(minutes_per_week=98.0)]))      # a little drift
    assert same.verdict == "confirmed"


# ----------------------------------------------------------------------------------------------- prepare
def test_practice_plan_is_numbered_steps_in_plain_words():
    p = prepare(_first(make_readers(skills=[skill_row()]), "practice"))
    assert 4 <= len(p["steps"]) <= 8 and all(isinstance(s, str) and s for s in p["steps"])
    assert "Probe the cliff edge" in p["text"] and any("practice case" in s for s in p["steps"])
    assert any("Close to a limit anywhere?" in s for s in p["steps"])


def test_automation_consent_summary_states_what_it_never_does():
    p = prepare(_first(make_readers(routines=[routine_row()]), "automate"))
    assert "shadow mode" in p["text"] and "never does: submit" in p["text"] and "3.1 to 5.2 hours" in p["text"]
    assert "approval queue" in p["steps"][0]


def test_calendar_hold_is_a_draft_description_and_says_nothing_is_written():
    p = prepare(_first(make_readers(calendar=[cal_row()]), "focus_block"))
    assert p["text"].startswith("Focus time") and "Nothing is written to your calendar" in " ".join(p["steps"])


def test_git_note_asks_for_a_read_only_analysis():
    p = prepare(_first(make_readers(git=[git_row()]), "git_habit"))
    assert "read only" in p["text"] and "change nothing" in p["text"]


def test_a_reword_hook_may_replace_the_text_but_a_failing_one_never_fails_the_card():
    cand = _first(make_readers(routines=[routine_row()]), "automate")
    base = prepare(cand)
    out = prepare(cand, reword=lambda c, p: {"text": "Reworded safely."})
    assert out["text"] == "Reworded safely." and out["steps"] == base["steps"]

    def boom(c, p):
        raise RuntimeError("model down")

    assert prepare(cand, reword=boom) == base
    assert prepare(cand, reword=lambda c, p: {"text": "   "}) == base
    assert prepare(cand, reword=lambda c, p: None) == base


def test_prepared_content_has_no_markup_characters():
    for rd, kind in ((dict(routines=[routine_row()]), "automate"), (dict(skills=[skill_row()]), "practice"),
                     (dict(calendar=[cal_row()]), "focus_block"), (dict(git=[git_row()]), "git_habit"), (dict(runs=[run_row()]), "agent_result")):
        p = prepare(_first(make_readers(**rd), kind))
        blob = p.get("text", "") + " ".join(p.get("steps", []))
        assert not any(ch in blob for ch in "<>[]{}`|"), kind
