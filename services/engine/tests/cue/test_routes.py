from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.api.errors import install_error_handlers
from understudy_engine.cue import routes as R
from understudy_engine.cue.live import LiveCue


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.cue_live = LiveCue()
    return TestClient(app)


def nxt(c, name, t, person="p_demo", **kw):
    r = c.get("/cue/next", params={"person": person, "fixture": name, "t": t, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_flag_off_is_404_extension_off_everywhere(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_CUE", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    c = TestClient(app)
    assert not R.enabled()
    for method, url, kw in (("get", "/cue/next?person=p_x", {}), ("get", "/growth?person=p_x", {}), ("get", "/cue/ledger?person=p_x", {}),
                            ("post", "/cue/feedback", {"json": {"event": "shown"}}), ("delete", "/cue/ledger?person=p_x", {}),
                            ("post", "/cue/quiet", {"json": {"minutes": 5}}), ("get", "/cue/reason?id=why.cliff", {})):
        r = getattr(c, method)(url, **kw)
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off", (url, r.text)


def test_master_flag_also_turns_it_on(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_CUE", raising=False)
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert R.enabled()


def test_next_over_the_stuck_fixture_walks_wait_cue_escalate():
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.cue_live = LiveCue()
    import os
    os.environ["UNDERSTUDY_X_CUE"] = "1"
    try:
        c = TestClient(app)
        seen = {}
        for t in (0, 60, 85, 87.5, 90, 105, 120):
            body = nxt(c, "stuck_after_result", t)
            seen[t] = body["data"]
        assert seen[0]["kind"] == "none" and seen[0]["why"]["reasons"][0] == "not_stuck"
        assert seen[87.5]["kind"] == "cue" and seen[87.5]["tier"] == 1 and seen[87.5]["new"] is True
        assert seen[87.5]["step"]["id"] == "cliff_a" and seen[87.5]["step"]["reason_id"] == "why.cliff"
        assert seen[87.5]["step"]["reason_text"] and len(seen[87.5]["step"]["reason_text"].split()) <= 12
        assert seen[87.5]["target"] == {"box_2d": [412, 96, 466, 388], "source": "dom", "confidence": 0.91}
        assert seen[90]["new"] is False and "persisting" in seen[90]["why"]["reasons"]
        assert seen[105]["kind"] == "none"
        assert seen[120]["kind"] == "cue" and seen[120]["tier"] == 2 and seen[120]["say"]["chip"] == "Next: Check cliff edges (A)"
        assert seen[120]["say"]["whisper"] is None
    finally:
        os.environ.pop("UNDERSTUDY_X_CUE", None)


def test_envelope_carries_meta_both_places_with_the_synthetic_badge(client):
    body = nxt(client, "stuck_after_result", 0)
    assert body["meta"]["origin"] == "synthetic" and body["meta"]["interval_level"] == 0.95 and body["meta"]["n_unit"] == "occurrences"
    assert body["data"]["meta"] == body["meta"]
    assert body["data"]["source"] == "rule"


def test_close_call_fixture_asks_and_answering_records_a_strong_label(client):
    for t in (0, 60, 85):
        nxt(client, "close_call", t)
    q = nxt(client, "close_call", 87.5)["data"]
    assert q["kind"] == "ask" and q["question"]["type"] == "close_call" and q["options"][-1] == {"id": "other", "label": "Something else"}
    r = client.post("/cue/feedback", json={"episode_id": q["episode_id"], "event": "answered", "option_id": "cliff_a"})
    assert r.status_code == 200 and r.json()["recorded"] is True and r.json()["intent_label"] is True
    nxt_ = nxt(client, "close_call", 90)["data"]
    assert nxt_["kind"] == "cue" and nxt_["step"]["id"] == "cliff_a" and nxt_["why"]["path_prob"] == 1.0
    bad = client.post("/cue/feedback", json={"episode_id": q["episode_id"], "event": "answered", "option_id": "reconcile"})
    assert bad.status_code in (200, 422)


def test_answer_must_be_one_of_the_options(client):
    for t in (0, 60, 85):
        nxt(client, "close_call", t)
    q = nxt(client, "close_call", 87.5)["data"]
    r = client.post("/cue/feedback", json={"episode_id": q["episode_id"], "event": "answered", "answer_id": "launch_missiles"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_answer"


def test_voice_is_off_by_default_and_whisper_needs_voice_ok(client):
    for t in (0, 85, 87.5, 120, 150, 180):
        d = nxt(client, "stuck_after_result", t)["data"]
        assert (d["say"] or {}).get("whisper") is None


def test_dry_polls_change_nothing(client):
    for t in (0, 85, 87.5):
        nxt(client, "stuck_after_result", t, dry=1)
    d = nxt(client, "stuck_after_result", 90, dry=1)["data"]
    assert d["kind"] == "none" and d["why"]["reasons"][0] in ("wait_signals", "not_stuck")


def test_feedback_validation_and_actor_guard(client):
    nxt(client, "stuck_after_result", 0)
    assert client.post("/cue/feedback", json={"event": "launch"}).status_code == 422
    assert client.post("/cue/feedback", json={"event": "shown", "how": "telepathy"}, params={"person": "p_demo"}).status_code == 422
    r = client.post("/cue/feedback", json={"event": "shown"}, params={"person": "p_demo"}, headers={"X-Understudy-Actor": "agent"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    r = client.post("/cue/feedback", json={"event": "shown"}, params={"person": "p_demo"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/cue/feedback", json={"event": "shown", "episode_id": "e_nope"}, params={"person": "p_demo"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_episode"


def test_accepted_dismissed_and_know_this_flow(client):
    for t in (0, 60, 85):
        nxt(client, "stuck_after_result", t)
    cue = nxt(client, "stuck_after_result", 87.5)["data"]
    r = client.post("/cue/feedback", json={"episode_id": cue["episode_id"], "event": "dismissed", "how": "esc", "seconds": 2.1}, params={"person": "p_demo"})
    assert r.status_code == 200 and r.json()["recorded"] is True
    d = nxt(client, "stuck_after_result", 90)["data"]
    assert d["kind"] == "none" and d["why"]["reasons"][0] == "dismissed_in_episode"


def test_quiet_hotkey(client):
    assert client.post("/cue/quiet", json={"minutes": 60}, params={"person": "p_demo"}).json()["minutes"] == 60
    for t in (0, 85, 87.5, 90):
        d = nxt(client, "stuck_after_result", t, person="p_demo")["data"]
    assert client.post("/cue/quiet", json={"minutes": -1}, params={"person": "p_demo"}).status_code == 422
    assert client.post("/cue/quiet", json={"minutes": 5}, params={"person": "p_demo"}, headers={"X-Understudy-Actor": "page"}).status_code == 403


def test_grounding_post_validates_the_box(client):
    ok = {"for_step": "cliff_a", "found": True, "chosen": "cliff_a", "available": ["cliff_a"], "box_2d": [10, 20, 60, 220], "confidence": 0.9, "source": "vision"}
    assert client.post("/cue/grounding", json=ok, params={"person": "p_x"}).status_code == 200
    for bad in ({**ok, "box_2d": [10, 20, 5, 220]}, {**ok, "box_2d": [10, 20, 60, 2200]}, {**ok, "source": "telepathy"}, {**ok, "box_2d": [1, 2, 3]}):
        assert client.post("/cue/grounding", json=bad, params={"person": "p_x"}).status_code == 422
    assert client.post("/cue/grounding", json=ok, params={"person": "p_x"}, headers={"X-Understudy-Actor": "model"}).status_code == 403


def test_unknown_fixture_and_fixtures_only_in_mock_mode(client, monkeypatch):
    assert client.get("/cue/next", params={"person": "p_demo", "fixture": "nope"}).status_code == 404
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    r = client.get("/cue/next", params={"person": "p_demo", "fixture": "stuck_after_result"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_fixture"


def test_no_context_is_silence_with_a_reason(client):
    r = client.get("/cue/next", params={"person": "p_nobody"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["kind"] == "none" and d["why"]["reasons"] == ["no_context"]


def test_reason_lookup(client):
    r = client.get("/cue/reason", params={"id": "why.cliff"})
    assert r.json() == {"id": "why.cliff", "text": "A figure near a limit can flip the answer."}
    assert client.get("/cue/reason", params={"id": "why.nope"}).status_code == 404


def test_proactivity_validated(client):
    assert client.get("/cue/next", params={"person": "p_demo", "fixture": "not_stuck", "proactivity": "loud"}).status_code == 422
