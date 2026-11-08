"""The routes: the list, one click to connect, one click to revoke, the write guard, and that a token never comes back."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.connections import routes as R
from understudy_engine.connections import secrets as sec
from understudy_engine.connections import state
from understudy_engine.connections.paths import state_path

TOKEN = "xoxp-9999-8888-NEVERECHOTHIS"


@pytest.fixture()
def calls():
    return []


@pytest.fixture()
def client(monkeypatch, calls):
    monkeypatch.setenv("UNDERSTUDY_X_CONNECTIONS", "1")

    def fake_agent(path, body=None, timeout=25.0):                 # the agent service is not running in these tests; a stub stands in for it
        calls.append(path)
        if path.endswith("/start"):
            return {"ok": True, "tools": 14, "counts": {"read": 11, "write": 3}}
        return {"stopped": True}

    monkeypatch.setattr(R, "_agent", fake_agent)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    return TestClient(app)


def test_the_router_is_off_without_the_flag(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_CONNECTIONS", raising=False)
    app = FastAPI()
    app.include_router(R.router)
    r = TestClient(app).get("/connections")
    assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off" and R.enabled() is False


def test_the_layer_is_registered_and_on_by_default_in_the_running_product():
    from understudy_engine.api.flags import DEFAULT_ON, EXTENSIONS, apply_default_flags

    assert EXTENSIONS["connections"] == "connections.routes" and "UNDERSTUDY_X_CONNECTIONS" in DEFAULT_ON
    env: dict[str, str] = {}
    apply_default_flags(env)
    assert env["UNDERSTUDY_X_CONNECTIONS"] == "1"
    env2 = {"UNDERSTUDY_X_CONNECTIONS": "0"}
    apply_default_flags(env2)
    assert env2["UNDERSTUDY_X_CONNECTIONS"] == "0"


def test_the_list_for_a_role_is_that_packs_set_and_every_chip_is_off(client):
    for role, n in (("programmer", 6), ("data-analyst", 7), ("benefits-processor", 3)):
        r = client.get(f"/connections?role={role}").json()
        assert len(r["data"]) == n and all(c["state"] == "off" and c["mode"] is None for c in r["data"])
    assert len(client.get("/connections").json()["data"]) == 15
    one = client.get("/connections?role=programmer").json()["data"][0]
    assert {"id", "app", "reads", "caution", "modes", "tools", "usage", "state"} <= set(one)
    assert one["modes"]["example"]["example"] is True and "with your token" in one["modes"]["real"]["summary"]
    assert not state_path().exists(), "listing connects nothing and writes nothing"


def test_connecting_needs_the_confirm_and_a_mock_listing_never_auto_connects(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    client.get("/connections?role=data-analyst")
    assert all(c["state"] == "off" for c in client.get("/connections").json()["data"])
    r = client.post("/connections/github/connect", json={"mode": "example"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "consent_required"
    assert client.get("/connections/github").json()["data"]["state"] == "off"


def test_connect_example_then_the_agent_is_asked_to_start_it_and_counts_come_back(client, calls):
    r = client.post("/connections/github/connect", json={"mode": "example", "confirm": True})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["state"] == "connected" and d["mode"] == "example" and d["example"] is True and d["agent"] == "online"
    assert d["probe"]["tools"] == 14 and calls == ["/connections/github/start"]
    assert r.json()["meta"]["origin"] == "synthetic"
    assert d["real_facts"]["publisher"] == "GitHub" and d["real_facts"]["version"] == "2.1.0"


def test_connect_real_stores_the_token_and_never_returns_it(client):
    body = {"mode": "real", "confirm": True, "secrets": {"SLACK_MCP_XOXP_TOKEN": TOKEN}}
    r = client.post("/connections/slack/connect", json=body)
    assert r.status_code == 200 and TOKEN not in r.text and r.json()["data"]["mode"] == "real"
    assert TOKEN not in client.get("/connections/slack").text and TOKEN not in client.get("/connections").text
    assert TOKEN not in state_path().read_text() and sec.backend().get("slack", "SLACK_MCP_XOXP_TOKEN") == TOKEN
    assert r.json()["meta"]["origin"] == "real"


def test_a_refused_connect_does_not_echo_the_token(client):
    r = client.post("/connections/slack/connect", json={"mode": "real", "confirm": True, "secrets": {"SLACK_MCP_XOXP_TOKEN": 'bad "token'}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_secret" and 'bad "token' not in r.text
    r = client.post("/connections/slack/connect", json={"mode": "real", "confirm": True, "secrets": {"WRONG_NAME": TOKEN}})
    assert r.status_code == 400 and TOKEN not in r.text


def test_when_the_agent_is_not_running_the_click_is_still_saved(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CONNECTIONS", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    c = TestClient(app)                                              # the real _agent: UNDERSTUDY_AGENT_URL points at a closed port
    d = c.post("/connections/filesystem/connect", json={"mode": "example", "confirm": True}).json()["data"]
    assert d["agent"] == "offline" and d["state"] == "connected" and d["probe"] is None


def test_revoke_is_one_call_forgets_the_token_and_asks_the_agent_to_stop(client, calls):
    client.post("/connections/slack/connect", json={"mode": "real", "confirm": True, "secrets": {"SLACK_MCP_XOXP_TOKEN": TOKEN}})
    r = client.post("/connections/slack/revoke")
    d = r.json()["data"]
    assert r.status_code == 200 and d["revoked"] is True and d["secrets_forgotten"] == 1 and d["process_stopped"] is True
    assert d["connection"]["state"] == "off" and calls[-1] == "/connections/slack/stop"
    assert sec.backend().get("slack", "SLACK_MCP_XOXP_TOKEN") is None


def test_reconfirm_after_a_changed_version(client, monkeypatch):
    client.post("/connections/slack/connect", json={"mode": "real", "confirm": True, "secrets": {"SLACK_MCP_XOXP_TOKEN": TOKEN}})
    rec = state.record("slack")
    rec["pinned_hash"] = "sha256:000000000000000000000000"
    doc = {"version": 1, "connections": {"slack": rec}}
    state_path().write_text(json.dumps(doc))
    assert client.get("/connections/slack").json()["data"]["state"] == "needs_reconfirm"
    assert client.post("/connections/slack/reconfirm", json={}).status_code == 400
    r = client.post("/connections/slack/reconfirm", json={"confirm": True})
    assert r.status_code == 200 and r.json()["data"]["state"] == "connected"


def test_writes_only_from_the_worker_on_this_machine_from_the_app(client):
    assert client.post("/connections/github/connect", json={"mode": "example", "confirm": True}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/connections/github/connect", json={"mode": "example", "confirm": True}, headers={"x-understudy-actor": "agent"}).status_code == 403
    assert client.post("/connections/github/revoke", headers={"x-understudy-actor": "agent"}).status_code == 403
    assert not state_path().exists()


def test_an_unknown_or_uncurated_connection_is_refused_there_is_no_way_to_add_one(client):
    for method, path in (("get", "/connections/evil_server"), ("post", "/connections/evil_server/connect"), ("get", "/connections/evil_server/reads")):
        r = getattr(client, method)(path, **({"json": {"mode": "real", "confirm": True}} if method == "post" else {}))
        assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_connection"
    paths = {r.path for r in R.router.routes}
    assert not any("add" in p or "custom" in p or "register" in p for p in paths)


def test_the_routine_optin_route_and_the_reads_route(client):
    client.post("/connections/github/connect", json={"mode": "example", "confirm": True})
    r = client.post("/connections/github/routines", json={"routine_id": "weekly_digest", "allowed": True})
    assert r.status_code == 200 and r.json()["data"]["routines"] == ["weekly_digest"]
    assert client.post("/connections/github/routines", json={"routine_id": "Bad Id", "allowed": True}).status_code == 400
    reads = client.get("/connections/github/reads").json()["data"]
    assert reads["calls"] == 0 and "outside the frame egress guard" in reads["note"]


def test_an_oversize_or_malformed_body_is_refused(client):
    assert client.post("/connections/github/connect", content=b"{not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/connections/github/connect", content=b"x" * 30_000).status_code == 413
