"""End to end on the real handoff readers: the demo state, the seed, the engine app under the flag, a press into the real queue."""
from __future__ import annotations

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from understudy_engine import demo
from understudy_engine.memory.paths import data_dir as real_data_dir

REAL = real_data_dir() / "synthetic"
pytestmark = pytest.mark.skipif(not ((REAL / "learners" / "truth.json").exists() and (REAL / "nine-to-five" / "events.jsonl").exists()),
                                reason="run `uv run understudy synth --all` first")


@pytest.fixture
def demo_env(tmp_path, monkeypatch):
    shared = tmp_path / "data"
    shared.mkdir()
    (shared / "synthetic").symlink_to(REAL)
    (shared / "golden" / "screenshots").mkdir(parents=True)
    (shared / "voice_cache").mkdir()
    (shared / "eval").mkdir()
    data, home = shared / "demo-data", tmp_path / "demo-home"
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    monkeypatch.setenv("HOME", str(fake_home))
    fake = types.ModuleType("understudy_agent.demo_bundle")
    fake.install = lambda *a, **k: "fake installer"
    monkeypatch.setitem(sys.modules, "understudy_agent.demo_bundle", fake)
    from understudy_engine import routes_handoff as rh

    rh._cache.clear()
    demo.seed(out=lambda m: None, bundle=False)
    monkeypatch.chdir(tmp_path)
    return types.SimpleNamespace(data=data, home=home)


def test_the_live_readers_find_the_demo_routine_and_a_skill_gap(demo_env):
    from datetime import datetime, timezone

    from understudy_engine.proactive.candidates import Ctx, collect
    from understudy_engine.proactive.sources import Readers

    got = collect(Ctx("p_learn01", datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)), Readers())
    kinds = {c.kind for c in got.candidates}
    assert "automate" in kinds and "practice" in kinds
    auto = next(c for c in got.candidates if c.kind == "automate")
    assert auto.subject == "routine:calc-entry-3x" and auto.numbers["episodes"] > 3
    assert got.diagnostics["routines"]["available"] and got.diagnostics["skills"]["available"]


def test_the_engine_app_serves_the_seeded_briefing_under_the_flag(demo_env):
    from datetime import datetime, timezone

    from understudy_engine.api.app import create_app
    from understudy_engine.proactive.seed import seed_demo

    assert seed_demo(demo_env.home, demo_env.data, now=datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc))["seeded"]
    app = create_app()
    assert app.state.extensions.get("proactive") is True
    c = TestClient(app)
    r = c.get("/briefing", params={"person": "p_learn01"})
    assert r.status_code == 200, r.text
    body = r.json()
    cards = body["data"]["cards"]
    assert sorted(x["kind"] for x in cards) == ["automate", "focus_block", "practice"] and body["data"]["dropped"] == []
    assert all(x["status"] == "ready" for x in cards)
    assert c.get("/briefing", params={"person": "p_learn01"}).json()["data"]["cards"] == cards         # stable (mock clock)
    text = c.get("/briefing/text", params={"person": "p_learn01"}).json()["text"]
    assert text.startswith("Good morning. You have three suggestions ready")

    auto = next(x for x in cards if x["kind"] == "automate")
    r = c.post(f"/briefing/{auto['id']}/fire", headers={"X-Understudy-Actor": "worker_approval"})
    assert r.status_code == 200, r.text
    item = json.loads((demo_env.data / "queue" / f"{r.json()['queue_id']}.json").read_text())
    assert item["status"] == "pending" and item["routine_id"] == "calc-entry-3x" and item["evidence"]["extracted"]["requested_mode"] == "shadow"
    # the routine itself is untouched by the press: switching it on is still the worker's separate approval
    routines = c.get("/routines", params={"person": "p_learn01"}).json()["data"]
    assert next(x for x in routines if x["id"] == "calc-entry-3x")["status"] == "proposed"


def test_switching_the_routine_on_elsewhere_makes_its_card_stale(demo_env):
    from datetime import datetime, timezone

    from understudy_engine.api.app import create_app
    from understudy_engine.proactive.seed import seed_demo

    seed_demo(demo_env.home, demo_env.data, now=datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc))
    c = TestClient(create_app())
    ok = c.post("/routines/calc-entry-3x/consent", json={"mode": "shadow"}, headers={"X-Understudy-Actor": "worker"})
    assert ok.status_code == 200, ok.text
    body = c.get("/briefing", params={"person": "p_learn01"}).json()
    assert "automate" not in [x["kind"] for x in body["data"]["cards"]]
    assert any("switched this routine on" in d["reason"] for d in body["data"]["dropped"])
