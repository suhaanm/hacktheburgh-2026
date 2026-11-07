"""Tier 1: the JSON step DSL on the sandbox sites (AGT-3, HND-3)."""
from __future__ import annotations

import asyncio
import copy

import pytest

from understudy_agent.core_sinks import FileAudit, FileQueue
from understudy_agent.sandbox_sites.bundles import calculator_bundle, casenote_bundle
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.sandbox_sites.specs import SITES
from understudy_agent.security.config import SecurityConfig
from understudy_agent.tiers.base import GateStop, PostconditionFailed, PreconditionFailed
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.dsl import DslRuntime, resolve_value, run_bundle, validate_bundle
from understudy_agent.tiers.safety import Safety


def _money(txt: str) -> float:
    import re

    return float(re.search(r"[\d,]+(?:\.\d+)?", txt).group(0).replace(",", ""))


@pytest.fixture
def sinks(tmp_path):
    return FileQueue(tmp_path / "queue"), FileAudit(tmp_path / "audit.jsonl")


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


@pytest.mark.parametrize("site", ["a", "b", "c"])
@pytest.mark.parametrize("hid", [0, 1, 3, 5])
async def test_bundle_replays_on_each_site(cluster, host, site, hid):
    h = generate_households(20)[hid]
    ctx = await host.new_context()
    page = await ctx.new_page()
    events = []
    rt = DslRuntime(page=page, params=h.params(), base_url=cluster.urls[site], navigator=f"nav-{site}",
                    emit=events.append)
    res = await run_bundle(calculator_bundle(site), rt)
    assert set(res.outputs) == {"amount", "status", "ref"}
    want = site_expected(site, h)["uc_monthly"]
    assert _money(res.outputs["amount"]) == pytest.approx(want, abs=0.06)
    assert events and all(e.tier == 1 for e in events)  # tier logged on every step
    assert res.checkpoints == [f"calculator_{site}_result_read"]


async def test_layout_v2_fails_the_first_precondition(cluster, host):
    h = generate_households(1)[0]
    page = await (await host.new_context()).new_page()
    rt = DslRuntime(page=page, params=h.params(), base_url=cluster.urls["b"], query="?layout=v2",
                    pre_timeout_ms=400, post_timeout_ms=600)
    with pytest.raises((PreconditionFailed, PostconditionFailed)):
        await run_bundle(calculator_bundle("b", "v1"), rt)
    # the v2 bundle works on the v2 layout
    rt2 = DslRuntime(page=page, params=h.params(), base_url=cluster.urls["b"], query="?layout=v2")
    res = await run_bundle(calculator_bundle("b", "v2"), rt2)
    assert res.outputs["amount"]


async def test_two_contexts_do_not_share_state(cluster, host):
    c1, c2 = await host.new_context(), await host.new_context()
    p1, p2 = await c1.new_page(), await c2.new_page()
    await p1.goto(cluster.urls["b"] + "/")
    await p1.evaluate("document.cookie = 'who=nav1; path=/'; localStorage.setItem('k','v1')")
    await p2.goto(cluster.urls["b"] + "/")
    assert await p2.evaluate("document.cookie") == ""
    assert await p2.evaluate("localStorage.getItem('k')") is None
    assert await p1.evaluate("document.cookie") == "who=nav1"


async def test_case_note_bundle_saves_a_draft_and_never_submits(cluster, host, sinks):
    q, a = sinks
    h = generate_households(1)[0]
    params = {"case_ref": h.case_ref, "result_a": "£313", "result_b": "£539.19 per month",
              "result_c": "313.14 GBP / month", "reconciliation": "discrepancy", "note_text": "checked cliff"}
    page = await (await host.new_context()).new_page()
    rt = DslRuntime(page=page, params=params, base_url=cluster.urls["a"], navigator="scribe")
    res = await run_bundle(casenote_bundle(), rt)
    assert res.outputs["note_id"].startswith("CN-") and res.outputs["status"] == "Draft"
    assert "£313" in res.outputs["body"]
    assert cluster.state.submissions == []


async def test_click_on_a_submit_button_is_stopped_by_the_gate(cluster, host, sinks):
    q, a = sinks
    h = generate_households(1)[0]
    params = {"case_ref": h.case_ref, "result_a": "1", "result_b": "2", "result_c": "3",
              "reconciliation": "agree", "note_text": "x"}
    page = await (await host.new_context()).new_page()
    await run_bundle(casenote_bundle(), DslRuntime(page=page, params=params, base_url=cluster.urls["a"]))
    submit = {"id": "evil", "version": 1, "params": [], "steps": [
        {"id": "submit", "op": "click", "selector": "#submit-note", "pre": [{"visible": "#submit-note"}]}]}
    safety = Safety(queue=q, audit=a, run_id="r_test")
    with pytest.raises(GateStop) as exc:
        await run_bundle(submit, DslRuntime(page=page, params={}, base_url="", safety=safety))
    assert exc.value.decision.verdict == "needs_human" and exc.value.decision.queue_id
    assert cluster.state.submissions == []
    item = q.list()[0]
    assert item["kind"] == "irreversible_step" and item["status"] == "pending" and item["run_id"] == "r_test"
    # with the gates layer ablated, the same click goes through (this is what the red-team ablation measures)
    safety_off = Safety(config=SecurityConfig.all_on().without("gates"), queue=q, audit=a, run_id="r_test")
    await run_bundle(submit, DslRuntime(page=page, params={}, base_url="", safety=safety_off))
    assert len(cluster.state.submissions) == 1


async def test_cancellation_stops_between_steps(cluster, host):
    h = generate_households(1)[0]
    page = await (await host.new_context()).new_page()
    calls = {"n": 0}

    def cur() -> bool:
        calls["n"] += 1
        return calls["n"] < 4

    rt = DslRuntime(page=page, params=h.params(), base_url=cluster.urls["b"], is_current=cur)
    with pytest.raises(asyncio.CancelledError):
        await run_bundle(calculator_bundle("b"), rt)


def test_validator_rejects_bad_bundles():
    good = calculator_bundle("a")
    assert validate_bundle(good) == []
    bad = copy.deepcopy(good)
    bad["steps"][1]["op"] = "eval"
    assert any("unknown op" in e for e in validate_bundle(bad))
    bad = copy.deepcopy(good)
    bad["steps"][0]["url"] = "http://evil.example/"
    assert any("goto url" in e for e in validate_bundle(bad))
    bad = copy.deepcopy(good)
    bad["steps"][1]["value"] = {"param": "not_declared"}
    assert any("undeclared param" in e for e in validate_bundle(bad))
    bad = copy.deepcopy(good)
    bad["steps"][1]["code"] = "page.evaluate('x')"
    assert any("unknown keys" in e for e in validate_bundle(bad))
    bad = copy.deepcopy(good)
    bad["steps"] = bad["steps"] * 4
    errs = validate_bundle(bad)
    assert any("too many steps" in e for e in errs)


def test_resolve_value_applies_unit_transforms():
    assert resolve_value({"param": "pay", "mul": 12.0, "round": 2}, {"pay": "1000"}) == "12000.00"
    assert resolve_value({"literal": "x"}, {}) == "x"
    assert resolve_value({"param": "pay", "mul": 12.0}, {"pay": ""}) == ""
