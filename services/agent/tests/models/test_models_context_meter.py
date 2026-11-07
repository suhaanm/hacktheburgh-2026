"""REQ-8: context manifests in the meter, cached input tokens, image tokens, image size limits, minimal closed prompts."""
from __future__ import annotations

import base64
import json
import random
from types import SimpleNamespace as NS

import httpx
import pytest
from understudy_engine.privacy import ledger
from understudy_engine.privacy.image import closed_schema_problem

from understudy_agent.models import prompts
from understudy_agent.models.config import GeminiModelIds, ModelIds
from understudy_agent.models.gemini_http import GeminiClient, Part
from understudy_agent.models.gemini_provider import GeminiProvider
from understudy_agent.models.imaging import MAX_FRAME_BYTES, make_test_png, prepare_frame
from understudy_agent.models.meter import (CallRecord, Meter, call_context, clean_manifest, current_manifest, default_meter,
                                           reset_default_meter)
from understudy_agent.models.openai_provider import OpenAIProvider
from understudy_agent.models.prices import assumptions, cost_estimate, price_for
from understudy_agent.models.routing import GeminiBackend, ModelRouter
from understudy_agent.models import routes

from .helpers import FakeGeminiClient, make_image, reply, sandbox_gate

IDS = GeminiModelIds(fast="lite-id", accurate="flash-id")
JPEG = prepare_frame(make_test_png(1280, 800))
MANIFEST = {"sections": [{"name": "system", "tokens": 812, "stable": True}, {"name": "pack", "tokens": 640}, {"name": "recent_events", "tokens": 90}],
            "dropped_items": 3, "prefix_hash": "a1b2c3d4e5f6a1b2c3d4", "prefix_tokens": 1500, "total_tokens": 1542}


@pytest.fixture(autouse=True)
def _fresh_meter():
    reset_default_meter()
    yield
    reset_default_meter()


def prov(*replies):
    c = FakeGeminiClient(*replies)
    return GeminiProvider(client=c, models=IDS), c


# ------------------------------------------------------------------------------------------------ the manifest is metadata only
def test_clean_manifest_keeps_metadata_and_drops_everything_else():
    m = clean_manifest({**MANIFEST, "text": "the customer Zebulon", "path": "/Users/x/y",
                        "sections": MANIFEST["sections"] + [{"name": "Bad Name!", "tokens": 5}, {"name": "ok", "tokens": "many"},
                                                            {"name": "nested", "tokens": {"a": 1}}, "junk"]})
    assert m == {"sections": {"system": 812, "pack": 640, "recent_events": 90}, "dropped_items": 3, "prefix_tokens": 1500,
                 "total_tokens": 1542, "prefix_hash": "a1b2c3d4e5f6"}
    assert "Zebulon" not in json.dumps(m) and "/Users" not in json.dumps(m)
    assert clean_manifest("nope") == {} and clean_manifest({"prefix_hash": "not hex!"}) == {}
    assert clean_manifest({"sections": {"a": 1, "b": -5, "c": True}}) == {"sections": {"a": 1}}          # a dict form is accepted; bad counts dropped


def test_call_context_is_scoped_and_nested_safe():
    assert current_manifest() is None
    with call_context(MANIFEST):
        assert current_manifest()["dropped_items"] == 3
        with call_context({"dropped_items": 9}):
            assert current_manifest() == {"dropped_items": 9}
        assert current_manifest()["dropped_items"] == 3
    assert current_manifest() is None


# ------------------------------------------------------------------------------------------------ provider calls are metered with it
def test_gemini_call_inside_a_context_gets_section_tokens_and_cache_fields(tmp_path):
    p, _ = prov(reply({"found": False, "confidence": 0.5}, tin=1500, tout=40, think=10))
    with call_context(MANIFEST):
        p.point(JPEG, "x")
    rec = default_meter().records()[-1]
    assert (rec["provider"], rec["role"], rec["ok"], rec["tier"]) == ("gemini", "point", True, "fast")
    assert rec["ctx_sections"] == {"system": 812, "pack": 640, "recent_events": 90} and rec["ctx_dropped_items"] == 3
    assert rec["ctx_prefix_hash"] == "a1b2c3d4e5f6" and rec["ctx_prefix_tokens"] == 1500 and rec["cache_eligible"] is True
    # the JSONL next to the ledger carries the same metadata and nothing else
    line = json.loads((ledger.ledger_path().with_name("model_meter.jsonl")).read_text().splitlines()[-1])
    assert line["ctx_sections"]["system"] == 812 and "image" not in json.dumps(line).lower().replace("image_tokens", "")


def test_cache_eligibility_follows_the_prefix_length_and_the_env_minimum(monkeypatch):
    p, _ = prov(reply({"found": False, "confidence": 0.5}), reply({"found": False, "confidence": 0.5}))
    with call_context({**MANIFEST, "prefix_tokens": 600}):
        p.point(JPEG, "x")
    assert default_meter().records()[-1]["cache_eligible"] is False
    monkeypatch.setenv("UNDERSTUDY_CACHE_MIN_TOKENS_GEMINI", "500")
    with call_context({**MANIFEST, "prefix_tokens": 600}):
        p.point(JPEG, "x")
    assert default_meter().records()[-1]["cache_eligible"] is True


def test_a_call_without_a_manifest_has_no_context_fields_and_failures_are_recorded():
    from understudy_agent.models.gemini_http import GeminiHTTPError

    p, _ = prov(reply({"found": False, "confidence": 0.5}), GeminiHTTPError("timeout", "slow"))
    p.point(JPEG, "x")
    r = default_meter().records()[-1]
    assert r["ctx_sections"] is None and r["cache_eligible"] is None
    with pytest.raises(GeminiHTTPError):
        p.point(JPEG, "x")
    f = default_meter().records()[-1]
    assert f["ok"] is False and f["error_kind"] == "timeout"


def test_openai_call_records_cached_tokens_and_the_cost_discount(monkeypatch):
    def resp(cached):
        return NS(id="r", output=[NS(type="message", content=[NS(type="output_text", text='{"text": "x"}')])], output_text='{"text": "x"}',
                  status="completed", usage=NS(input_tokens=4000, output_tokens=100, input_tokens_details=NS(cached_tokens=cached)))

    class FakeClient:
        def __init__(self, *rs):
            self.q, self.responses = list(rs), NS(create=lambda **kw: self.q.pop(0))

    p = OpenAIProvider(client=FakeClient(resp(0), resp(3072)), models=ModelIds(planner="p", fast="f", computer_use="c"))
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    with call_context(MANIFEST):
        p.plan([{"role": "user", "content": "plan"}], schema)
        cold = p.last_call
        p.plan([{"role": "user", "content": "plan"}], schema)
        warm = p.last_call
    assert cold["cached_input_tokens"] == 0 and warm["cached_input_tokens"] == 3072
    assert warm["cost_estimate_usd"] < cold["cost_estimate_usd"]
    expected = ((4000 - 3072) * 5.0 + 3072 * 5.0 * 0.25 + 100 * 30.0) / 1e6
    assert warm["cost_estimate_usd"] == pytest.approx(expected)
    recs = default_meter().records()
    assert [r["cached_input_tokens"] for r in recs] == [0, 3072] and recs[1]["role"] == "planner" and recs[1]["cache_eligible"] is True
    row = default_meter().summary()[0]
    assert row["cached_input_tokens"] == 3072 and row["cached_share_of_input"] == pytest.approx(3072 / 8000, abs=1e-4)
    assert row["calls_with_manifest"] == 2 and row["dropped_items"] == 6 and row["mean_section_tokens"]["system"] == 812.0


def test_unreported_cache_and_image_tokens_are_none_not_zero():
    p, _ = prov(reply({"found": False, "confidence": 0.5}))
    p.point(JPEG, "x")
    r = default_meter().records()[-1]
    assert r["cached_input_tokens"] is None and r["image_tokens"] is None


# ------------------------------------------------------------------------------------------------ what the providers report
def test_gemini_interactions_usage_gives_cached_and_image_tokens():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "{}"}]}],
                                         "usage": {"total_input_tokens": 1149, "total_output_tokens": 33, "total_thought_tokens": 0,
                                                   "total_cached_tokens": 512,
                                                   "input_tokens_by_modality": [{"modality": "text", "tokens": 57}, {"modality": "image", "tokens": 1092}]}})

    r = GeminiClient(transport=httpx.MockTransport(handler)).generate("m", [Part.text("x")])
    assert (r.cached_input_tokens, r.image_tokens) == (512, 1092)


def test_gemini_generate_content_usage_gives_cached_and_image_tokens():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}],
                                         "usageMetadata": {"promptTokenCount": 1126, "candidatesTokenCount": 48, "cachedContentTokenCount": 256,
                                                           "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 34}, {"modality": "IMAGE", "tokenCount": 1092}]}})

    r = GeminiClient(api="generate_content", transport=httpx.MockTransport(handler)).generate("m", [Part.text("x")])
    assert (r.cached_input_tokens, r.image_tokens) == (256, 1092)


def test_router_calls_are_metered_once_by_the_router_not_twice():
    fake = FakeGeminiClient(reply({"found": True, "confidence": 0.9, "box_2d": [10, 10, 60, 90]}, tin=1300))
    backend = GeminiBackend(provider_obj=GeminiProvider(client=fake, models=IDS))
    rm = Meter()
    router = ModelRouter(backends={"gemini": backend}, meter=rm)
    res = router.point(make_image("point"), "submit", gate=sandbox_gate())
    assert res.outcome == "answered"
    assert len(rm.records()) == 1 and default_meter().records() == []         # the provider's own line is suppressed inside a routed call
    assert rm.records()[0]["cached_input_tokens"] is None


def test_router_record_carries_cached_and_image_tokens_when_the_provider_reports_them():
    from understudy_agent.models.gemini_http import GeminiReply

    r = GeminiReply(text=json.dumps({"found": False, "confidence": 0.9}), input_tokens=1300, output_tokens=40, thought_tokens=0, latency_ms=50,
                    api="interactions", model="m", finish="completed", cached_input_tokens=1024, image_tokens=1092)
    backend = GeminiBackend(provider_obj=GeminiProvider(client=FakeGeminiClient(r), models=IDS))
    rm = Meter()
    ModelRouter(backends={"gemini": backend}, meter=rm).point(make_image("point"), "submit", gate=sandbox_gate())
    rec = rm.records()[0]
    assert rec["image_tokens"] == 1092 and rec["cached_input_tokens"] == 1024
    assert rec["cost_usd"] == pytest.approx(cost_estimate("gemini", "fast", 1300, 40, 1024))


# ------------------------------------------------------------------------------------------------ image sizes
def test_openai_vision_sends_a_jpeg_inside_the_frame_limit_when_the_png_is_too_big():
    rng = random.Random(7)
    noisy = make_test_png(1280, 720)
    from PIL import Image
    import io

    im = Image.frombytes("RGB", (1280, 720), rng.randbytes(1280 * 720 * 3))      # noise: a worst-case PNG
    buf = io.BytesIO()
    im.save(buf, "PNG")
    assert len(buf.getvalue()) > MAX_FRAME_BYTES and noisy
    seen = {}

    class FakeClient:
        def __init__(self):
            self.responses = NS(create=self._create)

        def _create(self, **kw):
            seen["url"] = kw["input"][0]["content"][1]["image_url"]
            return NS(id="r", output=[NS(type="message", content=[NS(type="output_text", text="{}")])], output_text="{}", status="completed",
                      usage=NS(input_tokens=10, output_tokens=2))

    p = OpenAIProvider(client=FakeClient(), models=ModelIds(planner="p", fast="f", computer_use="c"))
    p.vision(buf.getvalue(), "q", {"type": "object", "properties": {}})
    assert seen["url"].startswith("data:image/jpeg;base64,")
    assert len(base64.b64decode(seen["url"].split(",", 1)[1])) <= MAX_FRAME_BYTES
    # a normal screenshot stays a PNG
    p.vision(make_test_png(1280, 720), "q", {"type": "object", "properties": {}})
    assert seen["url"].startswith("data:image/png;base64,")


def test_prepare_frame_respects_both_limits():
    from PIL import Image
    import io

    im = Image.frombytes("RGB", (2560, 1600), random.Random(3).randbytes(2560 * 1600 * 3))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out = prepare_frame(buf.getvalue())
    w, h = Image.open(io.BytesIO(out)).size
    assert max(w, h) <= 1280 and len(out) <= MAX_FRAME_BYTES


# ------------------------------------------------------------------------------------------------ minimal closed prompts (CTX audit)
def test_glance_and_ground_requests_are_minimal_and_closed():
    import understudy_engine.awareness.purposes as ap
    from understudy_engine.awareness import schema as aschema
    from understudy_engine.privacy.image import get_image_purpose

    gl = get_image_purpose("awareness.glance")
    assert closed_schema_problem(aschema.glance_response_schema()) is None and gl.model.field_names() == ["trigger", "app_kind"]
    assert len(prompts.format_note("glance")) + len(ap.INSTRUCTIONS) < 2000            # a few hundred tokens of fixed text, no screen content
    menu = [{"id": "calc", "label": "the Calculate button"}, {"id": "next", "label": "the Continue button"}]
    assert closed_schema_problem(routes.cue_schema(["calc", "next"])) is None
    ins = routes.cue_instructions(menu)
    assert len(ins) < 1400 and "calc: the Calculate button" in ins
    name = routes.ensure_cue_purpose(menu)
    assert get_image_purpose(name).model.field_names() == ["app_kind"]                 # beside the frame: one enum, never a label or text


def test_prices_label_the_cached_assumption_and_accept_an_override(monkeypatch):
    assert assumptions()["openai.planner"]["cached_input_source"].startswith("assumed")
    monkeypatch.setenv("UNDERSTUDY_PRICE_OPENAI_PLANNER_CACHED_IN", "0.5")
    p = price_for("openai", "planner")
    assert p.cached_price == 0.5 and p.as_dict()["cached_input_source"] == "env"
    assert cost_estimate("openai", "planner", 1_000_000, 0, 1_000_000) == pytest.approx(0.5)
    assert cost_estimate("openai", "planner", 1000, 10, 5000) == cost_estimate("openai", "planner", 1000, 10, 1000)      # cached is capped at input


def test_a_manual_call_record_with_context_fields_round_trips_through_the_meter():
    m = Meter()
    m.record(CallRecord(role="planner", provider="openai", model="x", tier="planner", method="plan", ok=True, latency_ms=900, input_tokens=4000,
                        output_tokens=100, cached_input_tokens=2048, cache_eligible=True, ctx_sections={"system": 800}, ctx_dropped_items=2))
    row = m.summary()[0]
    assert row["cached_input_tokens"] == 2048 and row["cache_eligible_calls"] == 1 and row["mean_section_tokens"] == {"system": 800.0}


def test_extra_context_keys_and_estimate_error_are_recorded():
    """CONTEXT's manifest adds `stale` (names) and `image_frames`; the record keeps the provider's input tokens beside the estimate."""
    p, _ = prov(reply({"found": False, "confidence": 0.5}, tin=1700, tout=40, think=0))
    manifest = {**MANIFEST, "total_tokens": 1500, "stale": ["calendar", "Bad Name", "git"], "image_frames": 1, "note": "free text is dropped"}
    with call_context(manifest):
        p.point(JPEG, "x")
    r = default_meter().records()[-1]
    assert r["ctx_stale"] == ["calendar", "git"] and r["ctx_image_frames"] == 1
    assert r["input_tokens"] == 1700 and r["ctx_total_tokens"] == 1500 and r["ctx_estimate_error"] == 200      # actual minus estimate
    assert "free text" not in json.dumps(r)
    assert default_meter().summary()[0]["mean_ctx_estimate_error_tokens"] == 200.0


def test_gemini_provider_keeps_every_image_inside_the_frame_limits():
    from PIL import Image
    import io

    big = Image.frombytes("RGB", (2000, 1200), random.Random(5).randbytes(2000 * 1200 * 3))
    buf = io.BytesIO()
    big.save(buf, "PNG")
    p, c = prov(reply({"found": False, "confidence": 0.5}), reply({"found": False, "confidence": 0.5}))
    p.point(buf.getvalue(), "x")
    sent = [x for x in c.calls[0]["parts"] if x.kind == "image"][0].value
    w, h = Image.open(io.BytesIO(sent)).size
    assert len(sent) <= MAX_FRAME_BYTES and max(w, h) <= 1280
    p.point(JPEG, "x")
    assert [x for x in c.calls[1]["parts"] if x.kind == "image"][0].value == JPEG       # a frame that already fits is sent untouched
