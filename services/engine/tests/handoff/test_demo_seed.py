"""python -m understudy_engine.demo seed: an isolated, idempotent, no-manual-steps demo state."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import demo
from understudy_engine.memory.paths import data_dir as real_data_dir

REAL = real_data_dir() / "synthetic"
pytestmark = pytest.mark.skipif(not ((REAL / "learners" / "truth.json").exists() and (REAL / "nine-to-five" / "events.jsonl").exists()),
                                reason="run `uv run understudy synth --all` first")


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "synthetic").symlink_to(REAL)
    home = tmp_path / "demo-home"
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("HOME", str(fake_home))
    from understudy_engine import routes_handoff as rh

    rh._cache.clear()
    app = FastAPI()
    app.include_router(rh.router)
    c = TestClient(app)
    c.home, c.data, c.fake_home = home, data, fake_home
    return c


def _seed(**kw):
    lines: list[str] = []
    res = demo.seed(out=lines.append, **kw)
    return res, lines


def _cli_env(env, **extra):
    return {**os.environ, "UNDERSTUDY_HOME": str(env.home), "UNDERSTUDY_DATA_DIR": str(env.data), **extra}


def test_seed_builds_the_whole_demo_state_and_prints_what_it_did(env):
    res, lines = _seed()
    text = "\n".join(lines)
    assert res["seeded"] and res["person"] == "p_learn01" and res["routine"] == "calc-entry-3x" and res["coach"] == {"level": "L3", "chip": "dot", "case": 24}
    for needle in ("state home:", "onboarding:", "capture on", "skill state: L4 on enter-household-once", "rule proposal waiting", "routine: calc-entry-3x", "coach:", "done."):
        assert needle in text, needle
    # identity and capture consent, through the API
    assert env.get("/identity").json() == {"person": "p_learn01", "role": "benefits-processor"}
    mem = env.get("/memory").json()
    assert any(row["text"] == "Capture: times only" for row in mem["sections"]["Preferences"])
    assert any(row["text"].startswith("enter-household-once: L4") for row in mem["sections"]["Skill state"])
    # the pending rule proposal (three corrections already recorded)
    props = env.get("/memory/proposals").json()
    assert len(props) == 1 and props[0]["status"] == "proposed" and props[0]["evidence_count"] == 3 and props[0]["rule"] == "Summary length: detailed."
    # the routine: proposed, rung A0, nothing consented, eligible without an override
    r = env.get("/routines").json()["data"]
    assert [x["id"] for x in r] == ["calc-entry-3x"]
    calc = r[0]
    assert calc["status"] == "proposed" and calc["rung"] == "A0" and calc["consent"]["mode"] == "none"
    assert calc["skill_gate"]["eligible"] is True and calc["skill_gate"]["reason"].startswith("mastery L4") and calc["proposable"] is True
    assert calc["value"]["horizon_weeks"] == 4 and calc["proposal"]["what"]
    # coach/state with no parameters is p_learn01 at the seeded case
    c = env.get("/coach/state").json()
    assert c["case"] == 24 and c["cases_total"] == 30 and c["level"] == "L3" and c["chip"] == "dot" and c["person"] == "p_learn01"
    # the graph agrees: this person's routine, skills from the tracker at the same case
    g = env.get("/graph/work").json()["data"]
    assert [n["id"] for n in g["nodes"] if n["type"] == "routine"] == ["routine:calc-entry-3x"]
    assert any(n["type"] == "skill" for n in g["nodes"])


def test_the_demo_path_works_with_no_manual_steps(env):
    _seed()
    ok = env.post("/routines/calc-entry-3x/consent", json={"mode": "shadow"})            # no skill_override needed
    assert ok.status_code == 200 and ok.json()["status"] == "shadow" and ok.json()["rung"] == "A1"
    out = env.post("/routines/calc-entry-3x/shadow", json={"results": [{"run_id": f"d{i}", "matched": True} for i in range(20)]},
                   headers={"X-Understudy-Actor": "agent"}).json()
    assert out["rung"] == "A1" and out["runs"] == 20 and out["wilson_lower"] >= 0.8                # consent was shadow: capped at A1
    assert env.post("/routines/calc-entry-3x/consent", json={"mode": "approval"}).json()["rung"] == "A2"
    pid = env.get("/memory/proposals").json()[0]["id"]
    assert env.post(f"/memory/proposals/{pid}/approve").json()["status"] == "active"


def test_idempotent_without_reset_and_clean_with_reset(env):
    res, _ = _seed()
    before = (env.home / "memory.md").read_bytes(), (env.home / "memory_state.json").read_bytes()
    again, lines = _seed()
    assert again["seeded"] is False and "already seeded" in "\n".join(lines)
    assert ((env.home / "memory.md").read_bytes(), (env.home / "memory_state.json").read_bytes()) == before
    # the worker uses the demo: consent writes the agent's side file and the memory line
    env.post("/routines/calc-entry-3x/consent", json={"mode": "shadow"})
    side = env.data / "routines" / "calc-entry-3x" / "consent.json"
    assert side.exists()
    (env.home / "keep.txt").write_text("not ours")
    again, lines = _seed(reset=True)
    assert again["seeded"] is True and "reset: removed" in "\n".join(lines)
    assert not side.exists() and (env.home / "keep.txt").read_text() == "not ours"          # only the demo's own files go
    calc = env.get("/routines").json()["data"][0]
    assert calc["status"] == "proposed" and calc["rung"] == "A0" and calc["consent"]["mode"] == "none"
    assert len(env.get("/memory/proposals").json()) == 1 and env.get("/memory").json()["revision"] == res["revision"]


def test_it_will_not_touch_the_default_home_or_a_memory_file_it_did_not_make(env, monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_HOME")
    with pytest.raises(demo.DemoError, match="UNDERSTUDY_HOME is not set"):
        demo.seed(out=lambda s: None)
    assert not (env.fake_home / ".understudy").exists()                                       # nothing was created under HOME
    cli = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "seed"], capture_output=True, text=True, env=_cli_env(env, UNDERSTUDY_HOME=""))
    assert cli.returncode == 2 and "UNDERSTUDY_HOME" in cli.stderr
    assert not (env.fake_home / ".understudy").exists()
    # a home that already holds someone's own memory is refused, with or without --reset
    monkeypatch.setenv("UNDERSTUDY_HOME", str(env.home))
    env.home.mkdir(parents=True)
    (env.home / "memory.md").write_text("---\nrole: programmer\nrevision: 7\n---\n## Preferences\n- mine\n")
    for reset in (False, True):
        with pytest.raises(demo.DemoError, match="memory file"):
            demo.seed(reset=reset, out=lambda s: None)
    assert "- mine" in (env.home / "memory.md").read_text()


def test_missing_synthetic_data_is_a_plain_error(env, monkeypatch, tmp_path):
    empty = tmp_path / "empty-data"
    empty.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(empty))
    with pytest.raises(demo.DemoError, match="understudy synth"):
        demo.seed(out=lambda s: None)
    assert not (env.home / "memory.md").exists()


def test_module_entry_point_prints_and_exits_zero(env):
    cp = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "seed"], capture_output=True, text=True, env=_cli_env(env))
    assert cp.returncode == 0, cp.stderr
    assert "onboarding:" in cp.stdout and "routine: calc-entry-3x" in cp.stdout
    again = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "seed", "--reset"], capture_output=True, text=True, env=_cli_env(env))
    assert again.returncode == 0 and "reset: removed" in again.stdout
    st = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "status"], capture_output=True, text=True, env=_cli_env(env))
    assert "demo seeded: True" in st.stdout
