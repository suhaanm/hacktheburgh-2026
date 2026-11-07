"""Agent API on port 7710 (in-process TestClient; sandbox sites on ephemeral ports)."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from understudy_agent import golden
from understudy_agent.audit import AuditLog
from understudy_agent.queue import ApprovalQueue
from understudy_agent.server import create_app
from understudy_agent.supervisor import Supervisor


@pytest.fixture
def api(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    app = create_app(base_urls=cluster.urls, autostart_sandbox=False, supervisor=Supervisor(), queue=queue, audit=audit)
    with TestClient(app) as c:
        c.queue, c.tmp = queue, tmp_path
        yield c


SLOW = {"a": "?layout=v2", "b": "?layout=v2", "c": "?layout=v2"}  # selector breakers: tier 2 everywhere, several seconds


def wait_state(c, run_id, want, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/run/{run_id}").json()
        if r["state"] in want:
            return r
        time.sleep(0.2)
    raise AssertionError(f"run did not reach {want}: {r}")


def test_health(api):
    h = api.get("/health").json()
    assert h["ok"] and h["mock"] is True and h["voice"] is True and h["sandbox"] is True
    assert set(h["supervisor"]) == {"generation", "state"}


def test_unknown_run_is_a_plain_error(api):
    r = api.get("/run/r_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_error"
    assert api.post("/run/r_nope/stop").status_code == 404


def test_run_benefits_end_to_end_status_stream_and_result(api, cluster):
    r = api.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock", "navigators": 3})
    assert r.status_code == 200
    rid = r.json()["run_id"]
    with api.stream("GET", f"/run/{rid}/stream") as s:
        lines = [ln for ln in s.iter_lines() if ln]
    events = [(lines[i][7:], json.loads(lines[i + 1][6:])) for i in range(len(lines) - 1) if lines[i].startswith("event: ")]
    kinds = [k for k, _ in events]
    assert "step" in kinds and "stage" in kinds and kinds[-1] == "end"
    steps = [d for k, d in events if k == "step"]
    assert steps and all(set(d) >= {"navigator", "step", "tier", "action", "ok"} for d in steps)
    st = wait_state(api, rid, {"done", "failed", "paused", "stopped"})
    assert st["state"] == "done", st
    assert st["completion"] == {"ok": True, "missing": []} and st["false_claims"] == 0
    assert {n["site"] for n in st["navigators"]} >= {"a", "b", "c"} and all("tier" in n and "step" in n for n in st["navigators"])
    assert st["awaiting_approval"] and st["queue_id"] and st["note_id"].startswith("CN-")
    res = api.get(f"/run/{rid}/result").json()
    assert res["reconciliation"]["status"] in ("agree", "discrepancy") and res["evidence_dir"].endswith(rid)
    assert cluster.state.submissions == []
    pending = api.queue.list()
    assert [i["id"] for i in pending] == [st["queue_id"]]


def test_stop_wins_within_one_second(api, cluster):
    rid = api.post("/run/benefits", json={"household_id": "hh_0001", "mode": "mock", "switches": SLOW}).json()["run_id"]
    time.sleep(1.5)
    t0 = time.time()
    out = api.post(f"/run/{rid}/stop").json()
    assert out["stopped"] is True and isinstance(out["generation"], int)
    st = wait_state(api, rid, {"stopped", "done", "failed"}, timeout=3)
    assert time.time() - t0 < 1.0 and st["state"] == "stopped", st
    assert cluster.state.submissions == []


def test_kill_stops_blocks_new_runs_and_clears(api, cluster):
    rid = api.post("/run/benefits", json={"household_id": "hh_0001", "mode": "mock", "switches": SLOW}).json()["run_id"]
    time.sleep(1.2)
    assert api.post("/kill").json() == {"killed": True}
    st = wait_state(api, rid, {"stopped", "failed", "done"}, timeout=3)
    assert st["state"] == "stopped"
    assert (api.tmp / "data" / "KILL").exists()
    r = api.post("/run/benefits", json={"mode": "mock"})
    assert r.status_code == 423 and "kill" in r.json()["error"]["message"]
    assert api.get("/health").json()["supervisor"]["state"] == "killed"
    assert api.post("/kill/clear").json() == {"killed": False}
    assert api.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"}).status_code == 200


def test_a_newer_run_replaces_the_running_one(api):
    first = api.post("/run/benefits", json={"household_id": "hh_0001", "mode": "mock", "switches": SLOW}).json()["run_id"]
    time.sleep(0.8)
    second = api.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"}).json()["run_id"]
    assert wait_state(api, first, {"stopped", "failed", "done"}, timeout=5)["state"] == "stopped"
    assert wait_state(api, second, {"done", "failed", "paused"})["state"] == "done"


def test_injected_switch_pauses_the_run_via_the_api(api, cluster):
    rid = api.post("/run/benefits", json={"household_id": "hh_0001", "mode": "mock",
                                          "switches": {"a": "?variant=injected", "b": "?variant=injected",
                                                       "c": "?variant=injected"}}).json()["run_id"]
    st = wait_state(api, rid, {"paused", "done", "failed"})
    assert st["state"] == "paused" and not st["awaiting_approval"]
    assert cluster.state.exfil_hits == [] and cluster.state.submissions == []
    assert any(i["kind"] == "injection_pause" for i in api.queue.list("all"))


def test_cached_run_needs_a_golden_run_then_replays_offline(api, cluster):
    r = api.post("/run/benefits", json={"mode": "cached"})
    assert r.status_code == 409
    rid = api.post("/run/benefits", json={"household_id": "hh_0004", "mode": "mock"}).json()["run_id"]
    st = wait_state(api, rid, {"done", "failed", "paused"})
    assert st["state"] == "done"
    res = api.get(f"/run/{rid}/result").json()
    item = api.queue.get(res["queue_id"])
    run = api.app.state.runs[rid].run
    golden.save_golden(res, run.events, item, rid)
    assert golden.has_golden()
    before = len(api.queue.list("all"))
    cid = api.post("/run/benefits", json={"mode": "cached"}).json()["run_id"]
    cst = wait_state(api, cid, {"done", "failed", "stopped"}, timeout=20)
    assert cst["state"] == "done" and cst["cached"] is True and cst["awaiting_approval"]
    assert len(api.queue.list("all")) == before + 1  # a fresh approval item for the replay
    assert (api.tmp / "data" / "runs" / cid / "s4.png").exists()
    assert api.get(f"/run/{cid}/result").json()["run_id"] == cid


def test_finalize_requires_the_approval_first(api, cluster):
    from understudy_agent.security.settings import Origin

    rid = api.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"}).json()["run_id"]
    st = wait_state(api, rid, {"done", "failed", "paused"})
    assert api.post(f"/run/{rid}/finalize").json()["submitted"] is False and cluster.state.submissions == []
    api.queue.approve(st["queue_id"], origin=Origin.HUMAN_UI)
    assert api.post(f"/run/{rid}/finalize").json()["submitted"] is True
    assert api.post(f"/run/{rid}/finalize").json()["submitted"] is False
    assert len(cluster.state.submissions) == 1


def _consent(tmp_path, mode, rung="A2", revoked=False):
    d = tmp_path / "data" / "routines" / "calc-entry-3x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "consent.json").write_text(json.dumps({"mode": mode, "rung": rung, "irreversible_unattended": [], "revoked": revoked}))


def test_routine_run_needs_consent_and_a_compiled_bundle_then_runs_in_the_background(api, cluster):
    from understudy_agent.compile import compile_draft, save_bundle
    from understudy_agent.sandbox_sites.recordings import synthetic_recording
    from understudy_agent.models.mock_provider import MockProvider
    from understudy_agent.tiers.heuristic import HeuristicModelPort

    r = api.post("/routines/calc-entry-3x/run", json={"mode": "background"})
    assert r.status_code == 409 and "no consent" in r.json()["error"]["message"]
    _consent(api.tmp, "approval")
    assert api.post("/routines/calc-entry-3x/run", json={"mode": "background"}).status_code == 404  # nothing compiled yet
    model = HeuristicModelPort(MockProvider("benefits_clean"))
    for site, name in (("a", "a"), ("b", "b"), ("c", "c")):
        b, rep = compile_draft(synthetic_recording(site, base_urls=cluster.urls), base_urls=cluster.urls, model=model)
        save_bundle(b, name=name, root=api.tmp / "data")
    rid = api.post("/routines/calc-entry-3x/run", json={"mode": "background", "household_id": "hh_0002"}).json()["run_id"]
    st = wait_state(api, rid, {"done", "failed", "paused", "stopped"})
    assert st["state"] == "done" and st["awaiting_approval"] and cluster.state.submissions == []
    _consent(api.tmp, "approval", revoked=True)
    assert api.post("/routines/calc-entry-3x/run", json={"mode": "background"}).status_code == 409


def test_human_input_yields_a_background_routine_run_through_the_api(api, cluster):
    from understudy_agent.compile import compile_draft, save_bundle
    from understudy_agent.sandbox_sites.recordings import synthetic_recording
    from understudy_agent.models.mock_provider import MockProvider
    from understudy_agent.tiers.heuristic import HeuristicModelPort

    _consent(api.tmp, "approval")
    model = HeuristicModelPort(MockProvider("benefits_clean"))
    for site in "abc":
        b, _ = compile_draft(synthetic_recording(site, base_urls=cluster.urls), base_urls=cluster.urls, model=model)
        save_bundle(b, name=site, root=api.tmp / "data")
    rid = api.post("/routines/calc-entry-3x/run", json={"mode": "background", "household_id": "hh_0001"}).json()["run_id"]
    time.sleep(0.9)
    t0 = time.time()
    assert api.post("/human-input").json() == {"signalled": True}
    st = wait_state(api, rid, {"stopped", "done", "failed"}, timeout=3)
    assert time.time() - t0 < 1.5 and st["state"] == "stopped", st
    rep = api.get("/offhours/report").json()
    assert set(rep) >= {"ran", "queued", "failed", "yielded", "refused"}


# ------------------------------------------------------------------ the shared sandbox lock (runs on the SHARED sites)
@pytest.fixture
def api_shared(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    # ephemeral sites standing in for 7801-7803, but the service treats them as the SHARED ones
    app = create_app(base_urls=cluster.urls, autostart_sandbox=False, supervisor=Supervisor(), queue=queue, audit=audit,
                     shared_sites=True)
    with TestClient(app) as c:
        c.queue, c.tmp = queue, tmp_path
        yield c


def test_a_run_on_shared_sites_is_refused_while_someone_else_holds_the_lock(api_shared, cluster):
    from understudy_agent.sandbox_sites.lock import read_owner, sandbox_lock

    with sandbox_lock("study-sim", timeout_s=1):
        r = api_shared.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"})
        assert r.status_code == 409
        err = r.json()["error"]
        assert err["code"] == "sandbox_busy" and "'study-sim'" in err["message"] and "pid" in err["message"]
        assert "Try again when it finishes" in err["message"]
        assert api_shared.post("/routines/calc-entry-3x/run", json={"mode": "background"}).status_code in (404, 409)
    assert cluster.state.calculations == [] and api_shared.app.state.runs == {}   # nothing started, nothing registered
    assert read_owner() is None


def test_the_service_holds_the_lock_for_the_run_and_releases_it_when_done(api_shared, cluster):
    from understudy_agent.sandbox_sites.lock import read_owner

    rid = api_shared.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock", "switches": SLOW}).json()["run_id"]
    time.sleep(0.8)
    assert read_owner()["owner"] == f"agent-service:{rid}"          # held while the browser is acting
    wait_state(api_shared, rid, {"done", "failed", "paused"})
    deadline = time.time() + 5
    while time.time() < deadline and read_owner() is not None:
        time.sleep(0.05)
    assert read_owner() is None                                      # released when the run ended


def test_stop_releases_the_lock_and_a_newer_run_replaces_an_older_one(api_shared, cluster):
    from understudy_agent.sandbox_sites.lock import read_owner

    first = api_shared.post("/run/benefits", json={"household_id": "hh_0001", "mode": "mock", "switches": SLOW}).json()["run_id"]
    time.sleep(0.8)
    second = api_shared.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"})
    assert second.status_code == 200                                 # the service's own older run is replaced, not a 409
    sid = second.json()["run_id"]
    assert wait_state(api_shared, first, {"stopped", "failed", "done"}, timeout=5)["state"] == "stopped"
    assert wait_state(api_shared, sid, {"done", "failed", "paused"})["state"] == "done"
    api_shared.post("/run/benefits", json={"household_id": "hh_0003", "mode": "mock", "switches": SLOW})
    time.sleep(0.8)
    t0 = time.time()
    api_shared.post("/kill/clear")
    api_shared.post(f"/run/{sid}/stop")
    deadline = time.time() + 5
    while time.time() < deadline and read_owner() is not None:
        time.sleep(0.05)
    assert read_owner() is None and time.time() - t0 < 5


def test_finalize_and_routine_runs_take_the_lock_too(api_shared, cluster):
    from understudy_agent.sandbox_sites.lock import read_owner, sandbox_lock
    from understudy_agent.security.settings import Origin

    rid = api_shared.post("/run/benefits", json={"household_id": "hh_0002", "mode": "mock"}).json()["run_id"]
    st = wait_state(api_shared, rid, {"done", "failed", "paused"})
    api_shared.queue.approve(st["queue_id"], origin=Origin.HUMAN_UI)
    with sandbox_lock("study-sim", timeout_s=1):
        busy = api_shared.post(f"/run/{rid}/finalize")
        assert busy.status_code == 409 and busy.json()["error"]["code"] == "sandbox_busy"
        assert cluster.state.submissions == []
    assert api_shared.post(f"/run/{rid}/finalize").json()["submitted"] is True
    assert read_owner() is None


def test_agents_extension_is_off_by_default_and_never_breaks_the_server(cluster, tmp_path, monkeypatch):
    import sys
    import types

    from fastapi import APIRouter

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("UNDERSTUDY_X_AGENTS", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)

    def app_():
        return create_app(base_urls=cluster.urls, autostart_sandbox=False, supervisor=Supervisor(), shared_sites=False)

    with TestClient(app_()) as c:                                   # off by default
        assert c.get("/health").json()["extensions"] == {"agents": False}
        assert c.get("/agents/runs").status_code == 404
        assert "disabled" in c.app.state.extension_status["agents"]
    monkeypatch.setenv("UNDERSTUDY_X_AGENTS", "1")
    monkeypatch.setitem(sys.modules, "understudy_agent.runtime.routes", None)   # None makes the import raise ImportError
    with TestClient(app_()) as c:                                   # asked for, but the module cannot be imported
        h = c.get("/health").json()
        assert h["ok"] and h["extensions"] == {"agents": False}
        status = c.app.state.extension_status["agents"]
        assert status.startswith("not loaded:")
    # a router that does import is included
    pkg = types.ModuleType("understudy_agent.runtime")
    pkg.__path__ = []  # type: ignore[attr-defined]
    mod = types.ModuleType("understudy_agent.runtime.routes")
    r = APIRouter()
    r.add_api_route("/agents/runs", lambda: {"runs": []}, methods=["GET"])
    mod.router = r  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "understudy_agent.runtime", pkg)
    monkeypatch.setitem(sys.modules, "understudy_agent.runtime.routes", mod)
    monkeypatch.delenv("UNDERSTUDY_X_AGENTS")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    with TestClient(app_()) as c:
        assert c.get("/health").json()["extensions"] == {"agents": True}
        assert c.get("/agents/runs").json() == {"runs": []}
        assert c.app.state.extension_status["agents"] == "enabled"
