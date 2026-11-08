"""The `planning` state exists for one case: the router asks the model to break a tie. A watcher that saw it must also see it end."""
from __future__ import annotations

import pytest

from understudy_agent.tasks import TaskError

TIE = "can you look at my spreadsheet"        # a tie in the rules, with some evidence for claude_agent


def test_a_tie_is_shown_as_planning_then_routed(make_manager, port):
    port.check_out = {"route": "claude_agent"}
    m = make_manager()
    seq = m.last_seq()
    r = m.create(TIE, "typed")
    evs = m.events_since(seq)
    assert [(n, row["state"], row["latest"]) for _, n, row in evs][:2] == [
        ("task_progress", "planning", "Working out what to do"), ("task_progress", "waiting_consent", "Waiting for your go-ahead")]
    assert r["route"] == "claude_agent" and r["needs_consent"]["kind"] == "claude_agent"


def test_a_rules_only_route_never_flashes_planning(make_manager):
    m = make_manager()
    seq = m.last_seq()
    m.create("What is the capital of Scotland?", "typed")
    assert all(row["state"] != "planning" for _, _, row in m.events_since(seq))


def test_a_refused_planning_task_is_closed_for_watchers_and_forgotten(make_manager, port):
    port.check_out = {"route": "answer"}
    m = make_manager(max_running=0)
    seq = m.last_seq()
    with pytest.raises(TaskError) as e:
        m.create(TIE, "typed")
    assert e.value.code == "too_many_tasks"
    evs = m.events_since(seq)
    assert [(n, row["state"]) for _, n, row in evs] == [("task_progress", "planning"), ("task_finished", "failed")]
    assert evs[-1][2]["reason"].startswith("At most 0 tasks") and evs[-1][2]["task_id"] == evs[0][2]["task_id"]
    assert m.list_rows() == []
