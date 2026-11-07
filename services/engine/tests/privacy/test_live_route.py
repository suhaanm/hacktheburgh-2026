"""POST /privacy/ledger/live: ledger rows for live frame batches streamed from the Electron main process. Numbers, bools and enums only."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_privacy
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.privacy import canary, ledger

OK_GATE = {"consent": True, "denylisted_app": False, "secure_input": False, "unattended": False}


def app_client(monkeypatch, **kw):
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    return TestClient(app, **kw)


@pytest.fixture()
def client(monkeypatch):
    return app_client(monkeypatch)


def batch(**over):
    b = {"count": 5, "bytes": 90_000, "sha8": "0123456789abcdef", "width": 1280, "height": 720, "model": "gemini-3.8-live", "source": "real_screen",
         "gate": dict(OK_GATE), "latency_ms": 420}
    b.update(over)
    return b


ROW_KEYS = {"id", "t", "kind", "status", "purpose", "schema", "method", "fields", "payload", "image", "source", "provider", "model", "bytes", "mock", "ok",
            "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error", "reason"}


def test_a_reported_batch_is_one_complete_row_with_only_allowed_fields(client):
    r = client.post("/privacy/ledger/live", json=batch(input_tokens=900, output_tokens=0, cost_estimate_usd=0.003))
    assert r.status_code == 200 and r.json()["allowed"] is True and r.json()["status"] == "ok" and r.json()["reason"] is None
    [row] = ledger.read_all()
    assert set(row) <= ROW_KEYS and row["id"] == r.json()["ledger_id"]
    assert row["kind"] == "image" and row["purpose"] == "live.frame_batch" and row["status"] == "ok" and row["ok"] is True
    assert row["image"] == {"sha8": "0123456789abcdef", "bytes": 90_000, "width": 1280, "height": 720, "kind": "live_frame", "source": "real_screen"}
    assert row["payload"] == {"frames": 5} and row["model"] == "gemini:gemini-3.8-live" and row["provider"] == "gemini" and row["bytes"] == 90_000
    assert (row["latency_ms"], row["input_tokens"], row["output_tokens"], row["cost_estimate_usd"]) == (420, 900, 0, 0.003)
    assert row["mock"] is False
    s = ledger.summary()
    assert s["calls"] == 1 and s["images"]["sent"] == 1 and s["images"]["bytes_sent"] == 90_000


def test_the_main_process_can_announce_a_batch_first_and_report_its_result_after(client):
    a = client.post("/privacy/ledger/live", json=batch(latency_ms=None))
    assert a.json()["allowed"] is True and a.json()["status"] == "sending"
    assert ledger.read_all()[0]["status"] == "sending"
    r = client.post("/privacy/ledger/live/result", json={"ref": a.json()["ledger_id"], "ok": True, "latency_ms": 333, "input_tokens": 100})
    assert r.status_code == 200 and r.json() == {"ledger_id": a.json()["ledger_id"], "status": "ok"}
    [row] = ledger.read_all()
    assert row["status"] == "ok" and row["latency_ms"] == 333 and row["input_tokens"] == 100
    again = client.post("/privacy/ledger/live/result", json={"ref": a.json()["ledger_id"], "ok": False, "latency_ms": 1})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_finished"
    assert client.post("/privacy/ledger/live/result", json={"ref": "e_" + "0" * 16, "ok": True, "latency_ms": 1}).status_code == 404
    b = client.post("/privacy/ledger/live", json=batch(latency_ms=None)).json()
    assert client.post("/privacy/ledger/live/result", json={"ref": b["ledger_id"], "ok": False, "latency_ms": 9}).json()["status"] == "failed"
    assert ledger.read_all()[-1]["ok"] is False


def test_reporting_ok_false_with_a_latency_records_a_failed_batch(client):
    client.post("/privacy/ledger/live", json=batch(ok=False))
    assert ledger.read_all()[0]["status"] == "failed" and ledger.read_all()[0]["ok"] is False


@pytest.mark.parametrize("gate,reason", [
    ({"consent": True, "denylisted_app": False, "secure_input": False, "unattended": True}, "unattended"),
    ({"consent": True, "denylisted_app": True, "secure_input": True, "unattended": True}, "unattended"),
    ({"consent": False, "denylisted_app": False, "secure_input": False, "unattended": False}, "no_consent"),
    ({"consent": True, "denylisted_app": True, "secure_input": False, "unattended": False}, "denylisted_app"),
    ({"consent": True, "denylisted_app": False, "secure_input": True, "unattended": False}, "secure_input"),
])
def test_a_closed_gate_writes_one_blocked_row_and_says_do_not_send(client, gate, reason):
    r = client.post("/privacy/ledger/live", json=batch(latency_ms=None, gate=gate))
    assert r.status_code == 200 and r.json()["allowed"] is False and r.json()["reason"] == reason and r.json()["status"] == "blocked"
    [row] = ledger.read_all()
    assert row["status"] == "blocked" and row["reason"] == reason and row["id"] == r.json()["ledger_id"] and row["ok"] is False and row["bytes"] == 0
    assert row["image"]["sha8"] == "0123456789abcdef" and row["image"]["kind"] == "live_frame"
    s = ledger.summary()
    assert s["calls"] == 0 and s["images"]["blocked_by_reason"] == {reason: 1}


def test_unattended_real_screen_blocks_even_when_the_batch_is_reported_as_already_sent_and_the_row_says_so(client):
    gate = {**OK_GATE, "unattended": True}
    r = client.post("/privacy/ledger/live", json=batch(gate=gate, latency_ms=300, ok=True))
    assert r.json()["allowed"] is False and r.json()["reason"] == "unattended"
    [row] = ledger.read_all()
    assert row["status"] == "blocked" and row["error"] == "reported_after_send" and row["latency_ms"] == 300 and row["ok"] is False


def test_sandbox_needs_no_consent_and_may_be_unattended_and_the_row_says_so(client):
    r = client.post("/privacy/ledger/live", json=batch(source="sandbox", gate={"consent": False, "denylisted_app": False, "secure_input": False, "unattended": True}))
    assert r.json()["allowed"] is True
    row = ledger.read_all()[0]
    assert row["source"] == "sandbox" and row["image"]["source"] == "sandbox" and row["status"] == "ok"
    assert ledger.summary()["images"]["sent_by_source"] == {"sandbox": 1}


def test_a_web_page_cannot_report_a_sandbox_batch_but_the_local_main_process_can(client):
    sb = batch(source="sandbox")
    assert client.post("/privacy/ledger/live", json=sb, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/privacy/ledger/live", json=sb, headers={"origin": "http://localhost:5173"}).status_code == 403
    assert client.post("/privacy/ledger/live", json=sb, headers={"origin": "http://127.0.0.1:7801"}).status_code == 200
    assert client.post("/privacy/ledger/live", json=sb).status_code == 200            # Electron main sends no Origin: convention, not enforcement
    assert client.post("/privacy/ledger/live", json=batch(), headers={"origin": "app://understudy"}).status_code == 200


def test_only_this_machine_and_the_worker_actor_can_report(monkeypatch):
    c = app_client(monkeypatch)
    for actor in ("agent", "model", "page", "tool"):
        r = c.post("/privacy/ledger/live", json=batch(), headers={"x-understudy-actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert c.post("/privacy/ledger/live", json=batch(), headers={"origin": "https://evil.example"}).status_code == 403
    remote = app_client(monkeypatch, client=("203.0.113.9", 4000))
    assert remote.post("/privacy/ledger/live", json=batch()).status_code == 403
    assert ledger.read_all() == []


def test_flag_off_means_404(monkeypatch):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    c = TestClient(app)
    monkeypatch.delenv("UNDERSTUDY_X_PRIVACY", raising=False)
    for path in ("/privacy/ledger/live", "/privacy/ledger/live/result"):
        r = c.post(path, json=batch())
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off"


@pytest.mark.parametrize("extra", [
    {"frame": "AAAA"}, {"image": "base64"}, {"audio": "AAAA"}, {"transcript": "hello"}, {"title": "Ada's inbox"}, {"note": "x"},
    {"gate": {**OK_GATE, "extra": True}}, {"count": 0}, {"count": 1001}, {"bytes": 0}, {"sha8": "xyz"}, {"sha8": "0123456789ABCDEF"},
    {"width": 1281}, {"height": 0}, {"model": "Ada Lovelace's model"}, {"model": "models/gemini"}, {"model": "ada@example.com"}, {"model": ""},
    {"source": "local"}, {"provider": "other"}, {"latency_ms": -1}, {"count": "5"}, {"gate": {"consent": 1, **{k: v for k, v in OK_GATE.items() if k != "consent"}}},
    {"bytes": 4}, {"bytes": 5 * 409_601}, {"cost_estimate_usd": -1}, {"input_tokens": "lots"},
])
def test_any_extra_or_malformed_field_is_rejected_with_a_message_that_never_echoes_it(client, extra):
    r = client.post("/privacy/ledger/live", json=batch(**extra))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert "Ada" not in r.text and "AAAA" not in r.text and "hello" not in r.text and "base64" not in r.json()["error"]["message"].replace("only the documented", "")
    assert ledger.read_all() == []


def test_missing_required_fields_are_rejected(client):
    b = batch()
    for k in ("count", "bytes", "sha8", "width", "height", "model", "source", "gate"):
        bb = dict(b)
        del bb[k]
        assert client.post("/privacy/ledger/live", json=bb).status_code == 422, k


def test_a_body_big_enough_to_carry_a_frame_or_audio_is_refused_before_it_is_parsed_and_not_echoed(client):
    pi = canary.plant_image(1)
    body = batch()
    body["frame"] = base64.b64encode(pi.data).decode()
    r = client.post("/privacy/ledger/live", content=json.dumps(body), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
    assert pi.token not in r.text and base64.b64encode(pi.data).decode()[:40] not in r.text
    assert ledger.read_all() == []
    assert client.post("/privacy/ledger/live/result", content=b"x" * 5000).status_code == 413


def test_not_json_or_not_an_object_is_a_plain_error(client):
    assert client.post("/privacy/ledger/live", content=b"{nope", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/privacy/ledger/live", json=[1, 2]).status_code == 422


def test_result_body_rejects_extra_fields_and_bad_refs(client):
    assert client.post("/privacy/ledger/live/result", json={"ref": "e_0123456789abcdef", "ok": True, "latency_ms": 1, "frame": "x"}).status_code == 422
    assert client.post("/privacy/ledger/live/result", json={"ref": "../etc", "ok": True, "latency_ms": 1}).status_code == 422


def test_result_for_a_non_live_row_is_refused(client):
    from understudy_engine.privacy import egress
    from understudy_engine.privacy.image import ImageGate, SafeImage
    from understudy_engine.privacy.testing import CapturingPort

    res = egress.send_image("glance.screen_state", SafeImage(canary.plant_image(2).data, "glance"), {"mode": "triggered", "trigger": "stuck", "strict": False},
                            gate=ImageGate(True, False, False, False), port=CapturingPort())
    assert client.post("/privacy/ledger/live/result", json={"ref": res.ledger_id, "ok": True, "latency_ms": 1}).status_code == 404


def test_live_rows_appear_in_the_ledger_route_and_summary_like_other_image_rows(client):
    client.post("/privacy/ledger/live", json=batch())
    client.post("/privacy/ledger/live", json=batch(gate={**OK_GATE, "unattended": True}, latency_ms=None))
    rows = client.get("/privacy/ledger").json()["data"]
    assert [r["status"] for r in rows] == ["blocked", "ok"] and all(r["purpose"] == "live.frame_batch" for r in rows)
    s = client.get("/privacy/summary").json()["data"]
    assert s["images"]["sent"] == 1 and s["images"]["blocked_by_reason"] == {"unattended": 1}


def test_nothing_about_a_batch_other_than_the_allowed_fields_reaches_disk_or_logs(client, data_dir, tmp_path):
    from understudy_engine.privacy.testing import LogCapture

    with LogCapture() as logs:
        client.post("/privacy/ledger/live", json=batch())
        client.post("/privacy/ledger/live", json=batch(gate={**OK_GATE, "unattended": True}))
        client.post("/privacy/ledger/live", json=batch(title="Ada's inbox"))
    blob = "".join(p.read_text() for p in data_dir.rglob("*") if p.is_file()) + " ".join(logs.texts)
    assert "Ada" not in blob and "inbox" not in blob
