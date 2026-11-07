from __future__ import annotations

import pytest

from understudy_agent.sandbox_sites.runner import SandboxCluster


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
