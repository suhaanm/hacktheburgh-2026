"""Offline reproduction (no model, no network, no desktop): a focused <select> inside a form whose default submit button is 'Show my results'
(site C, panel 2). Prints what the trusted focus read returns, what the class gate says for Tab and Enter, and what the drift layer does when the
check call raises SchemaViolation (a reason longer than 200 characters)."""
import asyncio
import sys

import understudy_agent
from understudy_agent.models.errors import ProviderError, SchemaViolation
from understudy_agent.models.port import Action
from understudy_agent.models.strict import validate_output
from understudy_agent.security.drift import DRIFT_SCHEMA, DriftChecker, describe_step
from understudy_agent.security.gates import RoutineContext, TargetInfo, classify_step, gate
from understudy_agent.tiers.computer_use import BrowserPageActuator

HTML = ('<body><form method=post action="/results"><fieldset id=panel2>'
        '<label for=t>Housing</label><select id=t name=t><option>Renting</option><option>Owner occupier</option></select>'
        '<label for=r>Rent</label><input id=r name=r type=text>'
        '<button type=submit data-testid=show-results>Show my results</button></fieldset></form></body>')


async def main() -> None:
    print("package:", understudy_agent.__file__)
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://calc.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=HTML))
            await page.goto("http://calc.test/")
            act = BrowserPageActuator(page)
            for focus_id in ("t", "r"):
                await page.evaluate(f"document.getElementById('{focus_id}').focus()")
                for keys in (["Tab"], ["Enter"]):
                    tr = await act.read_target(Action("key", {"keys": keys}))
                    ti = TargetInfo(label=tr.label, role=tr.role, url=tr.url, field_attrs=tr.field_attrs, structure=tr.structure)
                    ctx = RoutineContext(mode="model_driven", recorded_hosts=frozenset({"calc.test"}))
                    cls = sorted(c.value for c in classify_step("key", {"keys": keys}, ti, ctx.recorded_hosts))
                    print(f"focus={'select' if focus_id == 't' else 'input '} key={keys[0]:5s} -> label={tr.label!r} role={tr.role!r} "
                          f"structure={list(tr.structure)} classes={cls} verdict={gate('key', {'keys': keys}, ctx, ti).verdict}")
        finally:
            await browser.close()

    # the drift layer: a reason of 201 characters is rejected by LOCAL validation (maxLength is stripped from the provider's strict schema)
    try:
        validate_output({"serves_goal": True, "reason": "x" * 201}, DRIFT_SCHEMA)
        print("201-char reason: accepted by validate_output")
    except SchemaViolation as e:
        print("201-char reason: SchemaViolation ->", str(e)[:60])

    class Port:
        def __init__(self, exc):
            self.exc = exc

        def check(self, prompt, schema):
            raise self.exc

    v = DriftChecker(Port(SchemaViolation("model output does not match schema: too long"))).check(
        "goal", describe_step("key", {"keys": ["Tab"]}, label="Show my results", host="127.0.0.1"))
    print("drift verdict when check raises SchemaViolation: on_goal=%s source=%s reason=%r" % (v.on_goal, v.source, v.reason))


asyncio.run(main())
