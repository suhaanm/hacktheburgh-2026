"""POST /privacy/ledger/live/audio (+ /result) and POST /privacy/ledger/direct (+ /result): call reports from local processes.
Metadata only; the gate runs before anything leaves; one merged row per call; no content can be sent."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_privacy
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.privacy import canary, ledger
from understudy_engine.privacy.testing import LogCapture

OK_GATE = {"consent": True, "denylisted_app": False, "secure_input": False, "unattended": False}


def make_client(monkeypatch, **kw):
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    return TestClient(app, **kw)


@pytest.fixture()
def client(monkeypatch):
    return make_client(monkeypatch)


def announce(**over):
    b = {"model": "gemini-3.8-live", "source": "real_screen", "provider": "gemini", "gate": dict(OK_GATE), "turn": "converse"}
    b.update(over)
    return b


def direct(**over):
    b = {"kind": "image", "purpose": "desktop.glance", "provider": "gemini", "model": "gemini-3.1-flash-lite", "bytes": 52_000, "count": 1,
         "source": "real_screen", "gate": dict(OK_GATE)}
    b.update(over)
    return b


# =========================================================================== live audio turns
def test_an_audio_turn_is_announced_then_finished_into_one_row_with_a_seconds_range_not_the_seconds(client):
    a = client.post("/privacy/ledger/live/audio", json=announce())
    assert a.status_code == 200 and a.json() == {"allowed": True, "status": "sending", "reason": None, "ledger_id": a.json()["ledger_id"]}
    [row] = ledger.read_all()
    assert row["kind"] == "audio" and row["status"] == "sending" and row["purpose"] == "live.audio_turn" and row["payload"] == {"turn": "converse"}
    r = client.post("/privacy/ledger/live/audio/result", json={"ref": a.json()["ledger_id"], "ok": True, "seconds": 7.3, "bytes": 234_567, "latency_ms": 640,
                                                               "cost_estimate_usd": 0.0004})
    assert r.status_code == 200 and r.json() == {"ledger_id": a.json()["ledger_id"], "status": "ok", "seconds_bucket": "5-15"}
    [row] = ledger.read_all()
    assert row["status"] == "ok" and row["ok"] is True and row["bytes"] == 234_567 and row["latency_ms"] == 640 and row["cost_estimate_usd"] == 0.0004
    assert row["audio"] == {"source": "real_screen", "kind": "live_audio", "bytes": 234_567, "seconds_bucket": "5-15"}
    assert row["payload"] == {"turn": "converse", "seconds_bucket": "5-15"} and row["model"] == "gemini:gemini-3.8-live" and row["mock"] is False
    assert "7.3" not in json.dumps(row)
    s = ledger.summary()
    assert s["calls"] == 1 and s["audio"]["sent"] == 1 and s["audio"]["bytes_sent"] == 234_567 and s["audio"]["blocked"] == 0


@pytest.mark.parametrize("seconds,bucket", [(0, "0-5"), (4.99, "0-5"), (5, "5-15"), (14.9, "5-15"), (15, "15-60"), (59.9, "15-60"), (60, "60+"), (600, "60+")])
def test_seconds_become_one_of_four_ranges(client, seconds, bucket):
    a = client.post("/privacy/ledger/live/audio", json=announce()).json()
    r = client.post("/privacy/ledger/live/audio/result", json={"ref": a["ledger_id"], "ok": True, "seconds": seconds, "bytes": 1000})
    assert r.json()["seconds_bucket"] == bucket


@pytest.mark.parametrize("gate,reason", [
    ({"consent": True, "denylisted_app": False, "secure_input": False, "unattended": True}, "unattended"),
    ({"consent": False, "denylisted_app": True, "secure_input": True, "unattended": True}, "unattended"),
    ({"consent": True, "denylisted_app": False, "secure_input": True, "unattended": False}, "secure_input"),
    ({"consent": True, "denylisted_app": True, "secure_input": False, "unattended": False}, "denylisted_app"),
    ({"consent": False, "denylisted_app": False, "secure_input": False, "unattended": False}, "no_consent"),
])
def test_a_closed_gate_blocks_the_turn_before_any_audio_and_writes_one_blocked_row(client, gate, reason):
    r = client.post("/privacy/ledger/live/audio", json=announce(gate=gate))
    assert r.status_code == 200 and r.json()["allowed"] is False and r.json()["reason"] == reason and r.json()["status"] == "blocked"
    [row] = ledger.read_all()
    assert row["kind"] == "audio" and row["status"] == "blocked" and row["reason"] == reason and row["bytes"] == 0 and row["ok"] is False
    s = ledger.summary()
    assert s["calls"] == 0 and s["audio"]["blocked"] == 1 and s["audio"]["blocked_by_reason"] == {reason: 1}


def test_a_sandbox_audio_turn_needs_no_consent_and_may_be_unattended(client):
    g = {"consent": False, "denylisted_app": False, "secure_input": False, "unattended": True}
    assert client.post("/privacy/ledger/live/audio", json=announce(source="sandbox", gate=g)).json()["allowed"] is True


def test_audio_result_refuses_unknown_finished_and_wrong_kind_refs_and_extra_fields(client):
    a = client.post("/privacy/ledger/live/audio", json=announce()).json()
    res = {"ref": a["ledger_id"], "ok": True, "seconds": 3, "bytes": 5}
    assert client.post("/privacy/ledger/live/audio/result", json={**res, "ref": "e_" + "0" * 16}).status_code == 404
    assert client.post("/privacy/ledger/live/audio/result", json={**res, "transcript": "hello"}).status_code == 422
    assert client.post("/privacy/ledger/live/audio/result", json={**res, "seconds": 601}).status_code == 422
    assert client.post("/privacy/ledger/live/audio/result", json={**res, "bytes": -1}).status_code == 422
    assert client.post("/privacy/ledger/live/audio/result", json=res).status_code == 200
    assert client.post("/privacy/ledger/live/audio/result", json=res).status_code == 409
    d = client.post("/privacy/ledger/direct", json=direct(latency_ms=None)).json()
    assert client.post("/privacy/ledger/live/audio/result", json={**res, "ref": d["ledger_id"]}).status_code == 404         # not an audio turn


@pytest.mark.parametrize("extra", [
    {"audio": "AAAA"}, {"transcript": "hello"}, {"text": "hi"}, {"model": "Ada Lovelace's model"}, {"model": ""}, {"source": "local"}, {"provider": "other"},
    {"turn": "dictate"}, {"turn": "Ada's call"}, {"gate": {**OK_GATE, "extra": 1}}, {"gate": {"consent": 1, **{k: v for k, v in OK_GATE.items() if k != "consent"}}},
])
def test_audio_announce_rejects_extra_or_malformed_fields_without_echoing_them(client, extra):
    r = client.post("/privacy/ledger/live/audio", json=announce(**extra))
    assert r.status_code == 422 and "Ada" not in r.text and "AAAA" not in r.text and "hello" not in r.text
    assert ledger.read_all() == []


def test_a_body_that_could_carry_audio_is_refused_unparsed(client):
    big = announce()
    big["audio"] = base64.b64encode(b"\x00" * 6000).decode()
    r = client.post("/privacy/ledger/live/audio", content=json.dumps(big), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large" and ledger.read_all() == []


# =========================================================================== legacy direct calls
def test_a_direct_call_reported_complete_is_one_merged_row_with_only_metadata(client):
    r = client.post("/privacy/ledger/direct", json=direct(latency_ms=820, ok=True, input_tokens=400, output_tokens=60, cost_estimate_usd=0.0003))
    assert r.status_code == 200 and r.json()["allowed"] is True and r.json()["status"] == "ok" and r.json()["reason"] is None
    [row] = ledger.read_all()
    assert row["kind"] == "reported" and row["purpose"] == "desktop.glance" and row["status"] == "ok" and row["ok"] is True and row["id"] == r.json()["ledger_id"]
    assert row["content"] == {"kind": "image", "bytes": 52_000, "count": 1, "source": "real_screen"} and row["payload"] == {"count": 1}
    assert row["provider"] == "gemini" and row["model"] == "gemini:gemini-3.1-flash-lite" and row["bytes"] == 52_000 and row["source"] == "real_screen"
    assert (row["latency_ms"], row["input_tokens"], row["output_tokens"], row["cost_estimate_usd"]) == (820, 400, 60, 0.0003)
    assert set(row) <= {"id", "t", "kind", "status", "purpose", "schema", "method", "fields", "payload", "content", "source", "provider", "model", "bytes",
                        "mock", "ok", "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error", "reason"}
    s = ledger.summary()
    assert s["calls"] == 1 and s["reported"]["sent"] == 1 and s["reported"]["sent_by_kind"] == {"image": 1} and s["reported"]["sent_by_provider"] == {"gemini": 1}
    assert s["reported"]["bytes_sent"] == 52_000


@pytest.mark.parametrize("kind", ["image", "audio", "file_text", "text"])
def test_every_content_kind_is_accepted_and_nothing_else(client, kind):
    assert client.post("/privacy/ledger/direct", json=direct(kind=kind)).status_code == 200
    assert ledger.read_all()[-1]["content"]["kind"] == kind


def test_announce_then_result_merges_into_one_row_and_updates_the_byte_count(client):
    a = client.post("/privacy/ledger/direct", json=direct(kind="file_text", purpose="desktop.embed", provider="gemini", bytes=10_000, count=12)).json()
    assert a["allowed"] is True and a["status"] == "sending" and ledger.read_all()[0]["status"] == "sending"
    r = client.post("/privacy/ledger/direct/result", json={"ref": a["ledger_id"], "ok": True, "latency_ms": 1500, "bytes": 9_800, "input_tokens": 2000})
    assert r.status_code == 200 and r.json() == {"ledger_id": a["ledger_id"], "status": "ok"}
    [row] = ledger.read_all()
    assert row["status"] == "ok" and row["bytes"] == 9_800 and row["content"]["bytes"] == 9_800 and row["content"]["count"] == 12 and row["input_tokens"] == 2000
    assert client.post("/privacy/ledger/direct/result", json={"ref": a["ledger_id"], "ok": False, "latency_ms": 1}).status_code == 409
    assert client.post("/privacy/ledger/direct/result", json={"ref": "e_" + "0" * 16, "ok": True, "latency_ms": 1}).status_code == 404
    b = client.post("/privacy/ledger/direct", json=direct()).json()
    assert client.post("/privacy/ledger/direct/result", json={"ref": b["ledger_id"], "ok": False, "latency_ms": 9}).json()["status"] == "failed"


@pytest.mark.parametrize("gate,reason", [
    ({"consent": True, "denylisted_app": False, "secure_input": False, "unattended": True}, "unattended"),
    ({"consent": True, "denylisted_app": True, "secure_input": True, "unattended": False}, "secure_input"),
    ({"consent": True, "denylisted_app": True, "secure_input": False, "unattended": False}, "denylisted_app"),
    ({"consent": False, "denylisted_app": False, "secure_input": False, "unattended": False}, "no_consent"),
])
@pytest.mark.parametrize("kind", ["image", "audio", "file_text", "text"])
def test_a_closed_gate_blocks_every_kind_writes_a_blocked_row_and_says_make_no_request(client, gate, reason, kind):
    r = client.post("/privacy/ledger/direct", json=direct(kind=kind, gate=gate, latency_ms=None))
    assert r.status_code == 200 and r.json()["allowed"] is False and r.json()["reason"] == reason and r.json()["status"] == "blocked"
    [row] = ledger.read_all()
    assert row["status"] == "blocked" and row["reason"] == reason and row["bytes"] == 0 and row["ok"] is False and row["content"]["kind"] == kind
    s = ledger.summary()
    assert s["calls"] == 0 and s["reported"]["blocked_by_reason"] == {reason: 1}


def test_unattended_real_screen_blocks_whatever_else_is_true_and_a_late_report_is_marked_reported_after_send(client):
    gate = {"consent": True, "denylisted_app": False, "secure_input": False, "unattended": True}
    r = client.post("/privacy/ledger/direct", json=direct(gate=gate, latency_ms=300, ok=True))
    assert r.json()["allowed"] is False and r.json()["reason"] == "unattended"
    [row] = ledger.read_all()
    assert row["status"] == "blocked" and row["error"] == "reported_after_send" and row["latency_ms"] == 300


def test_sandbox_direct_calls_need_no_consent_and_may_be_unattended_and_the_row_says_so(client):
    g = {"consent": False, "denylisted_app": False, "secure_input": False, "unattended": True}
    r = client.post("/privacy/ledger/direct", json=direct(source="sandbox", gate=g, provider="openai", model="gpt-model-from-env"))
    assert r.json()["allowed"] is True
    row = ledger.read_all()[0]
    assert row["source"] == "sandbox" and row["content"]["source"] == "sandbox" and row["model"] == "openai:gpt-model-from-env"
    assert client.post("/privacy/ledger/direct", json=direct(source="sandbox", gate={**g, "secure_input": True})).json()["reason"] == "secure_input"


@pytest.mark.parametrize("extra", [
    {"content": "hello"}, {"text": "hello"}, {"frame": "AAAA"}, {"image": "AAAA"}, {"title": "Ada's inbox"}, {"kind": "video"}, {"kind": ""},
    {"purpose": "Ada Lovelace review"}, {"purpose": "ada@example.com"}, {"purpose": "x"}, {"purpose": "desktop..glance"}, {"purpose": "a.b.c.d"},
    {"provider": "Gemini"}, {"provider": "g"}, {"provider": "ada@example.com"}, {"model": "Ada Lovelace's model"}, {"model": "models/gemini"},
    {"bytes": -1}, {"bytes": 3_000_000_000}, {"count": 0}, {"count": 100_001}, {"count": "5"}, {"source": "local"},
    {"gate": {**OK_GATE, "extra": True}}, {"gate": {"consent": "yes", **{k: v for k, v in OK_GATE.items() if k != "consent"}}},
    {"latency_ms": -1}, {"cost_estimate_usd": -0.1}, {"input_tokens": "many"},
])
def test_direct_rejects_any_extra_or_malformed_field_without_echoing_it(client, extra):
    r = client.post("/privacy/ledger/direct", json=direct(**extra))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert "Ada" not in r.text and "AAAA" not in r.text and "hello" not in r.text
    assert ledger.read_all() == []


def test_direct_requires_every_field(client):
    b = direct()
    for k in ("kind", "purpose", "provider", "model", "bytes", "count", "source", "gate"):
        bb = dict(b)
        del bb[k]
        assert client.post("/privacy/ledger/direct", json=bb).status_code == 422, k


def test_a_direct_body_big_enough_to_carry_content_is_refused_unparsed_and_not_echoed(client):
    pi = canary.plant_image(1)
    body = direct()
    body["frame"] = base64.b64encode(pi.data).decode()
    r = client.post("/privacy/ledger/direct", content=json.dumps(body), headers={"content-type": "application/json"})
    assert r.status_code == 413 and pi.token not in r.text and ledger.read_all() == []


# =========================================================================== who may report (shared by live, live audio and direct)
PATHS = [("/privacy/ledger/live/audio", announce), ("/privacy/ledger/direct", direct)]


@pytest.mark.parametrize("path,make", PATHS)
def test_only_the_local_worker_without_an_origin_can_report(monkeypatch, path, make):
    c = make_client(monkeypatch)
    for actor in ("agent", "model", "page", "tool"):
        assert c.post(path, json=make(), headers={"x-understudy-actor": actor}).status_code == 403
    for origin in ("https://evil.example", "http://localhost:5173", "app://understudy", "null"):
        assert c.post(path, json=make(), headers={"origin": origin, "x-understudy-actor": "worker"}).status_code == 403
    assert make_client(monkeypatch, client=("203.0.113.9", 4000)).post(path, json=make()).status_code == 403
    assert ledger.read_all() == []
    assert c.post(path, json=make()).status_code == 200


@pytest.mark.parametrize("path", ["/privacy/ledger/live/audio", "/privacy/ledger/live/audio/result", "/privacy/ledger/direct", "/privacy/ledger/direct/result"])
def test_flag_off_means_404(monkeypatch, path):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    monkeypatch.delenv("UNDERSTUDY_X_PRIVACY", raising=False)
    r = TestClient(app).post(path, json={})
    assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off"


def test_the_ledger_route_and_summary_show_all_three_kinds_together(client):
    client.post("/privacy/ledger/live/audio", json=announce())
    client.post("/privacy/ledger/direct", json=direct(latency_ms=10))
    client.post("/privacy/ledger/direct", json=direct(gate={**OK_GATE, "unattended": True}))
    rows = client.get("/privacy/ledger").json()["data"]
    assert sorted(r["kind"] for r in rows) == ["audio", "reported", "reported"]
    s = client.get("/privacy/summary").json()["data"]
    assert s["calls"] == 2 and s["audio"]["sent"] == 1 and s["reported"]["sent"] == 1 and s["reported"]["blocked"] == 1


def test_nothing_but_the_allowed_fields_reaches_disk_or_logs(client, data_dir):
    with LogCapture() as logs:
        client.post("/privacy/ledger/live/audio", json=announce())
        client.post("/privacy/ledger/direct", json=direct(purpose="desktop.glance"))
        client.post("/privacy/ledger/direct", json=direct(title="Ada's inbox", transcript="hello Ada"))
        client.post("/privacy/ledger/live/audio", json=announce(transcript="hello Ada"))
    blob = "".join(p.read_text() for p in data_dir.rglob("*") if p.is_file()) + " ".join(logs.texts)
    assert "Ada" not in blob and "inbox" not in blob and "hello" not in blob
