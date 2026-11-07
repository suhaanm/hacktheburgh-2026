from __future__ import annotations

from datetime import timedelta

import pytest

pytest.importorskip("understudy_agent", reason="run with: uv run --package understudy-agent pytest services/engine/tests/coach")

from fastapi.testclient import TestClient  # noqa: E402

from understudy_engine.api.app import create_app  # noqa: E402
from understudy_engine.coach import StuckScorer  # noqa: E402
from understudy_engine.store import EventStore  # noqa: E402

from .helpers import signature_events  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_PORT", "1")
    return tmp_path


@pytest.fixture()
def client(env):
    app = create_app(env, warm=False)
    app.state.coach.scorer = StuckScorer(fit=False)
    app.state.coach.tone = "short"
    return TestClient(app), env


def post_events(c, events):
    from understudy_engine.store import to_row

    r = c.post("/events", json=[to_row(e) for e in events])
    assert r.json()["rejected"] == []


def iso(e):
    return e.t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def test_next_returns_the_decision_in_the_analytic_envelope(client):
    c, _ = client
    evs = signature_events()
    post_events(c, evs)
    # poll twice at the end of the copy: the second consecutive signal opens the gate
    r1 = c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-2])})
    assert r1.status_code == 200
    r2 = c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-1])})
    body = r2.json()
    meta, d = body["meta"], body["data"]
    assert meta["origin"] == "synthetic" and meta["n_unit"] == "episodes" and "no model call" in meta["note"]
    assert d["action"] == "annotate" and d["target"]["zone"] == "cliff_button" and d["message"] == "Check cliff edges before you copy this result."
    assert set(d) >= {"person", "t", "action", "message", "why", "target", "missed", "confidence", "level", "chip", "decision_id", "task_id",
                      "step", "trigger", "reason_codes", "gate", "p_stuck", "p_source", "candidate", "mastery"}
    assert d["level"] == "L1" and d["chip"] == "full" and d["decision_id"].startswith("d_") and d["missed"][0] == "cliff_a"


def test_dry_run_changes_nothing_and_shows_the_candidate(client):
    c, root = client
    evs = signature_events()
    post_events(c, evs)
    for e in evs[-3:]:
        r = c.get("/coach/next", params={"person": "p_hand", "now": iso(e), "dry": 1}).json()["data"]
    assert r["action"] == "silent" and r["candidate"]["action"] == "annotate" and r["decision_id"] is None
    assert not [x for x in EventStore(root).read("synthetic", person="p_hand") if x.source == "coach"]


def test_unknown_person_and_bad_now(client):
    c, _ = client
    d = c.get("/coach/next", params={"person": "p_nobody"}).json()["data"]
    assert d["action"] == "silent" and d["reason_codes"] == ["no_events"]
    r = c.get("/coach/next", params={"person": "p_hand", "now": "yesterday"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_now"
    assert c.get("/coach/next").status_code == 422                       # person is required


def test_feedback_roundtrip_over_http(client):
    c, root = client
    evs = signature_events()
    post_events(c, evs)
    c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-2])})
    d = c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-1])}).json()["data"]
    later = (evs[-1].t + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    r = c.post("/coach/feedback", json={"decision_id": d["decision_id"], "outcome": "followed", "now": later})
    assert r.status_code == 200 and r.json()["recorded"] and r.json()["skill"]["CHECK_CLIFF"]["level"] == "L1"
    stored = [x for x in EventStore(root).read("synthetic", person="p_hand") if x.source == "coach"]
    assert [x.type for x in stored] == ["coach_shown", "coach_followed"]
    for bad in ({"decision_id": d["decision_id"], "outcome": "liked"}, {"decision_id": d["decision_id"], "outcome": "followed", "extra": 1}):
        assert c.post("/coach/feedback", json=bad).status_code == 422
    r = c.post("/coach/feedback", json={"decision_id": "d_nope", "outcome": "followed"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_decision"


def test_health_reports_the_coach_router(client):
    c, _ = client
    assert c.get("/health").json()["routers"]["coach"] is True
    paths = c.get("/openapi.json").json()["paths"]
    assert "/coach/next" in paths and "/coach/feedback" in paths and "/study/mode" in paths
