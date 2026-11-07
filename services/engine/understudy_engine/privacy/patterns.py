"""The PII and canary backstop (PRV-1). Last line of defence, not the first.

The first line is the type system: a ``SafePayload`` cannot hold free text. This module scans what is *about* to be sent
for the shapes that should never appear anyway: email addresses, phone numbers, file paths, URLs, National Insurance
numbers, long digit runs, secret-looking tokens, and the field-name patterns in ``packages/schema/sensitive_fields.json``.

The sensitive-field patterns are copied here (this package cannot import ``understudy_agent``). ``SENSITIVE_FALLBACK``
is the copy; the JSON file is read too when it is present, and a test fails if the copy has drifted behind the file.

Hits never carry the matched text: errors and logs say which field and which rule, never the value.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Any, Iterable

from ._paths import schema_dir

# Copy of packages/schema/sensitive_fields.json "patterns" (7 Nov 2026). Matched case-insensitively.
SENSITIVE_FALLBACK: tuple[str, ...] = (
    r"pass(word|wd|code|phrase)?",
    r"\bpin\b",
    r"\botp\b",
    r"one[- ]?time",
    r"2fa|mfa|verification[- ]code|security[- ]code",
    r"\bcvv\b|\bcvc\b|card[- ]?(number|no)|credit|debit",
    r"\biban\b|sort[- ]?code|account[- ]?(number|no)|routing",
    r"national[- ]?insurance|\bni[- ]?(number|no)\b|\bnino\b|\bssn\b|social[- ]security",
    r"passport|driving[- ]?licen[cs]e|date[- ]of[- ]birth|\bdob\b",
    r"secret|token|api[- ]?key|private[- ]key|seed[- ]phrase",
    r"cc-number|cc-csc|cc-exp|current-password|new-password|one-time-code",
)

_CODE_EXT = (
    "py|pyi|js|jsx|ts|tsx|mjs|go|rs|java|kt|swift|rb|php|c|cc|cpp|h|hpp|cs|sh|zsh|sql|md|txt|csv|tsv|json|jsonl|yaml|yml|"
    "toml|ini|cfg|env|key|pem|crt|ics|eml|doc|docx|xls|xlsx|ppt|pptx|pdf|png|jpg|jpeg|gif|zip|log"
)
_TLDS = (
    "com|org|net|io|co|uk|edu|gov|ac|dev|app|ai|me|us|eu|de|fr|es|nl|info|biz|xyz|test|example|invalid|local|internal|"
    "lan|corp|cloud|tech"
)

# name -> pattern. These apply to string values and keys.
PII_PATTERNS: dict[str, str] = {
    "email": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+",
    "url": rf"(?i)\b(?:https?|ftps?|ssh|file|s3|git|smb)://\S+|\bwww\.[a-z0-9\-]+\.\S+"
           rf"|(?<![\w@])[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)*\.(?:{_TLDS})\b",
    "path": rf"(?:~|\.{{1,2}})?/(?:[\w.\-@+ ]+/)+[\w.\-@+]*|[A-Za-z]:\\(?:[^\\\s]+\\?)+|\b[\w\-]+/[\w\-]+/[\w\-./]+"
            rf"|(?i:\b[\w\-]+/[\w\-]+\.(?:{_CODE_EXT})\b)|(?i:\b[\w\-]+\.(?:{_CODE_EXT})\b)",
    "phone": r"(?<![\w.])\+\d{1,3}[\s().-]*\d(?:[\s().-]*\d){6,13}(?!\d)"
             r"|(?<![\d.])0\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)"
             r"|(?<![\d.])\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)",
    "ni_number": r"(?i)\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
    "long_digits": r"\d{6,}|(?<!\d)(?:\d[\s-]?){13,19}(?!\d)",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "secret_like": r"\b(?:sk|pk|rk|ghp|gho|ghs|xox[abprs]|AKIA|AIza)[-_A-Za-z0-9]{10,}"
                   r"|\b[A-Za-z0-9+/_\-]{32,}={0,2}(?![A-Za-z0-9])",
}

# The project's own hashed ids (label_hash "h:<hex>", domain_hash "d:<hex>"; packages/schema/event.schema.json) are not
# personal data, but their hex digits can contain long digit runs by chance (about 1 in 7 at 12 hex characters). They are
# blanked out before the PII rules run so they are never refused for that reason.
_HASH_ID = re.compile(r"(?<![\w])[hd]:[0-9a-f]{4,16}(?![\w])")

NUMERIC_LIMIT = 1_000_000  # integers at or above this are refused as "looks like an id or a timestamp"

_lock = threading.Lock()
_compiled_pii: dict[str, re.Pattern[str]] | None = None
_compiled_sensitive: list[re.Pattern[str]] | None = None


@dataclass(frozen=True)
class Hit:
    """One backstop hit. ``path`` is the field path (dotted, with list indexes); ``rule`` names the pattern.
    Never the matched text."""

    path: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path or '(root)'}: {self.rule}"


def sensitive_patterns() -> list[str]:
    """The sensitive-field patterns: the repo file when readable, else the embedded copy, always including the copy."""
    out = list(SENSITIVE_FALLBACK)
    try:
        data = json.loads((schema_dir() / "sensitive_fields.json").read_text(encoding="utf-8"))
        for p in data.get("patterns", []):
            if isinstance(p, str) and p not in out:
                out.append(p)
    except (OSError, ValueError):
        pass
    return out


def _pii() -> dict[str, re.Pattern[str]]:
    global _compiled_pii
    with _lock:
        if _compiled_pii is None:
            _compiled_pii = {k: re.compile(v) for k, v in PII_PATTERNS.items()}
        return _compiled_pii


def _sensitive() -> list[re.Pattern[str]]:
    global _compiled_sensitive
    with _lock:
        if _compiled_sensitive is None:
            _compiled_sensitive = [re.compile(p, re.I) for p in sensitive_patterns()]
        return _compiled_sensitive


def reload() -> None:
    """Forget compiled patterns (tests that change the schema file)."""
    global _compiled_pii, _compiled_sensitive
    with _lock:
        _compiled_pii = None
        _compiled_sensitive = None


def scan_text(text: str, *, names: bool = True, pii: bool = True) -> list[str]:
    """Rule names that match ``text``. ``names=True`` adds the sensitive-field patterns (right for field names and for
    values that come from a fixed vocabulary; too noisy for model output). Empty list means clean."""
    rules: list[str] = []
    if pii:
        pii_text = _HASH_ID.sub("#", text)
        for rule, rx in _pii().items():
            if rx.search(pii_text):
                rules.append(rule)
    if names:
        # The schema patterns were written for UI labels ("api key", "card-number"); our names are snake_case or camelCase,
        # which they would miss (api_key, cardNumber). Match the raw text and two normalised spellings.
        spaced = re.sub(r"[_.]+", " ", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text))
        variants = {text, spaced, spaced.replace(" ", "-")}
        for i, rx in enumerate(_sensitive()):
            if any(rx.search(v) for v in variants):
                rules.append(f"sensitive_field_{i}")
    return rules


def scan_value(obj: Any, path: str = "", *, names: bool = True, pii: bool = True) -> list[Hit]:
    """Walk a JSON-like value (dict, list, str, numbers, bool, None) and return every hit."""
    hits: list[Hit] = []
    if isinstance(obj, bool) or obj is None:
        return hits
    if isinstance(obj, str):
        hits.extend(Hit(path, r) for r in scan_text(obj, names=names, pii=pii))
        return hits
    if isinstance(obj, int):
        if abs(obj) >= NUMERIC_LIMIT:
            hits.append(Hit(path, "large_number"))
        return hits
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            hits.append(Hit(path, "non_finite_number"))
        elif abs(obj) >= NUMERIC_LIMIT:
            hits.append(Hit(path, "large_number"))
        return hits
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else str(k)
            if not isinstance(k, str):
                hits.append(Hit(kp, "non_string_key"))
                continue
            for r in scan_text(k, names=names, pii=pii):
                hits.append(Hit(kp + "{key}", r))
            hits.extend(scan_value(v, kp, names=names, pii=pii))
        return hits
    if isinstance(obj, (list, tuple, set, frozenset)):
        for i, v in enumerate(obj):
            hits.extend(scan_value(v, f"{path}[{i}]", names=names, pii=pii))
        return hits
    hits.append(Hit(path, f"unexpected_type_{type(obj).__name__}"))
    return hits


def clean_rules(hits: Iterable[Hit]) -> list[str]:
    """Sorted unique rule names, for plain error messages."""
    return sorted({h.rule for h in hits})
