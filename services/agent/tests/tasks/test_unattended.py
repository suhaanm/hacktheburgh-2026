"""An unattended Claude task starts only from a routine's OWN consent record, never gets "Allow everything", and obeys the kill flag."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from understudy_agent.security.killflag import clear_kill, set_kill
from understudy_agent.tasks import TaskError

from .conftest import claude_text, wait_for
from .test_manager import done


def consent(routine: str, **d):
    p = Path(os.environ["UNDERSTUDY_DATA_DIR"]) / "routines" / routine / "consent.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"mode": "unattended", "rung": "A2", **d}))


def test_no_consent_record_means_no_start(make_manager):
    m = make_manager()
    with pytest.raises(TaskError) as e:
        m.start_for_routine("weekly-csv", claude_text("ok"))
    assert e.value.status == 409 and e.value.code == "not_allowed" and "no consent record" in e.value.message
    assert m.list_rows() == []


@pytest.mark.parametrize("d,why", [({"mode": "approval"}, "does not allow"), ({"mode": "shadow"}, "does not allow"),
                                   ({"mode": "never"}, "never"), ({"revoked": True}, "revoked"), ({"rung": "A1"}, "A2 or A3")])
def test_consent_that_does_not_allow_an_unattended_run_is_refused(make_manager, d, why):
    consent("weekly-csv", **d)
    m = make_manager()
    with pytest.raises(TaskError) as e:
        m.start_for_routine("weekly-csv", claude_text("ok"))
    assert e.value.code == "not_allowed" and why in e.value.message
    assert m.list_rows() == []


def test_a_consented_routine_starts_without_a_card_attended_false_and_never_with_everything(make_manager):
    consent("weekly-csv")
    m = make_manager()
    row = m.start_for_routine("weekly-csv", claude_text("ok"))
    assert row["attended"] is False and row["state"] == "running" and row["needs_consent"] is None and row["route"] == "claude_agent"
    t = done(m, row["task_id"])
    assert t.state == "done" and t.scope == "files_and_commands" and t.attended is False
    seen = json.loads((Path(t.folder) / "fake_seen.json").read_text())
    assert "--dangerously-skip-permissions" not in seen["argv"] and "--permission-mode" in seen["argv"]
    # the audit line names the routine; the ledger has the same start and stop rows as an attended task
    from understudy_agent.audit import AuditLog

    lines = [json.loads(x) for x in Path(AuditLog().path).read_text().splitlines()]
    assert any(x["routine"] == "weekly-csv" and x["outcome"] == "routine_unattended" for x in lines)
    from .test_manager import ledger_lines

    assert {x["method"] for x in ledger_lines() if t.task_id in str(x.get("note", ""))} == {"claude_agent_start", "claude_agent_stop"}


def test_an_unattended_start_obeys_the_kill_flag_the_cap_and_bad_ids(make_manager):
    consent("weekly-csv")
    m = make_manager(max_running=1)
    for bad in ("", "Weekly CSV", "../x", "a" * 80):
        with pytest.raises(TaskError) as e:
            m.start_for_routine(bad, "x")
        assert e.value.status == 422
    set_kill("test")
    try:
        with pytest.raises(TaskError) as e:
            m.start_for_routine("weekly-csv", claude_text("ok"))
        assert e.value.code == "kill_switch_set"
    finally:
        clear_kill()
    first = m.start_for_routine("weekly-csv", claude_text("hang"))
    assert wait_for(lambda: m.get(first["task_id"]).pid, 10)
    with pytest.raises(TaskError) as e:
        m.start_for_routine("weekly-csv", claude_text("ok", "second"))
    assert e.value.code == "too_many_tasks"
    m.stop(first["task_id"])


def test_a_request_with_a_secret_is_not_started_unattended(make_manager):
    consent("weekly-csv")
    m = make_manager()
    row = m.start_for_routine("weekly-csv", claude_text("ok", "password: hunter2hunter2"))
    assert row["state"] == "failed" and "key or a password" in row["reason"]
    assert not (Path.home() / "Knack" / "work").exists()
