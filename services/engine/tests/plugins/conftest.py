from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    """No test here may touch the shared data/ directory or the real ~/.understudy, and none may reach the network."""
    root = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.delenv("UNDERSTUDY_GRAPH", raising=False)
    monkeypatch.delenv("UNDERSTUDY_PLUGIN_PATH", raising=False)
