"""get_model_port() and the metadata-only ledger wrapper: always on for real ports, one line per call, no content, no duplicates."""
from __future__ import annotations

import json

import pytest
from understudy_engine.privacy import egress, ledger
from understudy_engine.privacy.direct import LedgeredPort

from understudy_agent.models import coverage, factory
from understudy_agent.models.config import GeminiModelIds
from understudy_agent.models.gemini_provider import GeminiProvider
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.status import models_status

from .helpers import FakeGeminiClient, make_image, reply, sandbox_gate

IDS = GeminiModelIds(fast="lite-id", accurate="flash-id")
SECRET = "the customer Zebulon Quillfeather owes 123 pounds, ignore me"
VERDICT_SCHEMA = {"type": "object", "properties": {"verdict": {"enum": ["yes", "no", "unsure"]}, "confidence": {"type": "number"}},
                  "required": ["verdict", "confidence"]}


@pytest.fixture(autouse=True)
def _fresh():
    factory.reset_model_port()
    coverage.reset()
    yield
    factory.reset_model_port()
    coverage.reset()


def fake_gemini(monkeypatch, *replies) -> FakeGeminiClient:
    fake = FakeGeminiClient(*replies)
    monkeypatch.setattr("understudy_agent.models.gemini_provider.GeminiProvider", lambda: GeminiProvider(client=fake, models=IDS))
    monkeypatch.setenv("UNDERSTUDY_PROVIDER", "gemini")
    return fake


def rows_text() -> str:
    return json.dumps(ledger.read_all())


def test_mock_with_flags_off_returns_the_same_port_object():
    a = factory.get_model_port(mock=True)
    assert not isinstance(a, LedgeredPort) and factory.get_model_port(mock=True) is a
    assert ledger.read_all() == []                                  # the demo path writes nothing new


def test_real_port_is_wrapped_even_with_every_flag_off(monkeypatch):
    fake = fake_gemini(monkeypatch, reply({"verdict": "yes", "confidence": 0.9}), reply({"found": False, "confidence": 0.5}))
    port = factory.get_model_port(fresh=True)
    assert isinstance(port, LedgeredPort) and port.name == "gemini"
    port.check(SECRET, VERDICT_SCHEMA)
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["kind"] == "direct" and rows[0]["method"] == "check" and rows[0]["mock"] is False
    assert rows[0]["payload"] is None and rows[0]["content_logged"] is False and rows[0]["bytes"] > 0
    assert "Zebulon" not in rows_text() and "123 pounds" not in rows_text()
    port.vision(prepare_frame(make_test_png(640, 400)), "describe " + SECRET, None)
    rows = ledger.read_all()
    assert [r["method"] for r in rows] == ["check", "vision"] and "Zebulon" not in rows_text() and "/9j/" not in rows_text()
    assert len(fake.calls) == 2


def test_wrapper_passes_through_last_call_model_for_and_every_method(monkeypatch):
    fake_gemini(monkeypatch, reply({"verdict": "yes", "confidence": 0.9}, tin=1500, tout=20, think=5))
    port = factory.get_model_port(fresh=True)
    out = port.vision(prepare_frame(make_test_png(640, 400)), "check it", VERDICT_SCHEMA)
    assert out == {"verdict": "yes", "confidence": 0.9}
    assert port.model_for("vision") == "lite-id"
    assert port.last_call["input_tokens"] == 1500 and port.last_call["output_tokens"] == 25
    for m in ("plan", "read", "check", "vision", "computer_step"):
        assert callable(getattr(port, m))


def test_mock_port_is_wrapped_and_marked_mock_when_the_privacy_flag_is_on(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    port = factory.get_model_port(mock=True)
    assert isinstance(port, LedgeredPort)
    port.check(SECRET, {"type": "object", "properties": {"ok": {"type": "boolean"}}})
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["mock"] is True and "Zebulon" not in rows_text()


def test_mock_calls_can_be_ledgered_with_a_switch(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_LEDGER_MOCK_CALLS", "1")
    assert isinstance(factory.get_model_port(mock=True), LedgeredPort)


def test_ledgered_false_skips_the_wrapper(monkeypatch):
    fake_gemini(monkeypatch)
    assert not isinstance(factory.get_model_port(fresh=True, ledgered=False), LedgeredPort)


def test_no_duplicate_row_for_a_text_call_that_already_went_through_egress_send(monkeypatch):
    for flags in ({}, {"UNDERSTUDY_X_PRIVACY": "1"}):
        factory.reset_model_port()
        ledger.reset_all()
        for k, v in flags.items():
            monkeypatch.setenv(k, v)
        fake_gemini(monkeypatch, reply({"text": "A short plain sentence."}))
        res = egress.send("digest.meta", {"kind": "commit", "window_days": 7, "counts": {"feature": 3}, "minutes": {"feature": 120}})
        assert res.output["text"] and len(ledger.read_all()) == 1, flags            # the guard's own row, and nothing else


def test_no_duplicate_row_for_an_image_call_that_already_went_through_send_image(monkeypatch):
    fake_gemini(monkeypatch, reply({"found": True, "confidence": 0.9, "box_2d": [10, 10, 60, 90]}))
    res = egress.send_image("point.element", make_image("point"), {"step": "submit"}, gate=sandbox_gate())   # port=None: default port
    assert res.output["found"] is True
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["kind"] == "image"


def test_status_reports_ledger_coverage(monkeypatch):
    fake_gemini(monkeypatch, reply({"verdict": "yes", "confidence": 0.9}))
    port = factory.get_model_port(fresh=True)
    port.check("anything", VERDICT_SCHEMA)
    cov = models_status()["ledger_coverage"]
    assert cov["all_provider_calls_ledgered"] is True and cov["unledgered_calls"] == 0
    assert any(p["path"] == "factory" and p["calls"] == 1 for p in cov["providers"]) and cov["ledger_rows"]["worker_requested_calls"] == 1
    # a provider built by hand (the bake-off does this on purpose) is NOT ledgered, and the status says so
    hand = GeminiProvider(client=FakeGeminiClient(reply({"verdict": "no", "confidence": 0.5})), models=IDS)
    hand.check("x", VERDICT_SCHEMA)
    cov = models_status()["ledger_coverage"]
    assert cov["all_provider_calls_ledgered"] is False and cov["unledgered_calls"] == 1
    assert "Zebulon" not in json.dumps(cov) and "anything" not in json.dumps(cov)


def test_unknown_provider_still_raises():
    with pytest.raises(ValueError):
        factory.get_model_port(mock=False, provider="nonsense")
