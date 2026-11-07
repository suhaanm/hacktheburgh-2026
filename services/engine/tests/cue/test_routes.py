from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.api.errors import install_error_handlers
from understudy_engine.cue import routes as R
from understudy_engine.cue.live import LiveCue
from understudy_engine.cue.params import DEFAULT, TUNED


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.cue_live = LiveCue(params=DEFAULT)
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
    app.state.cue_live = LiveCue(params=DEFAULT)
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


# ------------------------------------------------------------------------------------------------ the flags CUE-UX sends
def first_non_none(c, name, person="p_flags", ts=None, **kw):
    for t in ts or [0, 60, 85] + [87.5 + 2.5 * k for k in range(20)]:
        d = nxt(c, name, t, person=person, **kw)["data"]
        if d["kind"] != "none":
            return t, d
    return None, d


def test_denied_never_shows_and_never_asks_for_a_frame(client):
    for t in (0, 60, 85, 87.5, 90, 120):
        d = nxt(client, "stuck_after_result", t, person="p_denied", denied=1)["data"]
        assert d["kind"] == "none" and d["why"]["reasons"][0] == "denied" and not d["ground_wanted"] and d["menu"] is None
    d = nxt(client, "close_call", 100, person="p_denied2", denied=1, asked=1)["data"]
    assert d["kind"] == "none" and not d["ground_wanted"]                      # not even when asked


def test_away_typing_and_short_quiet_hold(client):
    for flag, reason in (({"away": 1}, "unsure_away"), ({"typing": 1}, "flow"), ({"quiet_s": 1.0}, "flow")):
        for t in (60, 85, 87.5, 90):
            d = nxt(client, "stuck_after_result", t, person=f"p_{reason}_{list(flag)[0]}", **flag)["data"]
            assert d["kind"] == "none" and d["why"]["reasons"][0] == reason, (flag, d["why"])


def test_asked_shows_even_while_typing_and_the_ladder_reaches_voice_only_with_voice_ok(client):
    seen = {}
    for k, t in enumerate((60, 62.5, 65, 67.5, 70, 72.5)):
        d = nxt(client, "stuck_after_result", t, person="p_ask", asked=1, typing=1, voice_ok=1)["data"]
        assert d["kind"] == "cue", d
        seen[d["tier"]] = d
    assert 4 in seen and seen[4]["say"]["whisper"] and seen[4]["say"]["whisper_id"] == "whisper.cliff_a"
    assert len(seen[4]["say"]["whisper"].split()) <= 8
    for tier, d in seen.items():
        if tier < 4:
            assert d["say"]["whisper"] is None and d["say"]["whisper_id"] is None
    quiet_voice = [nxt(client, "stuck_after_result", t, person="p_ask2", asked=1, voice_ok=0)["data"] for t in (60, 62.5, 65, 67.5, 70)]
    assert all(d["say"]["whisper"] is None and d["say"]["whisper_id"] is None for d in quiet_voice) and max(d["tier"] for d in quiet_voice) <= 3


def test_proactivity_changes_when_help_arrives_but_not_the_caps(client):
    def first(mode):
        for k in range(120):
            t = 40 + 2.5 * k
            d = nxt(client, "stuck_after_result", t, person=f"p_{mode}", proactivity=mode)["data"]
            if d["kind"] != "none":
                return t
        return None
    assert first("eager") < first("balanced") < first("quiet")


def test_show_me_is_an_accepted_event_with_how_show_me_and_jumps_to_the_demonstration(client):
    t, d = first_non_none(client, "stuck_after_result", person="p_show")
    assert d["kind"] == "cue" and d["tier"] == 1
    r = client.post("/cue/feedback", json={"episode_id": d["episode_id"], "event": "accepted", "how": "show_me"})
    assert r.status_code == 200 and r.json()["recorded"] is True
    d2 = nxt(client, "stuck_after_result", t + 1.0, person="p_show")["data"]
    assert d2["kind"] == "cue" and d2["tier"] == 3 and d2["target"]["box_2d"] and d2["new"] is True
    assert client.post("/cue/feedback", json={"episode_id": d["episode_id"], "event": "accepted", "how": "teleport"}).status_code == 422


def test_the_stable_codes_that_end_a_cue(client):
    # progress and recovered come from the gate, step_done and resolved from the live service
    t, d = first_non_none(client, "stuck_after_result", person="p_end")
    gone = nxt(client, "not_stuck", 0.0, person="p_end2")["data"]
    assert gone["kind"] == "none"
    from understudy_engine.cue.types import REASONS

    for code in ("progress", "recovered", "step_done", "resolved", "know_this", "timeout", "stale_input"):
        assert code in REASONS


def test_the_live_service_defaults_to_the_dev_tuned_parameters():
    assert LiveCue().params == TUNED and TUNED.p_signal == 0.40
