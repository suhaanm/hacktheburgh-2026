from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.awareness import routes
from understudy_engine.awareness.features import AWARENESS_COLUMNS

from .conftest import glance_event, window_event


def app() -> FastAPI:
    a = FastAPI()
    a.include_router(routes.router)
    return a


@pytest.fixture()
def client(flag_on):
    return TestClient(app())


def test_every_route_answers_404_extension_off_when_the_flag_is_off():
    c = TestClient(app())
    assert routes.enabled() is False
    for method, path, kw in (("post", "/awareness/events", {"json": [window_event()]}), ("get", "/awareness/summary?person=p_demo01", {}),
                             ("get", "/awareness/windows?person=p_demo01", {}), ("get", "/awareness/columns", {}), ("post", "/awareness/clear", {"json": {}})):
        r = getattr(c, method)(path, **kw)
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off", path


def test_the_master_flag_also_turns_it_on(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert routes.enabled() is True
    assert TestClient(app()).get("/awareness/columns").status_code == 200


def test_post_accepts_one_event_or_a_list_and_reports_each_rejection_without_its_value(client):
    r = client.post("/awareness/events", json=window_event(1))
    assert r.status_code == 200 and r.json() == {"accepted": 1, "duplicates": 0, "rejected": []}
    bad = window_event(3)
    bad["cursor"]["x"] = 123456
    r = client.post("/awareness/events", json=[window_event(2, t="2026-11-07T10:00:02.000Z"), bad, glance_event(4)])
    body = r.json()
    assert r.status_code == 200 and body["accepted"] == 2 and [x["index"] for x in body["rejected"]] == [1]
    assert "123456" not in r.text
    again = client.post("/awareness/events", json=[window_event(1)]).json()
    assert again["accepted"] == 0 and again["duplicates"] == 1


def test_post_refuses_bad_json_and_oversized_batches(client):
    assert client.post("/awareness/events", content=b"{not json", headers={"content-type": "application/json"}).status_code == 422
    big = [window_event(i, t=f"2026-11-07T11:{i // 60 % 60:02d}:{i % 60:02d}.000Z") for i in range(501)]
    r = client.post("/awareness/events", json=big)
    assert r.status_code == 422 and r.json()["error"]["code"] == "batch_too_large"


def test_events_are_only_accepted_from_this_machine_and_the_app(flag_on):
    remote = TestClient(app(), client=("203.0.113.9", 4000))
    r = remote.post("/awareness/events", json=[window_event(1)])
    assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    local = TestClient(app())
    assert local.post("/awareness/events", json=[window_event(1)], headers={"origin": "https://evil.example"}).status_code == 403
    # http_guard: the exact allow-list only (the dashboard origins, plus $UNDERSTUDY_ALLOWED_ORIGINS); a custom scheme is foreign, and the
    # desktop's main process (no Origin header) is the app's way in. (The app-level middleware also wants the actor header with an Origin.)
    assert local.post("/awareness/events", json=[window_event(1)], headers={"origin": "app://understudy"}).status_code == 403
    assert local.post("/awareness/events", json=[window_event(2)], headers={"origin": "http://localhost:5173", "x-understudy-actor": "worker"}).status_code == 200
    assert local.post("/awareness/events", json=[window_event(3)]).status_code == 200


def test_summary_and_windows_carry_the_envelope_and_the_honest_note(client):
    client.post("/awareness/events", json=[window_event(1), window_event(2, t="2026-11-07T10:00:02.000Z"), glance_event(3)])
    s = client.get("/awareness/summary?person=p_demo01").json()
    assert s["meta"]["origin"] == "real" and s["meta"]["n"] == 2 and s["meta"]["n_unit"] == "windows"
    assert "No coordinates" in s["meta"]["note"]
    assert s["data"]["windows"] == 2 and s["data"]["glances"] == 1
    w = client.get("/awareness/windows?person=p_demo01&limit=1").json()
    assert len(w["data"]["windows"]) == 1 and w["data"]["windows"][0]["t"] == "2026-11-07T10:00:02.000Z"
    assert set(w["data"]["windows"][0]) == {"t", "window_s", "app_kind", "sys_idle_s", "cursor", "glances"}
    both = client.get("/awareness/windows?person=p_demo01").json()["data"]["windows"][0]
    assert both["glances"][0]["blocker"] == "cannot_find_control"
    assert client.get("/awareness/summary?person=p_demo01&origin=synthetic").json()["meta"]["origin"] == "synthetic"


def test_query_validation(client):
    assert client.get("/awareness/summary?person=alice").status_code == 422
    assert client.get("/awareness/summary?person=p_demo01&origin=fake").status_code == 422
    assert client.get("/awareness/summary?person=p_demo01&since=yesterday").status_code == 422
    assert client.get("/awareness/windows?person=p_demo01&limit=0").status_code == 422
    assert client.get("/awareness/summary").status_code == 422
    assert client.get("/awareness/windows?person=../x").status_code == 422


def test_columns_lists_the_hazard_feature_names(client):
    d = client.get("/awareness/columns").json()
    assert d["data"]["columns"] == list(AWARENESS_COLUMNS) and d["data"]["span_s"] == 30


def test_clear_needs_the_worker_actor_and_this_machine(client, flag_on):
    client.post("/awareness/events", json=[window_event(1), window_event(2, person="p_other")])
    assert client.post("/awareness/clear", json={}).status_code == 403
    assert client.post("/awareness/clear", json={}, headers={"x-understudy-actor": "agent"}).status_code == 403
    remote = TestClient(app(), client=("203.0.113.9", 4000))
    assert remote.post("/awareness/clear", json={}, headers={"x-understudy-actor": "worker"}).status_code == 403
    r = client.post("/awareness/clear", json={"person": "p_other"}, headers={"x-understudy-actor": "worker"})
    assert r.status_code == 200 and r.json()["cleared"] == 1
    assert client.get("/awareness/summary?person=p_demo01").json()["data"]["windows"] == 1
    assert client.post("/awareness/clear", json={"person": "bad id"}, headers={"x-understudy-actor": "worker"}).status_code == 422
    assert client.post("/awareness/clear", json={"origin": "x"}, headers={"x-understudy-actor": "worker"}).status_code == 422
    assert client.post("/awareness/clear", json={}, headers={"x-understudy-actor": "worker"}).json()["cleared"] == 1
