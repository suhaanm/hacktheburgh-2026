"""The /briefing routes (contract shapes, worker-only writes) and the demo seed."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_proactive as R
from understudy_engine.proactive import seed as S
from understudy_engine.proactive.briefing import summary_text
from understudy_engine.proactive.store import BriefingStore

from .conftest import NOW, P, cal_row, make_readers, routine_row, skill_row

CARD_KEYS = {"id", "kind", "title", "why", "prepared", "risk_class", "sources", "source_tags", "expires_at", "status"}


@pytest.fixture
def client(env, monkeypatch):
    monkeypatch.setattr(R, "Readers", lambda: make_readers(routines=[routine_row()], skills=[skill_row()], calendar=[cal_row()]))
    app = FastAPI()
    app.include_router(R.router)
    c = TestClient(app)
    c.env = env
    return c


def _cards(client):
    r = client.get("/briefing", params={"person": P, "now": "2026-11-08T08:00:00Z"})
    assert r.status_code == 200, r.text
    return r.json()


def test_get_briefing_has_the_contract_shape(client):
    body = _cards(client)
    assert set(body) == {"meta", "data"} and body["data"]["cap"] == 3 and body["data"]["generated_at"]
    cards = body["data"]["cards"]
    assert 1 <= len(cards) <= 3
    for c in cards:
        assert CARD_KEYS <= set(c) and c["status"] == "ready" and c["risk_class"] in ("normal", "outward", "irreversible")
        assert c["kind"] in ("practice", "automate", "focus_block", "git_habit", "agent_result")
        assert set(c["prepared"]) <= {"text", "steps", "artifact_ref"} and (c["prepared"].get("text") or c["prepared"].get("steps"))
        assert c["sources"] == c["source_tags"] and isinstance(c["sources"], list) and c["expires_at"].endswith("Z")
    m = body["meta"]
    assert m["origin"] in ("synthetic", "real", "mixed") and m["n_unit"] == "decisions" and m["interval_level"] == 0.95
    assert body["data"]["sources"]["calendar"]["available"] is True


def test_unknown_person_without_a_default_is_a_plain_404(client, monkeypatch):
    monkeypatch.setattr(R, "_person", lambda p: p)
    r = client.get("/briefing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"


def test_bad_now_is_a_plain_422(client):
    r = client.get("/briefing", params={"person": P, "now": "tomorrow-ish"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_put_prepared_takes_the_prepared_object_as_the_body(client):
    card = _cards(client)["data"]["cards"][0]
    r = client.put(f"/briefing/{card['id']}/prepared", json={"text": "My words.", "steps": ["a", "b"]}, headers={"X-Understudy-Actor": "worker"})
    assert r.status_code == 200 and r.json()["prepared"] == {"text": "My words.", "steps": ["a", "b"]} and r.json()["edited"] is True
    again = next(c for c in _cards(client)["data"]["cards"] if c["id"] == card["id"])
    assert again["prepared"] == {"text": "My words.", "steps": ["a", "b"]}
    assert client.put(f"/briefing/{card['id']}/prepared", json={"prepared": {"text": "Wrapped form."}}).json()["prepared"] == {"text": "Wrapped form."}
    assert client.put(f"/briefing/{card['id']}/prepared", json={"steps": "no"}).status_code == 422
    assert client.put("/briefing/c_nope/prepared", json={"text": "x"}).status_code == 404


def test_fire_with_the_approval_actor_returns_a_queue_id_and_the_item_is_pending(client):
    pytest.importorskip("understudy_agent")
    cards = _cards(client)["data"]["cards"]
    auto = next(c for c in cards if c["kind"] == "automate")
    r = client.post(f"/briefing/{auto['id']}/fire", headers={"X-Understudy-Actor": "worker_approval", "Origin": "http://localhost:5173"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["queue_id"].startswith("q_") and "run_id" not in out and out["status"] == "fired"
    item = json.loads((client.env.data / "queue" / f"{out['queue_id']}.json").read_text())
    assert item["status"] == "pending" and item["routine_id"] == "calc-entry-3x"
    again = client.post(f"/briefing/{auto['id']}/fire")
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_ready" and again.json()["queue_id"] == out["queue_id"]


@pytest.mark.parametrize("actor", ["agent", "model", "page", "tool"])
def test_other_actors_are_refused_and_nothing_is_created(client, actor):
    cid = _cards(client)["data"]["cards"][0]["id"]
    for method, path, body in (("post", f"/briefing/{cid}/fire", None), ("post", f"/briefing/{cid}/dismiss", {"mode": "never"}),
                               ("put", f"/briefing/{cid}/prepared", {"text": "x"})):
        r = getattr(client, method)(path, json=body, headers={"X-Understudy-Actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert not (client.env.data / "queue").exists() or not list((client.env.data / "queue").glob("*.json"))
    assert next(c for c in _cards(client)["data"]["cards"] if c["id"] == cid)["status"] == "ready"
    audit = (client.env.data / "audit.jsonl").read_text()
    assert "briefing_write_refused" in audit


def test_a_foreign_origin_is_refused(client):
    cid = _cards(client)["data"]["cards"][0]["id"]
    r = client.post(f"/briefing/{cid}/fire", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_dismiss_never_is_recorded_and_honoured(client):
    cards = _cards(client)["data"]["cards"]
    cal = next(c for c in cards if c["kind"] == "focus_block")
    r = client.post(f"/briefing/{cal['id']}/dismiss", json={"mode": "never"}, headers={"X-Understudy-Actor": "worker_approval"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed" and r.json()["mode"] == "never"
    after = client.get("/briefing", params={"person": P, "refresh": 1, "now": "2026-11-30T08:00:00Z"}).json()["data"]["cards"]
    assert not [c for c in after if c["kind"] == "focus_block" and c["status"] == "ready"]
    st = BriefingStore().person(P)
    assert st["suppress"]["kind:focus_block"]["until"] is None and st["labels"][-1]["accepted"] is False
    assert client.post(f"/briefing/{cal['id']}/dismiss", json={"mode": "forever"}).status_code in (404, 409, 400)


def test_dismiss_not_now_defaults(client):
    cid = _cards(client)["data"]["cards"][0]["id"]
    r = client.post(f"/briefing/{cid}/dismiss")
    assert r.status_code == 200 and r.json()["mode"] == "not_now"


def test_text_endpoint_is_safe_to_speak(client):
    t = client.get("/briefing/text", params={"person": P, "now": "2026-11-08T08:00:00Z"}).json()["text"]
    assert t.startswith("Good morning.") and "calc" not in t.lower() and "Automate" not in t
    assert R.briefing_text is not None


def test_the_flag_helper_follows_the_environment(monkeypatch):
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_PROACTIVE"):
        monkeypatch.delenv(k, raising=False)
    assert R.enabled() is False
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    assert R.enabled() is True
    monkeypatch.delenv("UNDERSTUDY_X_PROACTIVE")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert R.enabled() is True


# ----------------------------------------------------------------------------------------------- seed
def test_seed_demo_makes_three_cards_idempotently(env):
    readers = make_readers(routines=[routine_row()], skills=[skill_row()], available={"calendar": False})
    out = S.seed_demo(env.home, env.data, now=NOW, readers=readers)
    assert out["seeded"] is True and sorted(out["kinds"]) == ["automate", "focus_block", "practice"]
    store = BriefingStore(env.data / "briefing.json")
    first = store.person(S.DEMO_PERSON)
    assert first["seed"] == S.SEED_TAG and len(first["cards"]) == 3 and first["generated_at"] == "2026-11-08T08:00:00Z"
    again = S.seed_demo(env.home, env.data, now=NOW.replace(day=9), readers=readers)
    assert again["seeded"] is False and store.person(S.DEMO_PERSON) == first
    cal = next(c for c in first["cards"] if c["kind"] == "focus_block")
    assert cal["verify_note"].startswith("Not re-checked") and cal["origin"] == "synthetic"
    assert all(c["ranking"]["note"].startswith("Seeded for the demo") for c in first["cards"])
    assert S.seed_demo(env.home, env.data, now=NOW, readers=readers, reseed=True)["seeded"] is True


def test_seeded_cards_survive_the_first_read_when_the_state_matches(env, monkeypatch):
    readers = make_readers(routines=[routine_row()], skills=[skill_row()], available={"calendar": False})
    S.seed_demo(env.home, env.data, now=NOW, readers=readers)
    from understudy_engine.proactive import briefing as B

    b = B.build(S.DEMO_PERSON, store=BriefingStore(env.data / "briefing.json"), readers=readers, now=NOW)
    assert sorted(c.kind for c in b.cards) == ["automate", "focus_block", "practice"] and b.dropped == []
    assert summary_text(b.cards).startswith("Good morning. You have three suggestions ready")


def test_seed_does_not_invent_a_card_for_a_source_that_has_nothing(env):
    readers = make_readers(routines=[routine_row()], skills=[], available={"calendar": False})      # skills readable but nothing to practise
    out = S.seed_demo(env.home, env.data, now=NOW, readers=readers)
    assert sorted(out["kinds"]) == ["automate", "focus_block"]
