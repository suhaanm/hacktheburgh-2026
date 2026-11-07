"""HTTP routes (docs/API_CONTRACT.md Extensions API, BGA): flag-gated, worker-only writes, the contract's shapes."""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_agent.runtime import routes
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.security.killflag import clear_kill, set_kill

from .helpers import register_test_kinds, wait_for

pytestmark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")
W = {"X-Understudy-Actor": "worker"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_AGENTS", "1")
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_everything_is_off_without_the_flag(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_AGENTS", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    for r in (c.get("/agents/runs"), c.get("/agents/kinds"), c.post("/agents/spawn", json={"kind": "data.profile"}, headers=W)):
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_disabled"
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert c.get("/agents/runs").status_code == 200


def test_spawn_list_get_follow_the_contract(client):
    assert client.get("/agents/runs").json() == []
    r = client.post("/agents/spawn", json={"kind": "data.profile", "params": {}, "mode": "foreground"}, headers=W)
    assert r.status_code == 200
    rid = r.json()["run_id"]
    assert wait_for(lambda: client.get(f"/agents/runs/{rid}").json()["state"] in ("done", "failed", "partial"), 60)
    one = client.get(f"/agents/runs/{rid}").json()
    assert one["state"] == "done" and one["kind"] == "data.profile" and one["mode"] == "foreground"
    assert set(one["parent"]) == {"id", "role", "state", "budget", "spent"}
    child = one["children"][0]
    assert {"id", "role", "state", "budget", "spent", "lease", "result_ref"} <= set(child)
    assert {"ttl_s", "remaining_s", "steps_left", "tools", "revoked"} <= set(child["lease"])
    assert one["artifacts"] and {"name", "kind", "path_ref"} <= set(one["artifacts"][0])
    assert one["result"]["all_verified"] is True
    assert all(s["check"] in ("verified", "uncertain", "failed") for s in one["result"]["children"]["c1"]["steps"])
    lst = client.get("/agents/runs").json()
    assert [x["run_id"] for x in lst] == [rid] and "artifacts" not in lst[0]
    art = client.get(f"/agents/runs/{rid}/artifacts/c1/profile.json")
    assert art.status_code == 200 and art.json()["n_rows"] == 240
    assert client.get(f"/agents/runs/{rid}/artifacts/c1/..%2Fx").status_code == 404
    assert client.get(f"/agents/runs/{rid}/artifacts/c9/profile.json").status_code == 404


def test_writes_need_the_worker_actor(client):
    body = {"kind": "data.profile"}
    for actor in ("agent", "page", "model", "tool"):
        r = client.post("/agents/spawn", json=body, headers={"X-Understudy-Actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert client.post("/agents/spawn", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/stop", headers={"X-Understudy-Actor": "page"}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/children/c1/revoke", headers={"X-Understudy-Actor": "model"}).status_code == 403


def test_bad_requests_get_plain_errors(client):
    assert client.post("/agents/spawn", json={"kind": "nope"}, headers=W).json()["error"]["code"] == "unknown_kind"
    assert client.post("/agents/spawn", json={"kind": "data.profile", "mode": "x"}, headers=W).status_code == 422
    assert client.post("/agents/spawn", json={"kind": "data.profile", "params": 5}, headers=W).status_code == 422
    assert client.post("/agents/spawn", content=b"not json", headers=W).status_code == 422
    assert client.post("/agents/spawn", json={"kind": "data.profile", "params": {"csv_path": "/nonexistent.csv"}},
                       headers=W).status_code in (200, 422)
    assert client.get("/agents/runs/r_nothere00").status_code == 404
    assert client.post("/agents/runs/r_nothere00/stop", headers=W).status_code == 404
    assert client.get("/agents/runs/..%2F..%2Fetc").status_code in (404, 422)


def test_spawn_refuses_while_the_kill_switch_is_set(client):
    set_kill("test")
    try:
        r = client.post("/agents/spawn", json={"kind": "data.profile"}, headers=W)
    finally:
        clear_kill()
    assert r.status_code == 423


def test_stop_and_revoke_endpoints_work_on_a_running_child(client):
    register_test_kinds()
    rid = client.post("/agents/spawn", json={"kind": "test.nap", "params": {"template": "nap_long"}}, headers=W).json()["run_id"]
    assert wait_for(lambda: (d := client.get(f"/agents/runs/{rid}").json()) and d["children"]
                    and d["children"][0]["spent"]["steps"] >= 1, 20)
    time.sleep(0.4)
    assert client.post(f"/agents/runs/{rid}/children/c9/revoke", headers=W).status_code == 404
    t0 = time.monotonic()
    assert client.post(f"/agents/runs/{rid}/children/c1/revoke", headers=W).json() == {"revoked": True, "child_id": "c1"}
    assert wait_for(lambda: client.get(f"/agents/runs/{rid}").json()["state"] not in ("running", "planning"), 2)
    assert time.monotonic() - t0 < 2
    child = client.get(f"/agents/runs/{rid}").json()["children"][0]
    assert child["state"] == "revoked" and child["lease"]["revoked"] is True
    rid2 = client.post("/agents/spawn", json={"kind": "test.nap", "params": {"template": "nap_long"}}, headers=W).json()["run_id"]
    assert wait_for(lambda: (d := client.get(f"/agents/runs/{rid2}").json()) and d["children"] and d["children"][0]["spent"]["steps"] >= 1, 20)
    t0 = time.monotonic()
    out = client.post(f"/agents/runs/{rid2}/stop", headers=W).json()
    assert out["stopped"] is True
    assert wait_for(lambda: client.get(f"/agents/runs/{rid2}").json()["state"] == "stopped", 1.0)
    assert time.monotonic() - t0 < 1.0
