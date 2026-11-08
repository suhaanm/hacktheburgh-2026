"""AGENTIC-3 item 1 inside the real tier-3 loop: a goal check that fails to run is retried, the ACTION is performed once.

The model proposes one click. The goal check (a model call) fails twice and then answers. The loop must call the computer-use model once
for that step, perform the click once, and spend no extra step. When every try fails the click is not performed at all and the run stops
at the gate, with the error class on the gate-stop row. Offline: a simulated actuator, a scripted model, a fake clock and sleeper.
"""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.errors import ProviderError
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.orchestrator import instrument_guard
from understudy_agent.queue import ApprovalQueue
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator, TargetRead
from understudy_agent.tiers.safety import Guard

HOST = "127.0.0.1:7801"
URL = f"http://{HOST}/"
CALCULATE = TargetRead("Calculate", "button", URL, None, ("submit_control",))


class CheckThatFailsFirst(MockProvider):
    """The goal-check call raises `failures` times and then behaves like the mock; every call is counted by method."""

    def __init__(self, failures: int, error: Exception | None = None) -> None:
        super().__init__("reader_basic")
        self.failures, self.error, self.tally = failures, error or ProviderError("APITimeoutError: Request timed out."), []

    def check(self, prompt, schema):
        self.tally.append("check")
        if self.failures > 0:
            self.failures -= 1
            raise self.error
        return {"serves_goal": True, "reason": "ordinary form step"}


class OneClickThenDone:
    name = "script"

    def __init__(self) -> None:
        self.calls = 0

    def computer_step(self, goal, shot, history, **kw):
        self.calls += 1
        return Action("click", {"x": 100, "y": 100}) if self.calls == 1 else Done("done", True)


def build(tmp_path, port):
    audit = AuditLog(tmp_path / "audit.jsonl")
    guard = Guard(port, run_id="r_retry", mode="model_driven", audit=audit, queue=ApprovalQueue(tmp_path / "q", audit=audit),
                  recorded_hosts=frozenset({HOST}))
    slept: list[float] = []
    guard.pipe.drift._sleep = slept.append
    rows: list[dict] = []
    instrument_guard(guard, "nav-x", rows, frozenset({HOST}))
    return guard, rows, slept


async def test_a_check_that_fails_twice_then_answers_does_not_repeat_the_click(tmp_path):
    port = CheckThatFailsFirst(failures=2)
    guard, rows, slept = build(tmp_path, port)
    model, act = OneClickThenDone(), SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    res = await ComputerUse(model, act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert res.outcome == "done"
    assert [a.kind for a in act.actions] == ["click"]                  # the action ran ONCE
    assert model.calls == 2                                            # one step for the click, one for the Done: no step was re-asked
    assert port.tally == ["check"] * 3                                 # the check ran three times: one try and two retries
    assert slept == [0.5, 1.5] and rows == []                          # a recovered check is no gate stop at all
    assert guard.pipe.drift.stats()["recovered"] == 1


async def test_when_every_try_fails_the_click_is_not_performed_and_the_stop_says_why(tmp_path):
    port = CheckThatFailsFirst(failures=99)
    guard, rows, slept = build(tmp_path, port)
    model, act = OneClickThenDone(), SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    with pytest.raises(GateStop):
        await ComputerUse(model, act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert act.actions == []                                           # nothing was done: fail closed
    assert model.calls == 1 and port.tally == ["check"] * 3 and slept == [0.5, 1.5]
    assert len(rows) == 1 and rows[0]["codes"] == ["drift:off_goal_unavailable"]
    assert rows[0]["check_error"] == "timeout" and rows[0]["check_attempts"] == 3


async def test_a_verdict_of_off_goal_is_one_call_and_still_stops_the_click(tmp_path):
    class Says(CheckThatFailsFirst):
        def check(self, prompt, schema):
            self.tally.append("check")
            return {"serves_goal": False, "reason": "unrelated"}

    port = Says(failures=0)
    guard, rows, slept = build(tmp_path, port)
    act = SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    with pytest.raises(GateStop):
        await ComputerUse(OneClickThenDone(), act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert act.actions == [] and port.tally == ["check"] and slept == []
    assert rows[0]["codes"] == ["drift:off_goal_model"] and rows[0]["check_error"] is None


# ----------------------------------------------------------------------------- iteration 8b: the note after a click on a drop-down (Gemini only)
async def _run_clicks(model, html, clicks, dropdown_note=None, final_hint=None, final_note=None):
    """Drive the real loop on a tiny page with scripted clicks; returns the prompts the model was given (one per step)."""
    from playwright.async_api import async_playwright

    from understudy_agent.tiers.computer_use import BrowserPageActuator
    from understudy_agent.tiers.facts import FactStore

    prompts: list[str] = []

    class Named:
        def __init__(self) -> None:
            self.name, self.n = model, 0

        def computer_step(self, goal, shot, history, **kw):
            prompts.append(goal)
            self.n += 1
            return Action("click", clicks[self.n - 1]) if self.n <= len(clicks) else Done("done", True)

    audit = AuditLog()
    guard = Guard(MockProvider("benefits_clean"), run_id="r_dd", mode="model_driven", audit=audit, queue=ApprovalQueue(), recorded_hosts=frozenset())
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://form.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            await page.goto("http://form.test/")

            async def verify():
                return True

            await ComputerUse(Named(), BrowserPageActuator(page), guard, navigator="n", facts=FactStore({"a.b": "x"}, {"a.b": lambda: "1"}),
                              stall_limit=9, dropdown_note=dropdown_note, final_hint=final_hint, final_note=final_note).run("g", verify)
        finally:
            await browser.close()
    return prompts


PAGE = ('<body style="margin:0"><select id=s style="position:absolute;left:100px;top:100px;width:200px;height:30px"><option>One</option>'
        '<option>Two</option></select><input id=t type=text style="position:absolute;left:100px;top:200px;width:200px;height:30px"></body>')
ON_SELECT, ON_TEXT = {"x": 150, "y": 115}, {"x": 150, "y": 215}


async def test_a_gemini_click_on_a_drop_down_is_followed_by_the_note_and_a_click_on_a_text_box_is_not():
    from understudy_agent.tiers.computer_use import DROPDOWN_NOTE

    prompts = await _run_clicks("gemini", PAGE, [ON_SELECT, ON_TEXT])
    assert DROPDOWN_NOTE.strip() in prompts[1] and DROPDOWN_NOTE.strip() not in prompts[0] and DROPDOWN_NOTE.strip() not in prompts[2]
    assert "{" not in DROPDOWN_NOTE and "handle of the fact" in DROPDOWN_NOTE        # closed wording: no handle, no value, no page text


async def test_another_provider_is_never_given_the_note_unless_it_is_switched_on():
    from understudy_agent.tiers.computer_use import DROPDOWN_NOTE

    assert all(DROPDOWN_NOTE.strip() not in p for p in await _run_clicks("openai", PAGE, [ON_SELECT, ON_TEXT]))
    assert any(DROPDOWN_NOTE.strip() in p for p in await _run_clicks("openai", PAGE, [ON_SELECT], dropdown_note=True))
    assert all(DROPDOWN_NOTE.strip() not in p for p in await _run_clicks("gemini", PAGE, [ON_SELECT], dropdown_note=False))


async def _run_typed(model, html, steps, value, entered_note=None):
    """Scripted steps (click or type of the handle `a.b`) on a tiny page, with the form audit's read-back on; returns the prompts."""
    from playwright.async_api import async_playwright

    from understudy_agent.tiers.computer_use import BrowserPageActuator
    from understudy_agent.tiers.facts import FactStore
    from understudy_agent.tiers.form_audit import FormAudit

    prompts: list[str] = []

    class Named:
        def __init__(self) -> None:
            self.name, self.n = model, 0

        def computer_step(self, goal, shot, history, **kw):
            prompts.append(goal)
            self.n += 1
            return steps[self.n - 1] if self.n <= len(steps) else Done("done", True)

    facts = FactStore({"a.b": "x"}, {"a.b": lambda: value})
    guard = Guard(MockProvider("benefits_clean"), run_id="r_en", mode="model_driven", audit=AuditLog(), queue=ApprovalQueue(), recorded_hosts=frozenset())
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://form.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            await page.goto("http://form.test/")

            async def verify():
                return True

            await ComputerUse(Named(), BrowserPageActuator(page), guard, navigator="n", facts=facts, form_audit=FormAudit(facts), stall_limit=9,
                              entered_note=entered_note).run("g", verify)
        finally:
            await browser.close()
    return prompts


TYPE = Action("type", {"text": "{a.b}"})


async def test_a_typed_handle_that_landed_without_changing_the_picture_is_confirmed_to_the_gemini_model():
    from understudy_agent.tiers.computer_use import ENTERED_NOTE

    note = ENTERED_NOTE.format(handle="a.b").strip()
    # the drop-down already says "One": typing "One" changes nothing on screen, so a model that judges by the picture would type it again
    prompts = await _run_typed("gemini", PAGE, [Action("click", ON_SELECT), TYPE, Action("screenshot", {})], "One")
    assert any(note in p for p in prompts[2:]), prompts[-1][-300:]                # the prompt of the step AFTER the typing step
    assert sum(note in p for p in prompts) == 1                                   # said once, after the typing step, never repeated
    # a text box that visibly changes: no note
    prompts = await _run_typed("gemini", PAGE, [Action("click", ON_TEXT), TYPE, Action("screenshot", {})], "12345")
    assert not any("IS entered" in p for p in prompts)


async def test_the_entered_note_is_for_the_gemini_configuration_only_and_follows_the_switch(monkeypatch):
    steps = [Action("click", ON_SELECT), TYPE, Action("screenshot", {})]
    assert not any("IS entered" in p for p in await _run_typed("openai", PAGE, steps, "One"))
    assert any("IS entered" in p for p in await _run_typed("openai", PAGE, steps, "One", entered_note=True))
    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "0")
    assert not any("IS entered" in p for p in await _run_typed("gemini", PAGE, steps, "One"))


async def test_the_note_follows_the_fit_switch(monkeypatch):
    from understudy_agent.tiers.computer_use import DROPDOWN_NOTE

    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "0")                                   # the wording of the first Gemini smokes: no note
    assert all(DROPDOWN_NOTE.strip() not in p for p in await _run_clicks("gemini", PAGE, [ON_SELECT]))


async def test_the_final_screen_is_announced_to_the_gemini_model_only_when_trusted_code_says_it_is_showing():
    from understudy_agent.tiers.computer_use import FINAL_NOTE

    async def showing():
        return True

    async def not_yet():
        return False

    note = FINAL_NOTE.strip()
    prompts = await _run_clicks("gemini", PAGE, [ON_TEXT, ON_TEXT], final_hint=showing)
    assert note not in prompts[0] and note in prompts[1] and "Reply DONE now" in note               # said after the click, in the next prompt
    assert all(note not in p for p in await _run_clicks("gemini", PAGE, [ON_TEXT, ON_TEXT], final_hint=not_yet))
    assert all(note not in p for p in await _run_clicks("openai", PAGE, [ON_TEXT, ON_TEXT], final_hint=showing))    # other providers: prompts as before
    assert any(note in p for p in await _run_clicks("openai", PAGE, [ON_TEXT], final_hint=showing, final_note=True))
    assert all(note not in p for p in await _run_clicks("gemini", PAGE, [ON_TEXT], final_hint=showing, final_note=False))


async def test_a_page_that_cannot_be_read_gives_no_final_note_and_does_not_stop_the_run():
    async def broken():
        raise RuntimeError("the page was mid-navigation")

    prompts = await _run_clicks("gemini", PAGE, [ON_TEXT, ON_TEXT], final_hint=broken)
    assert len(prompts) == 3
