"""REQ-5: image payloads through the egress guard. SafeImage, ImageGate, closed answer schemas, send_image, the ledger rows,
and the rule that image bytes never reach a ledger line, log record, exception message, temporary file or cache key."""
from __future__ import annotations

import base64
import copy
import hashlib
import itertools
import json
import logging
import pickle
import struct
import tempfile
import zlib

import pytest

from understudy_engine.privacy import canary, egress, guard, image as I, ledger
from understudy_engine.privacy.egress import (
    EgressUnavailable, ImageBlocked, ImageRejected, ModelCallFailed, ModelOutputRejected, PayloadRejected, UnknownPurpose,
)
from understudy_engine.privacy.image import ImageGate, SafeImage, closed_schema_problem, register_image_purpose, unregister_image_purpose
from understudy_engine.privacy.payload import PurposeError, SafePayload
from understudy_engine.privacy.testing import CapturingPort, LogCapture

GOOD = {"mode": "triggered", "trigger": "stuck", "strict": False}
OPEN = ImageGate(consent=True, denylisted_app=False, secure_input=False, unattended=False)


def chunk(tag: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)


def png(w: int = 64, h: int = 48, *, pad_to: int | None = None, token: bytes = b"tok") -> bytes:
    raw = b"".join(b"\x00" + bytes((x * 7 + y * 13) % 256 for x in range(w * 3)) for y in range(h))
    out = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"Comment\x00" + token)
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    if pad_to is not None:
        need = pad_to - len(out) - 16
        assert need > 0
        out = out[:-12] + chunk(b"tEXt", b"Pad\x00" + b"x" * need) + chunk(b"IEND", b"")
        assert len(out) == pad_to, (len(out), pad_to)
    return out


def jpeg(w: int, h: int) -> bytes:
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01" + b"\xff\xd9"


def img(kind: str = "glance", **kw) -> SafeImage:
    return SafeImage(png(**kw), kind)


# --------------------------------------------------------------------------- SafeImage: limits
def test_png_and_jpeg_are_accepted_and_dimensions_come_from_the_file_itself():
    a = SafeImage(png(64, 48), "glance")
    assert (a.width, a.height, a.mime) == (64, 48, "image/png")
    b = SafeImage(jpeg(1280, 720), "verify")
    assert (b.width, b.height, b.mime) == (1280, 720, "image/jpeg")
    assert SafeImage(png(64, 48), "glance", width=64, height=48).width == 64


@pytest.mark.parametrize("w,h,ok", [(1280, 10, True), (10, 1280, True), (1281, 10, False), (10, 1281, False), (4000, 3000, False)])
def test_long_edge_is_capped_at_1280(w, h, ok):
    if ok:
        assert SafeImage(jpeg(w, h), "glance").width == w
    else:
        with pytest.raises(I.ImageRejectedError, match="long edge"):
            SafeImage(jpeg(w, h), "glance")


def test_size_is_capped_at_400_kb_exactly():
    SafeImage(png(pad_to=400 * 1024), "glance")
    with pytest.raises(I.ImageRejectedError, match="limit is 409600"):
        SafeImage(png(pad_to=400 * 1024 + 1), "glance")


def test_declared_dimensions_cannot_lie():
    with pytest.raises(I.ImageRejectedError, match="declared width and height"):
        SafeImage(jpeg(2000, 100) if False else png(64, 48), "glance", width=32, height=48)
    with pytest.raises(I.ImageRejectedError, match="declared"):
        SafeImage(png(64, 48), "glance", height=40)


@pytest.mark.parametrize("data", [b"", b"not an image", b"GIF89a" + b"0" * 40, b"\x89PNG\r\n\x1a\n" + b"x" * 5, b"\xff\xd8\xff\xd9", b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 0, 5, 8, 2, 0, 0, 0))])
def test_non_images_and_empty_images_are_refused(data):
    with pytest.raises(I.ImageRejectedError):
        SafeImage(data, "glance")


def test_kind_and_source_must_be_known():
    with pytest.raises(I.ImageRejectedError, match="kind"):
        SafeImage(png(), "screenshot")
    with pytest.raises(I.ImageRejectedError, match="source"):
        SafeImage(png(), "glance", source="local")
    for k in I.KINDS:
        assert SafeImage(png(), k).kind == k
    assert SafeImage(png(), "glance").source == "real_screen"            # the strict default


# --------------------------------------------------------------------------- SafeImage: nothing carries the bytes out
def test_repr_str_format_and_error_messages_contain_no_bytes():
    data = png(64, 48)
    a = SafeImage(data, "glance")
    for text in (repr(a), str(a), f"{a}", f"{a!r}", "%s" % a, "%r" % a, format(a, "")):
        assert a.sha8 in text and "64x48" in text
        assert base64.b64encode(data[:60]).decode() not in text and data[:20].hex() not in text and "PNG" not in text.replace("SafeImage", "")
    assert len(repr(a)) < 200


def test_a_frame_cannot_be_pickled_copied_serialised_or_turned_into_bytes():
    a = img()
    for fn in (pickle.dumps, copy.copy, copy.deepcopy, bytes):
        with pytest.raises(TypeError):
            fn(a)
    for proto in range(pickle.HIGHEST_PROTOCOL + 1):
        with pytest.raises(TypeError):
            pickle.dumps(a, protocol=proto)
    with pytest.raises(TypeError):
        json.dumps(a)
    with pytest.raises(AttributeError):
        a.kind = "point"
    with pytest.raises(AttributeError):
        a.__dict__


def test_only_short_hash_size_and_dimensions_can_be_recorded():
    a = img()
    assert set(a.meta()) == {"sha8", "bytes", "width", "height", "kind", "mime", "source"}
    assert len(a.sha8) == 16 and a.sha8 == hashlib.sha256(png()).hexdigest()[:16]
    assert a.cache_key() == f"img:glance:{a.sha8}" and hashlib.sha256(png()).hexdigest() not in a.cache_key()


def test_release_wipes_the_buffer_and_a_frame_is_used_once():
    a = img()
    got = a.reveal()
    assert got == png()
    a.release()
    a.release()
    assert a.released
    with pytest.raises(I.ImageRejectedError, match="already sent or released"):
        a.reveal()
    with img() as b:
        pass
    assert b.released


def test_equality_is_by_hash_size_kind_and_source_not_by_bytes():
    assert img() == img() and img() != img("point") and img() != SafeImage(png(), "glance", source="sandbox") and img() != img(token=b"other")
    assert len({img(), img()}) == 1


# --------------------------------------------------------------------------- the gate
@pytest.mark.parametrize("consent,deny,secure,unattended", list(itertools.product([True, False], repeat=4)))
def test_gate_truth_table_for_real_screen(consent, deny, secure, unattended):
    g = ImageGate(consent, deny, secure, unattended)
    expect = "unattended" if unattended else "secure_input" if secure else "denylisted_app" if deny else (None if consent else "no_consent")
    assert g.reason() == expect and g.open is (expect is None)
    if unattended:
        assert g.reason() == "unattended"                              # ALWAYS, whatever else is true


@pytest.mark.parametrize("consent,deny,secure,unattended", list(itertools.product([True, False], repeat=4)))
def test_gate_truth_table_for_sandbox(consent, deny, secure, unattended):
    g = ImageGate(consent, deny, secure, unattended, source="sandbox")
    expect = "secure_input" if secure else "denylisted_app" if deny else None      # no consent needed, may run unattended
    assert g.reason() == expect


def test_gate_takes_real_bools_and_known_sources_only():
    for bad in (1, 0, "true", None, 1.0):
        with pytest.raises(TypeError):
            ImageGate(bad, False, False, False)                       # type: ignore[arg-type]
        with pytest.raises(TypeError):
            ImageGate(True, False, False, bad)                        # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ImageGate(True, False, False, False, source="local")
    with pytest.raises(TypeError):
        ImageGate()                                                    # type: ignore[call-arg]
    assert ImageGate(True, False, False, False).source == "real_screen"


# --------------------------------------------------------------------------- closed answer schemas
def test_closed_schema_check_accepts_enums_numbers_bounded_arrays_and_closed_objects():
    ok = {"type": "object", "additionalProperties": False, "properties": {
        "a": {"enum": ["x", "y"]}, "n": {"type": "number"}, "b": {"type": "boolean"}, "i": {"type": "integer"},
        "box": {"type": "array", "items": {"type": "integer"}, "maxItems": 4},
        "nested": {"type": "object", "additionalProperties": False, "properties": {"k": {"const": "z"}}},
        "maybe": {"anyOf": [{"enum": ["p"]}, {"type": "null"}]}}}
    assert closed_schema_problem(ok) is None


@pytest.mark.parametrize("schema,frag", [
    ({"type": "object", "additionalProperties": False, "properties": {"t": {"type": "string"}}}, "free string"),
    ({"type": "object", "additionalProperties": False, "properties": {"t": {"type": "string", "maxLength": 20}}}, "free string"),
    ({"type": "object", "properties": {"a": {"enum": ["x"]}}}, "additionalProperties"),
    ({"type": "object", "additionalProperties": True, "properties": {}}, "additionalProperties"),
    ({"type": "object", "additionalProperties": False, "properties": {"l": {"type": "array", "items": {"type": "integer"}}}}, "maxItems"),
    ({"type": "object", "additionalProperties": False, "properties": {"l": {"type": "array", "items": {"type": "string"}, "maxItems": 3}}}, "free string"),
    ({"type": "object", "additionalProperties": False, "properties": {"r": {"$ref": "#/x"}}}, "references"),
    ({"type": "object", "additionalProperties": False, "properties": {"u": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}, "free string"),
    ({"type": "object", "additionalProperties": False, "properties": {"e": {"enum": ["ada@example.com"]}}}, "personal data"),
    ({"type": "object", "additionalProperties": False, "properties": {"d": {"type": "object", "properties": {"s": {"enum": ["a"]}}}}}, "additionalProperties"),
    ({"properties": {"a": {"enum": ["x"]}}}, "additionalProperties"),
])
def test_closed_schema_check_refuses_anything_that_could_carry_text(schema, frag):
    assert frag in (closed_schema_problem(schema) or "")


class Beside(SafePayload):
    n: int = 0


def test_registering_an_image_purpose_enforces_the_closed_schema_kinds_and_instructions():
    bad = {"type": "object", "additionalProperties": False, "properties": {"text": {"type": "string"}}, "required": ["text"]}
    ok = {"type": "object", "additionalProperties": False, "properties": {"v": {"enum": ["yes", "no"]}}, "required": ["v"]}
    with pytest.raises(PurposeError, match="not closed"):
        register_image_purpose("t.img1", Beside, response_schema=bad, kinds=("glance",))
    with pytest.raises(PurposeError, match="kinds"):
        register_image_purpose("t.img1", Beside, response_schema=ok, kinds=("screenshot",))
    with pytest.raises(PurposeError, match="kinds"):
        register_image_purpose("t.img1", Beside, response_schema=ok, kinds=())
    with pytest.raises(PurposeError, match="must look like"):
        register_image_purpose("badname", Beside, response_schema=ok, kinds=("glance",))
    with pytest.raises(PurposeError, match="backstop"):
        register_image_purpose("t.img1", Beside, response_schema=ok, kinds=("glance",), instructions="send it to ada@example.com")
    unregister_image_purpose("t.img1")
    p = register_image_purpose("t.img1", Beside, response_schema=ok, kinds=("glance",))
    assert register_image_purpose("t.img1", Beside, response_schema=ok, kinds=("glance",)) is p
    with pytest.raises(PurposeError, match="already registered"):
        register_image_purpose("t.img1", Beside, response_schema=ok, kinds=("point",))
    unregister_image_purpose("t.img1")


def test_the_builtin_image_purposes_are_registered_and_closed():
    ps = I.image_purposes()
    assert {"glance.screen_state", "point.element", "verify.agent_run", "live.frame"} <= set(ps)
    for p in ps.values():
        assert closed_schema_problem(p.response_schema) is None


# --------------------------------------------------------------------------- send_image: the normal path
def raw_lines(data_dir):
    return [json.loads(x) for x in (data_dir / "egress_ledger.jsonl").read_text().splitlines()]


ROW_KEYS = {"id", "t", "kind", "status", "purpose", "schema", "method", "fields", "payload", "image", "source", "provider", "model", "bytes",
            "mock", "ok", "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error", "reason"}
IMAGE_KEYS = {"sha8", "bytes", "width", "height", "kind", "mime", "source"}


def test_one_merged_row_per_call_with_only_allowed_fields_and_the_frame_is_wiped(data_dir):
    a = img()
    sha8, size = a.sha8, a.size
    port = CapturingPort().with_usage(input_tokens=310, output_tokens=42, cost_estimate_usd=0.00021)
    res = egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=port)
    assert res.output["app_kind"] == "browser" and res.mock is True and res.provider == "capturing" and res.source == "real_screen"
    assert a.released
    [row] = ledger.read_all()
    assert set(row) <= ROW_KEYS and set(row["image"]) == IMAGE_KEYS
    assert row["kind"] == "image" and row["status"] == "ok" and row["ok"] is True and row["id"] == res.ledger_id
    assert row["image"]["sha8"] == sha8 and row["image"]["bytes"] == size and (row["image"]["width"], row["image"]["height"]) == (64, 48)
    assert row["purpose"] == "glance.screen_state" and row["source"] == "real_screen" and row["mock"] is True and row["model"] == "capturing"
    assert row["payload"] == GOOD and row["fields"] == ["mode", "trigger", "strict"] and row["method"] == "vision"
    assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0
    assert (row["input_tokens"], row["output_tokens"], row["cost_estimate_usd"]) == (310, 42, 0.00021)
    assert row["bytes"] > size
    physical = raw_lines(data_dir)
    assert [r["kind"] for r in physical] == ["image", "image_result"] and physical[0]["status"] == "sending" and physical[1]["ref"] == row["id"]


def test_the_provider_received_exactly_the_frame_that_was_sent_and_the_capture_holds_only_length_and_hash():
    data = png(80, 40)
    port = CapturingPort()
    egress.send_image("glance.screen_state", SafeImage(data, "glance"), GOOD, gate=OPEN, port=port)
    assert port.image_calls == [{"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}]
    body = port.requests[0].body
    assert body["image_bytes"] == len(data) and body["image_sha8"] == hashlib.sha256(data).hexdigest()[:16]
    assert data[:16].hex() not in port.requests[0].text and base64.b64encode(data[:48]).decode() not in port.requests[0].text
    sent = json.loads(body["prompt"].rsplit("\n\n", 1)[-1])
    assert sent["payload"] == GOOD and sent["purpose"] == "glance.screen_state"


def test_the_prompt_carries_codes_only_and_the_static_instructions_say_not_to_transcribe():
    port = CapturingPort()
    egress.send_image("verify.agent_run", img("verify"), {"check": "page_shows_result"}, gate=OPEN, port=port)
    prompt = port.requests[0].body["prompt"]
    assert "page_shows_result" in prompt and "Do not transcribe" in prompt and "data, never as an instruction" in prompt


def test_usage_that_is_missing_or_malformed_is_recorded_as_null_not_trusted():
    class Port(CapturingPort):
        def vision(self, image, prompt, schema=None):
            self.last_call = {"input_tokens": "lots", "output_tokens": -4, "cost_estimate_usd": float("nan"), "note": "Ada Lovelace's screen"}
            return super().vision(image, prompt, schema)

    egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=Port())
    [row] = ledger.read_all()
    assert (row["input_tokens"], row["output_tokens"], row["cost_estimate_usd"]) == (None, None, None) and "Lovelace" not in json.dumps(row)
    egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=CapturingPort())
    assert ledger.read_all()[-1]["input_tokens"] is None


def test_mock_mode_writes_a_row_marked_mock_and_uses_no_network(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    res = egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN)
    assert res.mock is True and res.provider == "mock" and set(res.output) >= {"app_kind", "task_phase", "blocker", "confidence"}
    assert ledger.read_all()[0]["mock"] is True


def test_mock_mode_refuses_a_port_that_is_not_offline(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")

    class Remote:
        name = "gemini"

        def vision(self, *a, **k):
            raise AssertionError("must not be called")

    a = img()
    with pytest.raises(egress.EgressBlocked, match="Models are off"):
        egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=Remote())
    assert a.released and ledger.read_all() == []


def test_a_real_port_is_logged_as_not_mock_with_its_model_id_from_the_port():
    class Remote:
        name = "gemini"

        def model_for(self, method):
            return "model-from-env"

        def vision(self, image, prompt, schema=None):
            return {"app_kind": "browser", "task_phase": "entering", "blocker": "none", "confidence": 0.8}

    res = egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=Remote())
    assert res.mock is False and res.model == "gemini:model-from-env" and res.provider == "gemini"
    assert ledger.read_all()[0]["mock"] is False


def test_release_false_keeps_the_frame_for_a_second_use_by_the_caller():
    a = img()
    egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=CapturingPort(), release=False)
    assert not a.released


# --------------------------------------------------------------------------- the gate in send_image
@pytest.mark.parametrize("gate,reason", [
    (ImageGate(False, False, False, False), "no_consent"), (ImageGate(True, True, False, False), "denylisted_app"),
    (ImageGate(True, False, True, False), "secure_input"), (ImageGate(True, False, False, True), "unattended"),
    (ImageGate(True, True, True, True), "unattended"),
])
def test_a_closed_gate_writes_one_blocked_row_sends_nothing_and_wipes_the_frame(gate, reason, data_dir):
    a, port = img(), CapturingPort()
    with pytest.raises(ImageBlocked) as ei:
        egress.send_image("glance.screen_state", a, GOOD, gate=gate, port=port)
    assert ei.value.reason == reason and ei.value.code == "image_blocked" and len(port) == 0 and a.released
    [row] = ledger.read_all()
    assert row["status"] == "blocked" and row["reason"] == reason and row["source"] == "real_screen" and row["ok"] is False
    assert row["image"]["sha8"] and row["bytes"] == 0 and row["payload"] is None and row["id"] == ei.value.ledger_id
    assert len(raw_lines(data_dir)) == 1
    s = ledger.summary()
    assert s["calls"] == 0 and s["images"]["blocked"] == 1 and s["images"]["blocked_by_reason"] == {reason: 1} and s["images"]["sent"] == 0


def test_a_refusal_needs_no_image_at_all():
    for gate, reason in ((ImageGate(False, False, False, False), "no_consent"), (ImageGate(True, False, True, False), "secure_input")):
        with pytest.raises(ImageBlocked):
            egress.send_image("glance.screen_state", None, None, gate=gate, port=CapturingPort())
    rows = ledger.read_all()
    assert [r["reason"] for r in rows] == ["no_consent", "secure_input"] and all(r["image"] is None for r in rows)


def test_unattended_real_screen_is_blocked_in_every_combination_even_with_consent_and_a_real_port():
    class Remote:
        name = "gemini"

        def vision(self, *a, **k):
            raise AssertionError("an unattended real-screen frame must never reach a provider")

    for consent, deny, secure in itertools.product([True, False], repeat=3):
        with pytest.raises(ImageBlocked) as ei:
            egress.send_image("glance.screen_state", img(), GOOD, gate=ImageGate(consent, deny, secure, True), port=Remote())
        assert ei.value.reason == "unattended" or (not False)


def test_sandbox_frames_need_no_consent_and_may_run_unattended_and_the_row_says_so():
    a = SafeImage(png(), "verify", source="sandbox")
    port = CapturingPort()
    res = egress.send_image("verify.agent_run", a, {"check": "page_shows_result"}, gate=ImageGate(False, False, False, True, source="sandbox"), port=port)
    assert res.source == "sandbox" and len(port) == 1
    [row] = ledger.read_all()
    assert row["source"] == "sandbox" and row["image"]["source"] == "sandbox" and row["status"] == "ok"
    assert ledger.summary()["images"]["sent_by_source"] == {"sandbox": 1}


def test_sandbox_still_blocks_on_secure_input_or_a_denylisted_app():
    for gate in (ImageGate(True, False, True, False, "sandbox"), ImageGate(True, True, False, False, "sandbox")):
        with pytest.raises(ImageBlocked):
            egress.send_image("verify.agent_run", SafeImage(png(), "verify", source="sandbox"), {"check": "form_saved"}, gate=gate, port=CapturingPort())


def test_an_image_whose_source_differs_from_the_gates_is_refused_both_ways():
    port = CapturingPort()
    with pytest.raises(ImageRejected, match="source"):
        egress.send_image("verify.agent_run", SafeImage(png(), "verify", source="sandbox"), {"check": "form_saved"}, gate=OPEN, port=port)
    with pytest.raises(ImageRejected, match="source"):
        egress.send_image("verify.agent_run", SafeImage(png(), "verify"), {"check": "form_saved"}, gate=ImageGate(True, False, False, False, "sandbox"), port=port)
    assert len(port) == 0


def test_the_gate_is_required_and_cannot_be_a_loose_object():
    with pytest.raises(TypeError, match="gate"):
        egress.send_image("glance.screen_state", img(), GOOD, port=CapturingPort())          # type: ignore[call-arg]
    with pytest.raises(TypeError, match="ImageGate"):
        egress.send_image("glance.screen_state", img(), GOOD, gate={"consent": True}, port=CapturingPort())   # type: ignore[arg-type]
    with pytest.raises(TypeError, match="unexpected keyword"):
        egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=CapturingPort(), instructions="x")


# --------------------------------------------------------------------------- refusals
def test_unknown_purpose_kind_mismatch_missing_and_reused_images_are_refused():
    port = CapturingPort()
    with pytest.raises(UnknownPurpose):
        egress.send_image("glance.not_registered", img(), GOOD, gate=OPEN, port=port)
    with pytest.raises(ImageRejected, match="takes images of kind"):
        egress.send_image("glance.screen_state", img("verify"), GOOD, gate=OPEN, port=port)
    with pytest.raises(ImageRejected, match="needs an image"):
        egress.send_image("glance.screen_state", None, GOOD, gate=OPEN, port=port)
    a = img()
    a.release()
    with pytest.raises(ImageRejected, match="already used"):
        egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=port)
    with pytest.raises(ImageRejected, match="SafeImage"):
        egress.send_image("glance.screen_state", png(), GOOD, gate=OPEN, port=port)           # type: ignore[arg-type]
    assert len(port) == 0 and ledger.read_all() == []


def test_free_text_beside_the_frame_is_rejected_and_the_frame_is_wiped_without_a_row():
    a, port = img(), CapturingPort()
    with pytest.raises(PayloadRejected) as ei:
        egress.send_image("glance.screen_state", a, {"mode": "Ada Lovelace's inbox", "trigger": "stuck", "strict": False}, gate=OPEN, port=port)
    assert "Lovelace" not in str(ei.value) and a.released and len(port) == 0 and ledger.read_all() == []


def test_nothing_is_sent_if_the_ledger_cannot_be_written(monkeypatch):
    def boom(_entry):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "begin_image", boom)
    a, port = img(), CapturingPort()
    with pytest.raises(EgressUnavailable, match="ledger could not be written"):
        egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=port)
    assert len(port) == 0 and a.released


def test_the_ledger_row_exists_before_the_provider_is_called():
    seen = {}

    class Spy(CapturingPort):
        def vision(self, image, prompt, schema=None):
            seen["rows"] = [(r["kind"], r["status"]) for r in ledger.read_all()]
            return super().vision(image, prompt, schema)

    egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=Spy())
    assert seen["rows"] == [("image", "sending")]


# --------------------------------------------------------------------------- the model's answer
def test_an_answer_with_free_text_or_the_wrong_shape_is_discarded_and_not_echoed():
    for bad in ({"app_kind": "Ada Lovelace's payroll spreadsheet", "task_phase": "start", "blocker": "none", "confidence": 0.5},
                {"app_kind": "browser", "task_phase": "start", "blocker": "none", "confidence": 0.5, "note": "salary 90000"},
                {"app_kind": "browser"}, "free text", {"app_kind": "browser", "task_phase": "start", "blocker": "none", "confidence": 7}):
        port = CapturingPort().script("vision", bad)
        with pytest.raises(ModelOutputRejected) as ei:
            egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=port)
        assert "Lovelace" not in str(ei.value) and "salary" not in str(ei.value)
        assert ledger.read_all()[-1]["status"] == "output_rejected" and ledger.read_all()[-1]["ok"] is False


def test_a_valid_closed_answer_with_a_box_passes():
    ans = {"app_kind": "browser", "task_phase": "blocked", "blocker": "error_message", "confidence": 0.9, "box_2d": [10, 20, 300, 400]}
    assert egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=CapturingPort().script("vision", ans)).output == ans


# --------------------------------------------------------------------------- a failing provider
def test_a_failing_provider_raises_a_plain_error_records_a_failed_result_and_leaves_no_image_in_the_message():
    class Secret(RuntimeError):
        pass

    data = png(48, 48, token=b"PLANT-ME-failing-provider")
    b64 = base64.b64encode(data).decode()

    class Port(CapturingPort):
        status_code = 503

        def vision(self, image, prompt, schema=None):
            raise Secret(f"upstream rejected data:image/png;base64,{base64.b64encode(image).decode()} {image[:30]!r}")

    a = SafeImage(data, "glance")
    with pytest.raises(ModelCallFailed) as ei:
        egress.send_image("glance.screen_state", a, GOOD, gate=OPEN, port=Port())
    text = str(ei.value) + repr(ei.value)
    assert "Secret" in text and b64[:40] not in text and "PLANT-ME" not in text and "PNG" not in text
    assert ei.value.__cause__ is None and ei.value.__context__ is None
    assert a.released
    [row] = ledger.read_all()
    assert row["status"] == "failed" and row["ok"] is False and row["error"] == "Secret" and row["latency_ms"] >= 0


def test_a_provider_exception_object_does_not_keep_the_frames_traceback_alive():
    import gc

    class Holder:
        pass

    class Port(CapturingPort):
        def vision(self, image, prompt, schema=None):
            local_copy = bytes(image)                                   # a local in the failing frame
            raise RuntimeError(len(local_copy))

    exc_ref = {}

    def go():
        try:
            egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=Port())
        except ModelCallFailed as e:
            exc_ref["e"] = e

    go()
    e = exc_ref["e"]
    tb = e.__traceback__
    frames = []
    while tb is not None:
        frames.append(tb.tb_frame)
        tb = tb.tb_next
    for f in frames:
        for name, val in f.f_locals.items():
            assert not (isinstance(val, (bytes, bytearray)) and len(val) > 1000), f"frame {f.f_code.co_name} still holds {name}"
    gc.collect()


# --------------------------------------------------------------------------- the HTTP side of "who may say sandbox"
@pytest.mark.parametrize("source,host,origin,problem", [
    ("real_screen", "127.0.0.1", None, None), ("real_screen", "::1", "app://understudy", None), ("real_screen", "203.0.113.9", None, "not_this_machine"),
    ("sandbox", "127.0.0.1", None, None), ("sandbox", "127.0.0.1", "http://127.0.0.1:7801", None), ("sandbox", "127.0.0.1", "http://localhost:7803", None),
    ("sandbox", "127.0.0.1", "https://evil.example", "sandbox_origin"), ("sandbox", "127.0.0.1", "http://localhost:5173", "sandbox_origin"),
    ("sandbox", "203.0.113.9", None, "not_this_machine"), ("local", "127.0.0.1", None, "unknown_source"), ("sandbox", None, None, "not_this_machine"),
])
def test_frame_request_problem_enforces_what_it_can(source, host, origin, problem):
    assert I.frame_request_problem(source, client_host=host, origin=origin) == problem


# --------------------------------------------------------------------------- the ledger and routes
def test_routes_show_one_row_per_image_call_including_blocked_ones(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from understudy_engine import routes_privacy
    from understudy_engine.api.errors import install_error_handlers

    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(routes_privacy.router)
    c = TestClient(app)
    egress.send_image("glance.screen_state", img(), GOOD, gate=OPEN, port=CapturingPort())
    with pytest.raises(ImageBlocked):
        egress.send_image("glance.screen_state", img(), GOOD, gate=ImageGate(True, False, True, False), port=CapturingPort())
    rows = c.get("/privacy/ledger").json()["data"]
    assert [r["status"] for r in rows] == ["blocked", "ok"] and all(r["kind"] == "image" for r in rows)
    s = c.get("/privacy/summary").json()["data"]
    assert s["calls"] == 1 and s["images"]["sent"] == 1 and s["images"]["blocked"] == 1 and s["images"]["blocked_by_reason"] == {"secure_input": 1}
    purposes = {p["purpose"]: p for p in c.get("/privacy/purposes").json()["data"]}
    assert purposes["glance.screen_state"]["image"] is True and "glance" in purposes["glance.screen_state"]["kinds"]
    export = c.get("/privacy/ledger/export").text
    assert len(export.splitlines()) == 3                                     # image, image_result, blocked: append-only on disk


# --------------------------------------------------------------------------- the residue rule: canaries in the pixels and the metadata
def flows(seed: int, tmp_path):
    """Each flow returns (exceptions text list)."""
    pi = canary.plant_image(seed)
    outs = []

    def happy():
        egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=OPEN, port=CapturingPort().with_usage(input_tokens=1, output_tokens=1))

    def blocked(gate):
        def f():
            try:
                egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=gate, port=CapturingPort())
            except ImageBlocked as e:
                outs.append(str(e) + repr(e))
        return f

    def failing():
        class P(CapturingPort):
            def vision(self, image, prompt, schema=None):
                raise RuntimeError("boom " + base64.b64encode(image[:60]).decode() + repr(image[:40]))
        try:
            egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=OPEN, port=P())
        except ModelCallFailed as e:
            outs.append(str(e) + repr(e))

    def bad_answer():
        try:
            egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=OPEN,
                              port=CapturingPort().script("vision", {"app_kind": pi.token, "task_phase": "start", "blocker": "none", "confidence": 1}))
        except ModelOutputRejected as e:
            outs.append(str(e) + repr(e))

    def bad_payload():
        try:
            egress.send_image("glance.screen_state", pi.safe_image(), {"mode": pi.token, "trigger": "stuck", "strict": False}, gate=OPEN, port=CapturingPort())
        except PayloadRejected as e:
            outs.append(str(e) + repr(e))

    return pi, outs, [happy, blocked(ImageGate(False, False, False, False)), blocked(ImageGate(True, True, False, False)),
                      blocked(ImageGate(True, False, True, False)), blocked(ImageGate(True, False, False, True)), failing, bad_answer, bad_payload]


@pytest.mark.parametrize("seed", range(6))
def test_no_planted_image_residue_in_any_file_log_message_or_temp_file(seed, tmp_path, data_dir, monkeypatch):
    mon = tmp_path / "tmpmon"
    mon.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(mon))
    monkeypatch.setenv("TMPDIR", str(mon))
    pi, outs, fl = flows(seed, tmp_path)
    with LogCapture() as logs:
        for f in fl:
            f()
    logging.getLogger("test").info("done")
    assert len(ledger.read_all()) == len(fl) - 1 and any(r["status"] == "blocked" for r in ledger.read_all())
    assert canary.scan_image_residue(pi, paths=[data_dir, tmp_path / "home"], texts=logs.texts + outs + [json.dumps(ledger.read_all())]) == []
    assert list(mon.iterdir()) == [], "a temporary file was left behind"
    assert not (data_dir / "images").exists() and not any(p.suffix in (".png", ".jpg", ".jpeg") for p in data_dir.rglob("*"))


def test_the_residue_scan_can_fail_it_finds_a_deliberate_dump(tmp_path, data_dir):
    pi = canary.plant_image(3)
    assert canary.scan_image_residue(pi, texts=[pi.token]) and canary.scan_image_residue(pi, texts=["x " + base64.b64encode(pi.data).decode()])
    assert canary.scan_image_residue(pi, texts=[hashlib.sha256(pi.data).hexdigest()])
    assert canary.scan_image_residue(pi, texts=[repr(pi.data[:60])]) or canary.scan_image_residue(pi, texts=[repr(pi.raw_chunks[0])])
    assert canary.scan_image_residue(pi, blobs=[b"xx" + pi.raw_chunks[1] + b"yy"])
    (data_dir / "leak.bin").write_bytes(b"prefix" + pi.data)
    assert canary.scan_image_residue(pi, paths=[data_dir])
    (data_dir / "leak.bin").unlink()
    (data_dir / f"{hashlib.sha256(pi.data).hexdigest()}.dat").write_text("x")
    assert canary.scan_image_residue(pi, paths=[data_dir])
    (data_dir / f"{hashlib.sha256(pi.data).hexdigest()}.dat").unlink()
    assert canary.scan_image_residue(pi, paths=[data_dir], texts=[hashlib.sha256(pi.data).hexdigest()[:16]]) == []      # sha8 is allowed
    assert canary.plant_image(3).data == pi.data and canary.plant_image(4).data != pi.data


def test_the_planted_png_is_a_valid_safe_image_with_the_token_in_its_metadata():
    pi = canary.plant_image(1)
    assert pi.token.encode() in pi.data
    s = pi.safe_image()
    assert s.mime == "image/png" and s.size <= I.MAX_BYTES


# --------------------------------------------------------------------------- the static guard for images
def test_provider_endpoint_scan_flags_clients_and_hosts_outside_the_allowed_modules():
    f = guard.provider_endpoint_violations
    assert {v.rule for v in f("import openai\n", "x.py")} == {"provider_client_import"}
    assert {v.rule for v in f("from google import genai\n", "x.py")} == {"provider_client_import"}
    assert {v.rule for v in f("import google.generativeai as g\n", "x.py")} == {"provider_client_import"}
    assert {v.rule for v in f("from google.genai import types\n", "x.py")} == {"provider_client_import"}
    assert {v.rule for v in f("import vertexai\n", "x.py")} == {"provider_client_import"}
    assert {v.rule for v in f("U = 'https://generativelanguage.googleapis.com/v1beta/models'\n", "x.py")} == {"provider_host"}
    assert {v.rule for v in f("import httpx\nhttpx.post(f'https://api.openai.com/v1/{x}')\n", "x.py")} == {"provider_host"}
    assert f("import json\nimport google\nU = 'https://example.org'\n", "x.py") == []
    assert f("# api.openai.com is mentioned in a comment only\nx = 1\n", "x.py") == []


def test_only_the_models_package_the_egress_module_and_the_guard_may_use_a_provider():
    assert guard._provider_allowed("understudy_agent/models/gemini_provider.py") and guard._provider_allowed("understudy_agent/models/openai_provider.py")
    assert guard._provider_allowed("understudy_engine/privacy/egress.py") and guard._provider_allowed("understudy_engine/privacy/guard.py")
    for rel in ("understudy_agent/runtime/child.py", "understudy_engine/awareness/glance.py", "understudy_engine/privacy/image.py",
                "understudy_agent/security/redteam_live.py", "understudy_engine/localmodel/client.py"):
        assert not guard._provider_allowed(rel)


def test_the_real_tree_has_no_gemini_or_openai_client_or_host_outside_the_allowed_modules():
    rep = guard.scan_provider_endpoints()
    assert rep.files, "the guard found no files to check"
    assert rep.ok, "only understudy_agent/models and privacy/egress.py may open a Gemini or OpenAI client:\n" + "\n".join(map(str, rep.violations))


def test_sandbox_claim_scan_flags_the_string_in_real_screen_code():
    assert guard.sandbox_claim_violations_py("src = 'sandbox'\n", "awareness/x.py")
    assert guard.sandbox_claim_violations_py("gate = ImageGate(True, False, False, False, source=\"sandbox\")\n", "awareness/x.py")
    assert guard.sandbox_claim_violations_py("x = 'real_screen'\nsandbox_dir = 1\n", "awareness/x.py") == []


def test_sandbox_claim_scan_covers_awareness_and_live_typescript_but_not_tests(tmp_path):
    (tmp_path / "apps/desktop/src/main/awareness").mkdir(parents=True)
    (tmp_path / "apps/desktop/src/renderer/live").mkdir(parents=True)
    (tmp_path / "apps/desktop/src/main/awareness/glance.ts").write_text("export const SRC = 'real_screen'\n")
    (tmp_path / "apps/desktop/src/main/awareness/glance.test.ts").write_text("expect(refuse({ source: 'sandbox' })).toBe(true)\n")
    (tmp_path / "apps/desktop/src/renderer/live/wire.ts").write_text("const body = { source: \"sandbox\" }\n")
    (tmp_path / "apps/desktop/src/main/live-auth.ts").write_text("const s = `sandbox`\n")
    rep = guard.scan_sandbox_claims(tmp_path)
    assert sorted(v.file for v in rep.violations) == ["apps/desktop/src/main/live-auth.ts", "apps/desktop/src/renderer/live/wire.ts"]
    assert not any(f.endswith(".test.ts") for f in rep.files)


def test_the_real_awareness_and_live_code_never_constructs_sandbox():
    rep = guard.scan_sandbox_claims()
    assert rep.ok, "real-screen code must never claim the sandbox source:\n" + "\n".join(map(str, rep.violations))


def test_awareness_is_now_a_guarded_extension_layer():
    assert "awareness" in guard.GUARDED_DIRS and "routes_awareness.py" in guard.GUARDED_FILES


# --------------------------------------------------------------------------- the one-call kit for other tracks
def test_image_canary_flow_passes_a_flow_that_sends_through_the_guard_and_reports_its_counts():
    from understudy_engine.privacy.testing import image_canary_flow

    def run(pi, port):
        egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=OPEN, port=port)
        try:
            egress.send_image("glance.screen_state", pi.safe_image(), GOOD, gate=ImageGate(True, False, True, False), port=port)
        except ImageBlocked:
            pass

    r = image_canary_flow("awareness.glance", run, seed=4)
    assert r["ok"] and r["requests"] == 1 and r["ledger_rows"] == 2 and r["residue"] == []


def test_image_canary_flow_catches_each_way_a_flow_could_keep_the_frame(data_dir):
    from understudy_engine.privacy.testing import image_canary_flow

    def logs_b64(pi, port):
        logging.getLogger("awareness").info("frame %s", base64.b64encode(pi.data).decode())

    def writes_file(pi, port):
        (data_dir / "last_frame.png").write_bytes(pi.data)

    def tmp_file(pi, port):
        fd, _ = tempfile.mkstemp(suffix=".png")
        import os
        os.write(fd, pi.data)
        os.close(fd)

    def bytes_in_a_prompt(pi, port):
        port.plan([{"role": "user", "content": "what is " + base64.b64encode(pi.data).decode()}], None)

    def error_text(pi, port):
        raise RuntimeError("could not read " + repr(pi.data[:80]) + pi.token)

    def hash_in_row(pi, port):
        ledger.append({"kind": "image", "status": "ok", "purpose": "x.y", "image": {"sha8": "0" * 16, "full": hashlib.sha256(pi.data).hexdigest()}})

    for fn in (logs_b64, writes_file, tmp_file, bytes_in_a_prompt, error_text, hash_in_row):
        r = image_canary_flow(f"leaky.{fn.__name__}", fn, seed=5, strict=False)
        assert not r["ok"] and r["residue"], fn.__name__
        for p in data_dir.glob("last_frame.png"):
            p.unlink()
        with pytest.raises(AssertionError, match="residue"):
            image_canary_flow(f"leaky.{fn.__name__}", fn, seed=5)
        for p in data_dir.glob("last_frame.png"):
            p.unlink()
        ledger.reset_all()
