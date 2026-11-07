"""OFF-1..7: start-or-wait, refuse when locked, keep-awake only while active, yield within a second, morning report."""
from __future__ import annotations

import json
import subprocess
import time

import httpx
import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.compile import compile_draft
from understudy_agent.handoff_io import EngineClient
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action
from understudy_agent.offhours import (
    FakeScreenState, KeepAwake, OffHoursRunner, PresenceWatcher, ScreenGuardedActuator, make_actuator, morning_report,
    run_desktop_task,
)
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.recordings import synthetic_recording
from understudy_agent.shadow import BackgroundRunner
from understudy_agent.supervisor import HumanInputSignal, Supervisor
from understudy_agent.tiers.computer_use import ActuatorRefused, SimulatedActuator
from understudy_agent.tiers.heuristic import HeuristicModelPort
from understudy_agent.tiers.safety import Guard


class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.terminated = cmd, False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


class Engine:
    def __init__(self, go=True, status=200):
        self.go, self.status, self.bodies = go, status, []

    def handler(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": "boom", "message": "x"}})
        return httpx.Response(200, json={"go": self.go, "survival": 0.91, "threshold": 0.6, "reason": "ok" if self.go else "short",
                                         "locked": False, "screen_source": "override"})

    def client(self):
        return EngineClient("http://engine.test", client=httpx.Client(transport=httpx.MockTransport(self.handler)))


def write_consent(root, mode="unattended", rung="A2", revoked=False):
    d = root / "routines" / "calc-entry-3x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "consent.json").write_text(json.dumps({"mode": mode, "rung": rung, "irreversible_unattended": [], "revoked": revoked}))


@pytest.fixture
def world(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    human = HumanInputSignal()
    sup = Supervisor(kill_flag=tmp_path / "KILL", human_input=human)
    model = HeuristicModelPort(MockProvider("benefits_clean"))
    screen = FakeScreenState(idle=900.0)
    popens: list[FakeProc] = []

    def popen(cmd, **kw):
        p = FakeProc(cmd, **kw)
        popens.append(p)
        return p

    ka = KeepAwake(popen)

    def make(engine: Engine):
        bg = BackgroundRunner("calc-entry-3x", supervisor=sup, human_input=human, model=model, base_urls=cluster.urls,
                              audit=audit, queue=queue, root=tmp_path, unattended=True)
        return OffHoursRunner("calc-entry-3x", engine=engine.client(), screen=screen, keepawake=ka, background=bg,
                              human=human, audit=audit, supervisor=sup, root=tmp_path, poll_s=0.05)

    yield dict(make=make, audit=audit, queue=queue, human=human, sup=sup, screen=screen, ka=ka, popens=popens, root=tmp_path)
    sup.close()
    ka.stop()


HH = generate_households(20)[1]


def args():
    return dict(person="p_learn01", d_min=45, gain=1.0, loss=2.0)


def audit_refusals(audit):
    return [x["note"] for x in audit.read(500) if x["kind"] == "offhours" and x["outcome"] == "refused"]


def test_refuses_without_unattended_consent(world):
    r = world["make"](Engine())
    for mode, rung, revoked in [("approval", "A2", False), ("unattended", "A1", False), ("unattended", "A2", True)]:
        write_consent(world["root"], mode, rung, revoked)
        res = r.tick(HH, **args())
        assert not res.started and res.code == "consent" and "not switched on" in res.reason
    assert not world["popens"] and audit_refusals(world["audit"]) == ["consent"] * 3


def test_refuses_when_the_screen_is_locked_asleep_or_unreadable(world):
    write_consent(world["root"])
    eng = Engine()
    r = world["make"](eng)
    world["screen"].is_locked = True
    res = r.tick(HH, **args())
    assert not res.started and res.code == "screen_locked" and "locked" in res.reason
    world["screen"].is_locked, world["screen"].is_asleep = False, True
    assert r.tick(HH, **args()).code == "screen_asleep"
    world["screen"].is_asleep = False
    r.screen = None
    assert r.tick(HH, **args()).code == "screen_unknown"
    assert not world["popens"] and eng.bodies == []  # never even asked the engine, never kept the machine awake
    assert audit_refusals(world["audit"]) == ["screen_locked", "screen_asleep", "screen_unknown"]


def test_refuses_when_the_kill_flag_is_set_or_the_engine_says_wait(world):
    write_consent(world["root"])
    r = world["make"](Engine(go=False))
    res = r.tick(HH, **args())
    assert res.code == "engine_wait" and res.decision["reason"] == "short" and not world["popens"]
    (world["root"] / "KILL").write_text("1")
    assert r.tick(HH, **args()).code == "kill"
    (world["root"] / "KILL").unlink()
    r2 = world["make"](Engine(status=500))
    assert r2.tick(HH, **args()).code == "engine_unreachable"


def test_go_runs_checkpointed_in_the_background_keeps_awake_only_while_active_and_reports(world, cluster):
    write_consent(world["root"])
    eng = Engine()
    r = world["make"](eng)
    res = r.tick(HH, **args(), run_id="r_off_1", now="2026-10-20T23:00:00Z")
    assert res.started and res.code == "go" and res.run_id == "r_off_1"
    body = eng.bodies[0]
    assert body == {"person": "p_learn01", "d_min": 45, "gain": 1.0, "loss": 2.0, "screen": "unlocked", "now": "2026-10-20T23:00:00Z"}
    assert world["ka"].active and world["popens"][0].cmd[:2] == ["caffeinate", "-dis"]  # awake while the run is active
    assert res.handle.wait(60) and res.handle.state == "done" and res.handle.result["completion"]["ok"]
    r.join(10)
    assert not world["ka"].active and world["popens"][0].terminated  # and no longer
    assert cluster.state.submissions == []
    rep = morning_report(world["audit"], world["queue"])
    assert [x["run_id"] for x in rep["ran"]] == ["r_off_1"] and rep["ran"][0]["outcome"] == "done"
    assert rep["ran"][0]["tier"] == 1 and rep["ran"][0]["minutes"] is not None
    assert len(rep["queued"]) == 1 and rep["failed"] == [] and rep["yielded"] == []
    text = json.dumps(rep)
    assert "GOV-" not in text and "T2U-" not in text


def test_the_worker_returning_aborts_the_run_within_one_second_and_the_report_says_so(world, cluster):
    write_consent(world["root"])
    r = world["make"](Engine())
    res = r.tick(HH, **args(), run_id="r_off_2")
    assert res.started
    deadline = time.time() + 20
    while time.time() < deadline and not any(x["kind"] == "agent_step" for x in world["audit"].read(500)):
        time.sleep(0.05)
    t0 = time.time()
    world["screen"].idle = 0.2  # the worker touched the machine: idle time fell to almost nothing
    assert res.handle.wait(1.0), "the run did not abort within one second"
    assert res.handle.state == "yielded" and time.time() - t0 < 1.0
    r.join(10)
    assert not world["ka"].active
    rep = morning_report(world["audit"], world["queue"])
    assert [y["run_id"] for y in rep["yielded"]] == ["r_off_2"]
    assert rep["ran"][0]["outcome"] == "yielded" and cluster.state.submissions == []
    # nothing is left half-done in the approval queue
    assert not [i for i in world["queue"].list("all") if i["kind"] == "irreversible_step"]


def test_the_report_lists_refusals_with_plain_reasons(world):
    write_consent(world["root"])
    world["screen"].is_locked = True
    world["make"](Engine()).tick(HH, **args())
    rep = morning_report(world["audit"], world["queue"])
    assert rep["ran"] == [] and rep["refused"][0]["reason"] == "The screen is locked, so I did not start."


def test_keep_awake_is_idempotent_and_stops():
    made = []
    ka = KeepAwake(lambda cmd, **kw: made.append(FakeProc(cmd)) or made[-1])
    ka.start(); ka.start()
    assert ka.active and ka.starts == 1
    ka.stop(); ka.stop()
    assert not ka.active and made[0].terminated


def test_presence_watcher_ignores_the_agents_own_input():
    human = HumanInputSignal()
    screen = FakeScreenState(idle=500.0)
    own = {"t": None}
    w = PresenceWatcher(screen, human, poll_s=0.02, own_activity=lambda: own["t"])
    w.start()
    try:
        time.sleep(0.1)
        seq = human.seq
        own["t"] = time.monotonic()      # the agent's actuator just produced an event
        screen.idle = 0.0                # which reset the idle clock
        time.sleep(0.2)
        assert human.seq == seq          # not treated as the worker
        own["t"] = None
        screen.idle = 0.0
        time.sleep(0.2)
        assert human.seq > seq           # the same drop with no agent event is the worker
    finally:
        w.stop()


# ------------------------------------------------------------------ desktop runner (simulated actuator only)
async def test_desktop_runner_stops_when_the_screen_locks_mid_run():
    screen = FakeScreenState()
    guard = Guard(MockProvider("computer_notepad"), run_id="r_desk", mode="model_driven", unattended=True,
                  unresolved_clicks_ok=True)
    sim = SimulatedActuator()

    class LocksAfterOne(ScreenGuardedActuator):
        async def execute(self, action):
            await super().execute(action)
            screen.is_locked = True

    from understudy_agent.tiers import computer_use as cu_mod

    async def verify():
        return True

    # a normal run completes on the simulated actuator
    res = await run_desktop_task("click the text area, type a line and press a key", model=MockProvider("computer_notepad"),
                                 guard=guard, actuator=sim, screen=screen, is_current=lambda: True, verify=verify)
    assert res.outcome == "done" and [a.kind for a in sim.actions] == ["click", "type", "key"]
    # the screen locking mid-run stops the next action
    screen2 = FakeScreenState()
    inner = SimulatedActuator()
    guarded = ScreenGuardedActuator(inner, screen2)
    await guarded.execute(Action("click", {"x": 5, "y": 5}))
    screen2.is_locked = True
    with pytest.raises(ActuatorRefused, match="locked"):
        await guarded.execute(Action("type", {"text": "x"}))
    assert len(inner.actions) == 1


def test_make_actuator_is_simulated_unless_explicitly_real():
    assert isinstance(make_actuator("TextEdit"), SimulatedActuator)
    with pytest.raises(ActuatorRefused, match="disabled"):
        make_actuator("TextEdit", real=True, env={})
