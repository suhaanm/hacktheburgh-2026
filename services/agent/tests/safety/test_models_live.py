"""Live probes (spike S1). A handful of tiny calls. Run with:
    UNDERSTUDY_LIVE=1 uv run --env-file .env pytest services/agent/tests/safety/test_models_live.py -m live -q
"""
from __future__ import annotations

import pytest

from understudy_agent.models import Action, Done, SafetyStop, boot_check
from understudy_agent.models.imaging import make_test_png
from understudy_agent.models.openai_provider import OpenAIProvider

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def provider():
    boot_check(out=lambda s: None)  # raises SystemExit with usable ids if a configured model is missing
    return OpenAIProvider()


def test_live_boot_check_models_usable():
    rep = boot_check(raise_on_fail=False, out=lambda s: None)
    assert rep.ok, rep.message


def test_live_structured_output(provider):
    schema = {"title": "sky", "type": "object", "required": ["colour"], "properties": {"colour": {"type": "string"}}}
    out = provider.check("What colour is the sky on a clear day? Answer with one word.", schema)
    assert "blue" in out["colour"].lower()


def test_live_vision_on_generated_png(provider):
    schema = {"title": "button", "type": "object", "required": ["label"], "properties": {"label": {"type": "string"}}}
    out = provider.vision(make_test_png(1280, 720, "Calculate"), "What is the label on the blue button?", schema)
    assert "calculate" in out["label"].lower()


def test_live_computer_tool_probe(provider):
    shot = make_test_png(2560, 1440, "Calculate")  # 2x-sized screenshot exercises downscale and mapping
    out = provider.computer_step("Click the blue Calculate button.", shot, [], session="live-probe")
    assert isinstance(out, (Action, Done, SafetyStop))
    if isinstance(out, Action):
        assert out.kind == "click"
        # button sits near the middle of the 2560x1440 image: x in [1075, 1485], y in [605, 720]
        assert 1000 < out.args["x"] < 1560 and 560 < out.args["y"] < 780, out
