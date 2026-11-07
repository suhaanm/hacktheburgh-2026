"""S-11 (Medium): an approval is a plain JSON file and a signature that is a coarse bucket, with no run binding.
(a) data/queue/<id>.json has no integrity tag: whoever can write that file (a local process, any bug that lets an agent write under data/)
    sets status=approved + decided_at=now and try_consume_approval accepts it. Only Origin.HUMAN_UI in code stands between.
(b) action_signature buckets pixels by 24 (x // 24), ignores labels and has no page/app/screen identity: an approval for the click at
    (100,100) 'Save' is good for (119,119) 'Delete'.
(c) try_consume_approval() never checks run_id/routine_id: an approval raised in run r1 is consumed by run r2 with the same signature.
Hermetic: temp dirs, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.actions import validate_action
from understudy_agent.security.gates import RoutineContext
from understudy_agent.security.pipeline import SafetyPipeline
from understudy_agent.security.settings import Origin


def item(q, sig, run="r1"):
    return q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature=sig, run_id=run)


def test_a_file_edit_is_enough_to_approve(tmp_path):
    q = ApprovalQueue(tmp_path / "q")
    it = item(q, "sig-1")
    p = q.root / f"{it['id']}.json"
    d = json.loads(p.read_text())
    d.update(status="approved", decided_at=datetime.now(timezone.utc).isoformat(), decided_by="worker")
    p.write_text(json.dumps(d))                                              # no HUMAN_UI call anywhere
    assert not q.consume_approval(it["id"], "sig-1"), "an approval written by editing the JSON file was accepted"


def test_an_approval_for_one_click_is_good_for_a_neighbour_in_the_same_24px_bucket(tmp_path):
    q = ApprovalQueue(tmp_path / "q")
    save = validate_action("click", {"x": 100, "y": 100, "label": "Save"}).signature
    delete = validate_action("click", {"x": 119, "y": 119, "label": "Delete"}).signature
    it = item(q, save)
    q.approve(it["id"], origin=Origin.HUMAN_UI)
    assert not q.consume_approval(it["id"], delete), "approval for 'Save' at (100,100) was consumed by 'Delete' at (119,119)"


def test_an_approval_from_run_r1_is_consumed_by_run_r2(tmp_path):
    q = ApprovalQueue(tmp_path / "q", audit=AuditLog(tmp_path / "a.jsonl"))
    act = {"kind": "click_element", "args": {"selector": "#submit", "label": "Submit"}}
    sig = validate_action("click_element", act["args"]).signature
    it = item(q, sig, run="r1")
    q.approve(it["id"], origin=Origin.HUMAN_UI)
    other = SafetyPipeline(MockProvider(), queue=q, audit=AuditLog(tmp_path / "a.jsonl"), routine=RoutineContext(mode="interactive", run_id="r2"))
    obs = other.observe(__import__("understudy_agent.security.detector", fromlist=["PageObservation"]).PageObservation(text="x"))
    dec = other.authorise(act, observation=obs, approved_queue_id=it["id"])
    assert dec.verdict != "allow", "run r2 used the approval the worker gave for run r1"
