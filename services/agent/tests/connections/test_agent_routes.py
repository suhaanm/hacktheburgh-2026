"""The agent's connection routes: the engine asks it to start or stop what the worker clicked, and nothing can ask it to call a tool."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from understudy_agent.connections import routes as R
from understudy_agent.connections.service import default_service
from understudy_engine.connections import registry, state


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CONNECTIONS", "1")
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app)


def test_there_is_no_route_that_calls_a_tool():
    paths = {(r.path, tuple(sorted(r.methods or ()))) for r in R.router.routes}
    assert paths == {("/connections/{conn_id}/start", ("POST",)), ("/connections/{conn_id}/stop", ("POST",)), ("/connections/{conn_id}/status", ("GET",))}


def test_start_refuses_what_the_worker_never_switched_on(client):
    r = client.post("/connections/github/start")
    assert r.status_code == 200 and r.json() == {"ok": False, "code": "not_connected", "tools": 0, "counts": {}}
    assert client.get("/connections/github/status").json() == {"id": "github", "running": False, "tools": 0}
    assert client.post("/connections/evil_server/start").json()["code"] == "unknown_connection"


def test_start_runs_a_consented_connection_and_returns_counts_only_then_stop_ends_it(client):
    state.connect(registry.get("github"), mode="example", confirm=True)
    r = client.post("/connections/github/start").json()
    assert r["ok"] is True and r["tools"] >= 14 and set(r["counts"]) >= {"read", "write", "send", "destructive", "execute", "refused"}
    assert not any(isinstance(v, str) for v in r["counts"].values()), "counts, never names or descriptions"
    assert client.get("/connections/github/status").json() == {"id": "github", "running": True, "tools": r["tools"]}
    assert client.post("/connections/github/stop").json() == {"stopped": True, "id": "github"}
    assert client.get("/connections/github/status").json()["running"] is False


def test_a_bad_id_is_refused_and_the_layer_flag_turns_the_routes_off(client, monkeypatch):
    assert client.post("/connections/Bad Id/start").status_code in (400, 404)
    assert client.post("/connections/..%2Fetc/start").status_code in (400, 404)
    monkeypatch.delenv("UNDERSTUDY_X_CONNECTIONS", raising=False)
    off = client.post("/connections/github/start")
    assert off.status_code == 404 and off.json()["error"]["code"] == "extension_off"
    assert not default_service().runner.is_running("github")


def test_the_agent_app_includes_the_router_and_boots_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")
    from understudy_agent.server import create_app

    app = create_app()
    assert app.state.extensions.get("connections") is True
    paths = {getattr(x, "path", "") for r in app.routes for x in (getattr(getattr(r, "original_router", None), "routes", None) or [r])}
    assert "/connections/{conn_id}/start" in paths
    assert not default_service().runner.is_running("github"), "creating the app starts no connection"
