"""ElevenLabs text-to-speech adapter (P2, off by default).

    speak_line(line_id, slots) -> SpeakResult        the ONLY thing a caller on the network may ask for (see lines.py)
    speak_detailed(text, kind) -> SpeakResult        free text: refused unless UNDERSTUDY_VOICE_DEBUG_TEXT=1 (a worker-only debug flag)

Used for narrated coach nudges and the morning briefing. Rules (REVIEW-PRIVACY P1b fixes first):
* A caller names a FIXED LINE (an id from `lines.py`) and typed slots (bounded numbers, ids from a closed set). The sentence is
  produced here, in code, so what can be spoken is a closed set we wrote plus numbers: never a name, never screen text.
  Free-form text is refused (`FreeTextRefused`; the route answers 422) unless the debug flag is set, and then it is ledgered as
  `voice.speak_free`.
* Every real call to the speech service writes a metadata-only ledger row through `privacy.ledger.record_direct`, whether or not the
  privacy extension is on: purpose `voice.speak`, provider and model, a character-count bucket, a hash of the voice id, cache miss,
  latency, ok. No text. If the ledger cannot be written, nothing is sent. A cached clip makes no network call and writes no row
  (it is counted in `status()`).
* The personal-data filter below stays as a second layer on the finished sentence.
* Flag off by default: set UNDERSTUDY_VOICE=1 to enable. With the flag off, in mock mode (UNDERSTUDY_MOCK=1) or with no
  key, the result is a short silent WAV, so every caller works offline and the demo never depends on the network.
* The key and the voice and model ids come from the environment only (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID,
  ELEVENLABS_MODEL). No voice or model id is hard-coded. If no voice id is set we list the account's voices once and
  pick a clear, neutral English one (the choice is cached and reported by `voice_choice()`). If no model id is set the
  field is omitted and the service default applies.
* Disk cache keyed by sha256(text + voice + model + format). A cache hit makes no network call.
* The caller never waits more than `deadline_s` (default 3 s). On timeout or any error the answer is the cached audio if
  any, else silence; a slow request keeps running in the background to warm the cache for next time.
* Privacy: only text written by our own coach and briefing code should be narrated. Text that looks like personal data
  (NI number, email, phone, card, IBAN) is never sent; the answer is silence.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from ..security.dataflow import personal_kinds
from . import lines as _lines
from ..security.paths import data_dir
from ..security.sanitize import sanitize_untrusted

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_DEADLINE_S = 3.0
MAX_CHARS = {"nudge": 280, "briefing": 1500}
SILENT_MIME = "audio/wav"

ENV_FLAG = "UNDERSTUDY_VOICE"
ENV_DEBUG_TEXT = "UNDERSTUDY_VOICE_DEBUG_TEXT"   # worker-only debug flag: allow free-form text (ledgered as voice.speak_free)
ENV_KEY = "ELEVENLABS_API_KEY"
ENV_VOICE = "ELEVENLABS_VOICE_ID"
ENV_MODEL = "ELEVENLABS_MODEL"
ENV_FORMAT = "ELEVENLABS_OUTPUT_FORMAT"
_DEFAULT_FORMAT = "mp3_22050_32"  # an audio format name (small, quick), not a model or voice id
_MIME_BY_PREFIX = {"mp3": "audio/mpeg", "pcm": "audio/L16", "ulaw": "audio/basic", "opus": "audio/ogg", "wav": "audio/wav"}


def _silent_wav(seconds: float = 0.3, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


SILENT_WAV = _silent_wav()


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _truthy(os.environ.get(ENV_FLAG))


def debug_text_enabled() -> bool:
    return _truthy(os.environ.get(ENV_DEBUG_TEXT))


class FreeTextRefused(PermissionError):
    """Free-form text was offered to the speech service without the debug flag. Nothing was sent."""


def mock_mode() -> bool:
    """True when we will not call the network: mock mode, or no key."""
    return _truthy(os.environ.get("UNDERSTUDY_MOCK")) or not os.environ.get(ENV_KEY, "").strip()


def cache_dir() -> Path:
    d = data_dir() / "voice_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _format() -> str:
    return os.environ.get(ENV_FORMAT, "").strip() or _DEFAULT_FORMAT


def _mime_for(fmt: str) -> str:
    return _MIME_BY_PREFIX.get(fmt.split("_", 1)[0], "application/octet-stream")


def _ext_for(mime: str) -> str:
    return {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg"}.get(mime, "bin")


def cache_key(text: str, voice: str, model: str, fmt: str) -> str:
    return hashlib.sha256("\x1f".join((text, voice, model, fmt)).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- voice choice

def pick_default_voice(voices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A clear, neutral English voice from an account's voice list. Deterministic. No ids are hard-coded."""
    def score(v: dict[str, Any]) -> tuple[int, str]:
        lab = v.get("labels") or {}
        name = str(v.get("name", "")).lower()
        s = 0
        if str(lab.get("language", "en")).lower() != "en":
            return (-100, name)
        s += 3 if str(lab.get("gender", "")).lower() == "neutral" else 0
        s += 2 if str(lab.get("descriptive", "")).lower() in ("calm", "professional", "crisp", "formal") else 0
        s += 1 if str(lab.get("use_case", "")).lower() in ("informative_educational", "conversational", "narration") else 0
        s += 2 if any(w in name for w in ("neutral", "clear")) else 0
        s -= 3 if any(w in name for w in ("husky", "warrior", "villain", "trickster", "quirky", "sassy", "hyped", "whisper")) else 0
        s -= 2 if str(lab.get("age", "")).lower() in ("old", "child") else 0
        return (s, name)

    usable = [v for v in voices if v.get("voice_id")]
    if not usable:
        return None
    return sorted(usable, key=lambda v: (-score(v)[0], score(v)[1]))[0]


def _choice_path() -> Path:
    """Path only: reading the choice must not create directories (status() is called on every health check)."""
    return data_dir() / "voice_cache" / "voice_choice.json"


def voice_choice() -> dict[str, str] | None:
    """The voice we use: {id, name, source}. Source is 'env' or 'auto'. None if not decided yet."""
    vid = os.environ.get(ENV_VOICE, "").strip()
    if vid:
        return {"id": vid, "name": "", "source": "env"}
    p = _choice_path()
    if p.exists():
        try:
            return {**json.loads(p.read_text()), "source": "auto"}
        except (json.JSONDecodeError, OSError):
            return None
    return None


# --------------------------------------------------------------------------- http

HttpFactory = Callable[[], httpx.Client]


def _default_http() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15.0, connect=3.0), base_url=API_BASE)


_http_factory: HttpFactory = _default_http  # tests replace this with a MockTransport client
_inflight: dict[str, threading.Thread] = {}
_inflight_lock = threading.Lock()


def set_http_factory(factory: HttpFactory | None) -> None:
    global _http_factory
    _http_factory = factory or _default_http


def _headers() -> dict[str, str]:
    return {"xi-api-key": os.environ[ENV_KEY].strip()}  # never logged or returned


def _ensure_voice(client: httpx.Client) -> str | None:
    c = voice_choice()
    if c:
        return c["id"]
    r = client.get("/voices", headers=_headers())
    r.raise_for_status()
    best = pick_default_voice(r.json().get("voices", []))
    if not best:
        return None
    cache_dir()  # create the directory on first write only
    _choice_path().write_text(json.dumps({"id": best["voice_id"], "name": best.get("name", "")}))
    return best["voice_id"]


def _synthesise(text: str, fmt: str, attempt: dict[str, Any] | None = None) -> tuple[bytes, str, str]:
    """Network call. Returns (audio, mime, voice_id). Raises on any failure. `attempt["posted"]` becomes True just before the text is
    sent, so the caller can write a ledger row only for a call in which text actually left."""
    model = os.environ.get(ENV_MODEL, "").strip()
    with _http_factory() as client:
        voice = _ensure_voice(client)
        if not voice:
            raise RuntimeError("no usable voice on the account")
        body: dict[str, Any] = {"text": text}
        if model:
            body["model_id"] = model
        if attempt is not None:
            attempt["posted"] = True
            attempt["voice"] = voice
        r = client.post(f"/text-to-speech/{voice}", params={"output_format": fmt}, headers={**_headers(), "accept": "*/*"}, json=body)
        r.raise_for_status()
        if not r.content:
            raise RuntimeError("empty audio")
        return r.content, _mime_for(fmt), voice


def _store(key: str, audio: bytes, mime: str) -> None:
    d = cache_dir()
    tmp = d / f"{key}.{_tmp_suffix()}.tmp"
    tmp.write_bytes(audio)
    os.replace(tmp, d / f"{key}.{_ext_for(mime)}")


def _tmp_suffix() -> str:
    return f"{os.getpid()}{threading.get_ident()}"


def _lookup(key: str) -> tuple[bytes, str] | None:
    try:
        d = cache_dir()
        for mime in ("audio/mpeg", "audio/wav", "audio/ogg", "application/octet-stream"):
            p = d / f"{key}.{_ext_for(mime)}"
            if p.exists():
                return p.read_bytes(), mime
    except OSError:
        return None  # an unwritable data directory has no cache; the ledger check then stops any send
    return None


# --------------------------------------------------------------------------- public API

@dataclass(frozen=True)
class SpeakResult:
    audio: bytes
    mime: str
    source: str   # live | cache | mock | disabled | silent | timeout | personal_data | error

    def as_tuple(self) -> tuple[bytes, str]:
        return self.audio, self.mime


# --------------------------------------------------------------------------- ledger (metadata only)
_cache_hits = 0
_CHAR_BUCKETS = ((20, "1-20"), (40, "21-40"), (80, "41-80"), (160, "81-160"), (320, "161-320"), (640, "321-640"))


def _chars_bucket(n: int) -> str:
    for hi, name in _CHAR_BUCKETS:
        if n <= hi:
            return name
    return "641+"


def _voice_hash(voice_id: str | None) -> str:
    return hashlib.sha256((voice_id or "auto").encode("utf-8")).hexdigest()[:8]


def _ledger_writable() -> bool:
    """Can a ledger line be written? Checked BEFORE text leaves: if the ledger cannot take a row, nothing is sent."""
    try:
        from understudy_engine.privacy import ledger

        p = ledger.ledger_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600))
        return True
    except Exception:
        return False


def _record_call(*, purpose: str, chars: int, voice_id: str | None, ok: bool, latency_ms: int) -> None:
    """One metadata-only ledger row for a real call to the speech service. Never the text. Purpose `voice.speak` (a fixed line) or
    `voice.speak_free` (debug free text). Written whether or not the privacy extension is on."""
    from understudy_engine.privacy import ledger

    model = os.environ.get(ENV_MODEL, "").strip() or "default"
    note = f"chars={_chars_bucket(chars)} voice={_voice_hash(voice_id)} cache=miss ok={int(ok)} ms={latency_ms}"
    try:
        ledger.record_direct(method="tts", model=f"elevenlabs:{model}", bytes_sent=chars, purpose=purpose, note=note)
    except OSError:
        pass  # the pre-send check passed; a late failure cannot unsend, and must not break the clip


def _clean(text: str, kind: str) -> str:
    cleaned = " ".join(sanitize_untrusted(text, max_chars=MAX_CHARS.get(kind, 280)).text.split())
    return cleaned


def speak_line(line_id: str, slots: dict[str, Any] | None = None, *, deadline_s: float = DEFAULT_DEADLINE_S) -> SpeakResult:
    """Speak a FIXED line by id with typed slots. Raises `lines.LineError` for an unknown id or a bad slot (nothing is sent)."""
    r = _lines.resolve(line_id, slots)
    return _speak(r.text, r.kind, deadline_s=deadline_s, purpose="voice.speak")


def speak_detailed(text: str, kind: str = "nudge", *, deadline_s: float = DEFAULT_DEADLINE_S) -> SpeakResult:
    """FREE-FORM text. Refused (`FreeTextRefused`) unless UNDERSTUDY_VOICE_DEBUG_TEXT=1 and the call would reach the network; with the
    voice off or in mock mode nothing is sent, so the usual silence is returned. Production callers use `speak_line`."""
    return _speak(text, kind, deadline_s=deadline_s, purpose="voice.speak_free")


def _speak(text: str, kind: str, *, deadline_s: float, purpose: str) -> SpeakResult:
    if kind not in MAX_CHARS:
        raise ValueError(f"kind must be one of {sorted(MAX_CHARS)}")
    if not enabled():
        return SpeakResult(SILENT_WAV, SILENT_MIME, "disabled")
    if mock_mode():
        return SpeakResult(SILENT_WAV, SILENT_MIME, "mock")
    free = purpose == "voice.speak_free"
    if free and not debug_text_enabled():
        raise FreeTextRefused("free-form text is not sent to the speech service; ask for a fixed line by id")
    clean = _clean(text, kind)
    if not clean:
        return SpeakResult(SILENT_WAV, SILENT_MIME, "silent")
    if personal_kinds(clean):
        return SpeakResult(SILENT_WAV, SILENT_MIME, "personal_data")

    fmt = _format()
    voice = (voice_choice() or {}).get("id", "auto")
    key = cache_key(clean, voice, os.environ.get(ENV_MODEL, "").strip() or "default", fmt)
    hit = _lookup(key)
    if hit:
        global _cache_hits
        _cache_hits += 1
        return SpeakResult(hit[0], hit[1], "cache")
    if not _ledger_writable():
        return SpeakResult(SILENT_WAV, SILENT_MIME, "error")  # no ledger row possible, so nothing leaves
    # Until the first call has picked a voice the key uses 'auto'; the result is stored under both keys.
    result: dict[str, Any] = {}
    done = threading.Event()
    n_chars = len(clean)

    def work() -> None:
        attempt: dict[str, Any] = {}
        t0 = time.monotonic()
        try:
            audio, mime, used_voice = _synthesise(clean, fmt, attempt)
            result["ok"] = (audio, mime)
            k2 = cache_key(clean, used_voice, os.environ.get(ENV_MODEL, "").strip() or "default", fmt)
            _store(k2, audio, mime)
            if k2 != key:
                _store(key, audio, mime)
        except Exception as e:  # network, auth, quota, timeout: never raised to the caller
            result["err"] = type(e).__name__
        finally:
            if attempt.get("posted"):
                _record_call(purpose=purpose, chars=n_chars, voice_id=attempt.get("voice"), ok="ok" in result,
                             latency_ms=int((time.monotonic() - t0) * 1000))
            done.set()
            with _inflight_lock:
                _inflight.pop(key, None)

    with _inflight_lock:
        th = _inflight.get(key)
        if th is None:
            th = threading.Thread(target=work, name="voice-tts", daemon=True)
            _inflight[key] = th
            th.start()
    done_in_time = _wait(th, done, deadline_s)
    if done_in_time and "ok" in result:
        return SpeakResult(result["ok"][0], result["ok"][1], "live")
    hit = _lookup(key)
    if hit:
        return SpeakResult(hit[0], hit[1], "cache")
    return SpeakResult(SILENT_WAV, SILENT_MIME, "timeout" if not done_in_time else "error")


def _wait(th: threading.Thread, done: threading.Event, deadline_s: float) -> bool:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if done.wait(0.02):
            return True
        if not th.is_alive():
            return True
    return done.is_set()


def prewarm_line(line_id: str, slots: dict[str, Any] | None = None) -> None:
    """Start synthesis of a FIXED line in the background without waiting (the morning briefing, so it is cached by 08:00)."""
    speak_line(line_id, slots, deadline_s=0.0)


def prewarm(text: str, kind: str = "briefing") -> None:
    """Debug only (free text; see `speak_detailed`)."""
    speak_detailed(text, kind, deadline_s=0.0)


def speak(text: str, kind: str = "nudge") -> tuple[bytes, str]:
    """Debug only (free text). Always returns (audio_bytes, mime); silence on any network trouble."""
    return speak_detailed(text, kind).as_tuple()


def wait_for_background(timeout_s: float = 5.0) -> None:
    """Join in-flight cache warmers (used by tests)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        with _inflight_lock:
            ths = list(_inflight.values())
        if not ths:
            return
        for t in ths:
            t.join(0.05)


def status() -> dict[str, Any]:
    c = voice_choice()
    return {"enabled": enabled(), "mock": mock_mode(), "voice_configured": bool(c), "voice": (c or {}).get("name") or None}


def diagnostics() -> dict[str, Any]:
    """Counters and the debug flag, for the status route. No text, no ids."""
    return {"free_text": debug_text_enabled(), "cache_hits": _cache_hits}
