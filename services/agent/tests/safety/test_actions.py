from __future__ import annotations

import pytest

from understudy_agent.models.port import Action
from understudy_agent.security.actions import (ActionRejected, BudgetExceeded, ObservationClock, StaleObservation,
                                               StepBudget, action_signature, validate_action, validate_model_action)

SCREEN = (1280, 720)


def rejects(kind, args=None, code=None, screen=SCREEN):
    with pytest.raises(ActionRejected) as e:
        validate_action(kind, args, screen=screen)
    if code:
        assert e.value.code == code, e.value.code


def test_valid_desktop_actions_normalise():
    assert validate_action("click", {"x": 10, "y": 20}, screen=SCREEN).args == {"x": 10, "y": 20, "button": "left"}
    assert validate_action("double_click", {"x": 1, "y": 2}).kind == "double_click"
    assert validate_action("type", {"text": "hello"}).args == {"text": "hello"}
    assert validate_action("key", {"keys": ["Cmd", "C"]}).args == {"keys": ["cmd", "C"]}
    assert validate_action("scroll", {"x": 5, "y": 5, "scroll_x": 0, "scroll_y": -300}).args["scroll_y"] == -300
    assert validate_action("drag", {"path": [{"x": 1, "y": 1}, {"x": 5, "y": 5}]}).args["path"][1] == {"x": 5, "y": 5}
    assert validate_action("wait", {}).args == {} and validate_action("screenshot").args == {}
    assert validate_action("click", {"x": 1, "y": 1, "hold_keys": ["SHIFT"]}).args["hold_keys"] == ["shift"]


def test_valid_browser_actions():
    assert validate_action("goto", {"url": "http://localhost:7801/?variant=clean"}).kind == "goto"
    assert validate_action("click_element", {"role": "button", "name": "Calculate"}).args["name"] == "Calculate"
    assert validate_action("fill", {"selector": "#adults", "value": "2"}).args["value"] == "2"
    assert validate_action("fill", {"selector": "#adults", "param": "household.adults"}).args["param"] == "household.adults"
    assert validate_action("extract", {"name": "result", "selector": "#out"}).args["name"] == "result"
    assert validate_action("wait_for", {"text": "Result"}).args["timeout_s"] == 5
    assert validate_action("back", {}).kind == "back"
    assert validate_action("forward", {}).kind == "forward" and validate_action("forward", {}).args == {}
    rejects("forward", {"url": "https://example.org"}, "unknown_arg")             # a step in the page's own history takes no address


def test_invalid_kind_and_batch_rejected():
    rejects("rm_rf", {}, "unknown_kind")
    rejects("shell", {"cmd": "ls"}, "unknown_kind")
    rejects(["click", "type"], {}, "batch_not_allowed")
    with pytest.raises(ActionRejected) as e:
        validate_model_action([Action("click", {"x": 1, "y": 1}), Action("click", {"x": 2, "y": 2})])
    assert e.value.code == "batch_not_allowed"


def test_unknown_and_missing_args_rejected():
    rejects("click", {"x": 1, "y": 1, "cmd": "rm"}, "unknown_arg")
    rejects("click", {"x": 1}, "missing_arg")
    rejects("type", {}, "missing_arg")


@pytest.mark.parametrize("bad", [-1, 1280, 99999, 1.5, "10", True, None])
def test_coordinates_must_be_on_screen_ints(bad):
    rejects("click", {"x": bad, "y": 5}, screen=SCREEN)


def test_coordinates_not_range_checked_without_a_screen_but_still_typed():
    assert validate_action("click", {"x": 5000, "y": 5000}).args["x"] == 5000
    rejects("click", {"x": 1.5, "y": 1}, screen=None)


def test_buttons_limited():
    rejects("click", {"x": 1, "y": 1, "button": "wheel"}, "bad_button")
    rejects("click", {"x": 1, "y": 1, "button": "back"}, "bad_button")
    rejects("double_click", {"x": 1, "y": 1, "button": "right"}, "bad_button")


def test_text_limits_and_hidden_characters():
    rejects("type", {"text": "x" * 501}, "text_too_long")
    rejects("type", {"text": ""}, "empty_text")
    rejects("type", {"text": "a\x00b"}, "control_chars")
    rejects("type", {"text": "a​b"}, "invisible_chars")
    rejects("type", {"text": "a‮b"}, "invisible_chars")
    rejects("type", {"text": 5}, "bad_text")


def test_keys():
    rejects("key", {"keys": []}, "bad_keys")
    rejects("key", {"keys": ["a"] * 5}, "bad_keys")
    rejects("key", {"keys": ["Hyperspace"]}, "unknown_key")
    rejects("key", {"keys": "Enter"}, "bad_keys")


def test_urls():
    rejects("goto", {"url": "javascript:alert(1)"}, "bad_url_scheme")
    rejects("goto", {"url": "file:///etc/passwd"}, "bad_url_scheme")
    rejects("goto", {"url": "http://user:pw@example.com/"}, "url_credentials")
    rejects("goto", {"url": "http:///nohost"}, "bad_url")
    rejects("goto", {"url": "http://example.com/" + "a" * 2100}, "text_too_long")
    assert validate_action("goto", {"url": "about:blank"}).kind == "goto"


def test_selector_rules():
    rejects("click_element", {}, "missing_target")
    rejects("click_element", {"selector": "#a", "role": "button", "name": "x"}, "ambiguous_target")
    rejects("fill", {"selector": "#a"}, "fill_source")
    rejects("fill", {"selector": "#a", "value": "x", "param": "p"}, "fill_source")
    rejects("fill", {"selector": "#a", "param": "bad param!"}, "bad_param")
    rejects("wait_for", {"selector": "#a", "text": "b"}, "wait_target")
    rejects("extract", {"name": "bad name", "selector": "#a"}, "bad_name")


def test_scroll_and_wait_limits():
    rejects("scroll", {"x": 1, "y": 1, "scroll_x": 0, "scroll_y": 99999}, "bad_scroll")
    rejects("wait", {"seconds": 99}, "bad_wait")
    rejects("scroll_page", {"dy": 99999}, "bad_scroll")
    rejects("drag", {"path": [{"x": 1, "y": 1}]}, "bad_path")
    rejects("drag", {"path": [{"x": 1, "y": 1}, {"x": 1}]}, "bad_path")


def test_port_action_object_validates():
    va = validate_model_action(Action("click", {"x": 640, "y": 360, "button": "left"}), screen=SCREEN)
    assert va.kind == "click"
    with pytest.raises(ActionRejected):
        validate_model_action(object())


# ---- signature
def test_signature_buckets_coordinates_and_hides_text():
    a = action_signature("click", {"x": 100, "y": 100, "button": "left"})
    b = action_signature("click", {"x": 110, "y": 105, "button": "left"})
    c = action_signature("click", {"x": 400, "y": 100, "button": "left"})
    assert a == b and a != c
    s = action_signature("type", {"text": "SECRET-NINO"})
    assert "SECRET" not in s
    # S-11: a different label is a different step (an approval for "Save" is not one for "Delete"); case and spacing are not
    assert action_signature("click", {"x": 1, "y": 1, "label": "A", "button": "left"}) != action_signature("click", {"x": 1, "y": 1, "label": "B", "button": "left"})
    assert action_signature("click", {"x": 1, "y": 1, "label": "Save  Draft", "button": "left"}) == action_signature("click", {"x": 1, "y": 1, "label": "save draft", "button": "left"})


# ---- budgets
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_step_budget_caps_steps():
    b = StepBudget(max_steps=3, deadline_s=100, clock=Clock())
    for _ in range(3):
        b.tick()
    with pytest.raises(BudgetExceeded) as e:
        b.tick()
    assert e.value.which == "steps"


def test_step_budget_deadline():
    c = Clock()
    b = StepBudget(max_steps=20, deadline_s=10, clock=c)
    b.tick()
    c.t = 10.5
    with pytest.raises(BudgetExceeded) as e:
        b.check()
    assert e.value.which == "deadline"


def test_observation_authorises_one_action_only_and_only_the_latest():
    c = Clock()
    oc = ObservationClock(max_age_s=5, clock=c)
    t1 = oc.new_observation()
    oc.authorise(t1)
    with pytest.raises(StaleObservation):
        oc.authorise(t1)  # already used
    t2 = oc.new_observation()
    t3 = oc.new_observation()
    with pytest.raises(StaleObservation):
        oc.authorise(t2)  # superseded
    c.t = 6
    with pytest.raises(StaleObservation):
        oc.authorise(t3)  # too old
    with pytest.raises(StaleObservation):
        oc.authorise(None)
