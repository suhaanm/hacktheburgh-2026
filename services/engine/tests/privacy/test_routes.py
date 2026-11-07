from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_privacy
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.privacy import egress, ledger
from understudy_engine.privacy.purposes import CalendarSuggestionWording
from understudy_engine.privacy.testing import CapturingPort


def make_app():
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    return app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    return TestClient(make_app())


def send_one(**over):
    base = dict(template="protect_focus_block", role="programmer", risk="low", learner={"meeting_h": 14.1, "focus_blocks_60": 3}, expert={"meeting_h": 8.0})
    base.update(over)
    return egress.send("calendar.suggestion_wording", CalendarSuggestionWording(**base), port=CapturingPort())


# --------------------------------------------------------------------------- flag
@pytest.mark.parametrize("path,method", [("/privacy/ledger", "get"), ("/privacy/summary", "get"), ("/privacy/purposes", "get"),
                                         ("/privacy/ledger/export", "get"), ("/privacy/ledger/clear", "post")])
def test_every_route_is_404_extension_off_when_the_flag_is_off(path, method):
    c = TestClient(make_app())
    r = getattr(c, method)(path)
    assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off"
    assert "UNDERSTUDY_X_PRIVACY" in r.json()["error"]["message"]


def test_master_flag_also_turns_it_on(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert TestClient(make_app()).get("/privacy/ledger").status_code == 200


# --------------------------------------------------------------------------- ledger
def test_ledger_is_newest_first_with_the_contract_fields_and_an_envelope(client):
    for i in range(3):
        send_one(learner={"meeting_h": 10 + i})
    body = client.get("/privacy/ledger").json()
    assert set(body) == {"meta", "data"} and len(body["data"]) == 3
    assert body["data"][0]["payload"]["learner"]["meeting_h"] == 12.0 and body["data"][2]["payload"]["learner"]["meeting_h"] == 10.0
    for row in body["data"]:
        assert {"t", "purpose", "schema", "fields", "payload", "model", "bytes"} <= set(row)
    assert body["meta"]["n"] == 3 and body["meta"]["n_unit"] == "runs" and body["meta"]["origin"] == "synthetic"   # CapturingPort = mock
    assert client.get("/privacy/ledger?limit=2").json()["data"][0]["payload"]["learner"]["meeting_h"] == 12.0
    assert len(client.get("/privacy/ledger?limit=2").json()["data"]) == 2


def test_ledger_limit_is_validated(client):
    assert client.get("/privacy/ledger?limit=0").status_code == 422
    assert client.get("/privacy/ledger?limit=100000").status_code == 422


def test_empty_ledger_is_an_empty_list(client):
    body = client.get("/privacy/ledger").json()
    assert body["data"] == [] and body["meta"]["n"] == 0


def test_origin_is_real_when_a_non_mock_line_exists_and_mixed_when_both(client):
    ledger.append({"purpose": "t.a", "payload": {}, "mock": False})
    assert client.get("/privacy/ledger").json()["meta"]["origin"] == "real"
    send_one()
    assert client.get("/privacy/ledger").json()["meta"]["origin"] == "mixed"


def test_export_is_jsonl_oldest_first(client):
    send_one(learner={"meeting_h": 10})
    send_one(learner={"meeting_h": 11})
    r = client.get("/privacy/ledger/export")
    lines = r.text.splitlines()
    assert r.status_code == 200 and len(lines) == 2 and "attachment" in r.headers["content-disposition"]
    assert json.loads(lines[0])["payload"]["learner"]["meeting_h"] == 10.0


# --------------------------------------------------------------------------- summary
def test_summary_matches_the_contract_and_is_honest(client):
    send_one()
    send_one()
    egress.send("git.habit_wording", {"habit": "no_tests", "learner_ratio": 0.2, "expert_ratio": 0.1, "n_commits": 30}, port=CapturingPort())
    d = client.get("/privacy/summary").json()["data"]
    assert d["calls"] == 3 and d["by_purpose"] == {"calendar.suggestion_wording": 2, "git.habit_wording": 1}
    assert d["last_call"]["purpose"] == "git.habit_wording" and d["last_call"]["mock"] is True
    assert d["canary"] == {"runs": 0, "planted": 0, "leaked": 0, "last_run": None}
    note = d["local_only_note"].lower()
    assert "asked for" in note and "does not claim that nothing else leaves" in note
    assert "nothing leaves this laptop" not in note and "no data leaves" not in note


def test_summary_shows_canary_results_after_a_canary_run(client):
    from understudy_engine.privacy.testing import canary_flow

    canary_flow("t.flow", lambda: {"events": [{"title": "x", "attendees": ["y"]}]},
                lambda fx, port: egress.send("calendar.suggestion_wording", dict(template="protect_focus_block", role="programmer", risk="low", learner={}, expert={}), port=port))
    c = client.get("/privacy/summary").json()["data"]["canary"]
    assert c["runs"] == 1 and c["planted"] == 2 and c["leaked"] == 0


# --------------------------------------------------------------------------- clear (worker only, this machine only)
def test_clear_works_for_the_worker_and_the_summary_remembers_it(client):
    send_one()
    send_one()
    r = client.post("/privacy/ledger/clear", headers={"x-understudy-actor": "worker"})
    assert r.status_code == 200 and r.json()["cleared"] == 2
    assert client.get("/privacy/ledger").json()["data"] == []
    s = client.get("/privacy/summary").json()["data"]
    assert s["calls"] == 0 and s["cleared"]["times"] == 1 and s["cleared"]["calls_removed"] == 2


def test_clear_defaults_to_the_worker_actor_like_the_other_writes(client):
    send_one()
    assert client.post("/privacy/ledger/clear").status_code == 200


@pytest.mark.parametrize("actor", ["agent", "model", "page", "tool", "system"])
def test_clear_is_refused_for_every_other_actor(client, actor):
    send_one()
    r = client.post("/privacy/ledger/clear", headers={"x-understudy-actor": actor})
    assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert len(ledger.read_all()) == 1


def test_clear_is_refused_from_a_foreign_origin_and_from_another_machine(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    send_one()
    c = TestClient(make_app())
    assert c.post("/privacy/ledger/clear", headers={"origin": "https://evil.example.org"}).status_code == 403
    assert c.post("/privacy/ledger/clear", headers={"origin": "http://localhost:5173"}).status_code == 200
    send_one()
    remote = TestClient(make_app(), client=("203.0.113.9", 4321))
    assert remote.post("/privacy/ledger/clear").status_code == 403
    assert len(ledger.read_all()) == 1


# --------------------------------------------------------------------------- purposes
def test_purposes_lists_what_may_be_sent_and_how_it_is_generalised(client):
    rows = {r["purpose"]: r for r in client.get("/privacy/purposes").json()["data"]}
    assert {"calendar.suggestion_wording", "git.habit_wording", "briefing.card_wording", "digest.meta"} <= set(rows)
    git = rows["git.habit_wording"]
    assert git["fields"] == ["habit", "learner_ratio", "expert_ratio", "n_commits"]
    assert git["bucketed"]["learner_ratio"] == ["ratio_10pct"] and git["bucketed"]["n_commits"] == ["count_lt5"]


def test_no_route_calls_a_model():
    import inspect

    src = inspect.getsource(routes_privacy)
    assert "egress.send" not in src and "get_model_port" not in src and "understudy_agent" not in src
