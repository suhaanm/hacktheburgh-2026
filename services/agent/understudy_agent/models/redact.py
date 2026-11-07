"""Redaction for every error and log path in the model layer (Gemini and the router).

Three things must never reach an exception message, a log line, a ledger line, a cache key or a fixture:

* an API key (the literal value of an environment key, a Google-style `AIza...` key, an `sk-...` key, a bearer token,
  an `x-goog-api-key` header value, a `key=` query parameter),
* image bytes (a base64 run of any real length is replaced by its size),
* the response body of a failed call beyond a short, redacted excerpt.

Pure functions, no I/O. `redact_text` is idempotent.
"""
from __future__ import annotations

import os
import re

_KEY_ENVS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "AUTH0_CLIENT_SECRET")
_MIN_SECRET_LEN = 8

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "<redacted:key>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"), "<redacted:key>"),
    (re.compile(r"(?i)(x-goog-api-key|authorization|api[-_]?key)(\s*[:=]\s*)(bearer\s+)?[^\s,;'\"}&]+"),
     r"\1\2<redacted:key>"),
    (re.compile(r"(?i)([?&]key=)[^&\s'\"]+"), r"\1<redacted:key>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{12,}"), "Bearer <redacted:key>"),
)
# Image payloads are base64: a long unbroken run of the base64 alphabet is never prose.
_B64_RUN = re.compile(r"(?:data:[a-z]+/[a-z0-9.+\-]+;base64,)?[A-Za-z0-9+/_\-]{200,}={0,2}")


def _secret_values() -> list[str]:
    out = []
    for name in _KEY_ENVS:
        v = os.environ.get(name, "").strip()
        if len(v) >= _MIN_SECRET_LEN:
            out.append(v)
    return out


def redact_text(text: object, *, max_chars: int = 400, extra_secrets: tuple[str, ...] = ()) -> str:
    """A safe, short rendering of `text` for an error message or log line."""
    s = str(text)
    for secret in (*_secret_values(), *(x for x in extra_secrets if x and len(x) >= _MIN_SECRET_LEN)):
        s = s.replace(secret, "<redacted:key>")
    for pat, repl in _PATTERNS:
        s = pat.sub(repl, s)
    s = _B64_RUN.sub(lambda m: f"<{len(m.group(0))} chars of encoded data>", s)
    if len(s) > max_chars:
        s = s[:max_chars] + "..."
    return s


def contains_secret(text: object) -> bool:
    """True when `text` still holds a key-shaped string or the value of a configured key (used by tests and guards)."""
    s = str(text)
    if any(v in s for v in _secret_values()):
        return True
    return bool(_PATTERNS[0][0].search(s) or _PATTERNS[1][0].search(s))
