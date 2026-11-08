"""REVIEW-PRIVACY: two egress channels that do not go through egress.send / send_image.

(1) POST /voice/speak: arbitrary text (<= 4000 chars) is sent to ElevenLabs, no purpose, no SafePayload, no ledger row.
(2) With the privacy flag off (the default), get_model_port() hands out an UNledgered port: planner calls with raw content leave
    with no ledger line at all.
Hermetic: httpx.MockTransport stands in for ElevenLabs; the mock model port stands in for OpenAI. No network.
Run: .venv/bin/python -m pytest evals/review/privacy/test_p1b_voice_and_default_ledger.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import json

import httpx
import pytest

CANARY_NAME = "Zebulon Quillfeather"          # a made-up person name
CANARY_TEXT = f"Reminder: call {CANARY_NAME} about the Hollowbrook invoice 4471-ZQ"   # passes the PII regexes (no digits run >=6)


@pytest.fixture()
def voice(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNDERSTUDY_VOICE", "1")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    monkeypatch.delenv("UNDERSTUDY_VOICE_DEBUG_TEXT", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi-FAKE-NOT-A-KEY")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voiceFAKE")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    from understudy_agent.voice import tts
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from understudy_agent.voice.router import router

    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append({"url": str(req.url), "body": json.loads(req.content or b"{}")})
        return httpx.Response(200, content=b"ID3FAKEAUDIO")

    tts.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url=tts.API_BASE))
    app = FastAPI(); app.include_router(router)
    yield TestClient(app), seen, tmp_path, tts
    tts.set_http_factory(None)


def _spoken(seen):
    return json.dumps([s["body"] for s in seen])


def test_free_text_is_now_refused_and_nothing_is_sent(voice):
    c, seen, tmp, tts = voice
    r = c.post("/voice/speak", json={"text": CANARY_TEXT, "kind": "nudge"})
    tts.wait_for_background(2)
    assert r.status_code == 422 and not seen, (r.status_code, r.text)


ATTACKS = [
    # (line_id, slots) the new registry must refuse (422) or render without anything the caller chose
    ("briefing.greeting", {"part": CANARY_NAME}),                                  # free string in an enum slot
    ("briefing.greeting", {"part": "morning\n" + CANARY_NAME.lower().replace(" ", "_")}),
    ("briefing.greeting", {"part": "m\u043erning"}),                                  # Cyrillic o homoglyph
    ("briefing.greeting", {"part": "morning", "extra": CANARY_NAME}),               # extra slot
    ("briefing.greeting", {"part": ["morning"]}),
    ("briefing.overnight", {"runs": 10**4000, "review": 1}),                       # huge int
    ("briefing.overnight", {"runs": 2.5, "review": 1}),
    ("briefing.overnight", {"runs": True, "review": 1}),
    ("briefing.overnight", {"runs": "2", "review": 1}),                            # digit string
    ("briefing.overnight", {"runs": 1, "review": 1, "x": 1}),
    ("coach.nice_work", {"name": CANARY_NAME.lower().replace(" ", "_")}),
    ("coach.nice_work\n", None),                                                    # $ matches before a trailing newline
    ("whisper." + CANARY_NAME.lower().replace(" ", "_"), None),                    # step id that is not in a pack
    ("whisper.read_case\n", None),
    ("question." + CANARY_NAME.lower().replace(" ", "_"), None),
]


@pytest.mark.parametrize("line_id,slots", ATTACKS, ids=[f"a{i}" for i in range(len(ATTACKS))])
def test_registry_attacks_send_nothing_the_caller_chose(voice, line_id, slots):
    c, seen, tmp, tts = voice
    body = {"line_id": line_id}
    if slots is not None:
        body["slots"] = slots
    r = c.post("/voice/speak", json=body)
    tts.wait_for_background(2)
    spoken = _spoken(seen)
    assert CANARY_NAME.split()[0].lower() not in spoken.lower() and "zebulon" not in spoken.lower(), (line_id, slots, spoken)
    assert "\n" not in spoken.replace("\\n", ""), "a newline reached the speech service"
    if r.status_code == 200:
        # accepted: then what was sent must be one of the fixed sentences with numbers only
        import re
        for s in seen:
            assert re.fullmatch(r"[A-Za-z ,.\d']+", s["body"]["text"]), s["body"]["text"]


def test_real_call_writes_one_metadata_only_ledger_row_and_an_unwritable_ledger_blocks_the_send(voice, monkeypatch):
    c, seen, tmp, tts = voice
    r = c.post("/voice/speak", json={"line_id": "briefing.overnight", "slots": {"runs": 3, "review": 2}})
    tts.wait_for_background(3)
    assert r.status_code == 200 and seen, r.text
    rows = [json.loads(l) for l in (tmp / "egress_ledger.jsonl").read_text().splitlines()]
    voice_rows = [x for x in rows if "voice" in json.dumps(x)]
    print("\nvoice ledger rows:", voice_rows)
    assert len(voice_rows) == 1
    blob = json.dumps(voice_rows[0])
    assert "routine" not in blob and "overnight" not in blob, "the spoken sentence must not be in the ledger row"
    # now make the ledger unwritable (a directory where the file should be) and use a NEW sentence so the cache cannot answer
    seen.clear()
    (tmp / "egress_ledger.jsonl").unlink()
    (tmp / "egress_ledger.jsonl").mkdir()
    r2 = c.post("/voice/speak", json={"line_id": "briefing.overnight", "slots": {"runs": 7, "review": 4}})
    tts.wait_for_background(2)
    print("unwritable ledger ->", r2.status_code, r2.headers.get("x-voice-source"), "sent:", len(seen))
    assert not seen, "audio was requested although the ledger could not be written"


def test_debug_flag_reopens_free_text_but_still_ledgers(voice, monkeypatch):
    c, seen, tmp, tts = voice
    monkeypatch.setenv("UNDERSTUDY_VOICE_DEBUG_TEXT", "1")
    r = c.post("/voice/speak", json={"text": CANARY_TEXT, "kind": "nudge"})
    tts.wait_for_background(3)
    print("\nDEBUG_TEXT=1: status", r.status_code, "sent", len(seen))
    # documents the residual risk: one environment variable restores the old behaviour (free text to a third party)
    assert r.status_code == 200 and seen and CANARY_NAME in _spoken(seen)
    rows = (tmp / "egress_ledger.jsonl").read_text().splitlines() if (tmp / "egress_ledger.jsonl").exists() else []
    assert len(rows) >= 1, "debug free text must still leave a ledger row"


def test_default_flags_off_mock_mode_makes_no_remote_call_and_is_not_wrapped(tmp_path, monkeypatch):
    """Mock mode: no remote call exists, so no ledger row is needed (the lead's position; I agree for Python). Documented, not a gap."""
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_PRIVACY", "UNDERSTUDY_LEDGER_MOCK_CALLS"):
        monkeypatch.delenv(k, raising=False)
    from understudy_agent.models import get_model_port
    from understudy_engine.privacy.direct import LedgeredPort
    port = get_model_port(mock=True, fresh=True)
    assert not isinstance(port, LedgeredPort) and getattr(port, "name", "") == "mock"


class _FakeProvider:
    """A stand-in for a real remote provider: records calls, never touches a network."""
    name = "fake"
    offline = False
    instances: list = []

    def __init__(self, *a, **k):
        self.calls = []
        _FakeProvider.instances.append(self)

    def plan(self, messages, schema=None):
        self.calls.append("plan"); return {"ok": True}

    def read(self, untrusted, schema):
        self.calls.append("read"); return {"ok": True}

    def check(self, prompt, schema):
        self.calls.append("check"); return {"ok": True}

    def vision(self, image, prompt, schema=None):
        self.calls.append("vision"); return {"ok": True}

    def computer_step(self, goal, screenshot, history, **kw):
        self.calls.append("computer_step"); return {"ok": True}


class _FakeGemini(_FakeProvider):
    name = "gemini"


class _FakeOpenAI(_FakeProvider):
    name = "openai"


# D49 (7 Nov): the default provider is Gemini and OpenAI is an explicit opt-in. The ledger guarantee must hold for BOTH, so every test
# below that builds a non-mock port runs once for the default and once for UNDERSTUDY_PROVIDER=openai.
@pytest.fixture(params=[None, "openai"], ids=["default_gemini", "explicit_openai"])
def provider(request):
    return request.param


def _non_mock_port(tmp_path, monkeypatch, provider=None):
    """Non-mock configuration with a FAKE provider (no key, no network, no model ids needed): UNDERSTUDY_MOCK unset, every extension flag
    unset. `provider=None` is the default (Gemini); "openai" is the explicit opt-in."""
    for k in ("UNDERSTUDY_MOCK", "UNDERSTUDY_X", "UNDERSTUDY_X_PRIVACY", "UNDERSTUDY_LEDGER_MOCK_CALLS", "UNDERSTUDY_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    if provider:
        monkeypatch.setenv("UNDERSTUDY_PROVIDER", provider)
    from understudy_agent.models import factory, gemini_provider, openai_provider
    monkeypatch.setattr(openai_provider, "OpenAIProvider", _FakeOpenAI)
    monkeypatch.setattr(gemini_provider, "GeminiProvider", _FakeGemini)
    factory.reset_model_port()
    _FakeProvider.instances.clear()
    from understudy_agent.models import get_model_port
    return get_model_port(fresh=True), factory


def test_non_mock_default_port_is_ledgered_with_metadata_only(tmp_path, monkeypatch, provider):
    port, _ = _non_mock_port(tmp_path, monkeypatch, provider)
    from understudy_engine.privacy.direct import LedgeredPort
    assert isinstance(port, LedgeredPort), "with every flag off, a non-mock port must still be ledgered"
    port.plan([{"role": "user", "content": f"typed value: {CANARY_NAME}"}], None)
    port.read(f"page text {CANARY_NAME}", {})
    port.check(f"prompt {CANARY_NAME}", {})
    port.vision(b"\x89PNG\r\n\x1a\nFAKEFRAME", f"look at {CANARY_NAME}", None)
    port.computer_step(f"goal {CANARY_NAME}", b"SCREENSHOTBYTES", [{"h": CANARY_NAME}])
    led = tmp_path / "data" / "egress_ledger.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    print("\nNON-MOCK, flags off, fake provider: rows =", len(rows), [r.get("method") for r in rows])
    assert len(rows) == 5 and {r["method"] for r in rows} == {"plan", "read", "check", "vision", "computer_step"}
    blob = led.read_text()
    assert "zebulon" not in blob.lower() and "FAKEFRAME" not in blob and "SCREENSHOTBYTES" not in blob
    assert all(r.get("payload") is None and r.get("content_logged") is False for r in rows)


def test_non_mock_call_is_not_made_when_the_ledger_cannot_be_written(tmp_path, monkeypatch, provider):
    port, _ = _non_mock_port(tmp_path, monkeypatch, provider)
    led = tmp_path / "data" / "egress_ledger.jsonl"
    led.mkdir(parents=True, exist_ok=True)                   # a directory where the file should be: appends fail
    inst = _FakeProvider.instances[-1]
    with pytest.raises(Exception):
        port.plan([{"role": "user", "content": "x"}], None)
    assert inst.calls == [], "the provider was called although no ledger row could be written"


# Reviewed exceptions: modules outside privacy/ and models/ that obtain a raw (unledgered) port ON PURPOSE. live_t3 is the hand-run LIVE
# tier-3 evaluation (a key, synthetic households on the headless sandbox sites, its own hard spend ledger, no real screen, never started by
# the app). It stays an exception only while nothing else imports it: that is asserted below, so no production path can reach its raw port.
REVIEWED_RAW_PORT_MODULES = {"understudy_agent/live_t3.py": "hand-run live evaluation on synthetic data; keeps its own spend ledger"}


def test_ledgered_false_is_not_an_open_escape_hatch(tmp_path, monkeypatch, provider):
    """get_model_port(ledgered=False) returns the RAW provider (egress uses it so the guard can write its own row). Regression for the
    review finding: no production module outside privacy/ and models/ obtains one, except the reviewed hand-run evaluation harness, and
    nothing imports that harness."""
    _non_mock_port(tmp_path, monkeypatch, provider)
    from understudy_agent.models import get_model_port
    from understudy_engine.privacy.direct import LedgeredPort
    raw = get_model_port(fresh=True, ledgered=False)
    assert not isinstance(raw, LedgeredPort)
    from understudy_engine.privacy import guard
    import re
    offenders = []
    importers = []
    for root in (guard.ENGINE_PKG, guard.AGENT_PKG):
        for p in root.rglob("*.py"):
            rel = p.relative_to(root).as_posix()
            if "__pycache__" in rel:
                continue
            text = p.read_text(encoding="utf-8")
            if re.search(r"\blive_t3\b", text) and not rel.endswith("live_t3.py"):
                importers.append(f"{root.name}/{rel}")
            if rel.startswith(("privacy/", "models/")):
                continue
            if re.search(r"ledgered\s*=\s*False|_get_raw_port", text) and f"{root.name}/{rel}" not in REVIEWED_RAW_PORT_MODULES:
                offenders.append(f"{root.name}/{rel}")
    assert offenders == [], f"modules that obtain an unledgered port: {offenders}"
    assert importers == [], f"a module imports the live evaluation harness, which holds a raw port: {importers}"
