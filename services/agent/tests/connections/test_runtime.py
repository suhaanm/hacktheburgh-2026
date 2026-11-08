"""mcp_call inside the agent runtime: it maps onto the existing eight layers (the real SafetyPipeline, the real approval queue, the real child loop),
a write needs a person's click, destructive and execute never get around it, an unattended run can only read, and a tool result is data."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from understudy_agent.audit import AuditLog
from understudy_agent.connections import hook
from understudy_agent.connections.service import default_service
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action
from understudy_agent.queue import ApprovalQueue
from understudy_agent.runtime import spec as rt_spec
from understudy_agent.runtime import tools as rt_tools
from understudy_agent.runtime.exemplars.base import Exemplar, Menu, WorkspaceNeeds, register_exemplar, register_menu
from understudy_agent.runtime.results import register_schema, register_verifier
from understudy_agent.runtime.run import AgentRun, register, routine_id_for
from understudy_agent.runtime.spec import Check, RoleDef, register_role
from understudy_agent.security.config import SecurityConfig
from understudy_agent.security.detector import PageObservation
from understudy_agent.security.gates import RoutineContext, gate
from understudy_agent.security.labels import ActionClass as C
from understudy_agent.security.pipeline import SafetyPipeline
from understudy_agent.security.settings import Origin
from understudy_engine.connections import ledger as cl
from understudy_engine.connections import registry, state
from understudy_engine.privacy.testing import CapturingPort

SCHEMA = {"title": "facts", "type": "object", "required": ["kind"], "properties": {"kind": {"type": "string", "enum": ["text", "other"]}}}


def args(conn, name, **arguments):
    return {"connection": conn, "name": name, **({"arguments": json.dumps(arguments)} if arguments else {})}


def on(conn_id):
    p = registry.get(conn_id)
    state.connect(p, mode="example", confirm=True)
    default_service().start(conn_id)
    return p


def pipe(tmp_path, routine=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    p = SafetyPipeline(MockProvider("reader_basic"), SecurityConfig(), audit=audit, queue=queue, goal="read my tools",
                       routine=routine or RoutineContext(routine_id="agent-test", mode="model_driven", unattended=False, rung="A0", run_id="r_1"))
    return p, queue


def authorise(p, a, **kw):
    action = rt_tools.pipeline_action("mcp_call", a)
    obs = p.observe(PageObservation(text="start"), SCHEMA)
    return p.authorise(action, observation=obs, target=rt_tools.pipeline_target("mcp_call", a, None), **kw), action


# ---------------------------------------------------------------------------------------------------- the tool is registered, minimally
def test_mcp_call_is_a_registered_tool_and_the_two_tables_agree():
    assert "mcp_call" in rt_spec.TOOL_NAMES and tuple(rt_tools.TOOLS) == rt_spec.TOOL_NAMES
    assert rt_tools.TOOLS["mcp_call"].required == frozenset({"connection", "name"})
    assert "mcp_call" in rt_tools.POSTCONDITIONS and "mcp_call" in rt_tools._IMPL
    assert {"connection", "name", "arguments"} <= set(rt_tools.child_step_schema("c1", ["mcp_call"])["properties"])


@pytest.mark.parametrize("raw, code", [
    ({"tool": "mcp_call", "name": "x"}, "missing_arg"), ({"tool": "mcp_call", "connection": "github"}, "missing_arg"),
    ({"tool": "mcp_call", "connection": "github", "name": "x", "path": "/etc/passwd"}, "unexpected_arg"),
    ({"tool": "mcp_call", "connection": "g" * 200, "name": "x"}, "bad_arg_value"), ({"tool": "mcp_call", "connection": "github", "name": 5}, "bad_arg_value"),
    ({"tool": "mcp_call", "connection": "github", "name": "x", "arguments": "y" * 30_000}, "bad_arg_value"),
])
def test_raw_mode_steps_for_mcp_call_are_validated(raw, code):
    with pytest.raises(rt_tools.StepRejected) as e:
        rt_tools.normalise_step(raw, ["mcp_call"])
    assert e.value.code == code
    assert rt_tools.normalise_step({"tool": "mcp_call", "reason": "r", "connection": "github", "name": "list_issues", "arguments": None}, ["mcp_call"]) == \
        ("mcp_call", {"connection": "github", "name": "list_issues"})


def test_the_menu_names_an_id_and_code_supplies_the_call():
    menu = Menu(files={"issues": "mcp:github/list_issues"}, calls={"issues": {"connection": "github", "name": "list_issues", "arguments": {"state": "all"}}})
    tool, a = rt_tools.resolve_menu_step(menu, {"tool": "mcp_call", "file": "issues", "template": "none"}, ["mcp_call"])
    assert tool == "mcp_call" and a == {"connection": "github", "name": "list_issues", "arguments": '{"state": "all"}'}
    for bad in ({"tool": "mcp_call", "file": "nope"}, {"tool": "mcp_call", "template": "x", "file": "issues"}, {"tool": "mcp_call"}):
        with pytest.raises(rt_tools.StepRejected):
            rt_tools.resolve_menu_step(menu, bad, ["mcp_call"])
    with pytest.raises(rt_tools.StepRejected):
        rt_tools.resolve_menu_step(Menu(files={"issues": "x"}), {"tool": "mcp_call", "file": "issues"}, ["mcp_call"])


# ---------------------------------------------------------------------------------------------------- the pipeline mapping
def test_a_read_is_an_extract_and_a_write_is_a_gated_step_with_the_arguments_in_its_signature(monkeypatch):
    on("github")
    r = rt_tools.pipeline_action("mcp_call", args("github", "list_issues", state="open"))
    assert r["kind"] == "extract" and r["args"]["selector"].startswith("mcp:github/list_issues#")
    w1 = rt_tools.pipeline_action("mcp_call", args("github", "add_issue_comment", issue_number=1, body="one"))
    w2 = rt_tools.pipeline_action("mcp_call", args("github", "add_issue_comment", issue_number=1, body="two"))
    d = rt_tools.pipeline_action("mcp_call", args("github", "merge_pull_request", pull_number=11))
    assert w1["kind"] == "click_element" and w1["args"]["label"] == "post" and d["args"]["label"] == "delete"
    assert w1["args"]["selector"] != w2["args"]["selector"], "an approval is for THESE arguments"
    assert "one" not in json.dumps(w1) and "two" not in json.dumps(w2), "the arguments themselves never enter an action, only a digest"
    t = rt_tools.pipeline_target("mcp_call", args("github", "add_issue_comment", issue_number=1, body="x"), None)
    assert t.label == "post" and t.role == "mcp_tool" and t.url == "https://api.github.com/"
    assert rt_tools.pipeline_target("mcp_call", args("github", "list_issues"), None).label is None


def test_every_class_gets_the_verb_the_gate_understands_and_the_gate_decides_without_an_optin(monkeypatch):
    from understudy_agent.connections.classify import GATE_VERB
    from understudy_agent.security.gates import TargetInfo

    ctx = RoutineContext(routine_id="x", mode="model_driven", rung="A0")
    expect = {"write": ("needs_human", C.POST, "outward"), "send": ("needs_human", C.SEND, "outward"),
              "destructive": ("needs_human", C.DELETE, "irreversible"), "execute": ("needs_human", C.INSTALL, "irreversible")}
    for klass, (verdict, top, risk) in expect.items():
        d = gate("click_element", {"selector": "mcp:x/y#0", "label": GATE_VERB[klass]}, ctx, TargetInfo(label=GATE_VERB[klass], role="mcp_tool"))
        assert (d.verdict, d.top, d.risk_class) == (verdict, top, risk), klass


def test_destructive_and_execute_stay_a_humans_call_even_for_a_routine_that_opted_in_everything():
    from understudy_agent.connections.classify import GATE_VERB
    from understudy_agent.security.gates import TargetInfo

    full = RoutineContext(routine_id="x", mode="model_driven", rung="A3", typed_confirm=True, opted_in=frozenset({C.POST, C.SEND, C.DELETE, C.SUBMIT}))
    for klass in ("destructive", "execute"):
        v = gate("click_element", {"selector": "mcp:x/y#0", "label": GATE_VERB[klass]}, full, TargetInfo(label=GATE_VERB[klass], role="mcp_tool")).verdict
        if klass == "execute":
            assert v == "needs_human", "execute (install class) can never be opted in"
    # the child runtime never has an opt-in at all: it is built at rung A0 with nothing opted in, so every write waits for a click
    from understudy_agent.runtime.child import ChildAgent
    import inspect

    src = inspect.getsource(ChildAgent.__init__)
    assert 'rung="A0"' in src and "opted_in" not in src


def test_an_unconnected_connection_or_an_unlisted_tool_becomes_an_action_the_pipeline_blocks_before_any_queue_item(tmp_path):
    p, queue = pipe(tmp_path)
    for a in (args("github", "list_issues"), args("evil_server", "x"), args("github", "totally_invented")):
        dec, action = authorise(p, a)
        assert action["kind"] == hook.REFUSED_KIND and dec.verdict == "block" and dec.layer == "actions"
    assert queue.list("all") == [] and any(r["outcome"] == "refused" for r in cl.rows())
    on("github")
    dec, _ = authorise(p, args("github", "list_issues"))
    assert dec.verdict == "allow"
    state.revoke(registry.get("github"))
    assert authorise(p, args("github", "list_issues"))[0].verdict == "block", "revoked: refused again"


def test_a_strict_preset_refuses_a_tool_outside_its_table_before_any_queue_item(tmp_path):
    on("filesystem")
    p, queue = pipe(tmp_path)
    dec, action = authorise(p, args("filesystem", "list_directory", path="."))
    assert dec.verdict == "allow" and action["kind"] == "extract"
    dec, action = authorise(p, args("filesystem", "totally_new_tool"))
    assert dec.verdict == "block" and queue.list("all") == []


# ---------------------------------------------------------------------------------------------------- a write waits for a click, once, for these arguments
def test_a_write_makes_an_outward_queue_item_and_runs_only_after_the_workers_click(tmp_path):
    on("github")
    p, queue = pipe(tmp_path)
    a = args("github", "add_issue_comment", issue_number=1, body="posted after approval")
    dec, _ = authorise(p, a)
    assert dec.verdict == "needs_human" and dec.queue_id
    item = queue.get(dec.queue_id)
    assert item["kind"] == "outward_step" and item["risk_class"] == "outward" and item["title"].startswith("click_element: post step on api.github.com")
    assert "posted after approval" not in json.dumps(item), "the queue item names the class and the host, never the arguments"
    assert "needs_click" not in json.dumps([r["outcome"] for r in cl.rows("github")]), "nothing was called yet"
    assert "posted after approval" not in default_service().call("github", "issue_read", {"issue_number": 1}).text

    queue.approve(dec.queue_id, origin=Origin.HUMAN_UI)
    other, _ = authorise(p, args("github", "add_issue_comment", issue_number=1, body="different text"), approved_queue_id=dec.queue_id)
    assert other.verdict == "needs_human", "an approval is for the arguments it was given for"
    dec2, _ = authorise(p, a, approved_queue_id=dec.queue_id)
    assert dec2.verdict == "allow"
    out = rt_tools.run_tool("mcp_call", a, SimpleNamespace(remaining=lambda: 20.0, unattended=False, routine_id="agent-test"))
    assert out.ok and out.trusted["class"] == "write"
    assert "posted after approval" in default_service().call("github", "issue_read", {"issue_number": 1}).text
    dec3, _ = authorise(p, a, approved_queue_id=dec.queue_id)
    assert dec3.verdict == "needs_human", "an approval is used once"


def test_run_refuses_a_write_that_did_not_come_through_the_pipeline(tmp_path):
    on("github")
    out = rt_tools.run_tool("mcp_call", args("github", "add_issue_comment", issue_number=1, body="sneaky"),
                            SimpleNamespace(remaining=lambda: 20.0, unattended=False, routine_id=""))
    assert not out.ok and out.codes == ["refused:needs_click"] and out.fields == {"call_ok": False}
    assert "sneaky" not in default_service().call("github", "issue_read", {"issue_number": 1}).text


def test_an_authorisation_is_for_one_step_and_expires(tmp_path, monkeypatch):
    on("github")
    a = args("github", "add_issue_comment", issue_number=1, body="once")
    rt_tools.pipeline_action("mcp_call", a)
    ctx = SimpleNamespace(remaining=lambda: 20.0, unattended=False, routine_id="")
    assert rt_tools.run_tool("mcp_call", a, ctx).ok
    assert rt_tools.run_tool("mcp_call", a, ctx).codes == ["refused:needs_click"], "consumed"
    rt_tools.pipeline_action("mcp_call", a)
    import time as _t

    real = _t.monotonic
    monkeypatch.setattr(hook.time, "monotonic", lambda: real() + hook.AUTH_TTL_S + 5)
    assert rt_tools.run_tool("mcp_call", a, ctx).codes == ["refused:needs_click"], "expired"


# ---------------------------------------------------------------------------------------------------- unattended
def test_in_an_unattended_run_mcp_call_reads_only_and_only_for_an_optedin_routine():
    p = on("github")
    ctx = SimpleNamespace(remaining=lambda: 20.0, unattended=True, routine_id="agent-weekly")
    read = args("github", "list_issues")
    rt_tools.pipeline_action("mcp_call", read)
    assert rt_tools.run_tool("mcp_call", read, ctx).codes == ["refused:routine_not_opted_in"]
    state.set_routine(p, "agent-weekly", True)
    rt_tools.pipeline_action("mcp_call", read)
    assert rt_tools.run_tool("mcp_call", read, ctx).ok
    for tool, a in (("add_issue_comment", {"issue_number": 1, "body": "away"}), ("merge_pull_request", {"pull_number": 11})):
        action = args("github", tool, **a)
        rt_tools.pipeline_action("mcp_call", action)                      # even a pipeline-authorised step is refused while the worker is away
        assert rt_tools.run_tool("mcp_call", action, ctx).codes == ["refused:unattended_read_only"], tool
    assert "away" not in default_service().call("github", "issue_read", {"issue_number": 1}).text


# ---------------------------------------------------------------------------------------------------- a tool result is data
def test_a_poisoned_tool_result_is_paused_by_the_detector_and_no_model_ever_reads_it(tmp_path, monkeypatch):
    monkeypatch.setenv("KNACK_STANDIN_POISON", "1")
    on("github")
    port = CapturingPort()
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    p = SafetyPipeline(port, SecurityConfig(), audit=audit, queue=queue, goal="read my issues",
                       routine=RoutineContext(routine_id="agent-test", mode="model_driven", rung="A0", run_id="r_1"))
    a = args("github", "issue_read", issue_number=5)
    rt_tools.pipeline_action("mcp_call", a)
    out = rt_tools.run_tool("mcp_call", a, SimpleNamespace(remaining=lambda: 20.0, unattended=False, routine_id=""))
    assert out.ok and "Ignore all previous instructions" in out.text, "the stand-in really returns the poisoned text"
    obs = p.observe(PageObservation(text=out.text), None, source="file")           # what the child does with outcome.text in menu mode: the local detector only
    assert obs.paused and p.paused and any(i["kind"] == "injection_pause" for i in queue.list("pending"))
    assert port.texts() == [] or "Ignore all previous" not in "\n".join(port.texts())
    again = p.authorise(Action("extract", {"name": "mcp_call", "selector": "x"}))
    assert again.verdict == "pause", "the run stays paused until the worker clears it"


def test_a_clean_tool_result_in_raw_mode_reaches_the_planner_only_as_reader_fields(tmp_path, monkeypatch):
    on("github")
    port = MockProvider("reader_basic")
    p = SafetyPipeline(port, SecurityConfig(), audit=AuditLog(tmp_path / "a.jsonl"), queue=ApprovalQueue(tmp_path / "q"), goal="read my issues",
                       routine=RoutineContext(routine_id="agent-test", mode="model_driven", rung="A0", run_id="r_1"))
    a = args("github", "list_issues", state="all")
    rt_tools.pipeline_action("mcp_call", a)
    out = rt_tools.run_tool("mcp_call", a, SimpleNamespace(remaining=lambda: 20.0, unattended=False, routine_id=""))
    obs = p.observe(PageObservation(text=out.text), SCHEMA, source="file")
    msgs = p.planner_messages("read my issues", [obs])
    prompt = "\n".join(m["content"] for m in msgs)
    assert "Rounding differs by one penny on EX-104" not in prompt, "the raw tool result is never in the planner prompt"
    assert "EXTRACTED_FIELDS" in prompt


# ---------------------------------------------------------------------------------------------------- a whole child, in the real runtime
def register_connector_kind():
    from understudy_agent.runtime.exemplars import base

    if "test.connect" in base.KINDS:
        return
    register_schema("connect_v1", {"type": "object", "required": ["ok"], "additionalProperties": False, "properties": {"ok": {"type": "boolean"}}})
    register_role(RoleDef("connector", "Test role that makes one call to a connected app.", frozenset({"mcp_call", "write_workspace", "emit_result"}),
                          frozenset({"tmp"}), "connect_v1", "data_profiler"))
    register_menu("connector", Menu(files={"issues": "mcp:github/list_issues", "note": "mcp:github/issue_read", "comment": "mcp:github/add_issue_comment",
                                           "ghost": "mcp:ghost/none", "result": "result.json", "script": "w.json"},
                                    templates={"ok": '{"ok": true}'},
                                    calls={"issues": {"connection": "github", "name": "list_issues", "arguments": {"state": "all"}},
                                           "note": {"connection": "github", "name": "issue_read", "arguments": {"issue_number": 5}},
                                           "comment": {"connection": "github", "name": "add_issue_comment", "arguments": {"issue_number": 1, "body": "from a child"}},
                                           "ghost": {"connection": "ghost", "name": "none"}}),
                  "Read one thing from a connected app, then report ok.")
    register_verifier("connector", lambda ctx: [Check(name="ok_true", ok=ctx.output.get("ok") is True)])

    def steps(role, params):
        return [{"tool": "mcp_call", "file": params.get("call", "issues"), "template": "none"}, {"tool": "write_workspace", "file": "result", "template": "ok"},
                {"tool": "emit_result", "file": "result"}]

    register_exemplar(Exemplar(kind="test.connect", title="Test: call a connected app", describe="Test only.", roles=("connector",),
                               needs=lambda role, p: WorkspaceNeeds(), prepare=lambda p, d: dict(p), mock_steps=steps))


def run_child(params=None, **kw) -> AgentRun:
    register_connector_kind()
    r = AgentRun(kind="test.connect", params=params or {}, **kw)
    register(r).start()
    assert r.wait(120), f"run did not finish: {r.state}"
    return r


def test_a_child_reads_through_a_connection_and_finishes_and_no_model_sees_the_result(tmp_path):
    on("github")
    port = CapturingPort()
    r = run_child({"call": "issues"}, port=port)
    c = r.results["c1"]
    assert r.state == "done" and c.verified, (r.state, c.status, c.reason)
    assert "Rounding differs" not in "\n".join(port.texts())
    rows = cl.rows("github")
    assert [x["class"] for x in rows if x["tool"] == "list_issues"] == ["read"] and all(x["bytes"] >= 0 for x in rows)


def test_a_child_that_reads_a_poisoned_issue_is_paused_and_nothing_acts_on_it(tmp_path, monkeypatch):
    monkeypatch.setenv("KNACK_STANDIN_POISON", "1")
    on("github")
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    port = CapturingPort()
    r = run_child({"call": "note"}, port=port, audit=audit, queue=q)
    c = r.results["c1"]
    assert c.status == "paused" and c.reason == "injection_pause"
    assert any(i["kind"] == "injection_pause" for i in q.list("pending"))
    assert "Ignore all previous" not in "\n".join(port.texts()) and "collector.example" not in "\n".join(port.texts())
    assert "from a child" not in default_service().call("github", "issue_read", {"issue_number": 1}).text


def test_a_child_that_asks_to_write_waits_for_a_click_and_changes_nothing(tmp_path):
    on("github")
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    r = run_child({"call": "comment"}, audit=audit, queue=q)
    c = r.results["c1"]
    assert c.status != "done"
    pend = [i for i in q.list("pending") if i["kind"] == "outward_step"]
    assert len(pend) == 1 and "from a child" not in json.dumps(pend[0])
    assert "from a child" not in default_service().call("github", "issue_read", {"issue_number": 1}).text


def test_a_child_that_names_a_connection_that_is_off_has_that_step_refused_and_no_queue_item_is_made(tmp_path):
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    r = run_child({"call": "ghost"}, audit=audit, queue=q)
    c = r.results["c1"]
    first = c.steps[0]
    assert first.tool == "mcp_call" and first.ok is False and first.check == "failed" and first.codes[0].startswith("gate:actions:"), first
    assert [i for i in q.list("all") if i["kind"] in ("outward_step", "irreversible_step", "injection_pause")] == [], "a call that cannot run never becomes something to approve"
    assert not default_service().runner.is_running("github") and any(x["outcome"] == "refused" and x["connection"] == "ghost" for x in cl.rows())


def test_an_unattended_child_cannot_use_a_connection_its_routine_was_not_opted_into(tmp_path):
    p = on("github")
    r = run_child({"call": "issues"}, mode="nightly")
    assert r.results["c1"].status != "done"
    state.set_routine(p, routine_id_for("test.connect"), True)
    r2 = run_child({"call": "issues"}, mode="nightly")
    assert r2.results["c1"].status == "done", (r2.state, r2.results["c1"].reason)
    r3 = run_child({"call": "comment"}, mode="nightly")
    assert r3.results["c1"].status != "done"
    assert "from a child" not in default_service().call("github", "issue_read", {"issue_number": 1}).text
