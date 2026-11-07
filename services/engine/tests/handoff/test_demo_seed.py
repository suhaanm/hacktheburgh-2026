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
    shared = tmp_path / "data"                       # stands in for the repo's shared data/ directory
    shared.mkdir()
    (shared / "synthetic").symlink_to(REAL)
    (shared / "golden" / "screenshots").mkdir(parents=True)
    for i in range(1, 5):
        (shared / "golden" / "screenshots" / f"s{i}.png").write_bytes(demo.placeholder_png(32, 18, (200, 210, 220 + i)))
    (shared / "voice_cache").mkdir()
    (shared / "eval").mkdir()
    data = shared / "demo-data"
    home = tmp_path / "demo-home"
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("HOME", str(fake_home))
    # Unit tests never run agent-core's real installer (it binds the shared sandbox ports): a do-nothing stand-in is in place by
    # default, so even a stray bundle=True cannot reach the real one. Tests that care replace it; one test removes it.
    import types

    fake = types.ModuleType("understudy_agent.demo_bundle")
    fake.install = lambda *a, **k: "fake installer: nothing written"
    monkeypatch.setitem(sys.modules, "understudy_agent.demo_bundle", fake)
    monkeypatch.setattr(__import__("understudy_agent"), "demo_bundle", fake, raising=False)
    from understudy_engine import routes_handoff as rh

    rh._cache.clear()
    app = FastAPI()
    app.include_router(rh.router)
    c = TestClient(app)
    c.home, c.data, c.fake_home, c.shared, c.tmp = home, data, fake_home, shared, tmp_path
    monkeypatch.chdir(tmp_path)
    return c


def _seed(**kw):
    kw.setdefault("bundle", False)       # the real bundle installer compiles against the sandbox sites (about 6 s); one test below runs it
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
    assert [x["id"] for x in r] == ["calc-entry-3x", "case-note-copy"]                      # two rows, the bigger one first
    calc = r[0]
    note = r[1]
    assert note["status"] == "proposed" and note["rung"] == "A0" and note["consent"]["mode"] == "none" and note["skill_gate"]["eligible"] is True
    assert calc["status"] == "proposed" and calc["rung"] == "A0" and calc["consent"]["mode"] == "none"
    assert calc["skill_gate"]["eligible"] is True and calc["skill_gate"]["reason"].startswith("mastery L4") and calc["proposable"] is True
    assert calc["value"]["horizon_weeks"] == 4 and calc["proposal"]["what"]
    # coach/state with no parameters is p_learn01 at the seeded case
    c = env.get("/coach/state").json()
    assert c["case"] == 24 and c["cases_total"] == 30 and c["level"] == "L3" and c["chip"] == "dot" and c["person"] == "p_learn01"
    # the graph agrees: this person's routine, skills from the tracker at the same case
    g = env.get("/graph/work").json()["data"]
    assert sorted(n["id"] for n in g["nodes"] if n["type"] == "routine") == ["routine:calc-entry-3x", "routine:case-note-copy"]
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
    assert again["seeded"] is True and "reset home: removed" in "\n".join(lines)
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
    cp = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "seed", "--no-bundle"], capture_output=True, text=True, env=_cli_env(env))
    assert cp.returncode == 0, cp.stderr
    assert "onboarding:" in cp.stdout and "routine: calc-entry-3x" in cp.stdout
    again = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "seed", "--reset", "--no-bundle"], capture_output=True, text=True, env=_cli_env(env))
    assert again.returncode == 0 and "reset home: removed" in again.stdout and "reset data: removed" in again.stdout and "not requested" in again.stdout
    st = subprocess.run([sys.executable, "-m", "understudy_engine.demo", "status"], capture_output=True, text=True, env=_cli_env(env))
    assert "demo seeded: True" in st.stdout


# ----------------------------------------------------------------------------- the isolated data directory
def _tree(root, skip=()):
    """name -> (kind, size, mtime_ns) for everything under root, not following symlinks, skipping some top-level names."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if rel.parts[0] in skip:
            continue
        st = p.lstat()
        out[str(rel)] = ("link:" + os.readlink(p) if p.is_symlink() else "dir" if p.is_dir() else "file", st.st_size if p.is_file() else 0,
                         st.st_mtime_ns if p.is_file() else 0)
    return out


def test_demo_data_dir_links_story_and_report(env):
    res, lines = _seed()
    text = "\n".join(lines)
    for name in ("synthetic", "golden", "voice_cache", "eval"):
        link = env.data / name
        assert link.is_symlink() and os.readlink(link) == f"../{name}" and link.resolve() == (env.shared / name).resolve()
    assert (env.data / "audit.jsonl").exists() and (env.data / "queue").is_dir() and (env.data / "runs").is_dir() and (env.data / "routines").is_dir()
    assert "morning story: 2 pending approvals (irreversible_step, shadow_mismatch)" in text and "demo bundle: not requested" in text
    from understudy_agent.audit import AuditLog
    from understudy_agent.queue import ApprovalQueue

    q = ApprovalQueue(env.data / "queue").list("pending")
    assert sorted(i["kind"] for i in q) == ["irreversible_step", "shadow_mismatch"]
    sub = next(i for i in q if i["kind"] == "irreversible_step")
    assert sub["title"] == "Submit case note CN-2041" and sub["risk_class"] == "irreversible" and sub["status"] == "pending"
    assert len(sub["evidence"]["screenshots"]) == 2 and sub["evidence"]["tier_log"] and sub["signature"]
    for item in q:                                                             # every screenshot the evidence names exists in the demo runs folder
        for rel in item["evidence"]["screenshots"]:
            assert (env.data / rel.replace("data/", "", 1)).exists(), rel
    assert sorted(p.name for p in (env.data / "runs" / "r_demo_0001").iterdir()) == ["s1.png", "s2.png", "s3.png", "s4.png"]
    log = AuditLog(env.data / "audit.jsonl")
    assert log.verify_chain() and len(log.read(limit=0)) == 10
    kinds = {r["kind"] for r in log.read(limit=0)}
    assert {"run_start", "run_end", "gate", "queue_enqueued", "yield"} <= kinds
    # the morning report built from those files tells the same story
    since = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rep = env.get("/offhours/report", params={"since": since}).json()
    assert [r["run_id"] for r in rep["ran"]] == ["r_demo_0001"] and rep["ran"][0]["minutes"] == 12.0 and rep["ran"][0]["tier"] == 2
    assert sorted(rep["queued"]) == sorted(i["id"] for i in q) and rep["failed"] == [] and [y["routine"] for y in rep["yielded"]] == ["benefits-workflow"]


def test_nothing_is_written_outside_the_two_demo_dirs(env):
    before_shared = _tree(env.shared, skip=("demo-data",))
    before_real = {str(p): p.stat().st_mtime_ns for p in REAL.rglob("*") if p.is_file()}
    before_tmp = _tree(env.tmp, skip=("demo-home", "data", "userhome"))
    for reset in (False, False, True, False):
        _seed(reset=reset)
    assert _tree(env.shared, skip=("demo-data",)) == before_shared               # the shared data dir: not one byte changed
    assert {str(p): p.stat().st_mtime_ns for p in REAL.rglob("*") if p.is_file()} == before_real
    assert _tree(env.tmp, skip=("demo-home", "data", "userhome")) == before_tmp
    assert list(env.fake_home.iterdir()) == []                                     # nothing under HOME, so no ~/.understudy
    assert sorted(p.name for p in env.home.iterdir()) <= sorted([".memory.lock", ".understudy-demo-home", "memory.md", "memory_state.json", "routines_state.json"])
    assert sorted(p.name for p in env.data.iterdir()) == sorted([".demo-growth", ".demo-story", ".understudy-demo-data", ".queue_key", "assist", "audit.jsonl", "eval", "golden", "queue", "routines", "runs", "synthetic", "voice_cache"])
    assert list(env.tmp.glob("*")) and not (env.tmp / "queue").exists() and not (env.tmp / "audit.jsonl").exists()   # nothing leaked into the working directory


def test_a_data_dir_that_is_not_the_demo_one_is_never_written(env, monkeypatch):
    (env.shared / "queue").mkdir()
    (env.shared / "queue" / "q_old.json").write_text("{}")
    (env.shared / "audit.jsonl").write_text("old line\n")
    (env.shared / "KILL").write_text("")
    before = _tree(env.shared, skip=("demo-data",))
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(env.shared))                      # the shared directory itself, not demo-data
    for reset in (False, True):
        res, lines = _seed(reset=reset)
        assert "is not a demo data dir" in "\n".join(lines) and "morning story" not in "\n".join(lines).replace("I will not write the morning", "")
    assert _tree(env.shared, skip=("demo-data",)) == before
    assert not (env.shared / "routines").exists() and (env.shared / "queue" / "q_old.json").read_text() == "{}"
    assert (env.home / "memory.md").exists()                                         # the home part still seeds


def test_reset_empties_only_the_demo_data_dirs_own_folders(env):
    _seed()
    (env.data / "queue" / "q_stale.json").write_text("{}")
    (env.data / "KILL").write_text("")
    (env.data / "runs" / "r_old").mkdir()
    (env.data / "routines" / "calc-entry-3x").mkdir(parents=True, exist_ok=True)
    (env.data / "routines" / "calc-entry-3x" / "consent.json").write_text("{}")
    _, lines = _seed(reset=True)
    assert "reset data: removed" in "\n".join(lines)
    assert not (env.data / "KILL").exists() and not (env.data / "queue" / "q_stale.json").exists() and not (env.data / "runs" / "r_old").exists()
    assert not (env.data / "routines" / "calc-entry-3x" / "consent.json").exists()
    assert len(list((env.data / "queue").glob("q_*.json"))) == 2 and (env.data / "runs" / "r_demo_0001" / "s1.png").exists()
    assert (env.data / "synthetic").is_symlink() and (env.shared / "synthetic").exists()   # links were unlinked, never followed


def test_demo_bundle_hook_is_called_when_present_and_tolerated_when_broken(env, monkeypatch):
    import types

    def install():
        d = env.data / "routines" / "calc-entry-3x"
        d.mkdir(parents=True, exist_ok=True)
        (d / "steps.json").write_text('{"steps": []}')
        return "ok"

    mod = types.ModuleType("understudy_agent.demo_bundle")
    mod.install = install
    monkeypatch.setitem(sys.modules, "understudy_agent.demo_bundle", mod)
    monkeypatch.setattr(__import__("understudy_agent"), "demo_bundle", mod, raising=False)
    res, lines = _seed(bundle=True)
    assert res["bundle"] and res["bundle"].endswith("routines/calc-entry-3x/steps.json") and "demo bundle installed" in "\n".join(lines)
    assert env.get("/routines").json()["data"][0]["driver"] == "compiled"          # the engine sees the compiled bundle in the demo data dir
    # a reset removes the bundle with the rest of the demo routines folder, and the hook puts it back
    (env.data / "routines" / "calc-entry-3x" / "steps.json").write_text("stale")
    res, _ = _seed(reset=True, bundle=True)
    assert (env.data / "routines" / "calc-entry-3x" / "steps.json").read_text() == '{"steps": []}'

    def boom():
        raise RuntimeError("bundle exploded")

    mod.install = boom
    res, lines = _seed(reset=True, bundle=True)
    assert res["seeded"] and res["bundle"] is None and "demo bundle FAILED: RuntimeError" in "\n".join(lines)


def _ports_busy() -> bool:
    import socket

    for port in (7801, 7802, 7803):
        with socket.socket() as sk:
            sk.settimeout(0.2)
            if sk.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def test_the_real_agent_bundle_installer_puts_steps_json_in_the_demo_data_dir(env, monkeypatch):
    """The only test that runs agent-core's real installer. It starts sandbox sites on the shared ports 7801 to 7803, so it takes
    the shared sandbox lock first (non-blocking) and skips when the lock or a port is busy: it can never wait on, or collide with,
    another agent's run. Every other test injects a fake installer or passes bundle=False."""
    import fcntl
    import importlib.util

    monkeypatch.undo()                                        # drops the fixture's stand-in installer (and its env), so the real module is visible
    if importlib.util.find_spec("understudy_agent.demo_bundle") is None:
        pytest.skip("understudy_agent.demo_bundle is not available")
    repo_data = REAL.parent                                   # the repo's real shared data/ directory
    lock_file = repo_data / "locks" / "sandbox.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pytest.skip("the shared sandbox lock is held by another run")
        if _ports_busy():
            pytest.skip("sandbox sites are already running on ports 7801 to 7803; not sharing them")
        monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(env.data))      # the real HOME stays: the installer needs the browser cache
        monkeypatch.setenv("UNDERSTUDY_HOME", str(env.home))
        monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
        shared = env.shared

        def snap():
            return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in repo_data.rglob("*")
                    if p.is_file() and not {"demo-home", "demo-data", "logs", "pids", "locks"} & set(p.parts)}

        before_repo, before_shared = snap(), _tree(shared, skip=("demo-data",))
        res, lines = _seed(bundle=True)
        text = "\n".join(lines)
        assert snap() == before_repo and _tree(shared, skip=("demo-data",)) == before_shared
        if "demo bundle FAILED" in text:
            pytest.skip("the sandbox sites or a browser are not available here: " + [l for l in lines if "FAILED" in l][0])
        steps = env.data / "routines" / "calc-entry-3x" / "steps.json"
        assert steps.exists() and res["bundle"] == str(steps) and "demo bundle installed" in text
        assert not (shared / "routines").exists()             # the shared data dir got nothing
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ----------------------------------------------------------------------------- Growth data (the shot list's "independence curve")
def test_growth_rows_are_one_labelled_simulated_learner_ending_just_before_now():
    from datetime import datetime, timezone

    from understudy_engine.cue import ledger as L

    now = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)
    rows = demo.demo_learner_rows(now)
    assist = [r for r in rows if r["stream"] == "assist"]
    off = [r for r in rows if r["stream"] != "assist"]
    assert len(assist) == 3 * demo.GROWTH_PER_SKILL and len(off) == 4
    assert {r["person"] for r in rows} == {"p_learn01"} and {r["origin"] for r in rows} == {"synthetic"}
    assert {r["origin_detail"] for r in rows} == {"synthetic_learner"}
    assert {r["skill"] for r in assist} == {"check-the-cliff", "reconcile-before-noting", "enter-household-once"}
    last = max(L.hour_to_epoch(r["t_hour"]) for r in assist)
    assert 0 <= now.timestamp() - last <= (demo.GROWTH_LAG_HOURS + 1) * 3600           # current, and never in the future
    assert demo.demo_learner_rows(now) == rows                                          # deterministic for a given clock
    for r in rows:
        L.validate_row(r)                                                               # every row passes the ledger's own schema


def test_seed_fills_the_growth_ledger_once_and_a_reset_puts_back_the_same_story(env):
    from understudy_engine.cue import paths as cue_paths

    res, lines = _seed()
    text = "\n".join(lines)
    assert res["growth"] is True and res["growth_counts"]["assist"] == 3 * demo.GROWTH_PER_SKILL and "growth: 90 assist occurrences" in text
    assert (env.data / "assist" / "ledger.jsonl").exists() and (env.data / ".demo-growth").exists()
    assert cue_paths.ledger_path() == env.data / "assist" / "ledger.jsonl"            # the file the route reads is the file the seed wrote
    before = (env.data / "assist" / "ledger.jsonl").read_bytes()
    _, again = _seed()
    assert "growth: already seeded" in "\n".join(again) and (env.data / "assist" / "ledger.jsonl").read_bytes() == before     # not twice
    (env.data / "assist" / "ledger.jsonl").write_text("stale\n")
    _seed(reset=True)
    assert (env.data / "assist" / "ledger.jsonl").read_text() != "stale\n" and (env.data / ".demo-growth").exists()


def test_growth_route_reports_ready_data_with_the_synthetic_label(env, monkeypatch):
    from understudy_engine.cue import routes as cue_routes

    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    _seed()
    app = FastAPI()
    app.include_router(cue_routes.router)
    c = TestClient(app)
    g = c.get("/growth", params={"person": "p_learn01"}).json()
    assert g["meta"]["origin"] == "synthetic" and g["data"]["origin_detail"] == "synthetic_learner"
    assert g["data"]["readiness"]["ready"] is True and g["data"]["occurrences"]["total"] >= 30 and len(g["data"]["curve"]) > 5
    assert g["data"]["offloaded"]["delegated"] + g["data"]["offloaded"]["automation"] == 4   # listed, never scored
    assert g["data"]["trend"]["direction"] != "too_early"


def test_growth_is_written_only_into_the_demo_data_dir(env, monkeypatch):
    (env.shared / "queue").mkdir()
    before = _tree(env.shared, skip=("demo-data",))
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(env.shared))                      # the shared directory itself, not demo-data
    res, lines = _seed()
    assert "growth" not in res and not (env.shared / "assist").exists() and not (env.shared / ".demo-growth").exists()
    assert _tree(env.shared, skip=("demo-data",)) == before
