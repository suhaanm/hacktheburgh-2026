"""GeminiClient against httpx.MockTransport: request shapes on both API paths, usage parsing, errors, and key hygiene."""
from __future__ import annotations

import json

import httpx
import pytest

from understudy_agent.models.config import ConfigError
from understudy_agent.models.errors import ModelRefusal
from understudy_agent.models.gemini_http import GeminiClient, GeminiHTTPError, Part
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.redact import contains_secret

from .conftest import FAKE_GEMINI_KEY
from .helpers import SECRET_PIXELS

JPEG = prepare_frame(make_test_png(640, 400))
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def client(handler, api="interactions") -> GeminiClient:
    return GeminiClient(api=api, transport=httpx.MockTransport(handler))


def interactions_ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={
        "status": "completed", "steps": [{"type": "thought", "signature": "x"},
                                         {"type": "model_output", "content": [{"type": "text", "text": '{"ok": true}'}]}],
        "usage": {"total_input_tokens": 1149, "total_output_tokens": 33, "total_thought_tokens": 72}})


def test_interactions_request_shape_and_key_in_header_only():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"], seen["body"] = str(req.url), dict(req.headers), json.loads(req.content)
        return interactions_ok(req)

    r = client(handler).generate("m-1", [Part.text("hi"), Part.image(JPEG)], system="sys", schema=SCHEMA, thinking="low",
                                 max_output_tokens=300)
    assert r.text == '{"ok": true}' and (r.input_tokens, r.output_tokens, r.thought_tokens) == (1149, 33, 72)
    assert r.billed_output_tokens == 105
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert seen["headers"]["x-goog-api-key"] == FAKE_GEMINI_KEY
    assert FAKE_GEMINI_KEY not in seen["url"] and "key=" not in seen["url"]
    b = seen["body"]
    assert b["model"] == "m-1" and b["store"] is False and b["system_instruction"] == "sys"
    assert b["generation_config"] == {"max_output_tokens": 300, "thinking_level": "low"}
    assert b["response_format"] == {"type": "text", "mime_type": "application/json", "schema": SCHEMA}
    assert b["input"][0] == {"type": "text", "text": "hi"}
    assert b["input"][1]["type"] == "image" and b["input"][1]["mime_type"] == "image/jpeg" and b["input"][1]["data"]
    assert FAKE_GEMINI_KEY not in json.dumps(b)


def test_generate_content_fallback_request_shape_and_usage():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"], seen["body"] = str(req.url), dict(req.headers), json.loads(req.content)
        return httpx.Response(200, json={
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "thinking...", "thought": True},
                                                                         {"text": '{"ok": false}'}]}}],
            "usageMetadata": {"promptTokenCount": 1126, "candidatesTokenCount": 48, "thoughtsTokenCount": 94}})

    r = client(handler, "generate_content").generate("m-2", [Part.text("hi"), Part.image(JPEG)], system="sys", schema=SCHEMA,
                                                      thinking="low")
    assert r.text == '{"ok": false}' and r.api == "generate_content"
    assert (r.input_tokens, r.output_tokens, r.thought_tokens) == (1126, 48, 94)
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/models/m-2:generateContent"
    assert seen["headers"]["x-goog-api-key"] == FAKE_GEMINI_KEY and FAKE_GEMINI_KEY not in seen["url"]
    g = seen["body"]["generationConfig"]
    assert g["responseMimeType"] == "application/json" and g["responseJsonSchema"] == SCHEMA
    assert g["thinkingConfig"] == {"thinkingLevel": "low"}
    assert seen["body"]["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert seen["body"]["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"


def test_api_choice_from_env_and_validation(monkeypatch):
    monkeypatch.setenv("GEMINI_API", "generate_content")
    assert GeminiClient().api == "generate_content"
    monkeypatch.setenv("GEMINI_API", "nonsense")
    with pytest.raises(ConfigError):
        GeminiClient()


def test_missing_key_is_a_clear_config_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ConfigError) as e:
        GeminiClient()
    assert "GEMINI_API_KEY" in str(e.value)


def test_repr_never_shows_key():
    assert FAKE_GEMINI_KEY not in repr(GeminiClient()) and "AIza" not in repr(GeminiClient())


@pytest.mark.parametrize("api", ["interactions", "generate_content"])
def test_http_error_exception_contains_no_key(api):
    """An error body that echoes the key (as some APIs do) must not reach the exception, its repr or its chain."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "code": 400,
                                                   "message": f"API key not valid: {req.headers['x-goog-api-key']} (key={FAKE_GEMINI_KEY})"}})

    with pytest.raises(GeminiHTTPError) as e:
        client(handler, api).generate("m", [Part.text("hi")], schema=SCHEMA)
    text = f"{e.value} | {e.value!r} | {e.value.args}"
    assert FAKE_GEMINI_KEY not in text and not contains_secret(text)
    assert e.value.kind == "api" and e.value.status == 400
    assert e.value.__cause__ is None and e.value.__context__ is None   # no transport object hangs off the exception


def test_network_error_exception_contains_no_key():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused for {req.url} with {req.headers['x-goog-api-key']}")

    with pytest.raises(GeminiHTTPError) as e:
        client(handler).generate("m", [Part.text("hi")])
    assert e.value.kind == "network" and FAKE_GEMINI_KEY not in f"{e.value!r}{e.value}"
    assert e.value.__cause__ is None and e.value.__suppress_context__   # raised `from None`: the httpx error is not chained


def test_image_bytes_never_in_an_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom " + json.loads(req.content)["input"][1]["data"])  # a server echoing the body back

    with pytest.raises(GeminiHTTPError) as e:
        client(handler).generate("m", [Part.text("x"), Part.image(JPEG)])
    assert len(str(e.value)) < 500 and SECRET_PIXELS not in str(e.value).encode()


def test_timeout_maps_to_timeout_kind():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(GeminiHTTPError) as e:
        client(handler).generate("m", [Part.text("x")])
    assert e.value.kind == "timeout"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "rate_limit"), (503, "api")])
def test_status_kinds(status, kind):
    with pytest.raises(GeminiHTTPError) as e:
        client(lambda req: httpx.Response(status, json={"error": {"status": "X", "message": "m"}})).generate("m", [Part.text("x")])
    assert e.value.kind == kind and e.value.status == status


def test_incomplete_and_empty_and_blocked():
    inc = lambda req: httpx.Response(200, json={"status": "incomplete", "steps": [], "usage": {}})  # noqa: E731
    with pytest.raises(GeminiHTTPError) as e:
        client(inc).generate("m", [Part.text("x")])
    assert e.value.kind == "incomplete"
    empty = lambda req: httpx.Response(200, json={"status": "completed", "steps": [], "usage": {}})  # noqa: E731
    with pytest.raises(GeminiHTTPError) as e:
        client(empty).generate("m", [Part.text("x")])
    assert e.value.kind == "empty"
    blocked = lambda req: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})  # noqa: E731
    with pytest.raises(ModelRefusal):
        client(blocked, "generate_content").generate("m", [Part.text("x")])
    maxtok = lambda req: httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}]})  # noqa: E731
    with pytest.raises(GeminiHTTPError) as e:
        client(maxtok, "generate_content").generate("m", [Part.text("x")])
    assert e.value.kind == "incomplete"


def test_api_revision_header_is_optional(monkeypatch):
    seen = []
    client(lambda req: (seen.append(dict(req.headers)), interactions_ok(req))[1]).generate("m", [Part.text("x")])
    assert "api-revision" not in seen[0]
    monkeypatch.setenv("GEMINI_API_REVISION", "2026-05-20")
    client(lambda req: (seen.append(dict(req.headers)), interactions_ok(req))[1]).generate("m", [Part.text("x")])
    assert seen[1]["api-revision"] == "2026-05-20"


def test_list_models_paginates_and_strips_prefix():
    pages = iter([
        {"models": [{"name": "models/a", "supportedGenerationMethods": ["generateContent"]}], "nextPageToken": "t2"},
        {"models": [{"name": "models/b-live", "supportedGenerationMethods": ["bidiGenerateContent"]}]},
    ])
    urls = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return httpx.Response(200, json=next(pages))

    got = client(handler).list_models()
    assert got == {"a": ["generateContent"], "b-live": ["bidiGenerateContent"]}
    assert "pageToken=t2" in urls[1] and all(FAKE_GEMINI_KEY not in u for u in urls)


def test_part_image_rejects_non_images_and_hides_bytes():
    with pytest.raises(ValueError):
        Part.image(b"not an image at all")
    assert "AAAA" not in repr(Part.image(JPEG)) and str(len(JPEG)) not in repr(Part.image(JPEG))
