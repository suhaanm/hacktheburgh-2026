from __future__ import annotations

from understudy_agent.models.errors import ProviderError
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.security.drift import DriftChecker, ProposedStep, StuckLoopDetector, describe_step


def feed(det, sigs):
    for s in sigs:
        det.record(s)
    return det.check()


def test_same_action_four_times_is_stuck_three_is_not():
    assert feed(StuckLoopDetector(), ["A"] * 3) is None
    r = feed(StuckLoopDetector(), ["A"] * 4)
    assert r and r.kind == "repeat" and r.code() == "stuck_repeat_p1"


def test_only_the_tail_matters():
    assert feed(StuckLoopDetector(), ["X", "Y", "A", "A", "A"]) is None
    assert feed(StuckLoopDetector(), ["X", "Y", "A", "A", "A", "A"]) is not None


def test_cycles_of_period_2_3_4_three_times():
    for period in (2, 3, 4):
        cyc = [chr(65 + i) for i in range(period)]
        assert feed(StuckLoopDetector(), cyc * 2) is None, period
        r = feed(StuckLoopDetector(), cyc * 3)
        assert r and r.kind == "cycle" and r.period == period, period


def test_progress_resets_the_pattern():
    d = StuckLoopDetector()
    assert feed(d, ["A", "B"] * 2 + ["C"]) is None
    d.reset()
    assert feed(d, ["A", "A", "A"]) is None


def test_period_5_cycles_are_not_flagged():
    assert feed(StuckLoopDetector(), list("ABCDE") * 3) is None


def test_describe_step_hides_typed_text_and_sanitises_labels():
    s = describe_step("type", {"text": "QQ123456C"}, label="Adults​<b>")
    assert "QQ123456C" not in s.render() and "9 characters" in s.render() and "<" not in s.render()


def test_drift_check_on_goal_and_off_goal_via_mock():
    chk = DriftChecker(MockProvider("reader_basic"))
    goal = "Enter the household in calculator A and read the result"
    ok = chk.check(goal, describe_step("type", {"text": "2"}, label="Household adults"))
    off = chk.check(goal, describe_step("goto", {}, host="crypto-exchange.example"))
    assert ok.on_goal and ok.source == "model"
    assert not off.on_goal


def test_drift_check_prompt_has_goal_and_step_but_no_page_text():
    port = MockProvider("reader_basic")
    DriftChecker(port).check("Do the thing", ProposedStep("click", "on 'Calculate'"), ["click on 'Next'"])
    prompt = next(c for c in port.calls if c["method"] == "check")["prompt"]
    assert "Goal: Do the thing" in prompt and "Proposed step: click on 'Calculate'" in prompt


def test_drift_check_fails_closed_when_the_model_is_unavailable():
    class Down(MockProvider):
        def check(self, prompt, schema):
            raise ProviderError("down")

    v = DriftChecker(Down("reader_basic")).check("g", ProposedStep("click", "x"))
    assert not v.on_goal and v.source == "unavailable"


def test_disabled_drift_check_allows():
    v = DriftChecker(MockProvider("reader_basic"), enabled=False).check("g", ProposedStep("goto", "evil"))
    assert v.on_goal and v.source == "off"
