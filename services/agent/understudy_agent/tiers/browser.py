"""One Playwright browser per run, one isolated context per navigator (AGT-9, CAP-6).

Contexts share nothing (cookies, storage, cache), and the browser is the agent's own headless profile,
never the human's. Set UNDERSTUDY_AGENT_HEADED=1 to watch a run.
"""
from __future__ import annotations

import os
from typing import Any


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
        kw.setdefault("viewport", {"width": 1280, "height": 800})
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
