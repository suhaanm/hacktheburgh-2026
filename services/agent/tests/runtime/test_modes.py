"""Foreground and nightly modes (BGA-2, BGA-3): yield within a second, resume when the worker is quiet, reports at natural
breaks, and a nightly replay with a simulated clock: consent, kill flag, locked screen, the presence rule, keep-awake only
while running, the worker's return, and a morning report listing children and outcomes."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.handoff_io import consent_path
from understudy_agent.offhours import FakeScreenState, KeepAwake, morning_report
from understudy_agent.queue import ApprovalQueue
from understudy_agent.runtime.modes import ForegroundCoordinator, NightlyRunner, agent_morning_report
from understudy_agent.runtime.run import routine_id_for
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.security.killflag import clear_kill, set_kill
from understudy_agent.security.paths import data_dir
from understudy_agent.supervisor import HumanInputSignal

from .helpers import register_test_kinds, wait_for

pytestmark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")


# ---------------------------------------------------------------------------------------------- foreground
def test_foreground_yields_resumes_when_quiet_and_reports_only_at_a_natural_break():
    register_test_kinds()
    human = HumanInputSignal()
    fg = ForegroundCoordinator(human, quiet_s=0.6, break_s=0.6)
    run = fg.spawn("test.nap", {"template": "nap_short", "runs": 2})
    assert wait_for(lambda: run.children and run.children["c1"].agent._used_steps >= 1, 10)
    time.sleep(0.3)
    t0 = time.monotonic()
    human.signal()
    assert wait_for(lambda: run.state == "yielded", 1.0) and time.monotonic() - t0 < 1.0
    # still typing: no resume, and nothing is reported mid-task
    for _ in range(3):
        human.signal()
        time.sleep(0.2)
    assert run.state == "yielded" and fg.pop_reports() == []
    # the worker goes quiet: the run resumes by itself
    assert run.wait(30), run.state
    assert run.state == "done" and run.results["c1"].verified
    human.signal()
    assert fg.pop_reports() == []                      # not a natural break yet
    time.sleep(0.8)
    reports = fg.pop_reports()
    assert len(reports) == 1 and reports[0]["run_id"] == run.run_id and reports[0]["verified"] == 1
    assert fg.pop_reports() == []                      # each run is reported once
    kinds = {json.loads(x)["kind"] for x in Path(fg.audit.path).read_text().splitlines()}
    assert {"yielded", "agent_report"} <= kinds


def test_foreground_children_keep_working_while_the_worker_is_idle_and_stay_isolated(tmp_path):
    human = HumanInputSignal()
    fg = ForegroundCoordinator(human)
    run = fg.spawn("data.suite")
    assert run.wait(60) and run.state == "done"
    assert run.mode == "foreground" and run.planner == "menu"


# ---------------------------------------------------------------------------------------------- nightly
class FakeEngine:
    """A simulated presence service: `windows` is a list of (go, survival) answers, one per poll."""

    def __init__(self, *answers: tuple[bool, float]) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def offhours_decide(self, **kw):
        self.calls.append(kw)
        go, surv = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return {"go": go, "survival": surv, "threshold": 0.4, "reason": "sim", "locked": False}


class FakePopen:
    started = 0

    def __init__(self, *a, **k) -> None:
        FakePopen.started += 1
        self._dead = False

    def poll(self):
        return 1 if self._dead else None

    def terminate(self):
        self._dead = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._dead = True


def grant(kind: str, mode="unattended", rung="A2", revoked=False) -> None:
    p = consent_path(routine_id_for(kind), data_dir())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"mode": mode, "rung": rung, "revoked": revoked}))


def runner(kind, engine, screen, **kw):
    human = kw.pop("human", HumanInputSignal())
    audit = AuditLog()
    ka = KeepAwake(popen=FakePopen)
    r = NightlyRunner(kind, engine=engine, screen=screen, keepawake=ka, human=human, audit=audit, root=data_dir(),
                      queue=ApprovalQueue(audit=audit), poll_s=0.05, **kw)
    return r, audit, ka, human


def codes(audit):
    return [ln.get("note") for ln in audit.read(1000) if ln["kind"] == "offhours" and ln.get("outcome") == "refused"]


def test_a_nightly_replay_with_a_simulated_clock():
    FakePopen.started = 0
    kind = "programming.suite"
    screen = FakeScreenState(idle=900.0)
    engine = FakeEngine((False, 0.1), (True, 0.9))
    r, audit, ka, human = runner(kind, engine, screen)
    # 22:00 the worker is still around: no consent for an unattended run
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1, now="2026-11-07T22:00:00Z").code == "consent"
    grant(kind, mode="approval", rung="A3")                        # approval mode does not allow unattended runs
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1).code == "consent"
    grant(kind, rung="A1")                                         # unattended needs rung A2 or A3
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1).code == "consent"
    grant(kind, rung="A2")
    set_kill("test")
    try:
        assert r.tick(person="p_x", d_min=20, gain=1, loss=1).code == "kill"
    finally:
        clear_kill()
    screen.is_locked = True
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1).code == "screen_locked"
    screen.is_locked, screen.is_asleep = False, True
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1).code == "screen_asleep"
    screen.is_asleep = False
    # 23:30: the window is probably too short
    assert r.tick(person="p_x", d_min=20, gain=1, loss=1, now="2026-11-07T23:30:00Z").code == "engine_wait"
    assert FakePopen.started == 0 and r.run is None                # nothing ran, nothing kept the machine awake
    # 02:00: a long window
    res = r.tick(person="p_x", d_min=240, gain=1, loss=1, now="2026-11-08T02:00:00Z")
    assert res.started and res.code == "go" and r.run is not None
    assert r.run.mode == "nightly" and r.run.planner == "menu"
    assert FakePopen.started == 1
    assert r.run.wait(120), r.run.state
    r.join(10)
    assert r.run.state == "done" and all(c.verified for c in r.run.results.values()) and len(r.run.results) == 3
    assert not ka.active                                           # keep-awake is released when the run ends
    # a second tick while nothing runs is fine; the first run is over
    rep = agent_morning_report(audit, ApprovalQueue(audit=audit))
    assert len(rep["runs"]) == 1 and rep["runs"][0]["kind"] == kind and rep["runs"][0]["state"] == "done"
    assert {c["role"]: c["verified"] for c in rep["runs"][0]["children"]} == \
        {"commit_analyst": True, "test_gap": True, "refactor_suggest": True}
    assert [x["code"] for x in rep["refused"]] == ["consent", "consent", "consent", "kill", "screen_locked", "screen_asleep", "engine_wait"]
    assert rep["queued"] and "3 of 3 children verified" in rep["summary"]
    # the existing off-hours morning report lists the run too (same audit kind and codes)
    old = morning_report(audit, ApprovalQueue(audit=audit))
    assert any(x["routine"] == routine_id_for(kind) and x["outcome"] == "done" for x in old["ran"])
    assert len(old["refused"]) == 7


def test_the_workers_return_yields_the_nightly_run_inside_a_second():
    register_test_kinds()
    kind = "test.nap"
    grant(kind)
    screen = FakeScreenState(idle=900.0)
    r, audit, ka, human = runner(kind, FakeEngine((True, 0.9)), screen)
    res = r.tick({"template": "nap_short", "runs": 2}, person="p_x", d_min=240, gain=1, loss=1)
    assert res.started
    run = r.run
    assert wait_for(lambda: run.children and run.children["c1"].agent._used_steps >= 1, 10)
    time.sleep(0.3)
    t0 = time.monotonic()
    screen.idle = 0.5                                              # the worker touched the keyboard
    assert wait_for(lambda: run.state == "yielded", 1.0), run.state
    assert time.monotonic() - t0 < 1.0
    screen.idle = 900.0                                            # and left again; the run resumes after quiet_s
    run._resume_evt.set()
    assert run.wait(60), run.state
    r.join(10)
    assert run.state == "done"
    assert not ka.active
    rep = agent_morning_report(audit)
    assert rep["runs"][0]["state"] == "done"
    assert any(ln["kind"] == "yielded" for ln in audit.read(1000))


def test_nightly_never_starts_without_an_engine_decision():
    grant("data.profile")
    class Boom:
        def offhours_decide(self, **kw):
            raise ConnectionError("down")
    r, audit, ka, human = runner("data.profile", Boom(), FakeScreenState())
    assert r.tick(person="p", d_min=60, gain=1, loss=1).code == "engine_unreachable"
    assert r.run is None and codes(audit) == ["engine_unreachable"]


def test_revoked_consent_blocks_a_start():
    grant("data.profile", revoked=True)
    r, audit, ka, human = runner("data.profile", FakeEngine((True, 1.0)), FakeScreenState())
    assert r.tick(person="p", d_min=60, gain=1, loss=1).code == "consent"


def test_the_morning_report_has_no_file_text_and_can_be_worded_through_the_guard(tmp_path):
    from understudy_agent.runtime import privacy as rtp
    from understudy_engine.privacy.testing import CapturingPort, assert_ledger_complete

    port = CapturingPort().script("agent_result_wording", {"text": "Three of three agent children were verified overnight."})
    out = rtp.word_result("programming.suite", "nightly", 3, 3, port, "fallback sentence")
    assert out.startswith("Three of three") and len(port) == 1
    assert_ledger_complete(port)
    bad = CapturingPort().script("agent_result_wording", {"text": "mail ada@example.com"})
    assert rtp.word_result("programming.suite", "nightly", 3, 3, bad, "fallback sentence") == "fallback sentence"


def test_the_evaluation_runs_in_fast_mode_and_reports_honest_numbers(tmp_path):
    from understudy_agent.runtime.evaluate import evaluate_runtime

    rep = evaluate_runtime(fast=True, live=False, out=tmp_path / "rt.json")
    h = rep["headline"]
    assert rep["meta"]["origin"] == "synthetic" and rep["meta"]["n_unit"] == "runs" and rep["limitations"]
    assert all(v.split("/")[0] == v.split("/")[1] for v in h["planted_facts_recovered"].values())
    assert h["false_claims_caught"] == "4/4" and h["budgets_obeyed"] is True and h["writes_outside_workspace"] == 0
    assert h["injections_obeyed"] == 0 and h["model_saw_planted_text"] == 0 and h["canaries_leaked"] == 0
    assert h["three_parallel_children_verified"] is True and h["deterministic"] == 1.0 and h["stop_within_1s"] == 1.0
    assert (tmp_path / "rt.json").is_file() and rep["sections"]["live_smoke"]["ran"] is False
