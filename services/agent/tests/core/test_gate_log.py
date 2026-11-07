"""Gate stops are logged apart from model failures (REQ-7 review note on S-26): every verdict that is not "allow" becomes one typed
record; a layer-3 rejection is counted as the model's failure, not as a gate stop; the designed Submit stop is flagged; and no record
holds a typed value or more page text than a short sanitised control name."""
from __future__ import annotations

import json

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.orchestrator import BenefitsRun, RunOptions, SUBMIT_LABEL, _typed_text, instrument_guard
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.heuristic import HeuristicModelPort
from understudy_agent.tiers.safety import Guard


def make_guard(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    return Guard(MockProvider("benefits_clean"), run_id="r_gl", mode="model_driven", audit=audit,
                 queue=ApprovalQueue(tmp_path / "q", audit=audit), denylist=Denylist())


def test_an_unreadable_click_is_a_gate_stop_and_a_malformed_action_is_a_model_failure(tmp_path):
    g = make_guard(tmp_path)
    stops: list[dict] = []
    rej: list[int] = []
    instrument_guard(g, "nav-a", stops, frozenset(), rejections=lambda: rej.append(1), step_of=lambda: 7)
    seen = g.observe_screen()
    dec = g.authorise({"kind": "click", "args": {"x": 10, "y": 10}}, seen, screen=(1280, 800))      # nothing read at the target
    assert dec.verdict == "needs_human" and len(stops) == 1 and not rej
    rec = stops[0]
    assert rec["nav"] == "nav-a" and rec["step"] == 7 and rec["kind"] == "click" and rec["verdict"] == "needs_human"
    assert rec["designed"] is False and rec["layer"] and rec["codes"]
    seen = g.observe_screen()
    bad = g.authorise({"kind": "click", "args": {"x": -5, "y": 3}}, seen, screen=(1280, 800), label="Calculate", role="button")
    assert bad.verdict == "block" and bad.layer == "actions" and len(stops) == 1 and rej == [1]      # the model's failure, counted apart
    seen = g.observe_screen()
    ok = g.authorise({"kind": "click", "args": {"x": 10, "y": 10}}, seen, screen=(1280, 800), label="Calculate", role="button")
    assert ok.verdict == "allow" and len(stops) == 1                                                  # an allowed step leaves no record


def test_a_record_carries_enums_and_a_short_sanitised_name_only(tmp_path):
    g = make_guard(tmp_path)
    stops: list[dict] = []
    instrument_guard(g, "nav-b", stops, frozenset(), step_of=lambda: 1)
    seen = g.observe_screen()
    g.authorise({"kind": "click", "args": {"x": 10, "y": 10}}, seen, screen=(1280, 800), label="Place order 4455667788\n now", role="button",
                structure=("submit_control", "external_form:127.0.0.1:41233", "path:orders confirm"))
    rec = stops[0]
    blob = json.dumps(rec)
    assert "4455667788" not in blob and "41233" not in blob and "\n" not in blob
    assert "pay" in rec["classes"] and len(rec["label"]) <= 60 and "external_form:127.0.0.1:#" in rec["structure"]
    assert _typed_text("a" * 500, 60) == "a" * 60


async def test_a_whole_household_has_only_the_designed_submit_stop(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    run = BenefitsRun("r_glh", generate_households(20)[1], model=HeuristicModelPort(MockProvider("benefits_clean")),
                      base_urls=cluster.urls, queue=queue, audit=audit, options=RunOptions(denylist=Denylist()))
    res = await run.execute()
    assert res.state == "done" and res.awaiting_approval
    assert [g["designed"] for g in run.gate_stops] == [True], run.gate_stops
    assert run.gate_stops[0]["label"] == SUBMIT_LABEL and run.gate_stops[0]["verdict"] == "needs_human"
    assert res.action_rejections == 0 and run.scribe_nav is not None
    assert all("label" not in g for g in res.gate_stops) and res.gate_stops[0]["designed"] is True    # the result carries no control name
