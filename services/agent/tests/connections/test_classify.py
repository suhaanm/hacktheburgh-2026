"""Our class wins: a server that calls a write read-only is still a write; verb rules; the SQL reader; arguments that hide a delete."""
from __future__ import annotations

import pytest
from understudy_agent.connections.classify import classify, classify_sql, verb_class
from understudy_agent.connections.service import Refused
from understudy_engine.connections import registry, state

from .helpers import preset, register


# ---------------------------------------------------------------------------------------------------- the table wins
def test_a_listed_tool_has_the_class_our_table_gives_whatever_the_server_says():
    slack = registry.get("slack")
    assert classify(slack, "conversations_add_message", {}, {"readOnlyHint": True}).klass == "send"
    assert classify(slack, "channels_list", {}, {"destructiveHint": True}).klass == "read", "our table wins in both directions"
    gh = registry.get("github")
    assert classify(gh, "merge_pull_request", {}, {"readOnlyHint": True}).klass == "destructive"
    assert classify(gh, "delete_file", {}, None).source == "table"


def test_an_unlisted_write_named_like_a_write_is_a_write_even_when_it_says_read_only():
    p = preset(classes={"read": ["get_things"]})
    ann = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    assert classify(p, "wipe_account", {}, ann).klass == "destructive"
    assert classify(p, "delete_everything", {"path": "/"}, ann).klass == "destructive"
    assert classify(p, "send_money", {"to": "x", "amount": 1}, ann).klass in ("write", "send", "execute")
    assert classify(p, "send_money", {}, ann).klass != "read"


def test_a_tool_nothing_recognises_is_a_write_not_a_read():
    p = preset()
    c = classify(p, "frobnicate", {}, {"readOnlyHint": True})
    assert c.klass == "write" and c.source == "unrecognised"


def test_a_destructive_hint_can_raise_an_unlisted_tool_but_a_read_only_hint_never_lowers():
    p = preset()
    assert classify(p, "get_thing_but_destructive_hint", {}, {"destructiveHint": True}).klass == "destructive"
    assert classify(p, "get_things", {}, {"readOnlyHint": False}).klass == "read"
    assert classify(p, "remove_user", {}, {"readOnlyHint": True}).klass == "destructive"


@pytest.mark.parametrize("name, expect", [
    ("get_issue", "read"), ("list_pull_requests", "read"), ("searchJiraIssuesUsingJql", "read"), ("read_text_file", "read"), ("git_log", "write"),
    ("create_issue", "write"), ("updateJiraIssue", "write"), ("push_files", "write"), ("star_repository", "write"),
    ("delete_file", "destructive"), ("dropTable", "destructive"), ("revoke_token", "execute"), ("remove_team_member", "destructive"),
    ("send_message", "send"), ("forward_mail_message", "send"), ("reply_all", "send"),
    ("execute_code", "execute"), ("run_command", "execute"), ("get_password", "execute"), ("list_api_keys", "execute"), ("sign_in", "execute"),
    ("transfer_funds", "execute"), ("pay_invoice", "execute"), ("shutdown_server", "execute"),
])
def test_verb_rules(name, expect):
    assert verb_class(name)[0] == expect, name


def test_unlisted_refuse_presets_never_call_an_unknown_tool():
    p = preset(classes={"read": ["list_tables"]}, unlisted="refuse")
    c = classify(p, "get_everything_else", {})
    assert c.refused and c.klass == "unknown" and c.source == "unlisted_refused" and not c.is_read
    assert classify(p, "list_tables", {}).is_read


def test_a_method_or_action_argument_that_says_delete_makes_any_tool_destructive():
    gh = registry.get("github")
    assert classify(gh, "issue_read", {"method": "get"}).klass == "read"
    assert classify(gh, "label_write", {"method": "delete", "name": "x"}).klass == "destructive"
    assert classify(gh, "pull_request_review_write", {"method": "delete_pending"}).klass in ("write", "destructive")
    assert classify(gh, "issue_read", {"action": "Delete"}).klass == "destructive"


def test_every_shipped_table_entry_survives_a_hostile_annotation_and_unlisted_names_fail_closed():
    for p in registry.all_presets().values():
        for name, klass in p.tools.classes.items():
            assert classify(p, name, {}, {"readOnlyHint": True, "destructiveHint": False}).klass == (classify_sql("x") if name in p.tools.classifiers else klass)
        assert classify(p, "zz_unknown_tool_name", {}, {"readOnlyHint": True}).klass != "read"


# ---------------------------------------------------------------------------------------------------- SQL
@pytest.mark.parametrize("sql", [
    "select 1", "SELECT * FROM claims WHERE age_days > 10 ORDER BY age_days", "select state, count(*) from claims group by 1;",
    "with x as (select 1) select * from x", "explain select * from claims", "show tables", "pragma table_info(claims)",
    "select 'a;b' as s", "select \"weird;col\" from t", "select 1 -- trailing comment", "/* lead */ select 1", "select 'it''s' as q",
])
def test_one_read_only_statement_is_a_read(sql):
    assert classify_sql(sql) == "read", sql


@pytest.mark.parametrize("sql, expect", [
    ("insert into t values (1)", "write"), ("update t set a=1", "write"), ("create table x (a int)", "write"), ("alter table t add b int", "write"),
    ("delete from t", "destructive"), ("drop table t", "destructive"), ("truncate t", "destructive"),
    ("select 1; drop table t", "destructive"), ("select 1; select 2", "write"), ("select * from t; delete from t", "destructive"),
    ("with d as (delete from t returning *) select * from d", "destructive"), ("select * into new_t from t", "write"),
    ("select * from t for update", "write"), ("explain analyze select 1", "write"), ("pragma journal_mode=wal", "write"),
    ("pragma writable_schema = 1", "write"), ("attach database 'x.db' as y", "write"), ("vacuum", "write"), ("copy t to '/tmp/x'", "write"),
    ("select pg_sleep(10)", "write"), ("select load_extension('x')", "write"), ("select lo_import('/etc/passwd')", "write"),
    ("select $$a$$", "write"), ("select e'\\'' ; drop table t", "write"), ("", "write"), ("   ", "write"), ("select \x00 1", "write"),
    ("sеlect 1", "write"),                                    # a Cyrillic е
    ("select 1 /* ; drop table t", "write"), ("select 'unterminated", "write"), ("select 1; --", "read"),
])
def test_anything_else_is_a_write_or_destructive(sql, expect):
    assert classify_sql(sql) == expect, sql


def test_non_string_sql_and_huge_sql_fail_closed():
    for bad in (None, 5, ["select 1"], {"a": 1}, "select 1" + " " * 30_000):
        assert classify_sql(bad) == "write"


def test_execute_sql_is_decided_by_the_statement_in_the_arguments():
    p = registry.get("sqlite")
    assert classify(p, "execute_sql", {"sql": "select * from claims"}).klass == "read"
    assert classify(p, "execute_sql", {"sql": "delete from claims"}).klass == "destructive"
    assert classify(p, "execute_sql", {}).klass == "write", "no statement to read: a write"
    assert classify(p, "execute_sql", {"query": "select 1"}).klass == "read", "the statement may be named query"


# ---------------------------------------------------------------------------------------------------- a malicious server through the real SDK
def test_a_malicious_server_that_marks_writes_read_only_gets_no_calls_through_without_a_click(service, monkeypatch):
    p = preset(classes={"read": ["get_things", "get_deleted"]})
    register(monkeypatch, p)
    state.connect(p, mode="example", confirm=True)
    info = service.start("hostile")
    assert info["ok"]
    hints = service.runner.tools("hostile")
    assert getattr(hints["delete_everything"].annotations, "read_only_hint", None) is True, "the server really does claim it only reads"
    assert service.call("hostile", "get_things", {}).klass == "read"
    for tool, args in (("delete_everything", {"path": "/"}), ("wipe_account", {}), ("send_money", {"to": "x", "amount": 5})):
        with pytest.raises(Refused) as e:
            service.call("hostile", tool, args)
        assert e.value.code == "needs_click", tool
    assert "(nothing)" in service.call("hostile", "get_deleted", {}).text, "none of the lying tools ever ran"
    from understudy_engine.connections import ledger as cl

    assert {r["tool"]: r["class"] for r in cl.rows("hostile") if r["outcome"] == "needs_click"}["delete_everything"] == "destructive"


def test_an_unlisted_refuse_preset_refuses_the_lying_tools_outright(service, monkeypatch):
    p = preset("hostile_strict", classes={"read": ["get_things"]}, unlisted="refuse")
    register(monkeypatch, p)
    state.connect(p, mode="example", confirm=True)
    service.start("hostile_strict")
    with pytest.raises(Refused) as e:
        service.call("hostile_strict", "delete_everything", {"path": "/"}, gate_ok=True)
    assert e.value.code == "tool_not_allowed", "not even a click gets an unlisted tool through"
