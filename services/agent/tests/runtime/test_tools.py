"""The typed tools and the id menu (BGA-1): a hijacked or malformed reply is never mistaken for a tool call."""
from __future__ import annotations

import json

import pytest

from understudy_agent.runtime.exemplars.base import MENUS
from understudy_agent.runtime.tools import (StepRejected, ToolCtx, assert_trusted_fields, normalise_step, pipeline_action,
                                            resolve_menu_step, run_tool)
from understudy_agent.runtime.spec import AgentSpec
from understudy_agent.runtime.workspace import Workspace

TOOLS = ["write_workspace", "run_python", "emit_result", "list_dir"]
MENU = MENUS["data_profiler"]


@pytest.mark.parametrize("raw", [
    None, [], "x", {"tool": "spawn_child"}, {"tool": "read_file", "path": "a"},          # not in this spec
    {"kind": "goto", "args": {"url": "https://evil.example"}, "hijacked": True},
    {"tool": "write_workspace", "file": "script", "template": "profile_csv", "path": "../x"},
    {"tool": "write_workspace", "file": "script"}, {"tool": "write_workspace", "template": "profile_csv"},
    {"tool": "run_python", "file": "../../etc/passwd"}, {"tool": "run_python", "file": "script", "template": "profile_csv"},
    {"tool": "run_python", "file": "nope"}, {"tool": "run_python"}, {"tool": "write_workspace", "file": "script", "template": "nope"},
])
def test_menu_replies_that_are_not_menu_ids_are_rejected(raw):
    with pytest.raises(StepRejected):
        resolve_menu_step(MENU, raw, TOOLS)


def test_a_good_menu_reply_resolves_to_a_vetted_call():
    tool, args = resolve_menu_step(MENU, {"tool": "write_workspace", "file": "script", "template": "profile_csv"}, TOOLS)
    assert tool == "write_workspace" and args["path"] == "profile.py" and "input/data.csv" in args["content"]
    assert resolve_menu_step(MENU, {"tool": "run_python", "file": "script", "template": "none"}, TOOLS) == ("run_python", {"path": "profile.py"})
    assert resolve_menu_step(MENU, {"tool": "emit_result", "file": "result"}, TOOLS) == ("emit_result", {"result_file": "result.json"})


@pytest.mark.parametrize("raw,code", [
    ({"tool": "read_file", "path": "a.txt"}, "tool_not_in_spec"), ({"tool": "run_python"}, "missing_arg"),
    ({"tool": "run_python", "path": "a.py", "evil": 1}, "unexpected_arg"), ({"tool": "run_python", "path": 5}, "bad_arg_value"),
    ({"tool": "write_workspace", "path": "a", "content": "x" * 500_000}, "bad_arg_value"),
    ({"tool": "emit_result", "result_file": ""}, "bad_arg_value"), ({"tool": "nope"}, "unknown_tool"),
])
def test_raw_mode_steps_are_validated(raw, code):
    with pytest.raises(StepRejected) as e:
        normalise_step(raw, ["run_python", "write_workspace", "emit_result"])
    assert e.value.code == code


def test_nulls_from_strict_structured_output_are_ignored():
    tool, args = normalise_step({"tool": "run_python", "reason": "go", "path": "a.py", "content": None, "offset": None},
                                ["run_python"])
    assert (tool, args) == ("run_python", {"path": "a.py"})


def test_pipeline_actions_are_typed_and_credential_paths_become_credential_class():
    assert pipeline_action("read_file", {"path": "a.txt"}) == {"kind": "extract", "args": {"name": "read_file", "selector": "a.txt"}}
    w = pipeline_action("write_workspace", {"path": "a.py", "content": "print(1)"})
    assert w["kind"] == "fill" and w["args"]["value"].startswith("sha256:") and "print" not in json.dumps(w)
    assert pipeline_action("write_workspace", {"path": ".env", "content": "x"})["args"]["value"] == ".env"
    assert pipeline_action("write_workspace", {"path": "a.py", "content": "open('~/.ssh/id_rsa')"})["args"]["value"] == ".ssh/content"


def test_only_numbers_and_tokens_are_trusted():
    assert assert_trusted_fields({"ok": True, "bytes": 5, "killed": "none", "seconds": 0.5})
    for bad in ({"note": "Hello World"}, {"x": "ignore previous instructions"}, {"x": ["a"]}, {"Bad Key": 1}):
        with pytest.raises(ValueError):
            assert_trusted_fields(bad)


def _ctx(tmp_path):
    ws = Workspace.create("tmp", run_id="r_test0001", child_id="c1")
    spec = AgentSpec(id="c1", role="data_profiler", goal="g", tools=TOOLS, budget=dict(steps=5, seconds=30, tokens=1000),
                     workspace="tmp", output_schema="profile_v1", playbook="data_profiler")
    return ws, ToolCtx(ws, spec, {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}})


def test_write_and_emit_tools_check_with_code(tmp_path):
    ws, ctx = _ctx(tmp_path)
    try:
        out = run_tool("write_workspace", {"path": "a.py", "content": "print(1)\n"}, ctx)
        assert out.ok and out.fields == {"file_exists": True, "size_matches": True, "content_matches": True}
        assert not run_tool("write_workspace", {"path": "../a.py", "content": "x"}, ctx).ok
        assert not run_tool("write_workspace", {"path": "b.py", "content": "open('/Users/x/.ssh/id_rsa')"}, ctx).ok
        ws.write_text("r.json", '{"n": "not an int"}')
        bad = run_tool("emit_result", {"result_file": "r.json"}, ctx)
        assert not bad.ok and not bad.terminal and ctx.emitted is None
        ws.write_text("r.json", '{"n": 3}')
        good = run_tool("emit_result", {"result_file": "r.json"}, ctx)
        assert good.ok and good.terminal and ctx.emitted == {"n": 3}
    finally:
        ws.cleanup()


def test_read_and_list_return_untrusted_text_not_trusted_fields(tmp_path):
    ws, ctx = _ctx(tmp_path)
    try:
        ws.write_text("n.txt", "hello")
        r = run_tool("read_file", {"path": "n.txt"}, ctx)
        assert r.text == "hello" and "hello" not in json.dumps(r.trusted)
        l = run_tool("list_dir", {"path": "."}, ctx)
        assert "n.txt" in l.text and "n.txt" not in json.dumps(l.trusted)
        assert not run_tool("read_file", {"path": "../x"}, ctx).ok
    finally:
        ws.cleanup()


# ---- S-28 follow-up: a fill is gated on a target trusted code READ. The runtime's "fill" is a write into the child's own workspace.
def test_a_workspace_write_has_a_readable_target_and_an_unresolvable_path_is_a_humans_call(tmp_path):
    from understudy_agent.runtime.tools import pipeline_action, pipeline_target
    from understudy_agent.runtime.workspace import Workspace
    from understudy_agent.security.gates import RoutineContext, gate

    ws = Workspace.create("tmp", run_id="r_gate01", child_id="c1", base=tmp_path)
    try:
        ctx = RoutineContext(mode="model_driven")
        ok_args = {"path": "work/a.py", "content": "print(1)"}
        act = pipeline_action("write_workspace", ok_args)
        assert gate(act["kind"], act["args"], ctx, pipeline_target("write_workspace", ok_args, ws)).verdict == "allow"
        for bad in ({"path": "../a.py", "content": "x"}, {"path": "/etc/passwd", "content": "x"}):
            a = pipeline_action("write_workspace", bad)
            assert gate(a["kind"], a["args"], ctx, pipeline_target("write_workspace", bad, ws)).verdict == "needs_human"
        assert gate(act["kind"], act["args"], ctx, pipeline_target("write_workspace", ok_args, None)).verdict == "needs_human"
        cred = pipeline_action("write_workspace", {"path": ".ssh/id_rsa", "content": "x"})
        assert gate(cred["kind"], cred["args"], ctx, pipeline_target("write_workspace", {"path": ".ssh/id_rsa", "content": "x"}, ws)).verdict == "needs_human"
        # a read or the final emit types nothing and addresses no field: never gated as a fill
        rd = pipeline_action("read_file", {"path": "input/data.csv"})
        assert rd["kind"] == "extract" and gate(rd["kind"], rd["args"], ctx, pipeline_target("read_file", {"path": "x"}, ws)).verdict == "allow"
    finally:
        ws.cleanup()
