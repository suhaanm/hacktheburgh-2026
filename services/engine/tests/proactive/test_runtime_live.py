"""The agent runtime end to end, in process: a run spawned for a person leaves the file the finished-run reader looks for."""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.proactive import briefing as B
from understudy_engine.proactive import fire as F
from understudy_engine.proactive.candidates import Ctx
from understudy_engine.proactive.sources import Readers, read_runs
from understudy_engine.proactive.store import BriefingStore

from .conftest import P, make_readers

routes = pytest.importorskip("understudy_agent.runtime.routes")


def test_a_finished_run_for_the_person_becomes_a_result_card_and_a_press_queues_it(env, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X_AGENTS", "1")
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    params = {"card_id": "c_x", "person": P, "prepared": {"text": "Look at the commits.", "steps": ["one"]}, "prepared_hash": "p:1", "habit": "smaller_commits"}
    other = c.post("/agents/spawn", json={"kind": "programming.commit_analyst", "params": {"person": "p_other"}, "mode": "foreground", "person": "p_other"})
    mine = c.post("/agents/spawn", json={"kind": "programming.commit_analyst", "params": params, "mode": "foreground", "person": P})
    assert mine.status_code == 200 and other.status_code == 200, (mine.text, other.text)
    for _ in range(120):
        rows = c.get("/agents/runs", params={"person": P}).json()
        if rows and all(r["state"] in ("done", "partial", "failed", "stopped") for r in rows):
            break
        time.sleep(0.5)
    from datetime import datetime, timezone

    t = datetime.now(timezone.utc)
    rd = read_runs(Ctx(P, t))
    assert rd.available and [i["run_id"] for i in rd.items] == [mine.json()["run_id"]] and rd.items[0]["state"] in ("done", "partial")
    assert rd.items[0]["children"] >= 1                                                     # the other person's run is nobody else's morning
    readers = Readers(routines=make_readers().routines, skills=make_readers().skills, calendar=make_readers().calendar, git=make_readers().git, runs=read_runs)
    store = BriefingStore(env.data / "briefing.json")
    b = B.build(P, store=store, readers=readers, now=t)
    assert [x.kind for x in b.cards] == ["agent_result"]
    out = F.fire(b.cards[0].id, actor="worker", store=store, readers=readers, now=t)
    assert out["queue_id"].startswith("q_") and "run_id" not in out
    again = B.build(P, store=store, readers=readers, now=t)                                  # viewed now: not raised again
    assert [x.kind for x in again.cards if x.status == "ready"] == []


def test_the_spawner_attributes_the_run_to_the_person():
    import httpx
    import json

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["actor"] = json.loads(request.content), request.headers.get("x-understudy-actor")
        return httpx.Response(200, json={"run_id": "r_abc123"})

    F.default_spawner(transport=httpx.MockTransport(handler))("programming.test_gap", {"person": P, "card_id": "c_1"}, "foreground")
    assert seen["body"]["person"] == P and seen["actor"] == "worker" and seen["body"]["kind"] == "programming.test_gap"
