"""Playwright fixtures for the role-sandbox tests: one headless Chromium per session, a fresh page per test. Skips cleanly if
Playwright or its Chromium is missing. Pages are created through ``new_page(color_scheme=..., width=..., height=...)``."""
from __future__ import annotations

import pytest

pw_sync = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="session")
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
