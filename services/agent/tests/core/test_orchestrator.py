"""One household end to end in mock mode (T+8 checkpoint): three navigators, verifier, critic, scribe, gate."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.orchestrator import (
    BenefitsRun, Check, RunOptions, compose_note, critic, default_checks, finalize, reconcile,
)
from understudy_agent.completion import validate_result_fields
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import Adult, Household, generate_households
from understudy_agent.sandbox_sites.oracle import disagreements, site_expected
from understudy_agent.security.denylist import Denylist
from understudy_agent.security.settings import Origin
from understudy_agent.tiers.heuristic import HeuristicModelPort


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    return queue, audit, tmp_path


def make_run(cluster, env, hid=0, **opt):
    queue, audit, _ = env
    h = generate_households(20)[hid]
    opts = RunOptions(denylist=Denylist(), **opt)
    run = BenefitsRun(f"r_t{hid}", h, model=HeuristicModelPort(MockProvider("benefits_clean")),
                      base_urls=cluster.urls, queue=queue, audit=audit, options=opts)
    return run, h


async def test_one_household_end_to_end(cluster, env):
    queue, audit, tmp = env
    run, h = make_run(cluster, env, hid=1)
    res = await run.execute()
    assert res.state == "done", res.reason
    assert res.completion == {"ok": True, "missing": []}
    assert set(res.results) == {"a", "b", "c"} and res.false_claims == 0
    assert res.cliff_checked == {"a": True, "b": True, "c": True}
    assert res.note_id and res.note_id.startswith("CN-")
    for s in "abc":
        assert res.results[s]["amount"] == pytest.approx(site_expected(s, h)["uc_monthly"], abs=0.06)
    # every step is tier 1 on the clean path, and every step has a tier
    steps = res.tier_log
    assert steps and all(isinstance(e["tier"], int) for e in steps) and {e["tier"] for e in steps} == {1}
    # three navigators ran in parallel, in their own contexts (events interleave)
    first = [e["navigator"] for e in steps[:12]]
    assert len(set(first)) >= 2
    # STOP BEFORE SUBMIT: nothing was submitted; one irreversible item is pending with evidence
    assert cluster.state.submissions == []
    assert res.awaiting_approval and res.queue_id
    item = queue.get(res.queue_id)
    assert item["kind"] == "irreversible_step" and item["risk_class"] == "irreversible" and item["status"] == "pending"
    assert item["run_id"] == run.run_id and res.note_id in item["title"]
    ev = item["evidence"]
    assert len(ev["screenshots"]) == 4 and set(ev["extracted"]) >= {"a", "b", "c", "note_id"}
    assert ev["expected"]["calculators"] == 3 and ev["tier_log"]
    # evidence bundle on disk
    d = tmp / "data" / "runs" / run.run_id
    assert (d / "evidence.json").exists() and (d / "case_note.md").exists()
    assert len(list(d.glob("s*.png"))) == 4
    saved = json.loads((d / "evidence.json").read_text())
    assert saved["household"]["synthetic"] is True
    # audit log carries no page text
    lines = audit.read(2000)
    assert lines and all(x["actor"] in ("agent", "system", "human") for x in lines)
    text = json.dumps(lines)
    assert "GOV-" not in text and "T2U-" not in text and res.note_text[:30] not in text
    assert audit.verify_chain()
    # CAP-6: the agent never wrote a human actor line
    assert not [x for x in lines if x["actor"] == "human"]


async def test_discrepancy_household_is_flagged_not_averaged_away(cluster, env):
    # hh_0004: savings exactly at 16,000: calculator c says no, a and b say yes
    run, h = make_run(cluster, env, hid=3)
    res = await run.execute()
    assert res.state == "done" and res.completion["ok"]
    assert res.reconciliation["status"] == "discrepancy" and res.reconciliation["needs_review"] is True
    assert "c" in res.reconciliation["outliers"] or "b" in res.reconciliation["outliers"]
    assert "discrepancy" in res.note_text.lower() and "capital_limit_16000" in res.note_text
    item = run.queue.get(res.queue_id)
    assert "DISAGREE" in item["summary"] and item["evidence"]["diff"]
    assert cluster.state.submissions == []


async def test_layout_change_on_one_site_uses_tier2_for_that_site_only(cluster, env):
    run, h = make_run(cluster, env, hid=2, query={"b": "?layout=v2"})
    res = await run.execute()
    assert res.state == "done", res.reason
    by_nav: dict[str, set[int]] = {}
    for e in res.tier_log:
        by_nav.setdefault(e["navigator"], set()).add(e["tier"])
    assert by_nav["nav-a"] == {1} and by_nav["nav-c"] == {1}
    assert 2 in by_nav["nav-b"] and 1 in by_nav["nav-b"]
    assert res.false_claims == 0 and res.cliff_checked["b"] is True


async def test_injected_pages_pause_the_whole_run_and_nothing_is_obeyed(cluster, env):
    queue, audit, _ = env
    run, h = make_run(cluster, env, hid=0, query={"a": "?variant=injected", "b": "?variant=injected",
                                                  "c": "?variant=injected"})
    res = await run.execute()
    assert res.state == "paused" and "injection" in res.reason
    assert cluster.state.exfil_hits == [] and cluster.state.submissions == []
    assert not res.awaiting_approval
    kinds = {i["kind"] for i in queue.list("all")}
    assert "injection_pause" in kinds and "irreversible_step" not in kinds
    assert not res.results  # no numbers were trusted from a page that was talking to the agent


async def test_one_injected_site_stops_the_others_too(cluster, env):
    run, h = make_run(cluster, env, hid=0, query={"c": "?variant=injected"})
    res = await run.execute()
    assert res.state == "paused"
    assert cluster.state.submissions == [] and cluster.state.exfil_hits == []
    assert res.completion["ok"] is False


async def test_stop_wins_within_one_second(cluster, env):
    queue, audit, _ = env
    flag = {"on": True}
    run, h = make_run(cluster, env, hid=0, query={"a": "?layout=v2", "b": "?layout=v2", "c": "?layout=v2"})
    run.is_current = lambda: flag["on"]
    task = asyncio.create_task(run.execute())
    await asyncio.sleep(1.2)  # let the navigators get going
    t0 = time.monotonic()
    flag["on"] = False
    res = await asyncio.wait_for(task, 5)
    assert time.monotonic() - t0 < 1.0
    assert res.state == "stopped"
    n = len(run.events)
    await asyncio.sleep(0.5)
    assert len(run.events) == n  # nothing more happens after stop
    assert cluster.state.submissions == []


async def test_finalize_submits_only_after_approval_and_only_once(cluster, env):
    queue, audit, _ = env
    run, h = make_run(cluster, env, hid=1)
    res = await run.execute()
    model = HeuristicModelPort(MockProvider("benefits_clean"))
    out = await finalize(run.run_id, res.note_id, res.queue_id, model=model, base_url_a=cluster.urls["a"], queue=queue, audit=audit)
    assert out["submitted"] is False and cluster.state.submissions == []  # still pending
    queue.approve(res.queue_id, origin=Origin.HUMAN_UI)
    out = await finalize(run.run_id, res.note_id, res.queue_id, model=model, base_url_a=cluster.urls["a"], queue=queue, audit=audit)
    assert out["submitted"] is True and len(cluster.state.submissions) == 1
    out = await finalize(run.run_id, res.note_id, res.queue_id, model=model, base_url_a=cluster.urls["a"], queue=queue, audit=audit)
    assert out["submitted"] is False and len(cluster.state.submissions) == 1  # the approval works once


async def test_a_calculator_that_never_answers_fails_the_run_without_a_note(cluster, env):
    run, h = make_run(cluster, env, hid=0, query={"c": "?glitch=503always"})
    res = await run.execute()
    assert res.state == "failed" and res.completion["ok"] is False
    assert any("calculator c" in m for m in res.completion["missing"])
    assert res.note_id is None and cluster.state.notes == {}
    assert any(i["kind"] == "batch_result" for i in run.queue.list("all"))


# ------------------------------------------------------------------ pure pieces
def rf(site, amt, status, ref):
    r, p = validate_result_fields(site, {"amount_text": amt, "status_text": status, "ref": ref})
    assert r, p
    return r


def test_reconcile_agree_and_discrepancy():
    a, b, c = rf("a", "£781", "You are likely to be eligible", "GOV-111111"), rf("b", "£781.00 per month", "Likely to qualify", "T2U-222222"), rf("c", "781.04 GBP / month", "ELIGIBLE", "ET-333333")
    r = reconcile({"a": a, "b": b, "c": c})
    assert r.status == "agree" and not r.needs_review and r.outliers == []
    c2 = rf("c", "0.00 GBP / month", "NOT ELIGIBLE", "ET-333333")
    r = reconcile({"a": a, "b": b, "c": c2})
    assert r.status == "discrepancy" and r.needs_review and r.outliers == ["c"] and r.value == 781.0


def test_critic_enforces_the_expert_policy():
    checks = default_checks()
    done = {"read_case": 1, "calc_a": 2, "calc_b": 3, "calc_c": 4, "cliff_a": 5, "cliff_b": 6, "cliff_c": 7, "reconcile": 8,
            "write_note": 9}
    ok = critic(checks, done, recon=None, flags=[], note_text="fine", sites_disagree=False)
    assert ok.ok
    skipped = {k: v for k, v in done.items() if k != "cliff_b"}
    rep = critic(checks, skipped, recon=None, flags=[], note_text="fine", sites_disagree=False)
    assert not rep.ok and any(f.check == "cliff_b" and f.severity == "blocker" for f in rep.findings)
    swapped = dict(done, reconcile=1)  # reconcile before the calculators
    assert not critic(checks, swapped, recon=None, flags=[], note_text="x", sites_disagree=False).ok
    a, c = rf("a", "£781", "ELIGIBLE", "GOV-111111"), rf("c", "0.00 GBP / month", "NOT ELIGIBLE", "ET-333333")
    recon = reconcile({"a": a, "b": a, "c": c})
    bad = critic(checks, done, recon=recon, flags=["capital_limit_16000"], note_text="all good", sites_disagree=True)
    assert not bad.ok and len([f for f in bad.findings if f.severity == "blocker"]) >= 2
    liar = reconcile({"a": a, "b": a, "c": a})  # says agree while the sites actually disagree
    assert not critic(checks, done, recon=liar, flags=[], note_text="x", sites_disagree=True).ok


def test_note_mentions_cliffs_and_discrepancy():
    h = generate_households(20)[3]
    a, b = rf("a", "£781", "ELIGIBLE", "GOV-111111"), rf("b", "£955", "ELIGIBLE", "T2U-222222")
    c = rf("c", "0.00 GBP / month", "NOT ELIGIBLE", "ET-333333")
    recon = reconcile({"a": a, "b": b, "c": c})
    note = compose_note(h, {"a": a, "b": b, "c": c}, recon, ["capital_limit_16000"], {"a": True, "b": True, "c": True})
    assert "discrepancy" in note.lower() and "capital_limit_16000" in note and "Stopped before submit" in note
    assert "GOV-111111" in note and "T2U-222222" in note and "ET-333333" in note
