"""S-28 (Medium): S-01 made an unreadable CLICK or Enter a human's call, but typing keeps the old rule: the gate blocks typing only when the focus read
SHOWS a sensitive field. When the focus read fails (an iframe, a custom element, a closed shadow root: 'opaque content' -> None) there are no field
attributes, so a type action is allowed. Tab moves focus into an iframe's password box with no click; a fact handle is then typed into it. Local
Chromium on route-served HTML. Controls: the same typing into an ordinary text field works."""
from __future__ import annotations

import pytest

from fakes import Scripted, always_true, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import BrowserPageActuator, ComputerUse
from understudy_agent.tiers.facts import FactStore

IFRAME = '<iframe id=f srcdoc="<input id=p type=password placeholder=Passcode>" style="width:300px;height:60px"></iframe>'
TEXT = '<input id=t type=text placeholder=Savings style="width:300px;height:30px">'


@pytest.mark.parametrize("html,where,expected", [(TEXT, "#t", "abc"), (IFRAME, "iframe", "")])
async def test_a_handle_is_not_typed_into_a_focus_the_gate_cannot_read(html, where, expected):
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://calc.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=f"<body>{html}</body>"))
            await page.goto("http://calc.test/")
            facts = FactStore({"x.y": "a value"}, {"x.y": lambda: "abc"})
            model = Scripted(Action("key", {"keys": ["tab"]}), Action("type", {"text": "{x.y}"}), Done("done", True))
            try:
                await ComputerUse(model, BrowserPageActuator(page), make_guard(), navigator="n", facts=facts, stall_limit=4).run("g", always_true)
            except GateStop:
                pass
            got = await page.input_value("#t") if where == "#t" else await page.frames[1].input_value("#p")
            assert got == expected, f"typed {got!r} into {where}"
        finally:
            await browser.close()
