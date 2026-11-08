"""One Playwright browser per run, one isolated context per navigator (AGT-9, CAP-6).

Contexts share nothing (cookies, storage, cache), and the browser is the agent's own headless profile,
never the human's. Set UNDERSTUDY_AGENT_HEADED=1 to watch a run.
"""
from __future__ import annotations

import os
from typing import Any


def search_page() -> str:
    """The page a typed task starts on when the worker named no address, and where the model's `search` action goes. Checked live from the
    agent's own browser, 8 Nov 2026: Bing's home page and results load for an automated browser; DuckDuckGo answers a search with its
    "418" error page, Google puts a consent wall in front of the search box, and Brave, Startpage, Mojeek and Ecosia show a bot check or an
    error. `KNACK_SEARCH_PAGE` (an http or https address) replaces it. It carries no query: the worker's words never ride in an address."""
    v = os.environ.get("KNACK_SEARCH_PAGE", "").strip()
    return v if v.startswith(("https://", "http://")) else "https://www.bing.com/"


def _viewport_from_env() -> dict[str, int]:
    """The page size the computer-use model sees (frame size sets the image tokens per step). UNDERSTUDY_T3_VIEWPORT=WxH to change it."""
    import os
    import re

    m = re.fullmatch(r"(\d{3,4})x(\d{3,4})", os.environ.get("UNDERSTUDY_T3_VIEWPORT", "").strip())
    return {"width": int(m.group(1)), "height": int(m.group(2))} if m else {"width": 1280, "height": 800}


class BrowserHost:
    def __init__(self, *, headless: bool | None = None) -> None:
        self.headless = (os.environ.get("UNDERSTUDY_AGENT_HEADED") != "1") if headless is None else headless
        self._pw: Any = None
        self._browser: Any = None
        self._contexts: list[Any] = []

    async def __aenter__(self) -> "BrowserHost":
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        return self

    async def new_context(self, **kw: Any) -> Any:
        kw.setdefault("viewport", _viewport_from_env())
        kw.setdefault("accept_downloads", False)
        ctx = await self._browser.new_context(**kw)
        ctx.set_default_timeout(8000)
        self._contexts.append(ctx)
        return ctx

    async def close_contexts(self) -> None:
        for c in self._contexts:
            try:
                await c.close()
            except Exception:  # noqa: BLE001
                pass
        self._contexts = []

    async def __aexit__(self, *exc: object) -> None:
        await self.close_contexts()
        try:
            if self._browser:
                await self._browser.close()
        finally:
            if self._pw:
                await self._pw.stop()
