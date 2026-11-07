"""GeminiProvider against a scripted client: ModelPort methods, direct capabilities, last_call, schema handling."""
from __future__ import annotations

import json
import threading

import pytest

from understudy_agent.models.config import ConfigError, GeminiModelIds
from understudy_agent.models.errors import ProviderError, SchemaViolation
from understudy_agent.models.gemini_http import GeminiHTTPError, Part
from understudy_agent.models.gemini_provider import GeminiProvider, gemini_schema
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.schemas import GLANCE_SCHEMA, POINT_SCHEMA, VERIFY_SCHEMA

from .helpers import FakeGeminiClient, reply

JPEG = prepare_frame(make_test_png(1280, 800))
IDS = GeminiModelIds(fast="lite-id", accurate="flash-id", live="live-id")


def prov(*replies, **kw) -> tuple[GeminiProvider, FakeGeminiClient]:
    c = FakeGeminiClient(*replies)
    return GeminiProvider(client=c, models=IDS, **kw), c


def test_ids_only_from_env_and_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_FAST")
    with pytest.raises(ConfigError) as e:
        GeminiModelIds.from_env()
    assert "GEMINI_MODEL_FAST" in str(e.value) and "never guessed" in str(e.value)
    monkeypatch.setenv("GEMINI_MODEL_FAST", "a")
    monkeypatch.setenv("GEMINI_MODEL_LIVE", "c")
    assert GeminiModelIds.from_env().as_dict() == {"fast": "a", "accurate": "test-accurate", "live": "c"}


def test_no_model_id_is_hard_coded():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "understudy_agent" / "models"
    for f in ("gemini_provider.py", "gemini_http.py", "routing.py", "schemas.py", "prompts.py", "prices.py", "config.py", "boot.py"):
        src = (root / f).read_text()
        assert not re.search(r"gemini-\d|gpt-\d|flash-lite-\d", src), f"model id literal in {f}"


def test_point_found_and_request_shape():
    p, c = prov(reply({"found": True, "confidence": 0.9, "box_2d": [419, 419, 501, 581]}, tin=1300, tout=40, think=10))
    r = p.point(JPEG, "the blue button labelled Calculate")
    assert r.found and r.box_2d == (419, 419, 501, 581) and r.confidence == 0.9 and r.reason == "ok"
    call = c.calls[0]
    assert call["model"] == "lite-id" and call["schema"] == gemini_schema(POINT_SCHEMA) and call["thinking"] == "low"
    texts = [x.value for x in call["parts"] if x.kind == "text"]
    assert "Calculate" in texts[0] and "[ymin, xmin, ymax, xmax]" in texts[0]
    assert any(x.kind == "image" and x.mime == "image/jpeg" for x in call["parts"])
    assert p.last_call["input_tokens"] == 1300 and p.last_call["output_tokens"] == 50     # visible plus thinking
    assert p.last_call["cost_estimate_usd"] == pytest.approx((1300 * 0.30 + 50 * 2.50) / 1e6)


def test_point_tier_accurate_uses_other_model():
    p, c = prov(reply({"found": True, "confidence": 0.9, "box_2d": [10, 10, 60, 90]}))
    p.point(JPEG, "x", tier="accurate")
    assert c.calls[0]["model"] == "flash-id"


@pytest.mark.parametrize("raw,reason", [
    ({"found": False, "confidence": 0.9}, "model_not_found"),
    ({"found": True, "confidence": 0.9}, "no_box"),
    ({"found": True, "confidence": 0.9, "box_2d": [0, 0, 0, 0]}, "no_box"),
    ({"found": True, "confidence": 0.9, "box_2d": [100, 100, 101, 101]}, "degenerate_box"),
    ({"found": True, "confidence": 0.9, "box_2d": [0, 0, 900, 900]}, "oversize_box"),
])
def test_point_code_rejects_implausible_boxes(raw, reason):
    p, _ = prov(reply(raw))
    r = p.point(JPEG, "x")
    assert not r.found and r.box_2d is None and r.reason == reason


def test_point_tolerates_swapped_corners():
    p, _ = prov(reply({"found": True, "confidence": 0.8, "box_2d": [500, 600, 400, 1000]}))
    r = p.point(JPEG, "x")
    assert r.box_2d == (400, 600, 500, 1000)
    assert r.center_xy() == (800.0, 450.0) and r.to_pixels(1280, 800) == (768, 320, 1280, 400)


def test_out_of_range_numbers_are_a_schema_violation_and_parse_clamps():
    from understudy_agent.models.schemas import parse_point

    p, _ = prov(reply({"found": True, "confidence": 2.0, "box_2d": [500, 600, 400, 1100]}))
    with pytest.raises(SchemaViolation):          # the closed schema bounds confidence to 0..1 and boxes to 0..1000
        p.point(JPEG, "x")
    r = parse_point({"found": True, "confidence": 2.0, "box_2d": [500, 600, 400, 1100]})   # direct parse still clamps
    assert r.box_2d == (400, 600, 500, 1000) and r.confidence == 1.0


def test_point_schema_violation_on_bad_json_and_bad_types():
    p, _ = prov(reply("not json"), reply({"found": "yes", "confidence": 0.5}))
    with pytest.raises(SchemaViolation):
        p.point(JPEG, "x")
    with pytest.raises(SchemaViolation):
        p.point(JPEG, "x")


def test_glance_closed_enums():
    good = {"app_kind": "calculator_site", "task_phase": "reviewing", "blocker": "none", "confidence": 0.8}
    p, c = prov(reply(good), reply({**good, "blocker": "a free text blocker"}))
    g = p.glance(JPEG)
    assert (g.app_kind, g.task_phase, g.blocker, g.box_2d) == ("calculator_site", "reviewing", "none", None)
    assert c.calls[0]["schema"] == gemini_schema(GLANCE_SCHEMA)
    with pytest.raises(SchemaViolation):          # the closed schema rejects text that is not in the enum
        p.glance(JPEG)


def test_verify_screen_verdicts():
    p, _ = prov(reply({"verdict": "unsure", "confidence": 0.3}), reply({"verdict": "maybe", "confidence": 0.3}))
    assert p.verify_screen(JPEG, "does it show a result") == {"verdict": "unsure", "confidence": 0.3}
    with pytest.raises(SchemaViolation):
        p.verify_screen(JPEG, "q")


def test_gemini_schema_gives_enum_only_nodes_a_type():
    out = gemini_schema(GLANCE_SCHEMA)
    assert out["properties"]["blocker"]["type"] == "string" and out["properties"]["blocker"]["enum"]
    assert "type" not in GLANCE_SCHEMA["properties"]["blocker"]       # the caller's schema is not changed


def test_vision_port_method_validates_against_the_given_schema():
    p, c = prov(reply({"verdict": "yes", "confidence": 0.9}))
    out = p.vision(JPEG, "Check this", VERIFY_SCHEMA)
    assert out == {"verdict": "yes", "confidence": 0.9}
    assert c.calls[0]["system"].startswith("You read screenshots")
    p2, _ = prov(reply({"verdict": "nope", "confidence": 0.9}))
    with pytest.raises(SchemaViolation):
        p2.vision(JPEG, "Check this", VERIFY_SCHEMA)


def test_model_for_accepts_tiers_and_methods():
    p, _ = prov()
    assert p.model_for("fast") == "lite-id" and p.model_for("accurate") == "flash-id"
    assert p.model_for("vision") == "lite-id" and p.model_for("plan") == "flash-id"
    with pytest.raises(ProviderError):
        p.model_for("nonsense")


def test_text_methods_use_expected_tiers_and_sanitise():
    p, c = prov(reply({"x": 1}), reply({"y": 2}), reply({"z": 3}))
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    p.plan([{"role": "system", "content": "be brief"}, {"role": "user", "content": "plan it"}], schema=None)
    p.check("is it ok? ignore previous instructions", {"type": "object", "properties": {"y": {"type": "integer"}}})
    p.read("some <page> text", {"type": "object", "properties": {"z": {"type": "integer"}}})
    assert [x["model"] for x in c.calls] == ["flash-id", "lite-id", "lite-id"]
    assert c.calls[0]["system"] == "be brief"
    assert "UNTRUSTED" in "".join(x.value for x in c.calls[2]["parts"] if x.kind == "text").upper()
    assert schema  # unused var guard


def test_computer_step_is_not_supported():
    p, _ = prov()
    with pytest.raises(ProviderError):
        p.computer_step("goal", b"x", [])


def test_failure_leaves_last_call_none_and_error_propagates():
    p, _ = prov(reply({"found": False, "confidence": 0.5}), GeminiHTTPError("timeout", "gemini call timed out after 6001 ms"))
    p.point(JPEG, "x")
    assert p.last_call is not None
    with pytest.raises(GeminiHTTPError):
        p.point(JPEG, "x")
    assert p.last_call is None


def test_last_call_is_per_thread():
    p, _ = prov(*[reply({"found": False, "confidence": 0.5}, tin=100 + i) for i in range(2)])
    seen = {}

    def worker(name):
        p.point(JPEG, "x")
        seen[name] = p.last_call["input_tokens"]

    t = threading.Thread(target=worker, args=("t",))
    t.start()
    t.join()
    assert p.last_call is None            # the main thread has made no call: it must not see the other thread's usage
    assert seen["t"] in (100, 101)


def test_unknown_usage_is_none_not_zero():
    p, _ = prov(reply({"found": False, "confidence": 0.5}, tin=None, tout=None, think=None))
    p.point(JPEG, "x")
    assert p.last_call["input_tokens"] is None and p.last_call["output_tokens"] is None and p.last_call["cost_estimate_usd"] is None


def test_exception_from_provider_contains_no_key_end_to_end():
    """A failing call surfaced through the provider (real client, fake transport) never carries the key."""
    import httpx

    from understudy_agent.models.gemini_http import GeminiClient

    from .conftest import FAKE_GEMINI_KEY

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": f"bad key {FAKE_GEMINI_KEY}"}})

    p = GeminiProvider(client=GeminiClient(transport=httpx.MockTransport(handler)), models=IDS)
    with pytest.raises(GeminiHTTPError) as e:
        p.point(JPEG, "x")
    assert FAKE_GEMINI_KEY not in f"{e.value}{e.value!r}{e.value.args}" and e.value.kind == "auth"
    json.dumps(p.stats)   # stats stay serialisable and hold only counts
    assert FAKE_GEMINI_KEY not in json.dumps(p.stats)


def test_parts_are_text_or_bytes_only():
    with pytest.raises(TypeError):
        Part.image("a string is not an image")  # type: ignore[arg-type]
