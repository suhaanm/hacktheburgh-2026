"""HTTP routes: /models/status, /cue/ground, /glance. Fake backends, a fake clock, the real privacy guard and the real AWARENESS handler."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from understudy_engine.privacy import ledger

from understudy_agent.models import routes
from understudy_agent.models.gemini_http import GeminiHTTPError
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.meter import Meter
from understudy_agent.models.routing import ModelRouter

from .helpers import Clock, FakeBackend

JPEG = prepare_frame(make_test_png(1280, 800))
B64 = base64.b64encode(JPEG).decode()
FRAME = {"mime": "image/jpeg", "b64": B64, "width": 1280, "height": 800}
MENU = [{"id": "calc", "label": "the Calculate button"}, {"id": "next", "label": "the Continue button"}]
OPEN = {"consent": True, "denylisted_app": False, "secure_input": False, "unattended": False}
GOOD = {"available": ["calc", "next"], "chosen": "calc", "confidence": 0.9, "box_2d": [419, 419, 501, 581]}
NOTFOUND = {"available": ["next"], "chosen": "none", "confidence": 0.8}
CANARY = "Zebulon Quillfeather"


def req(**kw):
    body = {"frame": dict(FRAME), "menu": [dict(m) for m in MENU], "app_kind": "browser", "tier_hint": "lite", "purpose": "cue.ground", "gates": dict(OPEN)}
    body.update(kw)
    return body


def make_router(gem=None, oa=None, clock=None) -> ModelRouter:
    backends = {}
    if gem is not None:
        backends["gemini"] = gem
    if oa is not None:
        backends["openai"] = oa
    return ModelRouter(backends=backends, meter=Meter(), clock=clock or Clock())


@pytest.fixture
def client(monkeypatch):
    holder = {}
    monkeypatch.setattr(routes, "get_router", lambda: holder["router"])
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    c.holder = holder  # type: ignore[attr-defined]
    return c


def gem(script, **kw):
    return FakeBackend("gemini", script, **kw)


def oai(script, **kw):
    return FakeBackend("openai", script, models={"fast": "openai-fast", "accurate": "openai-fast"}, **kw)


# ------------------------------------------------------------------------------------------------ /models/status
def test_status_route(client):
    r = client.get("/models/status")
    assert r.status_code == 200
    j = r.json()
    assert set(j["roles"]) == {"point", "glance", "verify"} and "ledger_coverage" in j
    assert "AIza" not in r.text and "sk-test" not in r.text


# ------------------------------------------------------------------------------------------------ /cue/ground
def test_cue_ground_success_and_ledger_has_no_frame_or_labels(client):
    g = gem({"fast": [GOOD], "accurate": []})
    client.holder["router"] = make_router(g)
    r = client.post("/cue/ground", json=req())
    assert r.status_code == 200, r.text
    b = r.json()
    assert b == {"ok": True, "available": ["calc", "next"], "chosen": "calc", "box_2d": [419, 419, 501, 581], "confidence": 0.9,
                 "source": "vision", "model_tier": "lite", "latency_ms": b["latency_ms"]}
    assert [c["tier"] for c in g.calls] == ["fast"]
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["purpose"].startswith("cue.ground_") and rows[0]["payload"] == {"app_kind": "browser"}
    text = json.dumps(rows)
    assert B64[:40] not in text and "Calculate button" not in text and "/9j/" not in text
    # the prompt the model saw carries the menu and the closed schema (ids as the enum)
    assert "calc: the Calculate button" in g.calls[0]["prompt"]
    assert g.calls[0]["schema"]["properties"]["chosen"]["enum"] == ["calc", "next", "none"]


def test_cue_ground_not_found_escalates_to_the_full_model(client):
    g = gem({"fast": [NOTFOUND], "accurate": [GOOD]})
    client.holder["router"] = make_router(g)
    b = client.post("/cue/ground", json=req()).json()
    assert b["chosen"] == "calc" and b["model_tier"] == "full" and [c["tier"] for c in g.calls] == ["fast", "accurate"]


def test_cue_ground_tier_hint_full_starts_on_the_full_model(client):
    g = gem({"fast": [], "accurate": [GOOD]})
    client.holder["router"] = make_router(g)
    b = client.post("/cue/ground", json=req(tier_hint="full")).json()
    assert b["model_tier"] == "full" and [c["tier"] for c in g.calls] == ["accurate"]


def test_cue_ground_not_found_everywhere_is_null(client):
    g = gem({"fast": [NOTFOUND], "accurate": [NOTFOUND]})
    client.holder["router"] = make_router(g)
    b = client.post("/cue/ground", json=req()).json()
    assert b["ok"] is True and b["chosen"] is None and b["box_2d"] is None and b["available"] == ["next"]


@pytest.mark.parametrize("box", [[0, 0, 900, 900], [100, 100, 101, 101]])
def test_cue_ground_rejects_boxes_that_fail_sanity(client, box):
    bad = {**GOOD, "box_2d": box}
    client.holder["router"] = make_router(gem({"fast": [bad], "accurate": [bad]}))
    b = client.post("/cue/ground", json=req()).json()
    assert b["chosen"] is None and b["box_2d"] is None and "calc" in b["available"]


def test_cue_ground_fallback_to_openai_when_gemini_is_down(client):
    client.holder["router"] = make_router(gem({"fast": [GeminiHTTPError("auth", "no")], "accurate": []}), oai({"fast": [GOOD]}))
    b = client.post("/cue/ground", json=req()).json()
    assert b["chosen"] == "calc" and b["model_tier"] == "lite"


@pytest.mark.parametrize("gates,reason", [
    ({"consent": False, "denylisted_app": False, "secure_input": False, "unattended": False}, "no_consent"),
    ({"consent": True, "denylisted_app": False, "secure_input": True, "unattended": False}, "secure_input"),
    ({"consent": True, "denylisted_app": True, "secure_input": False, "unattended": False}, "denylisted_app"),
    ({"consent": True, "denylisted_app": False, "secure_input": False, "unattended": True}, "unattended"),
])
def test_cue_ground_closed_gate_sends_nothing(client, gates, reason):
    g = gem({"fast": [GOOD]})
    client.holder["router"] = make_router(g)
    r = client.post("/cue/ground", json=req(gates=gates))
    assert r.status_code == 200 and r.json() == {"ok": False, "blocked_reason": reason}
    assert g.calls == [] and any(x.get("status") == "blocked" for x in ledger.read_all())
    assert B64[:40] not in json.dumps(ledger.read_all())


def test_cue_ground_sandbox_source_needs_no_consent_and_may_run_unattended(client):
    client.holder["router"] = make_router(gem({"fast": [GOOD]}))
    gates = {"consent": False, "denylisted_app": False, "secure_input": False, "unattended": True}
    assert client.post("/cue/ground", json=req(gates=gates, source="sandbox")).json()["ok"] is True


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("gates"),
    lambda b: b["gates"].pop("secure_input"),
    lambda b: b["gates"].update(consent="yes"),
    lambda b: b.update(menu=MENU[:1]),
    lambda b: b.update(menu=MENU * 4),
    lambda b: b.update(menu=[{"id": "none", "label": "x"}, {"id": "b", "label": "y"}]),
    lambda b: b.update(menu=[{"id": "a", "label": "x"}, {"id": "a", "label": "y"}]),
    lambda b: b.update(menu=[{"id": "A B", "label": "x"}, {"id": "b", "label": "y"}]),
    lambda b: b.update(purpose="glance"),
    lambda b: b.update(app_kind="toaster"),
    lambda b: b.update(tier_hint="huge"),
    lambda b: b["frame"].update(b64="!!!not base64!!!"),
    lambda b: b["frame"].update(mime="image/png"),
    lambda b: b["frame"].update(width=999),
    lambda b: b["frame"].update(width=5000),
    lambda b: b.update(frame="nope"),
    lambda b: b.update(source="somewhere"),
])
def test_cue_ground_validation_is_a_422_or_403_and_sends_nothing(client, mutate):
    g = gem({"fast": [GOOD]})
    client.holder["router"] = make_router(g)
    body = req()
    mutate(body)
    r = client.post("/cue/ground", json=body)
    assert r.status_code in (403, 422) and "error" in r.json() and g.calls == []


def test_cue_ground_privacy_backstop_on_labels_and_no_echo(client):
    client.holder["router"] = make_router(gem({"fast": [GOOD]}))
    body = req(menu=[{"id": "a", "label": "mail alice@example.com now"}, {"id": "b", "label": "the button"}])
    r = client.post("/cue/ground", json=body)
    assert r.status_code == 422 and "alice" not in r.text and "example.com" not in r.text


def test_cue_ground_refuses_other_machines_and_foreign_origins():
    r = routes.cue_ground_reply(req(), client_host="10.1.2.3", origin=None, router_=make_router(gem({"fast": [GOOD]})))
    assert r.status == 403 and r.body["error"]["code"] == "not_this_machine"
    r = routes.cue_ground_reply(req(source="sandbox"), client_host="127.0.0.1", origin="https://evil.example",
                                router_=make_router(gem({"fast": [GOOD]})))
    assert r.status == 403


def test_cue_ground_nothing_configured_is_a_503(client):
    client.holder["router"] = make_router(gem({"fast": []}, available=False), oai({"fast": []}, available=False))
    r = client.post("/cue/ground", json=req())
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable", r.text


def test_cue_ground_never_echoes_the_body_in_errors(client, monkeypatch):
    r = client.post("/cue/ground", content=f'{{"menu": "{CANARY}"', headers={"content-type": "application/json"})
    assert r.status_code == 422 and CANARY not in r.text
    monkeypatch.setattr(routes, "cue_ground_reply", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(CANARY)))
    r = client.post("/cue/ground", json=req(menu=[{"id": "a", "label": CANARY}, {"id": "b", "label": "y"}]))
    assert r.status_code == 500 and CANARY not in r.text and r.json()["error"]["code"] == "internal"


def test_cue_ground_mock_mode_uses_the_offline_port(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    r = client.post("/cue/ground", json=req())
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["source"] == "vision"


def test_parse_cue_drops_unknown_ids_and_dedupes():
    a = routes.parse_cue({"available": ["a", "a", "zzz"], "chosen": "b", "confidence": 0.5, "box_2d": [10, 10, 60, 90]}, ["a", "b"])
    assert a.available == ["a", "b"] and a.chosen == "b" and a.found


# ------------------------------------------------------------------------------------------------ /glance
GL = {"app_kind": "browser", "task_phase": "entering", "blocker": "none", "confidence": 0.9}
GLANCE_BODY = {"frame_b64": B64, "gates": dict(OPEN), "trigger": "stuck", "app_kind": "browser", "width": 1280, "height": 800}


def test_glance_runs_the_awareness_handler_through_the_router(client):
    g = gem({"fast": [GL], "accurate": []})
    client.holder["router"] = make_router(g)
    r = client.post("/glance", json=GLANCE_BODY)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ok"] is True and b["result"]["app_kind"] == "browser" and b["model"] == "gemini:gemini-fast"
    assert r.headers["x-model-route"] == "gemini-fast:ok"
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["purpose"] == "awareness.glance" and rows[0]["source"] == "real_screen"
    assert B64[:40] not in json.dumps(rows) and "/9j/" not in json.dumps(rows)


def test_glance_falls_back_to_openai_and_each_step_has_its_own_ledger_row(client):
    client.holder["router"] = make_router(gem({"fast": [GeminiHTTPError("api", "boom")], "accurate": []}), oai({"fast": [GL]}))
    r = client.post("/glance", json=GLANCE_BODY)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["model"] == "openai:openai-fast"
    assert r.headers["x-model-route"] == "gemini-fast:failed,openai-fast:ok"
    assert len([x for x in ledger.read_all() if x.get("kind") == "image"]) == 2


def test_glance_closed_gate_passes_the_handlers_reply_through(client):
    g = gem({"fast": [GL]})
    client.holder["router"] = make_router(g)
    body = {**GLANCE_BODY, "gates": {**OPEN, "unattended": True}}
    r = client.post("/glance", json=body)
    assert r.status_code == 200 and r.json() == {"ok": False, "blocked_reason": "unattended"} and g.calls == []


def test_glance_bad_requests_are_the_handlers_422_and_403(client):
    client.holder["router"] = make_router(gem({"fast": [GL]}))
    assert client.post("/glance", json={"nope": 1}).status_code == 422
    r = routes.glance_reply(GLANCE_BODY, client_host="10.0.0.9", origin=None, router_=make_router(gem({"fast": [GL]})))
    assert r.status == 403


def test_glance_nothing_available_is_a_503_and_nothing_is_echoed(client):
    client.holder["router"] = make_router(gem({"fast": []}, available=False))
    r = client.post("/glance", json=GLANCE_BODY)
    assert r.status_code == 503 and B64[:40] not in r.text
    r = client.post("/glance", content=f"{CANARY} not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and CANARY not in r.text


def test_glance_with_a_fake_handler_escalates_on_a_refused_answer(monkeypatch):
    calls = []

    def handler(body, *, client_host, origin, port=None, now=None):
        out = port.vision(b"\xff\xd8\xff", "p", {"type": "object"})
        calls.append(port.tier)
        if len(calls) == 1:
            return NS(status=200, body={"ok": False, "blocked_reason": "output_rejected"})
        return NS(status=200, body={"ok": True, "result": out, "model": port.model_for("vision")})

    g = gem({"fast": [GL], "accurate": [GL]})
    r = routes.glance_reply({}, client_host="testclient", origin=None, router_=make_router(g), handler=handler)
    assert r.status == 200 and r.body["ok"] is True and calls == ["fast", "accurate"]


def test_glance_mock_mode_calls_the_handler_once_on_its_own_port(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    seen = {}

    def handler(body, *, client_host, origin, port=None, now=None):
        seen["port"] = port
        return NS(status=200, body={"ok": True, "result": {}, "mock": True})

    r = routes.glance_reply({}, client_host="testclient", origin=None, handler=handler)
    assert r.status == 200 and seen["port"] is None
