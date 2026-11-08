"""The spend brake: --max-budget-usd on every Claude task (default US$2, the worker sets 0.5 to 20), the cost the CLI reports kept as a number,
and Knack's own stop when the reported cost reaches the limit. All against the FAKE claude."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from understudy_agent.tasks import claude_cli as cc
from understudy_agent.tasks import skills as sk
from understudy_agent.tasks.model import with_cost

from .conftest import claude_text, wait_for
from .test_claude_cli import alive, run_fake
from .test_manager import done


def flag_value(argv, flag):
    return argv[argv.index(flag) + 1]


# ------------------------------------------------------------------------------------------------------ the numbers
def test_with_cost_appends_a_number_and_keeps_the_line_short():
    assert with_cost("Wrote a.md.", 0.0629795) == "Wrote a.md. (cost US$0.06)"
    assert with_cost("Wrote a.md.", None) == "Wrote a.md."
    assert with_cost("Wrote a.md.", 0) == "Wrote a.md. (cost US$0.00)"
    long = with_cost("word " * 100, 12.3456)
    assert len(long) <= 140 and long.endswith("(cost US$12.35)")


def test_budget_settings_default_range_and_rounding():
    assert sk.load_settings()["max_budget_usd"] == 2.0
    for ok, want in ((0.5, 0.5), (20, 20.0), (3.456, 3.46), (1, 1.0)):
        assert sk.save_settings({"max_budget_usd": ok})["max_budget_usd"] == want
    sk.save_settings({"max_budget_usd": 5})
    for bad in (0.49, 0, -1, 20.01, 1000, "3", None, True, False, [2], {"a": 1}, float("nan")):
        assert sk.valid_budget(bad) is None, bad
        assert sk.save_settings({"max_budget_usd": bad})["max_budget_usd"] == 5.0              # a bad value changes nothing
    assert sk.load_settings()["max_budget_usd"] == 5.0


def test_budget_over_http_is_validated_and_listed(make_manager):
    from fastapi.testclient import TestClient

    from understudy_agent.server import create_app

    app = create_app(base_urls={"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"},
                     autostart_sandbox=False, shared_sites=False)
    app.state.tasks = make_manager()
    h = {"X-Understudy-Actor": "worker", "Content-Type": "application/json"}
    with TestClient(app) as c:
        assert c.get("/skills").json()["max_budget_usd"] == 2.0
        assert c.post("/skills/settings", json={"max_budget_usd": 7.5}, headers=h).json()["max_budget_usd"] == 7.5
        assert c.get("/skills").json()["max_budget_usd"] == 7.5
        for bad in (0.1, 25, "2", True, None):
            r = c.post("/skills/settings", json={"max_budget_usd": bad}, headers=h)
            assert r.status_code == 422 and r.json()["error"]["code"] == "bad_body", bad
        assert c.get("/skills").json()["max_budget_usd"] == 7.5
        assert c.post("/skills/settings", json={"max_budget_usd": 3}, headers={**h, "X-Understudy-Actor": "agent"}).status_code == 403


# ------------------------------------------------------------------------------------------------- the card and argv
def test_the_card_names_the_limit_and_the_command_carries_it(make_manager):
    m = make_manager()
    r = m.create(claude_text("ok"), "typed")
    card = r["needs_consent"]
    assert card["max_budget_usd"] == 2.0 and "Spend more than US$2.00 of your Claude account on this task" in card["cannot"]
    t = m.get(r["task_id"])
    argv = m._claude_argv(t, "files_and_commands")
    assert flag_value(argv, "--max-budget-usd") == "2.00" and t.max_budget_usd == 2.0
    assert flag_value(m._claude_argv(t, "everything"), "--max-budget-usd") == "2.00"             # "Allow everything" keeps the brake
    sk.save_settings({"max_budget_usd": 0.5})
    r2 = m.create(claude_text("ok", "second"), "typed")
    assert r2["needs_consent"]["max_budget_usd"] == 0.5
    assert flag_value(m._claude_argv(m.get(r2["task_id"]), "files_and_commands"), "--max-budget-usd") == "0.50"
    assert m.get(r["task_id"]).max_budget_usd == 2.0                                              # the first card keeps what it showed


def test_a_different_limit_is_a_different_pinned_command(make_manager):
    m = make_manager()
    t = m.get(m.create(claude_text("ok"), "typed")["task_id"])
    h = cc.command_hash(m._claude_argv(t, "files_and_commands"), t.folder)
    t.max_budget_usd = 20.0
    assert cc.command_hash(m._claude_argv(t, "files_and_commands"), t.folder) != h
    from understudy_agent.tasks import TaskError

    with pytest.raises(TaskError) as e:
        m.consent(t.task_id, "allow")                                                              # the pin no longer matches
    assert e.value.code == "command_changed"


def test_browser_cards_have_no_limit_and_never_a_cost(make_manager):
    m = make_manager()
    r = m.create("go to https://example.com and read the news online", "typed")
    assert r["needs_consent"]["max_budget_usd"] is None and m.get(r["task_id"]).row()["cost_usd"] is None


def test_the_child_really_received_the_flag(make_manager):
    m = make_manager()
    tid = m.create(claude_text("ok"), "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid)
    seen = json.loads((Path(t.folder) / "fake_seen.json").read_text())
    assert flag_value(seen["argv"], "--max-budget-usd") == "2.00"


# ---------------------------------------------------------------------------------------------------- the spend stop
def test_knack_stops_a_child_whose_reported_cost_reaches_the_limit(fake_claude, tmp_path):
    r, steps, cwd = run_fake(fake_claude, tmp_path, "spend", max_budget_usd=2.0)
    t0 = time.time()
    out = r.run()
    assert out.state == "failed" and out.why == "budget" and out.reason == "Reached the spend limit you set."
    assert out.cost_usd == 2.5 and time.time() - t0 < 6
    assert wait_for(lambda: not alive(int((cwd / "grandchild.pid").read_text())), 5)             # the whole group is gone


def test_without_a_limit_the_same_run_is_not_stopped_for_cost(fake_claude, tmp_path):
    r, _, _ = run_fake(fake_claude, tmp_path, "spend", max_seconds=1.5)                          # no max_budget_usd given
    out = r.run()
    assert out.why == "wall" and out.cost_usd == 2.5


def test_the_cli_stopping_itself_at_the_budget_has_the_same_plain_reason(fake_claude, tmp_path):
    out = run_fake(fake_claude, tmp_path, "cliself", max_budget_usd=2.0)[0].run()
    assert out.state == "failed" and out.why == "budget" and out.reason == cc.R_BUDGET and out.exit_code == 1 and out.cost_usd == 2.01


def test_a_finished_run_is_judged_by_its_result_not_killed_over_the_line(fake_claude, tmp_path):
    out = run_fake(fake_claude, tmp_path, "overok", max_budget_usd=2.0)[0].run()
    assert out.state == "done" and out.why == "ok" and out.cost_usd == 2.4 and out.result_text == "Finished the job."


def test_a_cost_below_the_limit_never_stops_anything(fake_claude, tmp_path):
    out = run_fake(fake_claude, tmp_path, "ok", max_budget_usd=2.0)[0].run()
    assert out.state == "done" and out.cost_usd == 0.0123


def test_cost_parsing_is_defensive():
    st = cc.StreamState()
    for line in (b'{"type":"x","total_cost_usd":"5"}\n', b'{"type":"x","total_cost_usd":true}\n', b'{"type":"x","total_cost_usd":-1}\n',
                 b'{"type":"x","total_cost_usd":1e9}\n'):
        cc.parse_line(line, st)
    assert st.cost_usd is None
    cc.parse_line(b'{"type":"x","total_cost_usd":0.4}\n', st)
    cc.parse_line(b'{"type":"x","total_cost_usd":0.2}\n', st)                                    # a lower later number never lowers the total
    assert st.cost_usd == 0.4


# ------------------------------------------------------------------------------------------- through the manager
def test_a_task_that_hits_the_limit_fails_with_the_plain_reason_and_the_number(make_manager):
    m = make_manager()
    tid = m.create(claude_text("spend"), "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "failed" and t.reason == "Reached the spend limit you set." and t.result is None
    row = m.get(tid).row()
    assert row["cost_usd"] == 2.5 and row["open"]["kind"] == "folder"                            # partial work can be opened
    stop_row = next(x for x in __import__("understudy_engine.privacy.ledger", fromlist=["x"]).read_all() if "stop=budget" in str(x.get("note", "")))
    assert "cost=2.5000" in stop_row["note"]


def test_the_cost_survives_a_stop_and_a_restart(make_manager):
    m = make_manager()
    tid = m.create(claude_text("spend", "again"), "typed")["task_id"]
    m.consent(tid, "allow")
    t = m.get(tid)
    assert wait_for(lambda: t.pid and (Path(t.folder) / "grandchild.pid").exists(), 10)
    time.sleep(0.2)
    m.stop(tid)
    assert wait_for(lambda: m.get(tid).cost_usd is not None, 8)                                  # the late outcome adds the number, not the state
    t2 = make_manager().get(tid)
    assert t2.state == "stopped" and t2.reason == "Stopped by you." and t2.cost_usd == m.get(tid).cost_usd


def test_an_unattended_routine_never_gets_more_than_the_default_brake(make_manager):
    import os

    data = Path(os.environ["UNDERSTUDY_DATA_DIR"]) / "routines" / "weekly-csv"
    data.mkdir(parents=True)
    (data / "consent.json").write_text(json.dumps({"mode": "unattended", "rung": "A2"}))
    sk.save_settings({"max_budget_usd": 15})
    m = make_manager()
    row = m.start_for_routine("weekly-csv", claude_text("ok"))
    t = done(m, row["task_id"])
    seen = json.loads((Path(t.folder) / "fake_seen.json").read_text())
    assert flag_value(seen["argv"], "--max-budget-usd") == "2.00" and t.max_budget_usd == 2.0
    sk.save_settings({"max_budget_usd": 1})
    row = m.start_for_routine("weekly-csv", claude_text("ok", "second"))
    assert flag_value(json.loads((Path(done(m, row["task_id"]).folder) / "fake_seen.json").read_text())["argv"], "--max-budget-usd") == "1.00"
