"""Context engineering (REQ-8): a bounded, code-maintained task state for children. The model's context stays small over a long
task, the state is the source of truth after a yield and a resume, the truncation order is the stated one, readings carry their age
and provenance, and the per-call token curve is measured."""
from __future__ import annotations

import json
import time

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.runtime import context, policy
from understudy_agent.runtime.context import K_RECENT, SUMMARY_MAX, TOTAL_BUDGET, TaskState, est
from understudy_agent.runtime.run import AgentRun, register
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.supervisor import HumanInputSignal
from understudy_engine.privacy.testing import CapturingPort

from .helpers import wait_for


def step(tool="run_python", file="script", tpl="none", ok=True, check="verified"):
    return {"tool": tool, "file": file, "template": tpl, "ok": ok, "check": check}


def test_completed_pending_and_written_follow_write_then_run():
    t = TaskState()
    t.record(step("write_workspace", "script", "repair_engine"))
    assert t.written == ["repair_engine"] and t.pending == "none"
    t.record(step("write_workspace", "control", "ctl_diagnose"))
    assert t.pending == "ctl_diagnose" and t.completed == []
    t.record(step("run_python", ok=False, check="failed"))                       # a crashed run: still pending (the step to repeat)
    assert t.pending == "ctl_diagnose" and t.completed == [] and t.failures == 1 and t.last == "failed"
    t.record(step("run_python"), signals={"tests_failing": 3})
    assert t.pending == "none" and t.completed == ["ctl_diagnose"] and t.signals == {"tests_failing": 3} and t.last == "ok"


def test_the_payload_is_bounded_over_a_thirty_step_task_and_flattens_after_k_steps():
    t = TaskState()
    sizes = []
    for i in range(30):
        tpl = f"ctl_{i % 9}"
        t.record(step("write_workspace", "control", tpl) if i % 2 == 0 else step("run_python"), signals={"tests_failing": 3} if i % 2 else None)
        task, meta = t.payload(30 - i - 1)
        sizes.append(meta["tok_task"])
        assert len(task["recent"]) <= K_RECENT and len(task["summary"]) <= SUMMARY_MAX
        assert meta["tok_task"] <= TOTAL_BUDGET
    assert max(sizes) <= TOTAL_BUDGET and sizes[-1] <= max(sizes[:K_RECENT]) * 2.0      # it stops growing with the number of steps
    legacy = [est([step("run_python")] * n) for n in range(1, 31)]                       # a plain list of every step grows linearly
    assert legacy[-1] > legacy[K_RECENT] * 2


def test_recent_is_verbatim_and_older_steps_are_rolled_up_by_a_code_template():
    t = TaskState()
    for i in range(20):
        t.record(step("run_python", ok=i % 5 != 0, check="verified" if i % 5 != 0 else "failed"))
    for i in range(4):
        t.record(step("write_workspace", "control", f"ctl_{i}"))
    task, meta = t.payload(10)
    assert len(task["recent"]) == K_RECENT and task["recent"] == t.steps[-K_RECENT:]
    by_tool = {x["tool"]: (x["n_ok"], x["n_failed"]) for x in task["summary"]}
    assert sum(sum(v) for v in by_tool.values()) == 24 - K_RECENT and set(by_tool) <= {"run_python", "write_workspace"}
    assert task["elided"] == 0 and meta["n_summary"] == len(task["summary"]) <= 2


def test_the_truncation_order_is_stated_and_the_protected_sections_are_never_cut():
    t = TaskState()
    tools = ["read_file", "list_dir", "git_log", "run_python", "write_workspace", "emit_result"]
    for i in range(60):                                                                   # every tool among the older steps
        t.steps.append({"tool": tools[i % 6], "file": "control", "template": f"ctl_compare_boundary_{i % 7}", "ok": i % 3 != 0, "check": "verified"})
    t.completed = [f"ctl_compare_boundary_{i:02d}" for i in range(24)]
    t.written = ["engine"]
    t.signals, t.signals_at = {n: 99999 + i for i, n in enumerate(policy.SIGNAL_NAMES)}, 55
    task, meta = t.payload(5)
    assert meta["truncated"] >= 1 and len(task["recent"]) <= K_RECENT
    assert len(task["summary"]) < 6 or len(task["recent"]) < K_RECENT                     # the stated order: summary lines first, then recent
    assert task["elided"] > 0 or len(task["summary"]) == 6
    assert len(task["completed"]) == 24 and task["written"] == ["engine"] and set(task["signals"]) == set(policy.SIGNAL_NAMES)
    assert context.TRUNCATION_ORDER[0] == "summary:oldest" and "signals" in context.NEVER_TRUNCATED and "pending" in context.NEVER_TRUNCATED


def test_readings_carry_their_age_and_provenance():
    t = TaskState()
    assert t.payload(5)[0]["signals_from"] == "none"
    t.record(step("run_python"), signals={"tests_failing": 2})
    task, _ = t.payload(4)
    assert task["signals_from"] == "last_run" and task["signals_age"] == 0
    for _ in range(3):
        t.record(step("write_workspace", "control", "ctl_x"))
    task, meta = t.payload(1)
    assert task["signals_age"] == 3 and meta["signals_age"] == 3                         # three steps old: stale, and it says so


def test_no_text_can_enter_the_task_payload():
    t = TaskState()
    t.record(step("write_workspace", "control", "ctl_diagnose"))
    task, _ = t.payload(3)
    blob = json.dumps(task)
    assert "input/" not in blob and ".py" not in blob and ".csv" not in blob


pytestmark_mark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")


@pytestmark_mark
def test_the_task_state_survives_a_yield_and_the_resumed_child_continues_from_it():
    human = HumanInputSignal()
    r = AgentRun(kind="programming.fix_bugs", human=human)
    register(r).start()
    assert wait_for(lambda: r.children and r.children["c1"].agent._used_steps >= 8, 60)
    human.signal()
    assert wait_for(lambda: r.state == "yielded", 3.0)
    before = r.children["c1"].agent.task.snapshot()
    assert before["completed"] and before["verified"] >= 7
    view = r.to_dict()["children"][0]["task"]
    assert view["completed"] == before["completed"] and view["pending"] == before["pending"]
    assert r.resume() and r.wait(120)
    after = r.results["c1"]
    assert after.verified and r.children["c1"].agent.task.completed[: len(before["completed"])] == before["completed"]


@pytestmark_mark
def test_every_planning_call_logs_section_counts_without_content_and_the_curve_is_bounded():
    audit = AuditLog()
    port = CapturingPort()
    r = AgentRun(kind="data.pipeline", port=port, audit=audit, mode="nightly")
    register(r).start()
    assert r.wait(240) and r.state == "done"
    lines = [json.loads(x) for x in open(audit.path)]
    ctx_lines = [x for x in lines if x["kind"] == "context"]
    assert len(ctx_lines) >= 20
    for x in ctx_lines:
        assert set(x["meta"]) <= {"n_steps", "n_completed", "n_recent", "n_summary", "n_elided", "n_signals", "signals_age", "tok_task",
                                  "tok_budget", "truncated", "tok_recent", "tok_summary", "tok_signals"}
        assert x["meta"]["tok_task"] <= x["meta"]["tok_budget"]
    toks = [x["meta"]["tok_task"] for x in ctx_lines]
    assert max(toks) <= TOTAL_BUDGET and toks[-1] <= max(toks[:10]) * 2.5
    # the static part (role spec and menu) is the system message and is the same on every call: it is the cacheable prefix
    sys_msgs = {c["body"]["messages"][0]["content"] for c in [{"body": b} for b in port.bodies() if "messages" in b]}
    assert len(sys_msgs) == 2                                                            # the parent's, and this role's (identical every step)


@pytestmark_mark
def test_the_typed_state_is_persisted_next_to_the_run_and_restores_exactly():
    from understudy_agent.security.paths import data_dir

    r = AgentRun(kind="data.profile")
    register(r).start()
    assert r.wait(60) and r.state == "done"
    p = data_dir() / "runs" / r.run_id / "children" / "c1.task.json"
    saved = json.loads(p.read_text())
    agent = r.children["c1"].agent
    assert TaskState.from_json(saved["task"]).to_json() == agent.task.to_json()
    assert saved["used_steps"] == agent._used_steps == 3 and saved["recoveries"] == 0
    blob = json.dumps(saved)
    assert "input/" not in blob and ".csv" not in blob and "north" not in blob                 # ids, booleans and counts only


@pytestmark_mark
def test_provider_token_counts_replace_the_estimate_when_the_port_keeps_them():
    from understudy_agent.runtime.mockscripts import AdaptiveMock, mock_plan, scripts_for

    class CountingMock(AdaptiveMock):
        last_call = {"input_tokens": 900, "output_tokens": 10}                                 # what the provider says the last call cost

    plan = mock_plan("data.profile")
    plan["children"][0]["max_tokens"] = 2000
    port = CountingMock("benefits_clean")
    sc = scripts_for("data.profile", {})
    sc["agent_plan"] = [plan]
    for t, rep in sc.items():
        port.script_plan(t, *rep)
    r = AgentRun(kind="data.profile", port=port, auto_script=False)
    register(r).start()
    assert r.wait(60)
    c = r.results["c1"]
    assert c.status == "budget" and "budget_tokens" in c.reason and c.spent.tokens >= 2000 and c.spent.tokens % 910 == 0
