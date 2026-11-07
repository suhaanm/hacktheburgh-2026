"""Runtime-track test setup: hermetic and offline. Every test gets its own tmp data dir, home and workspace root; the shared
sandbox lock is never taken (the exemplars do not use the sandbox sites); the real data directory is never touched, and a
test fails if data/KILL appears in it. Mock mode is on; no network."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REAL_DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_RUNTIME_WS_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.delenv("UNDERSTUDY_MOCK_SCENARIO", raising=False)
    monkeypatch.delenv("UNDERSTUDY_LIVE", raising=False)
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")      # as the engine's own tests: a local request with no Origin needs no token
    monkeypatch.delenv("UNDERSTUDY_GUARD_STRICT", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL_PLANNER", "test-planner")
    monkeypatch.setenv("OPENAI_MODEL_FAST", "test-fast")
    monkeypatch.setenv("OPENAI_MODEL_COMPUTER_USE", "test-computer")
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_AGENTS"):
        monkeypatch.delenv(k, raising=False)
    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    except Exception:
        pass
    # the sandbox lock is never taken by this track
    from understudy_agent.sandbox_sites import lock

    def _never(*a, **k):
        raise AssertionError("the runtime tests must never take the shared sandbox lock")

    monkeypatch.setattr(lock, "acquire", _never)
    had_kill = (REAL_DATA / "KILL").exists()
    try:
        from understudy_agent.runtime import run as rt_run

        rt_run.reset_registry()
    except Exception:
        pass
    yield
    try:
        from understudy_agent.runtime import run as rt_run

        for r in rt_run.live_runs():
            r.stop("test teardown")
            r.wait(5)
        rt_run.reset_registry()
    except Exception:
        pass
    if not had_kill:
        assert not (REAL_DATA / "KILL").exists(), "a test left data/KILL in the REAL data dir"
