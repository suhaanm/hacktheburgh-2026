"""REVIEW-PRIVACY P1b: the voice route speaks FIXED LINES by id, writes a metadata-only ledger row per real call, and refuses free text.

Hermetic: httpx.MockTransport stands in for the speech service. A planted person name must never reach the transport; a ledger row
must exist per real call and must hold no text.
"""
from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_agent.voice import lines, router, tts

NAME = "Zebulon Quillfeather"
PLANTED = f"Reminder: call {NAME} about the Hollowbrook invoice"
AUDIO = b"ID3\x04fake-mp3-bytes" * 20
VOICES = {"voices": [{"voice_id": "v_river", "name": "River - Relaxed, Neutral, Informative", "labels": {"language": "en", "gender": "neutral", "descriptive": "calm", "use_case": "conversational"}}]}


class Net:
    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/voices"):
            return httpx.Response(200, json=VOICES)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        return httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})

    def install(self) -> None:
        tts.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(self.handler), base_url=tts.API_BASE))

    def spoken(self) -> list[str]:
        """The text of every text-to-speech request that reached the (mock) host."""
        return [json.loads(r.content)["text"] for r in self.requests if "text-to-speech" in r.url.path]

    def everything_sent(self) -> str:
        return " ".join(r.content.decode("utf-8", "replace") + str(r.url) for r in self.requests)


@pytest.fixture
def net(monkeypatch, tmp_path):
    monkeypatch.setenv("UNDERSTUDY_VOICE", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-key-not-real")
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    monkeypatch.delenv("UNDERSTUDY_VOICE_DEBUG_TEXT", raising=False)
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_PRIVACY"):
        monkeypatch.delenv(k, raising=False)  # the ledger row must exist with the privacy extension OFF
    n = Net()
    n.install()
    yield n
    tts.wait_for_background(3)
    tts.set_http_factory(None)


def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def ledger_rows() -> list[dict]:
    from understudy_engine.privacy import ledger

    p = ledger.ledger_path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# ------------------------------------------------------------------ free text is refused
def test_free_text_is_refused_with_422_and_nothing_reaches_the_transport(net):
    c = client()
    r = c.post("/voice/speak", json={"text": PLANTED, "kind": "nudge"})
    tts.wait_for_background(2)
    assert r.status_code == 422 and r.json()["error"]["code"] == "free_text_refused"
    assert net.requests == []                       # not even the voice list was fetched
    assert NAME not in r.text                       # the refusal does not echo the text
    assert ledger_rows() == []


def test_free_text_is_refused_even_when_the_voice_is_off(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_VOICE", raising=False)
    monkeypatch.delenv("UNDERSTUDY_VOICE_DEBUG_TEXT", raising=False)
    assert client().post("/voice/speak", json={"text": PLANTED}).status_code == 422


def test_python_free_text_is_refused_when_it_would_reach_the_network(net):
    with pytest.raises(tts.FreeTextRefused):
        tts.speak_detailed(PLANTED, "nudge")
    with pytest.raises(tts.FreeTextRefused):
        tts.prewarm(PLANTED)
    assert net.requests == []


def test_text_and_line_id_together_or_neither_is_a_422(net):
    c = client()
    assert c.post("/voice/speak", json={"line_id": "coach.almost", "text": "x"}).status_code == 422
    assert c.post("/voice/speak", json={}).status_code == 422
    assert c.post("/voice/speak", json={"line_id": "coach.almost", "extra": "smuggled"}).status_code == 422
    assert net.requests == []


# ------------------------------------------------------------------ fixed lines
def test_a_fixed_line_is_spoken_and_one_metadata_row_is_written_with_no_text(net):
    r = client().post("/voice/speak", json={"line_id": "coach.nice_work"})
    tts.wait_for_background(3)
    assert r.status_code == 200 and r.headers["x-voice-source"] == "live" and r.content == AUDIO
    assert net.spoken() == ["Nice work on that step."]
    rows = ledger_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "direct" and row["purpose"] == "voice.speak" and row["model"].startswith("elevenlabs:")
    assert row["content_logged"] is False and row["payload"] is None
    assert "chars=21-40" in row["note"] and "cache=miss" in row["note"] and "ok=1" in row["note"] and "ms=" in row["note"] and "voice=" in row["note"]
    raw = json.dumps(row)
    for word in ("Nice", "work", "step"):
        assert word not in raw                      # the row holds no text
    assert "v_river" not in raw                     # the voice id is only a hash


def test_a_cached_clip_makes_no_network_call_and_writes_no_row(net):
    c = client()
    c.post("/voice/speak", json={"line_id": "coach.almost"})
    tts.wait_for_background(3)
    before_requests, before_rows = len(net.requests), len(ledger_rows())
    r = c.post("/voice/speak", json={"line_id": "coach.almost"})
    assert r.headers["x-voice-source"] == "cache" and r.content == AUDIO
    assert len(net.requests) == before_requests and len(ledger_rows()) == before_rows == 1
    assert tts.diagnostics()["cache_hits"] >= 1


def test_a_row_exists_per_real_call(net):
    c = client()
    for line in ("coach.almost", "coach.one_step", "coach.look_again"):
        c.post("/voice/speak", json={"line_id": line})
        tts.wait_for_background(3)
    assert len(net.spoken()) == 3 and len(ledger_rows()) == 3


def test_a_failed_call_is_ledgered_as_not_ok(net):
    net.status = 500
    r = client().post("/voice/speak", json={"line_id": "coach.almost"})
    tts.wait_for_background(3)
    assert r.headers["x-voice-source"] in ("error", "timeout")
    rows = ledger_rows()
    assert len(rows) == 1 and "ok=0" in rows[0]["note"]


def test_the_ledger_row_is_written_with_the_privacy_extension_off_and_on(net, monkeypatch):
    client().post("/voice/speak", json={"line_id": "coach.almost"})
    tts.wait_for_background(3)
    assert len(ledger_rows()) == 1                  # fixture: extension off
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    client().post("/voice/speak", json={"line_id": "coach.one_step"})
    tts.wait_for_background(3)
    assert len(ledger_rows()) == 2


def test_nothing_is_sent_when_the_ledger_cannot_be_written(net, monkeypatch, tmp_path):
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("a file where the data directory should be")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(blocked / "data"))
    r = client().post("/voice/speak", json={"line_id": "coach.almost"})
    tts.wait_for_background(2)
    assert r.headers["x-voice-source"] == "error"
    assert net.requests == []


# ------------------------------------------------------------------ slots
def test_slots_are_numbers_or_ids_and_make_the_sentence_in_code(net):
    c = client()
    r = c.post("/voice/speak", json={"line_id": "briefing.overnight", "slots": {"runs": 2, "review": 1}})
    tts.wait_for_background(3)
    assert r.status_code == 200
    assert net.spoken() == ["Good morning. 2 routines ran overnight and 1 needs your review."]
    r2 = c.post("/voice/speak", json={"line_id": "briefing.greeting", "slots": {"part": "evening"}})
    tts.wait_for_background(3)
    assert r2.status_code == 200 and net.spoken()[-1] == "Good evening."


@pytest.mark.parametrize(
    "body",
    [
        {"line_id": "no.such_line"},
        {"line_id": "briefing.overnight", "slots": {"runs": 2}},                                   # missing slot
        {"line_id": "briefing.overnight", "slots": {"runs": 2, "review": 1, "name": "x"}},         # extra slot
        {"line_id": "briefing.overnight", "slots": {"runs": 10_000, "review": 1}},                 # out of range
        {"line_id": "briefing.overnight", "slots": {"runs": -1, "review": 1}},
        {"line_id": "briefing.overnight", "slots": {"runs": "2", "review": 1}},                    # a string where a number goes
        {"line_id": "briefing.overnight", "slots": {"runs": 1.5, "review": 1}},
        {"line_id": "briefing.greeting", "slots": {"part": NAME}},                                 # a name in an enum slot
        {"line_id": "briefing.greeting", "slots": {"part": "Zebulon Quillfeather".lower()}},
        {"line_id": "briefing.greeting", "slots": {"part": "midnight"}},                           # not in the closed set
        {"line_id": "coach.almost", "slots": {"x": 1}},                                            # a fixed line takes no slots
        {"line_id": "../../etc/passwd"},
        {"line_id": "x" * 200},
    ],
)
def test_bad_lines_and_slots_are_refused_and_nothing_is_sent(net, body):
    r = client().post("/voice/speak", json=body)
    tts.wait_for_background(2)
    assert r.status_code == 422
    assert net.requests == [] and ledger_rows() == []
    assert NAME not in r.text


def test_a_planted_name_in_any_slot_never_reaches_the_transport(net):
    c = client()
    for slots in ({"part": NAME}, {"part": "morning", "who": NAME}, {"part": [NAME]}):
        c.post("/voice/speak", json={"line_id": "briefing.greeting", "slots": slots})
    tts.wait_for_background(2)
    assert NAME not in net.everything_sent()


# ------------------------------------------------------------------ pack and engine lines
def test_a_whisper_line_for_a_pack_step_resolves_to_the_pack_label():
    r = lines.resolve("whisper.read_case")
    assert r.text.startswith("Next, ") and "household" in r.text.lower()
    assert len(r.text.split()) <= 8
    with pytest.raises(lines.LineError):
        lines.resolve("whisper.not_a_step_in_any_pack")


def test_the_spoken_questions_are_the_engines_fixed_templates():
    assert lines.resolve("question.close_call").text == "Which of these is next?"
    with pytest.raises(lines.LineError):
        lines.resolve("question.free_form")


def test_catalogue_lists_ids_and_slot_shapes_but_no_text():
    cat = lines.catalogue()
    ids = {row["line_id"] for row in cat}
    assert {"coach.nice_work", "briefing.overnight", "question.close_call"} <= ids
    overnight = next(r for r in cat if r["line_id"] == "briefing.overnight")
    assert overnight["slots"] == {"runs": {"type": "int", "min": 0, "max": 999}, "review": {"type": "int", "min": 0, "max": 999}}
    assert "Good morning" not in json.dumps(cat)
    c = client().get("/voice/lines")
    assert c.status_code == 200 and c.json()["data"]


def test_every_fixed_line_is_short_and_free_of_personal_data_patterns():
    from understudy_agent.security.dataflow import personal_kinds

    for row in lines.catalogue():
        slots = {k: (v["ids"][0] if v["type"] == "enum" else v["min"]) for k, v in row["slots"].items()}
        text = lines.resolve(row["line_id"], slots).text
        assert 0 < len(text) <= 200, row["line_id"]
        assert not personal_kinds(text), row["line_id"]


# ------------------------------------------------------------------ the debug flag (worker-only) and the second layer
def test_the_debug_flag_allows_free_text_and_it_is_ledgered_as_such_without_the_text(net, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_VOICE_DEBUG_TEXT", "1")
    r = client().post("/voice/speak", json={"text": "A plain debug sentence.", "kind": "nudge"})
    tts.wait_for_background(3)
    assert r.status_code == 200 and net.spoken() == ["A plain debug sentence."]
    rows = ledger_rows()
    assert len(rows) == 1 and rows[0]["purpose"] == "voice.speak_free"
    assert "debug" not in json.dumps(rows[0]) and "sentence" not in json.dumps(rows[0])


def test_the_personal_data_filter_is_still_a_second_layer_on_the_debug_path(net, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_VOICE_DEBUG_TEXT", "1")
    r = client().post("/voice/speak", json={"text": "My national insurance number is QQ 12 34 56 C.", "kind": "nudge"})
    tts.wait_for_background(2)
    assert r.headers["x-voice-source"] == "personal_data"
    assert net.requests == [] and ledger_rows() == []


def test_with_the_voice_off_or_in_mock_mode_a_line_makes_no_call_and_writes_no_row(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_VOICE", raising=False)
    tts.set_http_factory(lambda: (_ for _ in ()).throw(AssertionError("network used")))
    try:
        r = client().post("/voice/speak", json={"line_id": "coach.almost"})
    finally:
        tts.set_http_factory(None)
    assert r.status_code == 200 and r.headers["x-voice-source"] == "disabled"
    assert ledger_rows() == []


def test_the_status_route_reports_the_flag_and_counters():
    s = client().get("/voice/status").json()
    assert {"enabled", "mock", "voice_configured", "voice", "free_text", "cache_hits"} <= set(s)
    assert s["free_text"] is False


def test_the_wake_lines_the_desktop_speaks_all_exist_here_with_the_same_words():
    """Hey Knack speaks five fixed lines by id (apps/desktop/src/main/wake/texts.ts). A line missing here is a 422 and silence."""
    import pathlib
    import re

    src = (pathlib.Path(__file__).resolve().parents[4] / "apps/desktop/src/main/wake/texts.ts").read_text()
    block = src[src.index("export const SPOKEN_LINES"):]
    block = block[: block.index("}")]
    desktop = dict(re.findall(r"'(wake\.[a-z_]+)':\s*'([^']*)'", block))
    assert len(desktop) == 5, desktop
    for line_id, text in desktop.items():
        assert lines.resolve(line_id, {}).text == text, line_id
