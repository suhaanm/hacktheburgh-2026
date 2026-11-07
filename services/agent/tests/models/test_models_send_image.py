"""The Gemini provider as a port behind the privacy track's `egress.send_image` (CapturingPort-style), and last_call on both providers."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest
from understudy_engine.privacy import egress, ledger
from understudy_engine.privacy.image import ImageGate, SafeImage
from understudy_engine.privacy.testing import CapturingPort

from understudy_agent.models.config import GeminiModelIds, ModelIds
from understudy_agent.models.gemini_provider import GeminiProvider
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.openai_provider import OpenAIProvider

from .helpers import FakeGeminiClient, make_image, reply, sandbox_gate

IDS = GeminiModelIds(fast="lite-id", accurate="flash-id")


def gemini_port(*replies):
    return GeminiProvider(client=FakeGeminiClient(*replies), models=IDS)


def test_send_image_point_through_gemini_provider_records_usage_and_no_pixels():
    port = gemini_port(reply({"found": True, "confidence": 0.9, "box_2d": [419, 419, 501, 581]}, tin=1236, tout=39, think=0))
    img = make_image("point")
    res = egress.send_image("point.element", img, {"step": "submit"}, gate=sandbox_gate(), port=port)
    assert res.output == {"found": True, "confidence": 0.9, "box_2d": [419, 419, 501, 581]}
    assert res.provider == "gemini" and res.model == "gemini:lite-id"
    assert (res.input_tokens, res.output_tokens) == (1236, 39)
    assert res.cost_estimate_usd == pytest.approx((1236 * 0.30 + 39 * 2.50) / 1e6, abs=1e-6)
    rows = ledger.read_all()
    text = json.dumps(rows)
    assert rows and rows[0]["model"] == "gemini:lite-id" and rows[0]["source"] == "sandbox"
    assert img.sha8 in text and "image" in rows[0]
    assert "SECRET" not in text and "/9j/" not in text          # no base64 JPEG header anywhere in the ledger
    assert img.released                                         # the frame was wiped after the call


def test_send_image_glance_and_verify_validate_the_closed_answer():
    port = gemini_port(
        reply({"app_kind": "calculator_site", "task_phase": "entering", "blocker": "none", "confidence": 0.9}),
        reply({"verdict": "yes", "confidence": 0.8}))
    r1 = egress.send_image("glance.screen_state", make_image("glance"),
                           {"mode": "triggered", "trigger": "stuck", "strict": False}, gate=sandbox_gate(), port=port)
    assert r1.output["app_kind"] == "calculator_site"
    r2 = egress.send_image("verify.agent_run", make_image("verify"), {"check": "page_shows_result"}, gate=sandbox_gate(), port=port)
    assert r2.output["verdict"] == "yes"


def test_send_image_rejects_free_text_answer_even_if_provider_accepted_it():
    """Defence in depth: if a provider returned an off-schema answer, egress discards it (the provider already raises)."""
    port = CapturingPort().script("vision", {"found": True, "confidence": 0.9, "label": "the secret account number"})
    with pytest.raises(egress.ModelOutputRejected):
        egress.send_image("point.element", make_image("point"), {"step": "submit"}, gate=sandbox_gate(), port=port)


def test_send_image_provider_failure_is_recorded_by_type_only():
    from understudy_agent.models.gemini_http import GeminiHTTPError

    port = gemini_port(GeminiHTTPError("timeout", "gemini call timed out after 6001 ms"))
    with pytest.raises(egress.ModelCallFailed) as e:
        egress.send_image("point.element", make_image("point"), {"step": "next"}, gate=sandbox_gate(), port=port)
    assert "GeminiHTTPError" in str(e.value) and "timed out after" not in str(e.value)
    assert port.last_call is None


def test_capturing_port_sees_prompt_and_closed_schema_only():
    port = CapturingPort()
    res = egress.send_image("point.element", make_image("point"), {"step": "save"}, gate=sandbox_gate(), port=port)
    assert res.output["found"] in (True, False)
    assert port.image_calls and "bytes" in port.image_calls[0]


def test_real_screen_unattended_is_blocked_before_any_call():
    port = gemini_port()   # an empty script: any call would raise IndexError
    gate = ImageGate(consent=True, denylisted_app=False, secure_input=False, unattended=True, source="real_screen")
    img = SafeImage(prepare_frame(make_test_png(640, 400)), "glance", source="real_screen")
    with pytest.raises(egress.ImageBlocked):
        egress.send_image("glance.screen_state", img, {"mode": "triggered", "trigger": "stuck", "strict": False},
                          gate=gate, port=port)
    assert port.client.calls == []


def test_openai_provider_sets_last_call(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.responses = NS(create=self._create)

        def _create(self, **kw):
            return NS(id="r1", output=[NS(type="message", content=[NS(type="output_text", text='{"verdict":"yes","confidence":0.7}')])],
                      output_text='{"verdict":"yes","confidence":0.7}', status="completed",
                      usage=NS(input_tokens=1500, output_tokens=60))

    p = OpenAIProvider(client=FakeClient(), models=ModelIds(planner="p", fast="f", computer_use="c"))
    assert p.last_call is None
    out = p.vision(make_test_png(640, 400), "check", {"type": "object", "properties": {
        "verdict": {"enum": ["yes", "no", "unsure"]}, "confidence": {"type": "number"}}, "required": ["verdict", "confidence"],
        "additionalProperties": False})
    assert out == {"verdict": "yes", "confidence": 0.7}
    assert p.last_call["input_tokens"] == 1500 and p.last_call["output_tokens"] == 60
    assert p.last_call["cost_estimate_usd"] == pytest.approx((1500 * 0.75 + 60 * 4.5) / 1e6)
    # the openai provider works as the port behind egress too (enum-only schema nodes get a type for strict mode)
    res = egress.send_image("verify.agent_run", make_image("verify"), {"check": "page_shows_result"}, gate=sandbox_gate(), port=p)
    assert res.output["verdict"] == "yes" and res.input_tokens == 1500
