"""The stand-ins end to end through the REAL SDK client: stdio, tools, results, the sandbox, and every refusal the service makes."""
from __future__ import annotations

import json

import pytest
from understudy_agent.connections.service import Refused
from understudy_engine.connections import ledger as cl
from understudy_engine.connections import state
from understudy_engine.privacy import ledger


def test_nothing_runs_for_a_connection_that_was_never_switched_on(service):
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {})
    assert e.value.code == "not_connected" and not service.runner.is_running("github")
    assert service.start("github") == {"ok": False, "code": "not_connected", "tools": 0, "counts": {}}
    with pytest.raises(Refused) as e:
        service.call("evil_server", "x", {})
    assert e.value.code == "unknown_connection"


def test_the_github_stand_in_starts_lists_tools_and_counts_by_our_class(service, connect_example):
    connect_example("github")
    r = service.start("github")
    assert r["ok"] and r["tools"] >= 14 and r["counts"]["read"] >= 10 and r["counts"]["write"] >= 2 and r["counts"]["destructive"] == 1
    assert service.runner.is_running("github")
    assert "list_issues" in service.runner.tools("github")


def test_a_read_goes_through_and_the_ledger_row_has_sizes_not_content(service, connect_example):
    connect_example("github")
    out = service.call("github", "list_issues", {"state": "open"})
    assert out.klass == "read" and out.example is True and "Rounding differs by one penny" in out.text and not out.is_error
    text = ledger.ledger_path().read_text()
    assert "list_issues" in text and "mcp:github" in text
    assert "Rounding differs" not in text and '"state"' not in text and "open" not in text.replace("outcome", "")
    rows = cl.rows("github")
    assert len(rows) == 1 and rows[0]["class"] == "read" and rows[0]["outcome"] == "ok" and rows[0]["bytes_result"] == len(out.text.encode()) and rows[0]["mock"] is True


def test_a_write_without_a_click_is_refused_as_needs_click_and_never_reaches_the_server(service, connect_example):
    connect_example("github")
    with pytest.raises(Refused) as e:
        service.call("github", "add_issue_comment", {"issue_number": 1, "body": "hello"})
    assert e.value.code == "needs_click" and e.value.outcome == "needs_click"
    read = service.call("github", "issue_read", {"issue_number": 1})
    assert "hello" not in read.text, "the refused write changed nothing"
    assert [r["outcome"] for r in cl.rows("github")] == ["needs_click", "ok"]


def test_a_write_with_the_pipelines_authorisation_runs_and_is_a_write_row(service, connect_example):
    connect_example("github")
    out = service.call("github", "add_issue_comment", {"issue_number": 1, "body": "hello from the test"}, gate_ok=True, expect_class="write")
    assert out.klass == "write" and not out.is_error
    assert "hello from the test" in service.call("github", "issue_read", {"issue_number": 1}).text
    assert [r["class"] for r in cl.rows("github")] == ["write", "read"]
    assert "hello from the test" not in ledger.ledger_path().read_text()


def test_the_class_must_still_be_the_one_that_was_approved(service, connect_example):
    connect_example("github")
    with pytest.raises(Refused) as e:
        service.call("github", "merge_pull_request", {"pull_number": 11}, gate_ok=True, expect_class="read")
    assert e.value.code == "class_changed"


def test_an_unknown_tool_name_is_never_forwarded(service, connect_example):
    connect_example("github")
    with pytest.raises(Refused) as e:
        service.call("github", "totally_invented_tool", {}, gate_ok=True)
    assert e.value.code == "unknown_tool"


def test_unattended_allows_only_a_read_and_only_for_the_routine_the_worker_opted_in(service, connect_example):
    p = connect_example("github")
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {}, unattended=True, routine_id="weekly_digest")
    assert e.value.code == "routine_not_opted_in"
    state.set_routine(p, "weekly_digest", True)
    assert service.call("github", "list_issues", {}, unattended=True, routine_id="weekly_digest").klass == "read"
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {}, unattended=True, routine_id="another_routine")
    assert e.value.code == "routine_not_opted_in"
    for tool, args in (("add_issue_comment", {"issue_number": 1, "body": "x"}), ("merge_pull_request", {"pull_number": 11})):
        with pytest.raises(Refused) as e:
            service.call("github", tool, args, unattended=True, routine_id="weekly_digest", gate_ok=True)
        assert e.value.code == "unattended_read_only", "even with a click-shaped gate_ok, an unattended run never writes"


def test_destructive_and_execute_classes_are_decided_by_us_not_the_server(service, connect_example):
    connect_example("github")
    for tool, args in (("merge_pull_request", {"pull_number": 11}),):
        with pytest.raises(Refused) as e:
            service.call("github", tool, args)
        assert e.value.code == "needs_click"
    assert cl.rows("github")[-1]["class"] == "destructive"


def test_the_kill_flag_and_the_denylist_stop_every_call(service, connect_example, tmp_path):
    connect_example("github")
    service._killed = lambda: True
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {})
    assert e.value.code == "kill_flag" and e.value.outcome == "blocked"
    service._killed = lambda: False
    from understudy_agent.security.denylist import Denylist

    service._denylist = lambda: Denylist([{"kind": "app", "value": "GitHub"}])
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {})
    assert e.value.code == "denylisted"


def test_the_denylist_by_host_applies_to_a_real_connection(service):
    from understudy_agent.security.denylist import Denylist
    from understudy_engine.connections import registry

    p = registry.get("github")
    service._denylist = lambda: Denylist([{"kind": "domain", "value": "github.com"}])
    with pytest.raises(Refused) as e:
        service._check_denylist(p, {"params": {}})
    assert e.value.code == "denylisted"
    service._denylist = lambda: Denylist([])
    service._check_denylist(p, {"params": {}})


def test_changed_pin_stops_everything_until_the_worker_confirms(service, connect_example, monkeypatch):
    connect_example("github")
    assert service.call("github", "list_issues", {}).klass == "read"
    import understudy_engine.connections.state as st
    from understudy_engine.connections.manifest import command_hash

    monkeypatch.setattr(st, "command_hash", lambda p, m: command_hash(p, m) + "x")
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {})
    assert e.value.code == "needs_reconfirm"
    assert service.start("github")["code"] == "needs_reconfirm"


def test_revoke_stops_the_process_and_later_calls_are_refused(service, connect_example):
    p = connect_example("github")
    service.start("github")
    assert service.runner.is_running("github")
    state.revoke(p)
    assert service.stop("github")["stopped"] is True and not service.runner.is_running("github")
    with pytest.raises(Refused) as e:
        service.call("github", "list_issues", {})
    assert e.value.code == "not_connected"


def test_bad_arguments_are_refused_before_anything(service, connect_example):
    connect_example("github")
    for bad in ([1, 2], {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}, {"x": "y" * 30_000}, {"x": object()}, {"k" * 100: 1}):
        with pytest.raises(Refused) as e:
            service.call("github", "list_issues", bad)             # type: ignore[arg-type]
        assert e.value.code == "bad_arguments"


def test_the_filesystem_stand_in_reads_its_sandbox_and_confines_paths(service, connect_example):
    connect_example("filesystem")
    assert "standup.md" in service.call("filesystem", "list_directory", {"path": "notes"}).text
    assert "Reconcile" in service.call("filesystem", "read_text_file", {"path": "notes/standup.md"}).text
    out = service.call("filesystem", "read_text_file", {"path": "../../../etc/passwd"})
    assert out.is_error, "a path outside the sandbox is refused by the server itself as well"
    with pytest.raises(Refused) as e:
        service.call("filesystem", "write_file", {"path": "notes/x.txt", "content": "x"})
    assert e.value.code == "needs_click"


def test_the_sqlite_stand_in_reads_with_a_single_select_and_needs_a_click_for_anything_else(service, connect_example):
    connect_example("sqlite")
    out = service.call("sqlite", "execute_sql", {"sql": "select state, count(*) as n from claims group by state order by state"})
    assert out.klass == "read" and out.source == "sql" and "open" in out.text
    for sql, klass in (("delete from claims", "destructive"), ("insert into claims values ('x','a',1,'h','open',1)", "write"),
                       ("select 1; drop table claims", "destructive"), ("update claims set state='closed'", "write")):
        with pytest.raises(Refused) as e:
            service.call("sqlite", "execute_sql", {"sql": sql})
        assert e.value.code == "needs_click" and cl.rows("sqlite")[-1]["class"] == klass, sql
    assert "60" in service.call("sqlite", "execute_sql", {"sql": "select count(*) from claims"}).text, "the refused statements changed nothing"
    assert "claims" in service.call("sqlite", "list_tables", {}).text


def test_every_example_preset_with_a_server_starts_and_lists_tools(service, connect_example):
    from understudy_engine.connections import registry

    for p in registry.all_presets().values():
        if not p.standin.get("script"):
            continue
        connect_example(p.id)
        r = service.start(p.id)
        assert r["ok"] and r["tools"] >= 4 and r["counts"]["read"] >= 1, (p.id, r)
        service.stop(p.id)


def test_the_slack_stand_in_send_is_a_send_class(service, connect_example):
    connect_example("slack")
    assert "claims-desk" in service.call("slack", "channels_list", {}).text
    with pytest.raises(Refused):
        service.call("slack", "conversations_add_message", {"channel_id": "C01", "text": "hi"})
    assert cl.rows("slack")[-1]["class"] == "send"


def test_a_source_preset_has_nothing_to_start(service, connect_example):
    connect_example("graph_outlook")
    assert service.start("graph_outlook") == {"ok": True, "tools": 0, "counts": {**{c: 0 for c in ("read", "write", "send", "destructive", "execute")}, "refused": 0}, "code": None}


def test_a_result_is_capped_and_non_text_blocks_are_only_counted(service, connect_example):
    from mcp_types import TextContent
    from understudy_agent.connections.runner import _flatten

    class Block:
        pass

    class R:
        content = [TextContent(type="text", text="a" * 100), Block()]
        structured_content = None
        is_error = False

    raw = _flatten(R(), 10)
    assert raw.truncated and len(raw.text) == 10 and raw.blocks_other == 1 and raw.bytes == 10
    assert json.dumps(raw.text) and True
