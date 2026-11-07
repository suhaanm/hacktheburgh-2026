from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.api.errors import install_error_handlers
from understudy_engine.attention import routes as R
from understudy_engine.attention.service import AttentionService
from understudy_engine.attention.store import AttentionStore

from .conftest import P, T0

CALM = {"quiet_s": 60, "local_hour": 10, "typing_burst": "0"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_ATTENTION", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.attention = AttentionService(AttentionStore(), clock=lambda: T0)
    return TestClient(app)


def test_flag_off_is_404_extension_off_everywhere(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_ATTENTION", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    c = TestClient(app)
    assert not R.enabled()
    for method, url, kw in (("post", "/attention/events", {"json": {"type": "run_finished", "subject": "r1"}}), ("get", f"/attention/next?person={P}", {}),
                            ("get", f"/attention/digest?person={P}", {}), ("post", "/attention/feedback", {"json": {"item_id": "x", "event": "shown"}}),
                            ("get", "/attention/why?item=x", {}), ("get", f"/attention/settings?person={P}", {}), ("post", "/attention/settings", {"json": {}}),
                            ("get", f"/attention/stats?person={P}", {}), ("get", f"/attention/export?person={P}", {}), ("delete", f"/attention?person={P}", {})):
        r = getattr(c, method)(url, **kw)
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off", (url, r.text)


def test_master_flag_also_turns_it_on(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_ATTENTION", raising=False)
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert R.enabled()


def test_the_engines_flag_table_would_wire_it_with_one_line():
    import importlib

    mod = importlib.import_module("understudy_engine.attention.routes")
    assert callable(mod.enabled) and mod.router is not None and mod.FLAG == "UNDERSTUDY_X_ATTENTION"


def test_events_next_feedback_why_digest_round_trip(client):
    r = client.post("/attention/events", params={"person": P}, json={"type": "approval_blocking", "subject": "q_12", "count": 2, "t": T0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coalesced"] is False and body["decision"]["badge"] is True and body["show"] is False
    nx = client.get("/attention/next", params={"person": P, "t": T0, "now": T0, **CALM})
    assert nx.status_code == 200
    data = nx.json()["data"]
    assert data["item"]["type"] == "approval_blocking" and data["item"]["title"] == "An approval is waiting" and "2 approvals" in data["item"]["body"]
    assert data["badges"]["needs_you"] == 2 and data["poll_after_s"] == 2.0
    iid = data["item"]["id"]
    again = client.get("/attention/next", params={"person": P, "now": T0 + 1, **CALM}).json()["data"]
    assert again["item"] is None and again["active"]["id"] == iid
    fb = client.post("/attention/feedback", params={"person": P}, json={"item_id": iid, "event": "followed", "seconds": 3})
    assert fb.status_code == 200 and fb.json()["label"] == "followed"
    why = client.get("/attention/why", params={"item": iid}).json()["data"]
    assert why["state"] == "acted" and why["reason_text"]
    dg = client.get("/attention/digest", params={"person": P, "kind": "now"}).json()["data"]
    assert dg["needs_you"] >= 1 and dg["lines"]
    st = client.get("/attention/stats", params={"person": P}).json()["data"]
    assert st["budget"]["per_day"] == 10


def test_a_cue_admission_answers_show_synchronously(client):
    r = client.post("/attention/events", params={"person": P}, json={"type": "cue_ask", "subject": "e_1", "expires_in_s": 12, "t": T0,
                                                                    "state": {"quiet_s": 5, "local_hour": 10}})
    assert r.status_code == 200 and r.json()["show"] is True
    r2 = client.post("/attention/events", params={"person": P}, json={"type": "cue_cue", "subject": "e_2", "t": T0 + 1, "state": {"quiet_s": 5, "local_hour": 10}})
    assert r2.json()["show"] is False and r2.json()["decision"]["reason_code"] == "dropped_lock"
    busy = client.post("/attention/events", params={"person": "p_other"}, json={"type": "cue_cue", "subject": "e_3", "t": T0, "state": {"typing_burst": True, "quiet_s": 0.2}})
    assert busy.json()["show"] is False and busy.json()["decision"]["reason_code"] == "dropped_flow"


def test_a_client_clock_is_ignored_outside_mock_mode(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    r = client.post("/attention/events", params={"person": P}, json={"type": "run_finished", "subject": "r1", "t": 5.0})
    assert r.status_code == 200
    ps = client.app.state.attention.store.person(P)
    assert next(iter(ps.items.values())).first_t == T0                                     # the service clock, not the client's t


def test_refusals_are_plain_json_with_no_free_text_accepted(client):
    r = client.post("/attention/events", params={"person": P}, json={"type": "run_finished", "subject": "r1", "title": "My private run"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_event" and "My private run" not in r.text
    assert client.post("/attention/events", params={"person": P}, json={"type": "nope", "subject": "r1"}).status_code == 422
    assert client.post("/attention/events", params={"person": P}, json={"type": "cue_cue", "subject": "e1", "state": {"title": "x"}}).status_code == 422
    assert client.get("/attention/digest", params={"person": P, "kind": "yearly"}).status_code == 422
    assert client.get("/attention/why", params={"item": "i_none"}).status_code == 404
    assert client.get("/attention/next", params={"person": P, "now": T0}).status_code == 200      # no state at all: an unknown worker, held


def test_unknown_worker_state_holds_everything_but_safety(client):
    client.post("/attention/events", params={"person": P}, json={"type": "approval_blocking", "subject": "q1", "t": T0})
    client.post("/attention/events", params={"person": P}, json={"type": "injection_pause", "subject": "r1", "t": T0})
    d = client.get("/attention/next", params={"person": P, "now": T0}).json()["data"]
    assert d["item"]["type"] == "injection_pause" and d["item"]["preempt"] is True
    d2 = client.get("/attention/next", params={"person": P, "now": T0 + 21}).json()["data"]
    assert d2["item"] is None and d2["badges"]["needs_you"] == 2


@pytest.mark.parametrize("actor", ["page", "model", "tool", "extension", "evil"])
def test_other_actors_cannot_write_and_the_refusal_is_audited_without_content(client, actor, tmp_path):
    h = {"X-Understudy-Actor": actor}
    for method, url, body in (("post", "/attention/events", {"type": "run_finished", "subject": "r1"}), ("post", "/attention/feedback", {"item_id": "x", "event": "shown"}),
                              ("post", "/attention/settings", {"budget_per_day": 3}), ("delete", f"/attention?person={P}", None)):
        r = getattr(client, method)(url, params={"person": P}, headers=h, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused", (url, actor)
    audit = (R.P.data_dir() / "audit.jsonl").read_text()
    assert "attention_write_refused" in audit and "run_finished" not in audit


def test_producers_may_post_events_but_only_the_worker_may_react_or_change_settings(client):
    h = {"X-Understudy-Actor": "agent"}
    assert client.post("/attention/events", params={"person": P}, headers=h, json={"type": "run_finished", "subject": "r1", "outcome": "done"}).status_code == 200
    assert client.post("/attention/feedback", params={"person": P}, headers=h, json={"item_id": "x", "event": "shown"}).status_code == 403
    assert client.post("/attention/settings", params={"person": P}, headers=h, json={"budget_per_day": 3}).status_code == 403


def test_a_foreign_origin_is_refused(client):
    r = client.post("/attention/settings", params={"person": P}, headers={"Origin": "https://evil.example", "Content-Type": "application/json"}, json={"budget_per_day": 3})
    assert r.status_code == 403
    ok = client.post("/attention/settings", params={"person": P}, headers={"Origin": "http://localhost:5173", "X-Understudy-Actor": "worker"}, json={"budget_per_day": 3})
    assert ok.status_code == 200 and ok.json()["data"]["budget_per_day"] == 3


def test_settings_round_trip_and_safety_is_fixed(client):
    g = client.get("/attention/settings", params={"person": P}).json()["data"]
    assert g["budget_per_day"] == 10 and g["level_glance"] is True and {t["type"] for t in g["types"]} >= {"cue_cue", "kill_engaged"}
    r = client.post("/attention/settings", params={"person": P}, json={"modes": {"run_finished": "digest"}, "level_glance": False})
    assert r.status_code == 200 and r.json()["data"]["level_glance"] is False
    bad = client.post("/attention/settings", params={"person": P}, json={"modes": {"kill_engaged": "quiet"}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "safety_fixed"
    assert client.post("/attention/settings", params={"person": P}, json={"colour": "red"}).status_code == 422


def test_export_and_delete(client):
    client.post("/attention/events", params={"person": P}, json={"type": "approval_waiting", "subject": "q1", "t": T0})
    ex = client.get("/attention/export", params={"person": P})
    assert ex.status_code == 200 and ex.json()["metadata_only"] is True
    assert client.delete("/attention", params={"person": P}).json() == {"deleted": 1}
    assert client.get("/attention/export", params={"person": P}).json()["state"]["items"] == {}


# ------------------------------------------------------------------------------------------------ the package is pure
PKG = Path(R.__file__).parent
FORBIDDEN = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "subprocess", "openai", "anthropic", "google", "websockets", "ftplib", "smtplib"}


def test_the_package_imports_no_network_model_or_process_module():
    for f in sorted(PKG.glob("*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            assert not (set(names) & FORBIDDEN), (f.name, names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("eval", "exec", "compile", "__import__"), (f.name, node.func.id)


def test_the_engine_privacy_guard_finds_nothing_in_this_package():
    from understudy_engine.privacy import guard

    rep = guard.scan_tree()
    assert [f for f in rep.files if f.startswith("attention/")]
    assert [v for v in rep.violations if "attention" in str(v)] == []
