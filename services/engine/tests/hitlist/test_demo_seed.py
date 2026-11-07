"""After `python -m understudy_engine.demo seed --reset` the seeded demo person's Repeats list gives two rows, the same two routines the
Routines screen lists, with the status the seed left them in (proposed: nothing decided yet). Skipped until `make synth` has run."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import demo
from understudy_engine.hitlist.routes import router
from understudy_engine.memory.paths import data_dir as real_data_dir

REAL = real_data_dir() / "synthetic"
pytestmark = pytest.mark.skipif(not ((REAL / "learners" / "truth.json").exists() and (REAL / "nine-to-five" / "events.jsonl").exists()),
                                reason="run `uv run understudy synth --all` first")


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "synthetic").symlink_to(REAL)
    (shared / "golden" / "screenshots").mkdir(parents=True)
    for i in range(1, 5):
        (shared / "golden" / "screenshots" / f"s{i}.png").write_bytes(demo.placeholder_png(32, 18, (200, 210, 220 + i)))
    (shared / "voice_cache").mkdir()
    (shared / "eval").mkdir()
    data, home, fake_home = shared / "demo-data", tmp_path / "demo-home", tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("HOME", str(fake_home))
    fake = types.ModuleType("understudy_agent.demo_bundle")
    fake.install = lambda *a, **k: "fake installer: nothing written"
    monkeypatch.setitem(sys.modules, "understudy_agent.demo_bundle", fake)
    monkeypatch.setattr(__import__("understudy_agent"), "demo_bundle", fake, raising=False)
    from understudy_engine import routes_handoff as rh

    rh._cache.clear()
    monkeypatch.chdir(tmp_path)
    demo.seed(out=lambda m: None, bundle=False)
    app = FastAPI()
    app.include_router(router)
    app.include_router(rh.router)
    return TestClient(app), data, home


def test_the_seeded_demo_gives_two_rows_that_match_the_routines_screen(seeded):
    c, _, _ = seeded
    routines = c.get("/routines").json()["data"]
    assert [r["id"] for r in routines] == ["calc-entry-3x", "case-note-copy"]
    for window in (7, 30):
        d = c.get(f"/hitlist?window={window}").json()["data"]
        assert d["state"] == "ok" and [r["id"] for r in d["rows"]] == ["calc-entry-3x", "case-note-copy"], d["rows"]
        assert [r["status"] for r in d["rows"]] == ["proposed", "proposed"]
        assert all(r["actions"]["routine_id"] == r["id"] and r["actions"]["can_automate"] for r in d["rows"])
        assert d["rows"][0]["minutes_per_week"]["point"] > d["rows"][1]["minutes_per_week"]["point"] > 0
        assert d["total"]["actions"] == 2


def test_watching_first_from_the_list_shows_as_learning_and_reset_clears_only_the_counts(seeded):
    c, data, home = seeded
    ok = c.post("/routines/case-note-copy/consent", json={"mode": "shadow"})
    assert ok.status_code == 200, ok.text
    rows = {r["id"]: r["status"] for r in c.get("/hitlist?window=7").json()["data"]["rows"]}
    assert rows == {"calc-entry-3x": "proposed", "case-note-copy": "learning"}
    memory = (home / "memory.md").read_bytes()
    routines_state = (home / "routines_state.json").read_bytes()
    out = c.post("/hitlist/reset").json()
    assert out["cleared"] == {"counters": 2, "hidden_marks": 0}
    assert c.get("/hitlist?window=7").json()["data"]["state"] == "counting_again"
    assert (home / "memory.md").read_bytes() == memory and (home / "routines_state.json").read_bytes() == routines_state     # nothing but its own file
