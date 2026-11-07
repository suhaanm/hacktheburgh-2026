"""SOUND (passes): in the browser path the focused control is read by trusted code, so typing a fact handle into a password field is refused
while the same handle into an ordinary text field is typed. Local headless Chromium on route-served HTML, no network."""
from __future__ import annotations

import pytest

from fakes import Scripted, always_true, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import BrowserPageActuator, ComputerUse
from understudy_agent.tiers.facts import FactStore

HTML = ('<body><input id=t type=text placeholder="Savings" style="position:absolute;left:50px;top:50px;width:200px;height:30px">'
        '<input id=p type=password placeholder="Passcode" style="position:absolute;left:50px;top:150px;width:200px;height:30px"></body>')


@pytest.mark.parametrize("field,y,expected", [("t", 65, "abc"), ("p", 165, "")])
async def test_a_handle_is_typed_into_a_text_field_and_refused_in_a_password_field(field, y, expected):
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://calc.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=HTML))
            await page.goto("http://calc.test/")
            facts = FactStore({"x.y": "a value"}, {"x.y": lambda: "abc"})
            model = Scripted(Action("click", {"x": 100, "y": y}), Action("type", {"text": "{x.y}"}), Done("done", True))
            try:
                await ComputerUse(model, BrowserPageActuator(page), make_guard(), navigator="n", facts=facts, stall_limit=4).run("g", always_true)
            except GateStop:
                pass
            assert await page.input_value(f"#{field}") == expected
        finally:
            await browser.close()
