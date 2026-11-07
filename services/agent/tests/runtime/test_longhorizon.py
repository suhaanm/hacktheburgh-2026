"""Long-horizon tasks (14 to 20 steps with typed feedback): planted bugs repaired and verified by code, a dirty dataset cleaned and
reconciled, interruption at step granularity, failure with recovery, the sanity check before a total is trusted, a nightly run of
three tasks with the morning report, and the privacy rule over every step."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.handoff_io import consent_path
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.offhours import FakeScreenState, KeepAwake
from understudy_agent.queue import ApprovalQueue
from understudy_agent.runtime import policy
from understudy_agent.runtime.exemplars import base
from understudy_agent.runtime.exemplars.longhorizon import make_bug_repo, make_orders, recount_pipeline
from understudy_agent.runtime.modes import NightlyRunner, agent_morning_report
from understudy_agent.runtime.run import AgentRun, register, routine_id_for
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.security.paths import data_dir
from understudy_agent.supervisor import HumanInputSignal
from understudy_engine.privacy import ledger
from understudy_engine.privacy.testing import CapturingPort, assert_ledger_complete

from .helpers import register_test_kinds, wait_for
from .test_modes import FakeEngine, FakePopen, grant, runner

pytestmark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")


def run_to_end(kind, params=None, *, timeout=240, **kw) -> AgentRun:
    r = AgentRun(kind=kind, params=params or {}, **kw)
    register(r).start()
    assert r.wait(timeout), f"run did not finish: {r.state}"
    return r


def checks(res) -> dict[str, bool]:
    return {c.name: c.ok for c in res.checks}


def test_three_planted_bugs_in_three_files_are_repaired_in_fourteen_steps_and_verified_by_code():
    r = run_to_end("programming.fix_bugs")
    c = r.results["c1"]
    assert r.state == "done" and c.verified, [(k, v) for k, v in checks(c).items() if not v]
    assert c.spent.steps == 14 and len(c.steps) == 14 and sum(1 for s in c.steps if s.tool == "run_python") == 6
    assert all(s.check == "verified" for s in c.steps)
    truth = r.params["truth"]
    o = c.output
    assert (o["tests_total"], o["failing_before"], o["failing_after"]) == (truth["tests_total"], truth["failing_before"], 0) and truth["failing_before"] == 6
    assert {f["file"] for f in o["fixes"]} == {b["file"] for b in truth["bugs"]}
    assert {f["class"] for f in o["fixes"]} == {"compare_boundary", "arith_operator", "off_by_one"}
    assert o["backtracks"] >= 1                                        # the decoy class was tried and rolled back
    ck = checks(c)
    assert ck["patched_files_equal_the_planted_originals"] and ck["no_test_was_edited"] and ck["tests_all_succeed_with_the_patch"]
    patch = next(a for a in c.artifacts if a.kind == "patch")
    assert patch.name == "bug_fixer.patch"


def test_the_patch_draft_is_queued_for_approval_and_the_source_repo_is_untouched(tmp_path):
    src = tmp_path / "bugs"
    make_bug_repo(src)
    before = (src / "calc" / "stats.py").read_text()
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    r = run_to_end("programming.fix_bugs", {"repo_path": str(src)}, audit=audit, queue=q)
    assert r.results["c1"].verified and (src / "calc" / "stats.py").read_text() == before
    assert any(i["title"].startswith("Patch draft ready") and i["status"] == "pending" for i in q.list("all"))


def test_a_dirty_dataset_is_cleaned_reconciled_and_every_number_recounted():
    r = run_to_end("data.pipeline")
    c = r.results["c1"]
    assert r.state == "done" and c.verified, [(k, v) for k, v in checks(c).items() if not v]
    t, o = r.params["truth"], c.output
    assert c.spent.steps == 20
    assert (o["duplicates_removed"], o["unit_fixes"]) == (t["duplicates"], t["gbx_lines"])
    assert o["outlier_lines"] == t["outlier_lines"] and o["rows_in"] == t["rows_in"]
    assert o["grand_total"] == pytest.approx(t["control_total"]) and o["reconciled"] and o["total_trusted"]
    assert t["naive_total_gbp"] != pytest.approx(t["control_total"], rel=0.001)         # without cleaning the total is far off
    assert {x["region"]: x["total"] for x in o["region_totals"]} == pytest.approx(t["region_totals"], abs=0.011)
    assert any(a.name == "revenue_by_region.png" for a in c.artifacts)


def test_skipping_the_cleaning_gives_an_untrusted_total_the_sanity_check_works():
    r = run_to_end("data.pipeline", {"lazy": True})
    c = r.results["c1"]
    o = c.output
    assert not c.verified and c.status == "failed"        # incomplete: the cleaning was skipped, so it does not match the recount
    ck = checks(c)
    assert o["reconciled"] is False and o["total_trusted"] is False and o["duplicates_removed"] == 0
    assert abs(o["grand_total"] - o["control_total"]) > 1000
    assert ck["a_total_is_trusted_only_if_it_reconciles"] and ck["reconciled_flag_is_consistent_with_its_own_numbers"]   # but honest


def test_a_result_that_trusts_a_total_that_does_not_reconcile_is_caught():
    tpl = base.MENUS["data_pipeline"].templates["pipeline_engine"]
    liar = tpl.replace('"total_trusted": bool(rec and rec["gap_cents"] == 0)', '"total_trusted": True')
    assert liar != tpl
    base.MENUS["data_pipeline"].templates["pipeline_engine_liar"] = liar
    try:
        r = run_to_end("data.pipeline", {"lazy": True}, port=_scripted_with(liar_tpl="pipeline_engine_liar", kind="data.pipeline", params={"lazy": True}),
                       auto_script=False)
    finally:
        del base.MENUS["data_pipeline"].templates["pipeline_engine_liar"]
    c = r.results["c1"]
    assert c.claimed_success and not c.verified and c.status == "failed"
    assert checks(c)["a_total_is_trusted_only_if_it_reconciles"] is False


def _scripted_with(*, liar_tpl: str, kind: str, params: dict):
    """The mock model, but it writes a tampered engine (same ids, different text) instead of the vetted one."""
    from understudy_agent.runtime.mockscripts import AdaptiveMock, mock_plan
    from understudy_agent.runtime.exemplars.base import KINDS

    ex = KINDS[kind]
    port = AdaptiveMock("benefits_clean")
    port.script_plan("agent_plan", mock_plan(kind))
    role = ex.roles[0]

    def pol(payload):
        out = ex.policy(role, params, payload)
        if out.get("template") in ("repair_engine", "pipeline_engine"):
            out = dict(out, template=liar_tpl)
        return out

    port.set_policy(f"child_step_{role}", pol)
    return port


def test_an_engine_that_edits_the_tests_to_make_them_succeed_is_not_verified():
    tpl = base.MENUS["bug_fixer"].templates["repair_engine"]
    cheat = tpl.replace("    rollback(st)\n", "    rollback(st)\n    t = open('tests/test_stats.py').read().replace('0.5', '0.25')\n    open('tests/test_stats.py', 'w').write(t)\n", 1)
    assert cheat != tpl
    base.MENUS["bug_fixer"].templates["engine_cheat"] = cheat
    try:
        r = run_to_end("programming.fix_bugs", port=_scripted_with(liar_tpl="engine_cheat", kind="programming.fix_bugs", params={}), auto_script=False)
    finally:
        del base.MENUS["bug_fixer"].templates["engine_cheat"]
    c = r.results["c1"]
    assert not c.verified and checks(c).get("no_test_was_edited") is False


# ---------------------------------------------------------------------------------------------- interruption and recovery
@pytest.mark.parametrize("kind,at,total", [("programming.fix_bugs", 7, 14), ("data.pipeline", 9, 20)])
def test_an_interruption_mid_run_yields_and_resumes_at_the_step_it_stopped_at(kind, at, total):
    human = HumanInputSignal()
    r = AgentRun(kind=kind, human=human)
    register(r).start()
    assert wait_for(lambda: r.children and r.children["c1"].agent._used_steps >= at, 60)
    t0 = time.monotonic()
    human.signal()
    assert wait_for(lambda: r.state == "yielded", 3.0), r.state
    assert time.monotonic() - t0 < 1.5
    done_before = [(s.tool, s.check) for s in r.children["c1"].agent.steps]
    assert len(done_before) >= at
    assert r.resume() and r.wait(120), r.state
    c = r.results["c1"]
    assert r.state == "done" and c.verified
    seq = [(s.tool, s.check) for s in c.steps]
    assert seq[:len(done_before)] == done_before                       # nothing before the interruption was redone
    assert len(seq) <= total + 1 and sum(1 for s in c.steps if s.tool == "emit_result") == 1
    assert c.spent.steps <= total + 1


@pytest.mark.parametrize("kind", ["programming.fix_bugs", "data.pipeline"])
def test_a_crashed_script_is_recovered_from_and_the_task_still_completes_verified(kind):
    r = run_to_end(kind, {"fault_at": 4})
    c = r.results["c1"]
    assert r.state == "done" and c.verified and c.recoveries == 1
    failed = [s for s in c.steps if not s.ok]
    assert len(failed) == 1 and failed[0].tool == "run_python" and failed[0].check == "failed"
    audit_kinds = [ln["kind"] for ln in AuditLog().read(5000)]
    assert "agent_recover" in audit_kinds


def test_recovery_has_a_cap_and_a_script_that_always_crashes_ends_the_child():
    register_test_kinds()
    base.MENUS["napper"].templates["crash"] = "raise SystemExit(1)\n"
    plan_steps = lambda role, p: [{"tool": "write_workspace", "file": "script", "template": "crash", "x": 0}][:0] or \
        [{"tool": "write_workspace", "file": "script", "template": "crash"}] + [{"tool": "run_python", "file": "script"}] * 6 + [{"tool": "emit_result", "file": "result"}]
    ex = base.KINDS["test.nap"]
    old = ex.mock_steps
    object.__setattr__(ex, "mock_steps", plan_steps)
    try:
        r = run_to_end("test.nap", {})
    finally:
        object.__setattr__(ex, "mock_steps", old)
        del base.MENUS["napper"].templates["crash"]
    c = r.results["c1"]
    assert c.recoveries == policy.MAX_RECOVERIES and c.status == "failed" and not c.verified and not c.claimed_success


def test_blockers_are_never_recovered_from_a_timeout_stops_the_child():
    """Recovery is for ordinary script failures. A blocker (a timeout here) stops the child at once."""
    from understudy_agent.runtime.mockscripts import mock_plan, scripts_for

    register_test_kinds()
    plan = mock_plan("test.nap")
    plan["children"][0]["max_seconds"] = 3
    port = MockProvider("benefits_clean")
    sc = scripts_for("test.nap", {"template": "nap_long", "runs": 3})
    sc["agent_plan"] = [plan]
    for t, rep in sc.items():
        port.script_plan(t, *rep)
    c = run_to_end("test.nap", {"template": "nap_long", "runs": 3}, port=port, auto_script=False).results["c1"]
    assert c.recoveries == 0 and c.status == "timeout"


# ---------------------------------------------------------------------------------------------- nightly, privacy
def test_a_nightly_run_of_three_tasks_and_the_morning_report():
    screen = FakeScreenState(idle=900.0)
    human = HumanInputSignal()
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    tasks = ["programming.fix_bugs", "data.pipeline", "programming.suite"]
    runs = []
    for kind in tasks:
        grant(kind)
        nr = NightlyRunner(kind, engine=FakeEngine((True, 0.9)), screen=screen, keepawake=KeepAwake(popen=FakePopen), human=human,
                           audit=audit, queue=q, root=data_dir(), poll_s=0.05)
        res = nr.tick(person="p_x", d_min=240, gain=1, loss=1)
        assert res.started, res.reason
        assert nr.run.wait(240), nr.run.state
        nr.join(10)
        runs.append(nr.run)
    assert [r.state for r in runs] == ["done", "done", "done"] and all(c.verified for r in runs for c in r.results.values())
    rep = agent_morning_report(audit, q)
    assert [x["kind"] for x in sorted(rep["runs"], key=lambda x: tasks.index(x["kind"]))] == tasks
    assert sum(x["verified"] for x in rep["runs"]) == 1 + 1 + 3 and sum(x["total"] for x in rep["runs"]) == 5
    assert "3 agent runs" in rep["summary"] and "5 of 5 children verified" in rep["summary"]
    assert any(i["title"].startswith("Patch draft ready") for i in q.list("pending")) and rep["queued"]


@pytest.mark.parametrize("kind", ["programming.fix_bugs", "data.pipeline"])
def test_long_tasks_leak_nothing_and_send_only_typed_signals(kind, tmp_path):
    if kind == "data.pipeline":
        make_orders(tmp_path / "o", canary="CNRYlh01")
        params = {"data_dir": str(tmp_path / "o")}
    else:
        make_bug_repo(tmp_path / "r")
        params = {"repo_path": str(tmp_path / "r")}
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    port = CapturingPort()
    r = run_to_end(kind, params, mode="nightly", port=port, audit=audit, queue=q)
    assert r.state == "done" and r.planner == "menu"
    assert len(port) >= 14
    assert_ledger_complete(port)
    blob = "\n".join(port.texts())
    for needle in ("c0001", "o00001", "calc/stats", "x <= v", "def rank", "Hello", "orders.csv"):
        assert needle not in blob, needle
    seen = set()
    for row in ledger.read_all():
        if "task" in row["payload"]:
            seen |= set(row["payload"]["task"]["signals"])
    assert seen and seen <= set(policy.SIGNAL_NAMES)


def test_an_emit_before_the_result_exists_is_recovered_from():
    """The live smoke showed a model emitting before running the last phase. That is a recoverable mistake, not the end."""
    from understudy_agent.runtime.mockscripts import mock_plan, scripts_for

    port = MockProvider("benefits_clean")
    sc = scripts_for("data.profile", {})
    steps = sc["child_step_data_profiler"]
    sc["child_step_data_profiler"] = [steps[0], steps[2], steps[1], steps[2]]       # write, EMIT too early, run, emit
    for t, rep in sc.items():
        port.script_plan(t, *rep)
    r = run_to_end("data.profile", port=port, auto_script=False)
    c = r.results["c1"]
    assert c.verified and c.recoveries == 1 and [s.tool for s in c.steps] == ["write_workspace", "emit_result", "run_python", "emit_result"]
    assert [s.ok for s in c.steps] == [True, False, True, True]
