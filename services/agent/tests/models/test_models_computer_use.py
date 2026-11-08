"""Gemini computer-use as a dry-run ModelPort.computer_step: action mapping, coordinates, safety stops, request shape."""
from __future__ import annotations

import json

import httpx
import pytest

from understudy_agent.models.config import GeminiModelIds
from understudy_agent.models.errors import ProviderError
from understudy_agent.models.gemini_http import GeminiClient
from understudy_agent.models.gemini_provider import GeminiProvider
from understudy_agent.models.imaging import make_test_png
from understudy_agent.models.port import Action, Done, SafetyStop

from .helpers import FakeGeminiClient, reply

PNG = make_test_png(1280, 800)           # 1280 x 800: normalised 500,500 is pixel 640,400


@pytest.fixture(autouse=True)
def _first_smoke_wording(monkeypatch):
    """The tests below pin the faithful mapping of the API's flags and the wording of the first Gemini smokes. The iteration 8b
    configuration (`UNDERSTUDY_GEMINI_FIT`, ON by default) is tested at the end of this file, where it is switched on again."""
    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "0")


def call(name, **args):
    return reply("", calls=({"id": "call_1", "name": name, "arguments": args},))


def prov(*replies, **ids):
    c = FakeGeminiClient(*replies)
    return GeminiProvider(client=c, models=GeminiModelIds(fast="lite", accurate="flash", **ids)), c


def test_click_maps_normalised_coordinates_to_screenshot_pixels():
    p, c = prov(call("click", x=474, y=381, intent="Click Calculate"))
    a = p.computer_step("press calculate", PNG, [])
    assert isinstance(a, Action) and a.kind == "click" and a.args == {"x": 607, "y": 305, "button": "left"}
    assert c.calls[0]["tools"] == [{"type": "computer_use", "environment": "browser"}]
    assert c.calls[0]["model"] == "flash"                                    # the accurate model unless GEMINI_MODEL_COMPUTER_USE is set
    assert "press calculate" in c.calls[0]["parts"][0].value
    assert p.last_call["input_tokens"] == 1200


def test_computer_use_model_id_from_the_environment_only(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_COMPUTER_USE", "cu-model")
    assert GeminiModelIds.from_env().computer_use == "cu-model" and GeminiModelIds.from_env().as_dict()["computer_use"] == "cu-model"
    p, c = prov(call("click", x=1, y=1), computer_use="cu-model")
    p.computer_step("g", PNG, [])
    assert c.calls[0]["model"] == "cu-model"


def test_coordinates_are_clamped_to_the_image():
    p, _ = prov(call("click", x=1000, y=1500))
    a = p.computer_step("g", PNG, [])
    assert a.args["x"] == 1279 and a.args["y"] == 799


@pytest.mark.parametrize("name,args,kind,expect", [
    ("double_click", {"x": 500, "y": 500}, "double_click", {"x": 640, "y": 400}),
    ("hover_at", {"x": 250, "y": 750}, "move", {"x": 320, "y": 600}),
    ("type_text_at", {"x": 10, "y": 10, "text": "hello"}, "click", {"x": 13, "y": 8, "button": "left"}),   # the click comes FIRST (below)
    ("type_text", {"text": "hello"}, "type", {"text": "hello"}),
    ("key_combination", {"keys": "Control+a"}, "key", {"keys": ["Control", "a"]}),
    ("scroll_document", {"direction": "down", "amount": 5}, "scroll", {"x": 640, "y": 400, "scroll_x": 0, "scroll_y": 600}),
    ("scroll_at", {"x": 500, "y": 500, "direction": "up"}, "scroll", {"x": 640, "y": 400, "scroll_x": 0, "scroll_y": -360}),
    ("drag_and_drop", {"x": 0, "y": 0, "destination_x": 500, "destination_y": 500}, "drag", {"path": [{"x": 0, "y": 0}, {"x": 640, "y": 400}]}),
    ("wait_5_seconds", {}, "wait", {}),
    ("screenshot", {}, "screenshot", {}),
])
def test_action_mapping(name, args, kind, expect):
    p, _ = prov(call(name, **args))
    a = p.computer_step("g", PNG, [])
    assert isinstance(a, Action) and a.kind == kind and a.args == expect


def test_safety_decision_becomes_a_safety_stop_never_acknowledged():
    p, _ = prov(call("click", x=1, y=1, safety_decision={"decision": "require_confirmation", "explanation": "starts a call"}))
    r = p.computer_step("g", PNG, [])
    assert isinstance(r, SafetyStop) and r.checks[0]["code"] == "require_confirmation"
    p, _ = prov(call("click", x=1, y=1, safety_decision={"decision": "allowed"}))
    assert isinstance(p.computer_step("g", PNG, []), Action)


def test_text_only_replies_are_done_or_failed():
    p, _ = prov(reply("DONE: the result is on screen"), reply("FAILED: no calculate button"), reply("I am not sure"))
    d = p.computer_step("g", PNG, [])
    assert isinstance(d, Done) and d.claimed_success and d.summary == "the result is on screen"
    f = p.computer_step("g", PNG, [])
    assert isinstance(f, Done) and not f.claimed_success
    assert not p.computer_step("g", PNG, []).claimed_success


def test_unknown_action_is_a_failed_done_and_bad_coordinates_raise():
    p, _ = prov(call("teleport", x=1, y=1), call("click", x="left", y=2))
    r = p.computer_step("g", PNG, [])
    assert isinstance(r, Done) and not r.claimed_success
    with pytest.raises(ProviderError):
        p.computer_step("g", PNG, [])


def test_history_is_sent_with_normalised_coordinates_and_no_typed_text():
    p, c = prov(call("click", x=1, y=1))
    p.computer_step("g", PNG, [{"kind": "click", "args": {"x": 640, "y": 400}, "ok": True}, {"kind": "type", "args": {"text": "secret value"}}])
    sent = c.calls[0]["parts"][0].value
    assert '"x": 500' in sent and "secret value" not in sent and "<12 chars>" in sent


def test_generate_content_api_refuses_the_tool():
    from understudy_agent.models.gemini_http import GeminiClient

    p = GeminiProvider(client=GeminiClient(api="generate_content", transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                       models=GeminiModelIds(fast="a", accurate="b"))
    with pytest.raises(ProviderError):
        p.computer_step("g", PNG, [])


def test_real_client_request_shape_and_function_call_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"status": "requires_action", "usage": {"total_input_tokens": 1107, "total_output_tokens": 36, "total_thought_tokens": 116},
                                         "steps": [{"type": "thought"}, {"id": "c1", "type": "function_call", "name": "click",
                                                                          "arguments": {"x": 474, "y": 381, "intent": "x"}}]})

    p = GeminiProvider(client=GeminiClient(transport=httpx.MockTransport(handler)), models=GeminiModelIds(fast="a", accurate="b"))
    a = p.computer_step("press calculate", PNG, [])
    assert a.kind == "click" and a.args["x"] == 607
    assert seen["body"]["tools"] == [{"type": "computer_use", "environment": "browser"}] and seen["body"]["store"] is False
    assert p.last_call["output_tokens"] == 152


def test_gemini_note_is_in_the_prompt_and_the_wrapper_passes_the_new_keywords(monkeypatch):
    p, c = prov(call("click", x=1, y=1))
    p.computer_step("g", PNG, [], store=False, note="The last click was refused: it was on the deny list.")
    sent = c.calls[0]["parts"][0].value
    assert "Note: The last click was refused: it was on the deny list." in sent
    from understudy_engine.privacy.direct import LedgeredPort

    p2, _ = prov(call("click", x=1, y=1))
    w = LedgeredPort(p2)
    assert w.computer_step("g", PNG, [], session="s", store=False, note="n").kind == "click"      # the ledger wrapper forwards **kw


def kinds(actions):
    return [(a.kind, a.args) for a in actions]


def test_type_text_at_is_a_click_then_the_typing_each_its_own_step_and_one_model_call():
    """The API's click-and-type is two actions the gate must see one at a time: the click gets the trusted target read, then the typing
    has a resolved focus. The flags are faithful: clear_before_typing selects all and deletes, press_enter presses Enter, and an absent
    flag means the API's default (both on)."""
    import sys

    sel = ["cmd", "a"] if sys.platform == "darwin" else ["ctrl", "a"]
    p, c = prov(call("type_text_at", x=500, y=500, text="{household.savings}", press_enter=False, clear_before_typing=False))
    out = [p.computer_step("g", PNG, [], session="n1") for _ in range(2)]
    assert kinds(out) == [("click", {"x": 640, "y": 400, "button": "left"}), ("type", {"text": "{household.savings}"})]
    assert len(c.calls) == 1                                          # the second step needed no model call
    p, c = prov(call("type_text_at", x=500, y=500, text="{a.b}", press_enter=True, clear_before_typing=True))
    out = [p.computer_step("g", PNG, [], session="n1") for _ in range(5)]
    assert kinds(out) == [("click", {"x": 640, "y": 400, "button": "left"}), ("key", {"keys": sel}), ("key", {"keys": ["backspace"]}),
                          ("type", {"text": "{a.b}"}), ("key", {"keys": ["enter"]})] and len(c.calls) == 1
    p, c = prov(call("type_text_at", x=500, y=500, text="{a.b}"), call("click", x=1, y=1))
    out = [p.computer_step("g", PNG, [], session="n1") for _ in range(5)]
    assert [k for k, _ in kinds(out)] == ["click", "key", "key", "type", "key"]       # defaults: clear and press enter
    assert p.computer_step("g", PNG, [], session="n1").kind == "click" and len(c.calls) == 2    # the queue is empty: the model is asked again


def test_the_queued_part_is_per_session_and_begin_task_drops_it():
    p, c = prov(call("type_text_at", x=500, y=500, text="t", press_enter=False, clear_before_typing=False),
                call("type_text_at", x=100, y=100, text="u", press_enter=False, clear_before_typing=False), call("click", x=1, y=1))
    assert p.computer_step("g", PNG, [], session="a").kind == "click"
    assert p.computer_step("g", PNG, [], session="b").kind == "click"           # another session is not served a's queued typing
    assert p.computer_step("g", PNG, [], session="a").args == {"text": "t"}
    assert p.computer_step("g", PNG, [], session="b").args == {"text": "u"}
    p, c = prov(call("type_text_at", x=500, y=500, text="t", press_enter=False, clear_before_typing=False), call("click", x=2, y=2))
    p.computer_step("g", PNG, [], session="a")
    p.begin_task("a")                                                           # a fresh task: the queued typing is dropped, never carried
    a = p.computer_step("g", PNG, [], session="a")
    assert a.kind == "click" and a.args["x"] == 3 and len(c.calls) == 2


def test_type_text_at_without_coordinates_is_plain_typing():
    p, _ = prov(call("type_text_at", text="hi"))
    a = p.computer_step("g", PNG, [])
    assert a.kind == "type" and a.args == {"text": "hi"}


# ----------------------------------------------------------------------------- iteration 8b: the Gemini fit (default on)
def test_the_fit_paragraph_and_the_clear_before_typing_system_text_reach_the_request(monkeypatch):
    from understudy_agent.models.gemini_provider import GEMINI_FORM_FIT, _CU_SYSTEM, _CU_SYSTEM_FIT, fit_enabled

    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "1")
    assert fit_enabled()
    p, c = prov(call("click", x=1, y=1))
    p.computer_step("GOAL-TEXT", PNG, [])
    user, system = c.calls[0]["parts"][0].value, c.calls[0]["system"]
    assert user.startswith("Goal: GOAL-TEXT\n" + GEMINI_FORM_FIT) and system == _CU_SYSTEM_FIT != _CU_SYSTEM
    assert "set clear_before_typing to true only when the field already holds" in system and "{household.savings}" in GEMINI_FORM_FIT
    assert "click it ONCE, then type its handle" in GEMINI_FORM_FIT and "never drawn in the screenshot" in GEMINI_FORM_FIT
    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "0")                       # the wording of the first smokes, byte for byte
    p, c = prov(call("click", x=1, y=1))
    p.computer_step("GOAL-TEXT", PNG, [])
    assert c.calls[0]["system"] == _CU_SYSTEM and GEMINI_FORM_FIT not in c.calls[0]["parts"][0].value
    assert "clear_before_typing to false" in _CU_SYSTEM and not fit_enabled()


def test_with_the_fit_on_no_enter_follows_the_typing_and_an_absent_clear_flag_means_no_clearing(monkeypatch):
    """The API's default adds an Enter after typing (an Enter in a text field submits the form with whatever it holds) and clears the field
    first (two more gated steps and two more goal checks per field). The benefits forms are moved on by clicking their buttons and their
    fields start empty, so the fit configuration never queues an Enter and reads an absent clear flag as false. A model that WANTS a field
    replaced says clear_before_typing true and gets the select-all and the delete."""
    import sys

    sel = ["cmd", "a"] if sys.platform == "darwin" else ["ctrl", "a"]
    click = ("click", {"x": 640, "y": 400, "button": "left"})
    monkeypatch.setenv("UNDERSTUDY_GEMINI_FIT", "1")
    for args in ({}, {"press_enter": True}, {"press_enter": False, "clear_before_typing": False}):
        p, c = prov(call("type_text_at", x=500, y=500, text="{a.b}", **args))
        out = [p.computer_step("g", PNG, [], session="n1") for _ in range(2)]
        assert kinds(out) == [click, ("type", {"text": "{a.b}"})] and len(c.calls) == 1
        assert p._pending.get("n1") in (None, [])                              # nothing else is queued: no Enter, no clearing
    for args in ({"clear_before_typing": True}, {"press_enter": True, "clear_before_typing": True}):
        p, c = prov(call("type_text_at", x=500, y=500, text="{a.b}", **args))
        out = [p.computer_step("g", PNG, [], session="n1") for _ in range(4)]
        assert kinds(out) == [click, ("key", {"keys": sel}), ("key", {"keys": ["backspace"]}), ("type", {"text": "{a.b}"})]
        assert p._pending.get("n1") in (None, [])                              # an explicit request to clear is honoured, an Enter is still not queued
