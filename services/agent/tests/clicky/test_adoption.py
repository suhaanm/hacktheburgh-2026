"""How the agent-runtime and safety tracks plug the lifts in: a lease in front of the real SafetyPipeline, the real
audit log as the event sink, the real kill flag, and a postcondition after the step. Everything runs in tmp dirs with
the mock model port; no network, no real data directory."""
from __future__ import annotations

import json

from clicky_lift import (
    Condition,
    LeaseBook,
    Observation,
    StopReason,
    equals,
    matches,
    verify,
)
from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.detector import PageObservation
from understudy_agent.security.gates import RoutineContext, TargetInfo
from understudy_agent.security.killflag import clear_kill, is_killed, set_kill
from understudy_agent.security.pipeline import SafetyPipeline
from understudy_agent.security.settings import Origin

PAGE = "http://localhost:7801/calc"
CLEAN = PageObservation(text="Calculator A\nEntitlement: 812.40", url=PAGE, title="Calc A")
SCHEMA = {"title": "calc_result", "type": "object", "required": ["entitlement"],
          "properties": {"entitlement": {"type": "number"}, "note": {"type": "string", "maxLength": 80}}}


def audit_sink(audit: AuditLog, run_id: str):
    """The whole adapter: a lease event becomes one audit line (tokens and numbers only)."""
    def sink(ev: dict) -> None:
        audit.append("system", ev["kind"], routine="bga_child", run_id=run_id, outcome=ev["outcome"],
                     note_code=f"lease:{ev['code']}", meta={"lease_id": ev["lease_id"], "steps": ev["steps"],
                                                           **({"tool": ev["tool"]} if "tool" in ev else {})})
    return sink


def make_pipeline(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    routine = RoutineContext(routine_id="bga_child", run_id="r_child1", mode="compiled", rung="A2")
    pipe = SafetyPipeline(MockProvider("reader_basic"), audit=audit, queue=queue, routine=routine,
                          goal="Enter the household in calculator A and read the result")
    return pipe, audit


def test_lease_in_front_of_the_pipeline_audit_chain_and_kill_flag(tmp_path, clock):
    pipe, audit = make_pipeline(tmp_path)
    book = LeaseBook(clock=clock, killed=is_killed, on_event=audit_sink(audit, "r_child1"))
    lease = book.issue(holder="child_1", tools={"click", "type", "screenshot"}, ttl_s=120, max_steps=10)

    def step(kind, args, label):
        d = lease.check(kind)                                    # 1. lease: scope, deadline, step cap, revoke
        if not d.allowed:
            return d, None
        obs = pipe.observe(CLEAN, SCHEMA)                        # 2. the SafetyPipeline: all eight layers, unchanged
        dec = pipe.authorise(Action(kind, args), observation=obs, target=TargetInfo(label=label, role="button", url=PAGE))
        return d, dec

    d, dec = step("click", {"x": 10, "y": 10}, "Calculate")
    assert d.allowed and dec.verdict == "allow"
    pipe.record_result(dec.action, True)

    # a tool outside the child's scope never reaches the pipeline, and the lease stops
    d, dec = step("goto", {"url": "https://example.org"}, None)
    assert not d.allowed and d.code == StopReason.SCOPE_VIOLATION and dec is None
    assert not lease.check("click").allowed

    # a fresh lease; the kill flag set by the worker stops it on the next check
    lease2 = book.issue(holder="child_2", tools={"click"}, ttl_s=120, max_steps=10)
    assert lease2.check("click").allowed
    set_kill("test")
    try:
        assert lease2.check("click").code == StopReason.KILL_FLAG
    finally:
        clear_kill()

    # the real audit log took every lease event, chained, with no raw text and no unvetted names
    assert audit.verify_chain()
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    kinds = [x["kind"] for x in lines if x["kind"].startswith("lease_")]
    assert kinds.count("lease_issued") == 2 and "lease_denied" in kinds and kinds.count("lease_stopped") == 2
    assert "goto" in json.dumps(lines)                           # a well-formed tool name may be named
    assert "Calculator A" not in json.dumps(lines)


def test_postcheck_after_the_step_and_a_lease_that_stops_on_a_false_done(tmp_path, clock):
    book = LeaseBook(clock=clock)
    lease = book.issue(holder="child_1", tools={"click", "extract"}, ttl_s=120, max_steps=10)
    cond = Condition.of(matches("note_id", r"CN-\d{4}"), equals("status", "saved"))

    assert lease.check("click").allowed
    ok = verify(cond, Observation({"note_id": "CN-1234", "status": "saved"}))
    assert ok.ok and lease.record(ok) is True

    assert lease.check("click").allowed
    false_done = verify(cond, Observation({"note_id": "", "status": "saved"}))      # the model said done; the page disagrees
    assert false_done.verdict == "failed" and lease.record(false_done) is False
    assert lease.check("click").code == StopReason.VERIFICATION

    audit = AuditLog(tmp_path / "audit2.jsonl")
    audit.append("agent", "step", run_id="r_child1", outcome=false_done.verdict, note_code=f"post:{false_done.reason}",
                 meta=false_done.audit_meta())                                          # post results are valid audit meta
    assert audit.verify_chain()


def test_the_approval_age_gap_found_by_clk_1_is_closed(tmp_path):
    """CLK-1 found that consume_approval ignored approval age; agent-safety added a max age. Clicky's confirmation state
    expired requests but never made them single-use; the queue has both, so no confirmation module was lifted."""
    now = [1_000_000.0]
    queue = ApprovalQueue(tmp_path / "queue", clock=lambda: now[0])

    def approved(sig: str) -> str:
        item = queue.enqueue(kind="irreversible_step", title="submit case note", summary="needs a click",
                             risk_class="irreversible", signature=sig)
        queue.approve(item["id"], origin=Origin.HUMAN_UI)
        return item["id"]

    fresh = approved("sig_submit_1")
    assert queue.consume_approval(fresh, "sig_submit_1") is True
    assert queue.consume_approval(fresh, "sig_submit_1") is False        # single use
    stale = approved("sig_submit_2")
    now[0] += 8 * 3600                                                   # approved at 22:00, the run resumes at 06:00
    assert queue.consume_approval(stale, "sig_submit_2") is False
