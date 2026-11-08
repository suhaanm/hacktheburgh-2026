"""The HTTP routes of the task API through the real agent app and the real shared guard: shapes, actors, the token on the consent
route, stop without a token, the kill route, the SSE stream, skills settings."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from understudy_agent.tasks import TaskManager, manager as mgr_mod
from understudy_agent.tasks.routes import sse_stream

from .conftest import claude_text, wait_for
from .test_manager import CARD_KEYS, ROW_KEYS

ORIGIN = "http://localhost:5173"


def worker(extra=None, actor="worker"):
    h = {"X-Understudy-Actor": actor, "Content-Type": "application/json"}
    h.update(extra or {})
    return h


@pytest.fixture
def app_client(make_manager, monkeypatch):
    """The real agent app (sandbox not started) with a manager that uses the fake claude and a fake model."""
    from understudy_agent.server import create_app

    m = make_manager()
    monkeypatch.setattr(mgr_mod, "_default", m)
    app = create_app(base_urls={"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"},
                     autostart_sandbox=False, shared_sites=False)
    app.state.tasks = m
    with TestClient(app) as c:
        c.manager = m
        yield c


@pytest.fixture
def strict_client(make_manager, monkeypatch, tmp_path):
    """Production-like guard: no relaxation, a per-boot token, a browser Origin, the service's own Host."""
    monkeypatch.setenv("UNDERSTUDY_GUARD_STRICT", "1")
    from understudy_agent.server import create_app

    m = make_manager()
    app = create_app(base_urls={"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"},
                     autostart_sandbox=False, shared_sites=False)
    app.state.tasks = m
    with TestClient(app, base_url="http://127.0.0.1:7710") as c:
        c.manager = m
        c.token = (Path(__import__("os").environ["UNDERSTUDY_DATA_DIR"]) / ".token").read_text().strip()
        yield c


def test_post_tasks_follows_the_contract(app_client):
    r = app_client.post("/tasks", json={"text": claude_text("ok"), "source": "typed"}, headers=worker())
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"task_id", "route", "summary", "needs_consent", "question"} and body["route"] == "claude_agent"
    assert set(body["needs_consent"]) == CARD_KEYS and body["question"] is None
    tid = body["task_id"]
    rows = app_client.get("/tasks").json()
    assert [x["task_id"] for x in rows] == [tid] and set(rows[0]) == ROW_KEYS
    d = app_client.get(f"/tasks/{tid}").json()
    assert set(d) == ROW_KEYS | {"steps", "answer"} and d["steps"] == [] and d["state"] == "waiting_consent"
    assert app_client.get("/tasks/tk_00000000").status_code == 404
    assert app_client.get("/tasks/not-an-id").json()["error"]["code"] == "no_such_task"


def test_bad_bodies_are_422(app_client):
    for body in ({}, {"text": ""}, {"text": "x" * 4001}, {"text": 5}, {"text": "hello", "source": "telepathy"}, [1]):
        r = app_client.post("/tasks", json=body, headers=worker())
        assert r.status_code == 422 and r.json()["error"]["code"] == "bad_body", body
    r = app_client.post("/tasks", content=b"not json", headers=worker())
    assert r.status_code == 422


def test_actors_other_than_the_worker_cannot_create_answer_stop_or_consent(app_client):
    tid = app_client.post("/tasks", json={"text": claude_text("ok"), "source": "typed"}, headers=worker()).json()["task_id"]
    for actor in ("agent", "model", "tool", "page", "extension"):
        h = worker(actor=actor)
        assert app_client.post("/tasks", json={"text": "hello there?", "source": "typed"}, headers=h).status_code == 403
        assert app_client.post(f"/tasks/{tid}/stop", json={}, headers=h).status_code == 403
        assert app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=h).status_code == 403
        assert app_client.post("/skills/settings", json={"use_claude_skills": False}, headers=h).status_code == 403
    assert app_client.manager.get(tid).state == "waiting_consent"
    # the voice actor may create, answer and stop, never consent
    h = worker(actor="voice")
    assert app_client.post("/tasks", json={"text": "what time is it?", "source": "voice"}, headers=h).status_code == 201
    assert app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=h).status_code == 403
    # a plain worker actor cannot press the consent button either: only worker_approval
    assert app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=worker()).status_code == 403
    assert app_client.manager.get(tid).state == "waiting_consent"
    assert app_client.post(f"/tasks/{tid}/stop", json={}, headers=h).status_code == 200


def test_consent_route_runs_the_task_and_reports(app_client):
    tid = app_client.post("/tasks", json={"text": claude_text("ok"), "source": "typed"}, headers=worker()).json()["task_id"]
    r = app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=worker(actor="worker_approval"))
    assert r.status_code == 200 and r.json()["state"] == "running" and set(r.json()) == ROW_KEYS
    assert wait_for(lambda: app_client.get(f"/tasks/{tid}").json()["state"] == "done", 15)
    d = app_client.get(f"/tasks/{tid}").json()
    assert d["result"] == "Wrote summary.md with three rows." and d["cost_usd"] == 0.0123 and d["open"]["kind"] == "file" and d["steps"][0] == "Started"
    r = app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=worker(actor="worker_approval"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_waiting"


def test_consent_needs_the_token_stop_does_not(strict_client):
    c = strict_client
    h = {"Origin": ORIGIN, "X-Understudy-Actor": "worker", "Content-Type": "application/json"}
    r = c.post("/tasks", json={"text": claude_text("hang"), "source": "typed"}, headers=h)
    assert r.status_code == 201, r.text
    tid = r.json()["task_id"]
    ha = {**h, "X-Understudy-Actor": "worker_approval"}
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=ha)
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_required"
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers={**ha, "X-Understudy-Token": "0" * 64})
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_invalid"
    assert c.manager.get(tid).state == "waiting_consent"
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers={**ha, "X-Understudy-Token": c.token})
    assert r.status_code == 200 and r.json()["state"] == "running"
    assert wait_for(lambda: c.manager.get(tid).pid, 10)
    r = c.post(f"/tasks/{tid}/stop", json={}, headers=h)                                      # stopping needs no token
    assert r.status_code == 200 and r.json()["state"] == "stopped" and r.json()["reason"] == "Stopped by you."


def test_a_foreign_origin_or_host_cannot_write(strict_client):
    c = strict_client
    r = c.post("/tasks", json={"text": "hello?", "source": "typed"},
               headers={"Origin": "https://evil.example", "X-Understudy-Actor": "worker", "Content-Type": "application/json"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_refused"
    r = c.post("/tasks", json={"text": "hello?", "source": "typed"},
               headers={"Origin": ORIGIN, "Content-Type": "application/json"})                   # no actor with an Origin
    assert r.status_code == 403 and r.json()["error"]["code"] == "actor_required"
    r = c.post("/tasks", content=b'{"text":"hello?"}', headers={"Origin": ORIGIN, "X-Understudy-Actor": "worker", "Content-Type": "text/plain"})
    assert r.status_code == 415
    r = c.get("/tasks", headers={"Host": "evil.example"})
    assert r.status_code == 421


def test_the_kill_route_stops_running_tasks(app_client):
    c = app_client
    tid = c.post("/tasks", json={"text": claude_text("hang"), "source": "typed"}, headers=worker()).json()["task_id"]
    c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=worker(actor="worker_approval"))
    assert wait_for(lambda: c.manager.get(tid).pid, 10)
    try:
        assert c.post("/kill", headers={"X-Understudy-Actor": "worker"}).status_code == 200
        t = c.manager.get(tid)
        assert t.state == "stopped" and "kill switch" in t.reason
    finally:
        c.post("/kill/clear", headers={"X-Understudy-Actor": "worker"})


def test_answer_a_question_card_over_http(app_client):
    r = app_client.post("/tasks", json={"text": "sort this out for me", "source": "typed"}, headers=worker()).json()
    assert r["route"] == "unclear" and r["needs_consent"] is None and len(r["question"]["options"]) == 4
    tid = r["task_id"]
    assert app_client.post(f"/tasks/{tid}/answer", json={"option_id": "nope"}, headers=worker()).status_code == 422
    r = app_client.post(f"/tasks/{tid}/answer", json={"option_id": "answer"}, headers=worker())
    assert r.status_code == 200 and r.json()["route"] == "answer"
    assert wait_for(lambda: app_client.get(f"/tasks/{tid}").json()["state"] == "done", 10)
    assert app_client.get(f"/tasks/{tid}").json()["answer"].startswith("Edinburgh")


def test_open_reveals_only_the_recorded_path(app_client, monkeypatch):
    calls = []
    import subprocess as sp

    monkeypatch.setattr(sp, "run", lambda *a, **k: calls.append(a[0]) or sp.CompletedProcess(a[0], 0))
    monkeypatch.setattr("sys.platform", "darwin")
    tid = app_client.post("/tasks", json={"text": claude_text("ok"), "source": "typed"}, headers=worker()).json()["task_id"]
    assert app_client.post(f"/tasks/{tid}/open", json={}, headers=worker()).json()["error"]["code"] == "nothing_to_open"
    app_client.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=worker(actor="worker_approval"))
    assert wait_for(lambda: app_client.get(f"/tasks/{tid}").json()["state"] == "done", 15)
    r = app_client.post(f"/tasks/{tid}/open", json={}, headers=worker())
    assert r.status_code == 200 and r.json() == {"opened": True}
    t = app_client.manager.get(tid)
    assert calls == [["open", "-R", t.open["path"]]]                                           # reveal only: never executes anything
    assert app_client.post("/tasks/tk_00000000/open", json={}, headers=worker()).status_code == 404


def test_sse_stream_snapshot_events_and_heartbeat(make_manager):
    m = make_manager(offline=True)
    m.create("what time is it?", "typed")                                                       # one finished task before connecting

    async def collect():
        out = []
        gen = sse_stream(m, max_seconds=1.2, heartbeat_s=0.4, poll_s=0.02)
        task = asyncio.ensure_future(_drain(gen, out))
        await asyncio.sleep(0.2)
        await asyncio.to_thread(m.create, "what day is it?", "typed")
        await task
        return out

    async def _drain(gen, out):
        async for chunk in gen:
            out.append(chunk)

    out = asyncio.run(collect())
    parsed = []
    for chunk in out:
        lines = chunk.strip().splitlines()
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ") and chunk.endswith("\n\n")
        parsed.append((lines[0][7:], json.loads(lines[1][6:])))
    assert parsed[0][0] == "snapshot" and len(parsed[0][1]["tasks"]) == 1 and set(parsed[0][1]["tasks"][0]) == ROW_KEYS
    names = [n for n, _ in parsed]
    assert "task_started" in names and "task_finished" in names and "heartbeat" in names
    assert all(set(d) == ROW_KEYS for n, d in parsed if n.startswith("task_"))
    assert set(next(d for n, d in parsed if n == "heartbeat")) == {"t"}


def test_sse_route_streams_events_and_is_not_read_as_a_task_id(app_client):
    import threading

    res: dict = {}

    def go():
        with app_client.stream("GET", "/tasks/events") as r:
            res["ct"], res["cache"] = r.headers["content-type"], r.headers.get("cache-control")
            lines = []
            for line in r.iter_lines():
                lines.append(line)
                if len(lines) == 2:
                    break
            res["lines"] = lines

    th = threading.Thread(target=go, daemon=True)
    th.start()
    th.join(10)
    assert not th.is_alive(), "the stream did not start"
    assert res["ct"].startswith("text/event-stream") and res["cache"] == "no-store"
    assert res["lines"][0] == "event: snapshot" and json.loads(res["lines"][1][6:]) == {"tasks": []}


def test_skills_listing_and_settings_over_http(app_client):
    sk = Path.home() / ".claude" / "skills" / "pdf-tools"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: pdf-tools\ndescription: Read and merge PDF files\n---\nbody\n")
    kn = Path.home() / "Knack" / "skills" / "house-style"
    kn.mkdir(parents=True)
    (kn / "SKILL.md").write_text("---\nname: house-style\ndescription: Our house writing style\n---\nbody\n")
    r = app_client.get("/skills?refresh=1").json()
    assert r["use_claude_skills"] is True and r["off"] == [] and r["max_minutes"] == 30 and r["max_budget_usd"] == 2.0 and set(r) == {
        "use_claude_skills", "off", "max_minutes", "max_budget_usd", "skills"}
    assert app_client.post("/skills/settings", json={"max_minutes": 45}, headers=worker()).json()["max_minutes"] == 45
    assert app_client.get("/skills").json()["max_minutes"] == 45
    assert app_client.post("/skills/settings", json={"max_minutes": 0}, headers=worker()).status_code == 422
    assert app_client.post("/skills/settings", json={"max_minutes": True}, headers=worker()).status_code == 422
    assert app_client.post("/skills/settings", json={"max_minutes": 121}, headers=worker()).status_code == 422
    assert {(s["name"], s["source"], s["enabled"]) for s in r["skills"]} == {("pdf-tools", "claude", True), ("house-style", "knack", True)}
    assert all(set(s) == {"name", "description", "source", "enabled"} for s in r["skills"])
    r = app_client.post("/skills/settings", json={"use_claude_skills": False, "off": ["house-style"]}, headers=worker()).json()
    assert r["use_claude_skills"] is False and r["off"] == ["house-style"]
    assert {(s["name"], s["enabled"]) for s in r["skills"]} == {("pdf-tools", False), ("house-style", False)}
    assert app_client.post("/skills/settings", json={"use_claude_skills": "no"}, headers=worker()).status_code == 422
    assert app_client.post("/skills/settings", json={"off": "x"}, headers=worker()).status_code == 422
    assert app_client.post("/skills/settings", json={"use_claude_skills": True, "off": []}, headers=worker()).json()["off"] == []
