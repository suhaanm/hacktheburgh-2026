"""routes_localmodel: status shape, digest guard, items_ref safety. A tiny app includes the router (api/app.py is another track's)."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_localmodel
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.localmodel import config


@pytest.fixture()
def client():
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_localmodel.router)
    return TestClient(app)


def put_items(name: str, items) -> None:
    d = config.data_dir() / "localmodel" / "items"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(items))


def test_status_in_rules_mode_has_the_contract_shape(client):
    r = client.get("/localmodel/status")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["origin"] == "real" and "note" in body["meta"]
    d = body["data"]
    assert {"enabled", "running", "model", "endpoint", "mode"} <= set(d)
    assert d["mode"] == "rules" and d["running"] is False and d["enabled"] is False
    assert set(d["model"]) == {"file", "size_bytes", "sha_ok"} and d["reason"] == "mock_mode"
    assert d["endpoint"].startswith("http://127.0.0.1:") and d["bind"] == "127.0.0.1"
    assert "tokens_per_s" not in d


def test_status_with_the_stub_running_reports_tokens_per_second(client, stub):
    from understudy_engine.localmodel import server

    assert server.get_server().start()
    d = client.get("/localmodel/status").json()["data"]
    assert d["running"] is True and d["mode"] == "model" and d["enabled"] is True
    assert d["tokens_per_s"] == 25.0 and d["model"]["size_bytes"] == stub.model_path.stat().st_size


def test_status_never_starts_a_server(client, stub, monkeypatch):
    from understudy_engine.localmodel import server

    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    d = client.get("/localmodel/status").json()["data"]
    assert d["running"] is False and d["mode"] == "model"                 # usable, but not started by a status read


def test_digest_route_needs_the_worker_actor(client):
    put_items("c.json", ["Fix x"])
    r = client.post("/localmodel/digest", json={"task": "commit_digest", "items_ref": "c.json"}, headers={"x-understudy-actor": "model"})
    assert r.status_code == 403
    r = client.post("/localmodel/digest", json={"task": "commit_digest", "items_ref": "c.json"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_digest_route_returns_digests_only(client):
    put_items("c.json", [{"message": "Fix the crash for Zorblax Holdings", "files": ["a.py"]}, "wip"])
    r = client.post("/localmodel/digest", json={"task": "commit_digest", "items_ref": "c.json"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["n"] == 2 and data["source"] == "rules" and len(data["digests"]) == 2
    assert "zorblax" not in r.text.lower() and "crash" not in r.text.lower()


@pytest.mark.parametrize("ref", ["../secret.json", "/etc/passwd", ".hidden", "a/b.json", ""])
def test_items_ref_cannot_escape_the_items_directory(client, ref):
    r = client.post("/localmodel/digest", json={"task": "event_digest", "items_ref": ref})
    assert r.status_code in (404, 422)


def test_missing_items_file_is_404_and_extra_fields_are_refused(client):
    assert client.post("/localmodel/digest", json={"task": "event_digest", "items_ref": "nope.json"}).status_code == 404
    assert client.post("/localmodel/digest", json={"task": "event_digest", "items_ref": "a.json", "items": ["raw"]}).status_code == 422


def test_engine_app_includes_the_router_only_when_the_flag_is_on(tmp_path, monkeypatch):
    from understudy_engine.api.app import create_app

    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    off = TestClient(create_app(tmp_path, warm=False))
    assert off.get("/localmodel/status").status_code == 404
    monkeypatch.setenv("UNDERSTUDY_X_LOCALMODEL", "1")
    on = TestClient(create_app(tmp_path, warm=False))
    r = on.get("/localmodel/status")
    assert r.status_code == 200 and r.json()["data"]["mode"] == "rules"          # mock mode: never starts a server
