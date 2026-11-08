"""AGENTIC-3 item 3: the pop-up premise behind 'set a native drop-down by fact through code', tested with NO model (headless Chromium, the
real page actuator, sandbox site B on a private port, a drop-down with an index and no household value in sight).

Observed in the installed Chromium (7 Nov 2026) and pinned here, so that a browser update that changes it is named by a failing test:
  * a click on a native drop-down draws nothing in a headless screenshot (the pop-up is not in the frame);
  * a click aimed at where an option would be does NOT select it: it lands on the page underneath (the active element changes, the
    selection does not);
  * arrow keys and Enter on a click-opened drop-down do not commit a choice either;
  * but TYPING the option's text commits it at once, whether or not the drop-down was clicked first, and Tab then only moves on.
So the model's blind clicks and key presses at a pop-up cannot work, and the typed-handle route the loop already uses does; what failed in the
held-out round was omission and landing (see docs/reference-notes/cu-failure-diagnosis.md), which the read-back now sees (tiers/form_audit.py).
"""
from __future__ import annotations

import pytest

from understudy_agent.models.port import Action
from understudy_agent.sandbox_sites.specs import SITES
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import BrowserPageActuator, screen_changed, screen_fingerprint


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


async def fresh(host, cluster):
    page = await (await host.new_context()).new_page()
    await page.goto(cluster.urls["b"] + SITES["b"].start_path, wait_until="domcontentloaded")
    return page, BrowserPageActuator(page)


async def where(page, sel):
    b = await page.locator(sel).bounding_box()
    return int(b["x"] + b["width"] / 2), int(b["y"] + b["height"] / 2), b


async def state(page):
    return await page.evaluate("""() => { const e = document.querySelector('#bedrooms'); const a = document.activeElement;
        return {idx: e.selectedIndex, active: a ? (a.id || a.tagName) : null}; }""")


async def test_a_click_on_the_drop_down_draws_no_pop_up_in_the_frame(cluster, host):
    page, act = await fresh(host, cluster)
    x, y, _ = await where(page, "#bedrooms")
    before = screen_fingerprint(await act.screenshot())
    await act.execute(Action("click", {"x": x, "y": y}))
    assert (await state(page))["active"] == "bedrooms"                     # the drop-down has focus ...
    assert not screen_changed(before, screen_fingerprint(await act.screenshot()))   # ... and the frame shows no pop-up


async def test_a_click_where_an_option_would_be_does_not_select_it(cluster, host):
    page, act = await fresh(host, cluster)
    x, y, b = await where(page, "#bedrooms")
    await act.execute(Action("click", {"x": x, "y": y}))
    await act.execute(Action("click", {"x": x, "y": y + int(b["height"] / 2) + 22}))
    s = await state(page)
    assert s["idx"] == 0 and s["active"] != "bedrooms"                     # the click went to the page under the pop-up


async def test_arrow_keys_and_enter_do_not_commit_a_choice_on_a_click_opened_drop_down(cluster, host):
    page, act = await fresh(host, cluster)
    x, y, _ = await where(page, "#bedrooms")
    await act.execute(Action("click", {"x": x, "y": y}))
    for keys in (["down"], ["down"], ["enter"]):
        await act.execute(Action("key", {"keys": keys}))
    assert (await state(page))["idx"] == 0


@pytest.mark.parametrize("click_first", [True, False])
async def test_typing_the_option_text_commits_it_at_once(cluster, host, click_first):
    page, act = await fresh(host, cluster)
    if click_first:
        x, y, _ = await where(page, "#bedrooms")
        await act.execute(Action("click", {"x": x, "y": y}))
    else:
        await page.focus("#bedrooms")
    await act.execute(Action("type", {"text": "3"}))
    assert (await state(page))["idx"] == 2                                 # committed before any Tab
    await act.execute(Action("key", {"keys": ["tab"]}))
    assert (await state(page))["idx"] == 2                                 # and Tab only moved on
