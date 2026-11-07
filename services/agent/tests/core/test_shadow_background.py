"""HND-4 shadow mode and HND-5 background runs that yield to the human."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.compile import compile_draft
from understudy_agent.handoff_io import (
    Consent, EngineClient, EngineError, consent_allows, read_consent,
)
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.sandbox_sites.recordings import synthetic_recording
from understudy_agent.shadow import BackgroundRunner, ConsentRefused, ShadowRunner, compare
from understudy_agent.supervisor import HumanInputSignal, Supervisor
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.heuristic import HeuristicModelPort


class FakeEngine:
    """Implements the documented POST /routines/{id}/shadow contract with understudy_engine.trust's ladder."""

    def __init__(self, rung="A1"):
        from understudy_engine.trust.ladder import LadderState

        self.state = LadderState(rung=rung)
        self.posts: list[dict] = []
        self.headers: list[str] = []
        self.seen: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        from understudy_engine.trust.ladder import record_run

        body = json.loads(request.content)
        self.posts.append(body)
        self.headers.append(request.headers.get("x-understudy-actor", ""))
        accepted, dups = 0, []
        promoted = demoted = False
        for it in body["results"]:
            if it["run_id"] in self.seen:
                dups.append(it["run_id"])
                continue
            self.seen.add(it["run_id"])
            accepted += 1
            outcome = it.get("event") or ("clean" if it["matched"] else "mismatch")
            d = record_run(self.state, outcome)
            self.state, promoted, demoted = d.state, promoted or d.promoted, demoted or d.demoted
        s = self.state
        return httpx.Response(200, json={"runs": s.runs, "matches": s.clean, "wilson_lower": s.wilson_lower, "rung": s.rung,
                                         "promoted": promoted, "demoted": demoted, "accepted": accepted,
                                         "duplicates": dups, "blocked": False})

    def client(self) -> EngineClient:
        return EngineClient("http://engine.test", client=httpx.Client(transport=httpx.MockTransport(self.handler)))


def write_consent(root, routine, mode="shadow", rung="A1", revoked=False):
    d = root / "routines" / routine
    d.mkdir(parents=True, exist_ok=True)
    (d / "consent.json").write_text(json.dumps({"mode": mode, "rung": rung, "irreversible_unattended": [],
                                                "revoked": revoked}))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    audit = AuditLog(tmp_path / "audit.jsonl")
    return ApprovalQueue(tmp_path / "queue", audit=audit), audit, tmp_path


@pytest.fixture
def model():
    return HeuristicModelPort(MockProvider("benefits_clean"))


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


def bundles_for(cluster, model, sites="abc"):
    out = {}
    for s in sites:
        b, rep = compile_draft(synthetic_recording(s, base_urls=cluster.urls), base_urls=cluster.urls, model=model)
        assert b is not None, rep.errors
        out[s] = b
    return out


def hh(i):
    return generate_households(20)[i]


def worker_for(h, sites="abc"):
    return {s: site_expected(s, h)["uc_monthly"] for s in sites}


# ------------------------------------------------------------------ consent
def test_consent_rules_fail_closed(tmp_path):
    assert read_consent("nope", tmp_path) == Consent()
    assert not consent_allows(Consent(), "shadow")[0]
    for mode, kind, want in [("shadow", "shadow", True), ("shadow", "background", False), ("approval", "background", True),
                             ("approval", "unattended", False), ("unattended", "unattended", True), ("never", "shadow", False),
                             ("not_now", "shadow", False)]:
        assert consent_allows(Consent(mode=mode, rung="A2", present=True), kind)[0] is want, (mode, kind)
    assert not consent_allows(Consent(mode="unattended", rung="A1", present=True), "unattended")[0]
    assert not consent_allows(Consent(mode="unattended", rung="A3", revoked=True, present=True), "shadow")[0]


# ------------------------------------------------------------------ shadow
def test_compare_is_code_checked():
    assert compare({"a": 313.0, "b": 313.14}, {"a": 313.0, "b": 313.14}) == (True, [])
    ok, diffs = compare({"a": 313.0, "b": None}, {"a": 313.0, "b": 313.14})
    assert not ok and diffs == [{"site": "b", "agent": None, "worker": 313.14}]
    assert not compare({"a": 313.5}, {"a": 313.0})[0]


async def test_shadow_does_not_start_without_consent(cluster, host, model, env):
    q, a, root = env
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model, "a"), model=model, audit=a, queue=q,
                     base_urls=cluster.urls, root=root)
    with pytest.raises(ConsentRefused):
        await r.run_episode(host, hh(1), worker_for(hh(1), "a"))
    write_consent(root, "calc-entry-3x", revoked=True)
    with pytest.raises(ConsentRefused):
        await r.run_episode(host, hh(1), worker_for(hh(1), "a"))
    assert cluster.state.calculations == []  # nothing even ran
    assert any(x["kind"] == "consent" and x["outcome"] == "refused" for x in a.read(50))


async def test_shadow_match_posts_the_code_checked_verdict_and_saves_nothing(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")
    eng = FakeEngine()
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model), model=model, engine=eng.client(), audit=a, queue=q,
                     base_urls=cluster.urls, root=root)
    out = await r.run_episode(host, hh(3), worker_for(hh(3)), run_id="r_shadow_1")
    assert out.matched and out.engine["accepted"] == 1 and out.engine["rung"] == "A1"
    body = eng.posts[0]
    assert body == {"results": [{"run_id": "r_shadow_1", "matched": True}]} and eng.headers == ["agent"]
    assert cluster.state.notes == {} and cluster.state.submissions == []  # nothing saved or submitted
    assert len(cluster.state.calculations) == 3
    # a retry with the same run id is ignored by the engine contract, not double counted
    again = r.engine.post_shadow("calc-entry-3x", [{"run_id": "r_shadow_1", "matched": True}])
    assert again["duplicates"] == ["r_shadow_1"] and eng.state.runs == 1


async def test_shadow_mismatch_counts_against_the_bound_and_queues_a_review(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")
    eng = FakeEngine()
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model), model=model, engine=eng.client(), audit=a, queue=q,
                     base_urls=cluster.urls, root=root)
    worker = worker_for(hh(3))
    worker["b"] += 25.0  # the worker typed something different on b
    out = await r.run_episode(host, hh(3), worker, run_id="r_shadow_2")
    assert not out.matched and out.diffs[0]["site"] == "b" and "b" in out.reason
    assert eng.posts[0]["results"][0] == {"run_id": "r_shadow_2", "matched": False, "reason": out.reason}
    assert "£" not in out.reason and len(out.reason) <= 200
    items = q.list()
    assert items and items[0]["kind"] == "shadow_mismatch"
    assert eng.state.runs == 1 and eng.state.clean == 0 and eng.state.rung == "A1"  # a mismatch at A1 does not demote


async def test_a_broken_routine_posts_a_failure_event(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")
    eng = FakeEngine(rung="A2")
    bundles = bundles_for(cluster, model, "b")
    bundles["b"]["steps"][2]["selector"] = "#does-not-exist"
    bundles["b"]["steps"][2]["precondition"] = {"selector_visible": "#does-not-exist"}
    r = ShadowRunner("calc-entry-3x", bundles, model=model, engine=eng.client(), audit=a, queue=q, base_urls=cluster.urls,
                     root=root)
    out = await r.run_episode(host, hh(1), worker_for(hh(1), "b"), run_id="r_shadow_3")
    assert out.event == "failure" and not out.matched
    assert eng.posts[0]["results"][0] == {"run_id": "r_shadow_3", "event": "failure"}
    assert eng.state.rung == "A1"  # demoted one rung


async def test_an_injected_page_during_shadow_posts_an_injection_event(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")
    eng = FakeEngine(rung="A2")
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model, "b"), model=model, engine=eng.client(), audit=a,
                     queue=q, base_urls=cluster.urls, root=root)
    # the recorded start url has no variant switch: the injected page is reached through the runtime query
    out = await r.run_episode(host, hh(1), worker_for(hh(1), "b"), run_id="r_shadow_4", query={"b": "?variant=injected"})
    assert out.event == "injection" and eng.posts[0]["results"][0]["event"] == "injection"
    assert cluster.state.exfil_hits == [] and cluster.state.submissions == []


async def test_twenty_clean_episodes_earn_the_promotion_a1_to_a2(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")
    eng = FakeEngine()
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model, "a"), model=model, engine=eng.client(), audit=a,
                     queue=q, base_urls=cluster.urls, root=root)
    promoted_at = None
    for i, h in enumerate(generate_households(20)):
        out = await r.run_episode(host, h, worker_for(h, "a"), run_id=f"r_shadow_{100 + i}")
        assert out.matched, (h.id, out.diffs, out.reason)
        if out.engine["promoted"] and promoted_at is None:
            promoted_at = i + 1
    assert promoted_at == 20 and eng.state.rung == "A2"
    assert eng.state.wilson_lower == pytest.approx(0.839, abs=0.002)  # the stated bound: 20 clean of 20


async def test_engine_errors_are_reported_not_hidden(cluster, host, model, env):
    q, a, root = env
    write_consent(root, "calc-entry-3x")

    def refuse(request):
        return httpx.Response(409, json={"error": {"code": "blocked", "message": "routine is blocked"}})

    eng = EngineClient("http://engine.test", client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(EngineError) as e:
        eng.post_shadow("calc-entry-3x", [{"run_id": "r_x", "matched": True}])
    assert e.value.status == 409 and e.value.code == "blocked"
    r = ShadowRunner("calc-entry-3x", bundles_for(cluster, model, "a"), model=model, engine=eng, audit=a, queue=q,
                     base_urls=cluster.urls, root=root)
    out = await r.run_episode(host, hh(1), worker_for(hh(1), "a"), run_id="r_shadow_9")
    assert out.engine == {"error": "blocked", "status": 409}


# ------------------------------------------------------------------ background run that yields
@pytest.fixture
def sup(tmp_path):
    human = HumanInputSignal()
    s = Supervisor(kill_flag=tmp_path / "KILL", human_input=human)
    yield s, human
    s.close()


def test_background_run_refuses_without_the_right_consent(cluster, model, env, sup):
    q, a, root = env
    s, human = sup
    br = BackgroundRunner("calc-entry-3x", supervisor=s, human_input=human, model=model, base_urls=cluster.urls, audit=a,
                          queue=q, root=root)
    with pytest.raises(ConsentRefused, match="no consent"):
        br.start(hh(1))
    write_consent(root, "calc-entry-3x", mode="shadow")
    with pytest.raises(ConsentRefused, match="does not allow"):
        br.start(hh(1))
    write_consent(root, "calc-entry-3x", mode="approval", rung="A2", revoked=True)
    with pytest.raises(ConsentRefused, match="revoked"):
        br.start(hh(1))


def test_background_run_uses_the_compiled_routine_in_its_own_context_and_stops_before_submit(cluster, model, env, sup):
    q, a, root = env
    s, human = sup
    write_consent(root, "calc-entry-3x", mode="approval", rung="A2")
    br = BackgroundRunner("calc-entry-3x", supervisor=s, human_input=human, model=model, base_urls=cluster.urls, audit=a,
                          queue=q, root=root, bundles=bundles_for(cluster, model))
    h = br.start(hh(1), run_id="r_bg_1")
    assert h.wait(60) and h.state == "done", (h.state, h.reason)
    res = h.result
    assert res["state"] == "done" and res["completion"]["ok"] and res["awaiting_approval"]
    assert cluster.state.submissions == []
    assert [i["kind"] for i in q.list()] == ["irreversible_step"]
    steps = {(e["navigator"], e["tier"]) for e in res["tier_log"]}
    assert {("nav-a", 1), ("nav-b", 1), ("nav-c", 1)} <= steps


def test_human_input_yields_the_background_run_within_one_second_and_it_can_resume(cluster, model, env, sup):
    q, a, root = env
    s, human = sup
    write_consent(root, "calc-entry-3x", mode="approval", rung="A2")
    br = BackgroundRunner("calc-entry-3x", supervisor=s, human_input=human, model=model, base_urls=cluster.urls, audit=a,
                          queue=q, root=root, hold_off_s=0.4)
    h = br.start(hh(1), run_id="r_bg_2")
    deadline = time.time() + 20
    while time.time() < deadline and not any(x["kind"] == "agent_step" for x in a.read(500)):
        time.sleep(0.05)  # wait until the run is really working
    t0 = time.time()
    human.signal()
    assert h.wait(1.0), "the run did not yield within one second"
    assert h.state == "yielded" and time.time() - t0 < 1.0
    assert not br.can_resume()  # the human only just touched the machine
    br.join_after(3)
    assert any(x["kind"] == "yielded" and x["run_id"] == "r_bg_2" for x in a.read(2000))
    assert cluster.state.submissions == []
    time.sleep(0.5)
    assert br.can_resume()
    h2 = br.start(hh(1), run_id="r_bg_3")
    assert h2.wait(60) and h2.state == "done" and h2.result["completion"]["ok"]
