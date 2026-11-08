"""GET /calendar/week and /calendar/suggestions: flag gating, envelope, shapes, errors, no text."""
from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_calendar
from understudy_engine.calendar.features import CONTRACT_KEYS


@pytest.fixture()
def client(monkeypatch, store):
    monkeypatch.setenv("UNDERSTUDY_X_CALENDAR", "1")
    monkeypatch.setattr(routes_calendar, "_store", lambda: store)
    app = FastAPI()
    app.include_router(routes_calendar.router)
    return TestClient(app)


def test_every_route_is_404_when_the_flag_is_off(monkeypatch, store):
    monkeypatch.delenv("UNDERSTUDY_X_CALENDAR", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    monkeypatch.setattr(routes_calendar, "_store", lambda: store)
    app = FastAPI()
    app.include_router(routes_calendar.router)
    c = TestClient(app)
    for path in ("/calendar/week?person=p_nov05", "/calendar/suggestions?person=p_nov05", "/calendar/people", "/calendar/catalogue"):
        r = c.get(path)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found" and "UNDERSTUDY_X_CALENDAR" in r.json()["error"]["message"]


def test_master_flag_turns_it_on(monkeypatch, store):
    monkeypatch.delenv("UNDERSTUDY_X_CALENDAR", raising=False)
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    monkeypatch.setattr(routes_calendar, "_store", lambda: store)
    app = FastAPI()
    app.include_router(routes_calendar.router)
    assert TestClient(app).get("/calendar/catalogue").status_code == 200


def test_week_envelope_and_contract_shape(client):
    r = client.get("/calendar/week", params={"person": "p_nov05", "week": "2026-W43"})
    assert r.status_code == 200
    body = r.json()
    meta, d = body["meta"], body["data"]
    assert meta["origin"] == "synthetic" and meta["n_unit"] == "days" and meta["interval_level"] == 0.95 and "expert reference" in meta["note"] and "generated" not in meta["note"].lower() and meta["generated_at"]
    assert d["week"] == "2026-W43" and len(d["days"]) == 7
    assert set(CONTRACT_KEYS) <= set(d["features"]) and set(CONTRACT_KEYS) <= set(d["expert"])
    for day in d["days"] + d["expert"]["days"]:
        assert set(day) >= {"dow", "blocks"}
        for b in day["blocks"]:
            assert re.fullmatch(r"\d\d:\d\d", b["start"]) and re.fullmatch(r"\d\d:\d\d", b["end"]) and b["kind"] in ("meeting", "focus", "break", "offscreen", "free")
            assert b.get("n_attendees_bucket", "lt5") in ("lt5", "5to9", "10plus")
    assert len(d["expert"]["days"]) == 7 and d["expert"]["days"][0]["blocks"]
    assert [x["feature"] for x in d["gap"]["rows"]][:8] == list(CONTRACT_KEYS)
    row = d["gap"]["rows"][0]
    assert set(row) >= {"feature", "learner", "expert", "delta", "ci"} and len(row["ci"]) == 2 and row["ci"][0] <= row["delta"] <= row["ci"][1] + 1e-9


def test_default_week_is_the_latest_and_default_person_is_the_demo_persona(client):
    a = client.get("/calendar/week", params={"person": "p_nov05"}).json()["data"]
    assert a["week"] == "2026-W44"
    b = client.get("/calendar/week").json()["data"]
    assert b["person"] == "p_ninetofive"
    assert client.get("/calendar/week", params={"person": "p_nov05", "week": "2026-10-20"}).json()["data"]["week"] == "2026-W43"


def test_errors_are_plain_and_specific(client):
    r = client.get("/calendar/week", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person" and "p_ninetofive" in r.json()["error"]["message"]
    r = client.get("/calendar/week", params={"person": "p_nov05", "week": "banana"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_week"
    r = client.get("/calendar/week", params={"person": "p_nov05", "week": "2027-W10"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_week" and "2026-W42" in r.json()["error"]["message"]
    r = client.get("/calendar/suggestions", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"
    assert client.get("/calendar/suggestions", params={"person": "p_nov05", "limit": 99}).status_code == 422


def test_suggestions_shape_and_limit(client):
    r = client.get("/calendar/suggestions", params={"person": "p_nightowl"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) >= 4 and all(set(s) >= {"id", "template", "text", "numbers", "expert_ref", "risk", "can_draft"} for s in data)
    assert all(s["risk"] == "low" and isinstance(s["can_draft"], bool) and s["source"] == "templated" for s in data)
    assert [s["priority"] for s in data] == sorted((s["priority"] for s in data), reverse=True)
    assert len(client.get("/calendar/suggestions", params={"person": "p_nightowl", "limit": 2}).json()["data"]) == 2
    assert client.get("/calendar/suggestions", params={"person": "p_exp01"}).json()["data"] == []
    assert client.get("/calendar/suggestions", params={"person": "p_nov01"}).json()["data"] == []        # the clean control
    one = client.get("/calendar/suggestions", params={"person": "p_nightowl", "week": "2026-W42"}).json()
    assert one["meta"]["n"] == 1 and one["data"][0]["week"] == "2026-W42"


def test_reword_is_ignored_while_the_privacy_layer_is_off(client, monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_PRIVACY", raising=False)
    r = client.get("/calendar/suggestions", params={"person": "p_nightowl", "reword": 1}).json()
    assert all(s["source"] == "templated" for s in r["data"]) and "privacy layer is off" in r["meta"]["note"]


def test_reword_goes_through_the_guard_when_the_privacy_layer_is_on(client, monkeypatch, tmp_path):
    from understudy_engine.privacy.testing import hermetic
    hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    r = client.get("/calendar/suggestions", params={"person": "p_nightowl", "reword": 1, "limit": 2}).json()
    # mock mode: the stub's sentence is not shown as wording; the template stays and the ledger line is still written
    assert all(s["source"] == "templated" and s.get("ledger_id") for s in r["data"])
    from understudy_engine.privacy import ledger
    assert len([x for x in ledger.read_all() if x.get("purpose") == "calendar.suggestion_wording"]) == 2


def test_people_and_catalogue(client):
    people = client.get("/calendar/people").json()
    assert people["meta"]["n"] == 28 and {p["group"] for p in people["data"]} == {"persona", "expert", "novice"}
    assert all(p["weeks"] == ["2026-W42", "2026-W43", "2026-W44"] for p in people["data"])
    cat = client.get("/calendar/catalogue").json()["data"]
    assert len(cat) >= 8 and all({"id", "title", "can_draft"} <= set(c) for c in cat)


def test_responses_hold_no_free_text(client):
    """Every string in a week response is an enum, a label, a time or an id from a small set."""
    d = client.get("/calendar/week", params={"person": "p_nov05", "week": "2026-W43"}).json()["data"]
    allowed_re = re.compile(r"^(\d\d:\d\d|\d{4}-\d\d-\d\d|\d{4}-W\d\d|[a-z0-9_\-]+|[A-Z_]+|Europe/London|UTC)$")
    long_strings = []

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for v in x:
                walk(v, path)
        elif isinstance(x, str) and not allowed_re.match(x):
            long_strings.append((path, x))
    walk(d)
    # only the plain-language descriptions the server writes itself may be longer strings
    assert {p for p, _ in long_strings} <= {".expert.reference", ".gap.interval"}, long_strings
    assert not any("@" in v for _, v in long_strings)
