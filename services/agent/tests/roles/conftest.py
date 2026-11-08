"""Playwright fixtures for the role-sandbox tests: one headless Chromium per test module, a fresh page per test. Skips cleanly if
Playwright or its Chromium is missing. Pages are created through ``new_page(color_scheme=..., width=..., height=...)``."""
from __future__ import annotations

import pytest

pw_sync = pytest.importorskip("playwright.sync_api")


# Module scope, not session: the sync API keeps an asyncio loop running in this thread for as long as it is open, and `asyncio.run()` raises
# "cannot be called from a running event loop" in that thread. A session-scoped browser stayed open for the rest of the run and broke
# every later test that calls `asyncio.run` (tests/tasks, which sorts after tests/roles). One Chromium per test module closes it in between.
@pytest.fixture(scope="module")
def browser():
    with pw_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture()
def new_page(browser):
    ctxs = []

    def make(color_scheme: str = "light", width: int = 1440, height: int = 900):
        ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=color_scheme)
        ctxs.append(ctx)
        page = ctx.new_page()
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        return page

    yield make
    for c in ctxs:
        c.close()
