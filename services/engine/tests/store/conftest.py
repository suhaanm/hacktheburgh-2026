from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    """No test here may touch the shared data/ directory or the real ~/.understudy (KILL flag, queue, audit, study state,
    memory file): other agents run tests at the same time, and a stale data/KILL would stop the live demo services.
    Tests that need data generate it under their own tmp dir (the synthetic generators are deterministic)."""
    root = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)
    monkeypatch.setenv("AGENT_PORT", "1")                     # no engine under test may forward a stop to the live agent
    monkeypatch.delenv("UNDERSTUDY_ENGINE_LISTEN_PORT", raising=False)
