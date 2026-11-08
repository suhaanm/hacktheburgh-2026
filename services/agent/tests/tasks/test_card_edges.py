"""Edges of the question and consent cards: a refused pick leaves the card in place; a card cannot be answered twice."""
from __future__ import annotations

import pytest

from understudy_agent.tasks import TaskError

from .conftest import claude_text, wait_for
from .test_manager import done


def test_a_refused_answer_pick_keeps_the_question_card(make_manager):
    m = make_manager(max_running=1)
    busy = m.create(claude_text("hang"), "typed")["task_id"]
    m.consent(busy, "allow")
    assert wait_for(lambda: m.get(busy).pid, 10)
    q = m.create("sort this out for me", "typed")
    tid = q["task_id"]
    with pytest.raises(TaskError) as e:
        m.answer(tid, "answer")                                     # the cap is full: refused, nothing changed
    assert e.value.status == 429
    t = m.get(tid)
    assert t.state == "waiting_consent" and t.route == "unclear" and t.row()["question"] == q["question"]
    m.stop(busy)
    assert wait_for(lambda: m.running_count() == 0, 5)
    assert m.answer(tid, "answer").route == "answer"                # and it works once there is room
    assert done(m, tid).state == "done"


def test_declined_and_stopped_cards_cannot_be_used_again(make_manager):
    m = make_manager()
    tid = m.create(claude_text("ok"), "typed")["task_id"]
    m.stop(tid)
    for choice in ("allow", "everything", "decline"):
        with pytest.raises(TaskError) as e:
            m.consent(tid, choice)
        assert e.value.code == "not_waiting"
    assert not (m.get(tid).pid)


def test_a_question_task_has_no_consent_card_to_press(make_manager):
    m = make_manager()
    tid = m.create("sort this out for me", "typed")["task_id"]
    with pytest.raises(TaskError) as e:
        m.consent(tid, "allow")
    assert e.value.code == "not_waiting"                            # a pick is needed first; "allow" never starts an unknown route
    assert m.get(tid).state == "waiting_consent"
