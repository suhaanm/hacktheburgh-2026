from __future__ import annotations

import os
from pathlib import Path

import pytest

from understudy_agent.sandbox_sites.runner import SandboxCluster

REAL_DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Every test gets its own data dir, its own home, and no way to reach the real data/ dir or the real sandbox
    ports. A test can never create or leave data/KILL in the repo's data dir (a stale flag stops the live demo)."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for site in "ABC":
        monkeypatch.setenv(f"SANDBOX_PORT_{site}", "9")        # the discard port: nothing real is ever listening there
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:9")      # no accidental calls to the live engine
    had_kill = (REAL_DATA / "KILL").exists()
    yield
    if not had_kill:
        assert not (REAL_DATA / "KILL").exists(), "a test left data/KILL in the REAL data dir"


@pytest.fixture(scope="session")
def cluster():
    with SandboxCluster(ephemeral=True) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_sandbox_state(request):
    if "cluster" in request.fixturenames:
        request.getfixturevalue("cluster").state.reset()
    yield


@pytest.fixture
def pw_browser():
    # function scope on purpose: the sync API keeps an event loop running in this thread while it is open,
    # which would break every async test that runs after it
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()
