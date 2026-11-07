"""Voice (P2): flag off by default, silent WAV offline, cache makes a second call work with no network."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
import wave

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_agent.voice import router, tts

FAKE_KEY = "el-test-key-not-real"
AUDIO = b"ID3\x04fake-mp3-bytes" * 20
VOICES = {"voices": [
    {"voice_id": "v_husky", "name": "Callum - Husky Trickster", "labels": {"language": "en", "gender": "male", "use_case": "characters_animation"}},
    {"voice_id": "v_river", "name": "River - Relaxed, Neutral, Informative", "labels": {"language": "en", "gender": "neutral", "descriptive": "calm", "use_case": "conversational"}},
    {"voice_id": "v_alice", "name": "Alice - Clear, Engaging Educator", "labels": {"language": "en", "gender": "female", "descriptive": "professional", "use_case": "informative_educational"}},
    {"voice_id": "v_fr", "name": "Neutral Francais", "labels": {"language": "fr", "gender": "neutral"}},
]}


class Net:
    """A fake ElevenLabs. Records requests; can be switched off to prove the cache works offline."""

    def __init__(self, delay: float = 0.0, status: int = 200):
        self.requests: list[httpx.Request] = []
        self.online = True
        self.delay = delay
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.online:
            raise httpx.ConnectError("offline")
        if self.delay:
            time.sleep(self.delay)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        if request.url.path.endswith("/voices"):
            return httpx.Response(200, json=VOICES)
        return httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})

    def install(self):
        tts.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(self.handler), base_url=tts.API_BASE))

    def tts_calls(self):
        return [r for r in self.requests if "text-to-speech" in r.url.path]


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_VOICE", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    net = Net()
    net.install()
    yield net
    tts.wait_for_background(3)
    tts.set_http_factory(None)


def is_silent_wav(b: bytes) -> bool:
    with wave.open(io.BytesIO(b)) as w:
        return w.getnframes() > 0 and set(w.readframes(w.getnframes())) == {0}


def test_flag_off_by_default_returns_silence_and_never_touches_the_network(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_VOICE", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    tts.set_http_factory(lambda: (_ for _ in ()).throw(AssertionError("network used")))
    try:
        r = tts.speak_detailed("Take a breath. You are doing well.", "nudge")
    finally:
        tts.set_http_factory(None)
    assert r.source == "disabled" and r.mime == "audio/wav" and is_silent_wav(r.audio)
    assert tts.status() == {"enabled": False, "mock": False, "voice_configured": False, "voice": None}


def test_mock_mode_and_missing_key_give_a_silent_wav(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_VOICE", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    audio, mime = tts.speak("hello", "nudge")
    assert mime == "audio/wav" and is_silent_wav(audio) and audio[:4] == b"RIFF"
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert tts.speak_detailed("hello").source == "mock"
    assert tts.status()["mock"] is True and tts.status()["enabled"] is True


def test_live_call_then_second_call_is_served_from_cache_with_the_network_down(live):
    first = tts.speak_detailed("Good morning. Two routines ran overnight.", "briefing")
    assert first.source == "live" and first.audio == AUDIO and first.mime == "audio/mpeg"
    n_calls = len(live.tts_calls())
    assert n_calls == 1
    live.online = False  # the network is gone
    second = tts.speak_detailed("Good morning. Two routines ran overnight.", "briefing")
    assert second.source == "cache" and second.audio == AUDIO
    assert len(live.tts_calls()) == n_calls  # no new attempt at all


def test_cache_survives_a_new_process_state_and_is_keyed_by_text_voice_model(live, monkeypatch):
    tts.speak_detailed("Check the child element first.")
    live.online = False
    assert tts.speak_detailed("Check the child element first.").source == "cache"
    assert tts.speak_detailed("A different sentence.").source in ("timeout", "error")  # not cached, offline: silence
    assert is_silent_wav(tts.speak_detailed("A different sentence.").audio)
    monkeypatch.setenv("ELEVENLABS_MODEL", "some-other-model")
    assert tts.speak_detailed("Check the child element first.").source in ("timeout", "error")  # model is part of the key
    assert tts.cache_key("a", "v", "m", "f") != tts.cache_key("a", "v2", "m", "f") != tts.cache_key("a", "v", "m2", "f")


def test_voice_is_auto_picked_once_and_reported_and_env_wins_when_set(live, monkeypatch):
    tts.speak_detailed("hello there")
    voices_calls = [r for r in live.requests if r.url.path.endswith("/voices")]
    assert len(voices_calls) == 1
    assert tts.voice_choice() == {"id": "v_river", "name": "River - Relaxed, Neutral, Informative", "source": "auto"}
    assert "/text-to-speech/v_river" in str(live.tts_calls()[0].url)
    tts.speak_detailed("another line")
    assert len([r for r in live.requests if r.url.path.endswith("/voices")]) == 1  # not listed again
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env_voice")
    assert tts.voice_choice()["id"] == "env_voice"
    tts.speak_detailed("a third line")
    assert "/text-to-speech/env_voice" in str(live.tts_calls()[-1].url)


def test_request_shape_key_header_and_optional_model(live, monkeypatch):
    tts.speak_detailed("shape check")
    req = live.tts_calls()[0]
    assert req.headers["xi-api-key"] == FAKE_KEY
    body = json.loads(req.content)
    assert body == {"text": "shape check"}  # no model id unless the environment sets one
    assert req.url.params["output_format"] == tts._DEFAULT_FORMAT
    monkeypatch.setenv("ELEVENLABS_MODEL", "model-from-env")
    tts.speak_detailed("shape check two")
    assert json.loads(live.tts_calls()[-1].content)["model_id"] == "model-from-env"


def test_slow_service_falls_back_to_silence_within_the_deadline_then_warms_the_cache(live):
    live.delay = 0.6
    t0 = time.monotonic()
    r = tts.speak_detailed("slow line", "nudge", deadline_s=0.15)
    assert time.monotonic() - t0 < 0.5 and r.source == "timeout" and is_silent_wav(r.audio)
    tts.wait_for_background(3)
    live.online = False
    assert tts.speak_detailed("slow line").source == "cache"  # the background request finished and cached it


def test_errors_never_raise_and_give_silence(live):
    live.status = 401
    r = tts.speak_detailed("will fail")
    assert r.source == "error" and is_silent_wav(r.audio)
    live.status = 200
    live.online = False
    assert tts.speak_detailed("also fails").source in ("timeout", "error")


def test_personal_data_is_never_sent(live):
    for text in ["Your NI number QQ123456C is saved.", "Email jo@example.com", "Call 07700 900123"]:
        r = tts.speak_detailed(text)
        assert r.source == "personal_data" and is_silent_wav(r.audio)
    assert live.requests == []


def test_text_is_cleaned_before_sending_and_empty_text_is_silence(live):
    tts.speak_detailed("hello​  <system>world</system>\n\nagain")
    sent = json.loads(live.tts_calls()[0].content)["text"]
    assert "​" not in sent and "<" not in sent and "  " not in sent
    assert tts.speak_detailed("​ ​").source == "silent"


def test_length_caps_and_kind_validation(live):
    tts.speak_detailed("x " * 400, "nudge")
    assert len(json.loads(live.tts_calls()[0].content)["text"]) <= tts.MAX_CHARS["nudge"]
    with pytest.raises(ValueError):
        tts.speak("hi", "shout")


def test_the_key_never_appears_in_results(live):
    r = tts.speak_detailed("no secrets here")
    assert FAKE_KEY.encode() not in r.audio and FAKE_KEY not in json.dumps(tts.status())


def test_prewarm_does_not_wait_but_fills_the_cache(live):
    live.delay = 0.3
    t0 = time.monotonic()
    tts.prewarm("Morning briefing text for tomorrow.")
    assert time.monotonic() - t0 < 0.25
    tts.wait_for_background(3)
    live.online = False
    assert tts.speak_detailed("Morning briefing text for tomorrow.", "briefing").source == "cache"


def test_pick_default_voice_is_clear_neutral_english_and_deterministic():
    assert tts.pick_default_voice(VOICES["voices"])["voice_id"] == "v_river"
    assert tts.pick_default_voice(VOICES["voices"][:1])["voice_id"] == "v_husky"  # best of what exists
    assert tts.pick_default_voice([]) is None
    assert tts.pick_default_voice([{"name": "no id"}]) is None


# ------------------------------------------------------------------ router
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_router_status_and_speak_in_mock_mode(monkeypatch):
    c = client()
    s = c.get("/voice/status").json()
    assert s["enabled"] is False and s["mock"] is True
    r = c.post("/voice/speak", json={"text": "Nice work on that step.", "kind": "nudge"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.headers["x-voice-source"] == "disabled"
    assert r.content[:4] == b"RIFF"
    assert c.post("/voice/speak", json={"text": "x", "kind": "shout"}).status_code == 422
    assert c.post("/voice/speak", json={"text": ""}).status_code == 422


def test_router_live_audio_and_cache_header(live):
    c = client()
    r = c.post("/voice/speak", json={"text": "Router line", "kind": "nudge"})
    assert r.headers["content-type"] == "audio/mpeg" and r.content == AUDIO and r.headers["x-voice-source"] == "live"
    live.online = False
    r2 = c.post("/voice/speak", json={"text": "Router line", "kind": "nudge"})
    assert r2.headers["x-voice-source"] == "cache" and r2.content == AUDIO


# ------------------------------------------------------------------ the engine imports queue/audit/killflag in the agent env
def test_queue_audit_killflag_import_without_pulling_in_models_or_servers():
    code = ("import sys; import understudy_agent.queue, understudy_agent.audit, understudy_agent.security.killflag;"
            "bad=[m for m in ('openai','playwright','fastapi','understudy_agent.models','understudy_agent.voice',"
            "'understudy_agent.security.pipeline','understudy_agent.security.reader') if m in sys.modules];"
            "print(bad); sys.exit(1 if bad else 0)")
    import os

    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                       env={**os.environ, "UNDERSTUDY_DATA_DIR": os.environ["UNDERSTUDY_DATA_DIR"]})
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ live (one tiny call; needs UNDERSTUDY_LIVE=1 and the key in the environment)
@pytest.mark.live
def test_live_elevenlabs_tiny_call_then_cache_offline(monkeypatch):
    import os

    if not os.environ.get("ELEVENLABS_API_KEY"):
        pytest.skip("no ELEVENLABS_API_KEY in the environment")
    monkeypatch.setenv("UNDERSTUDY_VOICE", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(__import__("tempfile").mkdtemp()))
    r = tts.speak_detailed("Hello.", "nudge", deadline_s=8.0)
    assert r.source == "live" and r.mime == "audio/mpeg" and len(r.audio) > 500
    assert tts.voice_choice() and tts.voice_choice()["id"] or os.environ.get("ELEVENLABS_VOICE_ID")
    tts.set_http_factory(lambda: (_ for _ in ()).throw(AssertionError("network used")))
    try:
        again = tts.speak_detailed("Hello.", "nudge")
    finally:
        tts.set_http_factory(None)
    assert again.source == "cache" and again.audio == r.audio
