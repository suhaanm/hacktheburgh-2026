"""Guards that run on every digest (LOC-2, PRV-4): strict schema, no verbatim span, PII backstop, fail closed.

A digest holds enums, booleans and numbers only, so the no-verbatim-span and PII checks are a backstop: if a string that
is not in its field's vocabulary ever appears (a changed schema, a model that ignored the grammar, an injected
instruction that made it echo text), the item is rejected and the caller falls back to the rules answer for that item.
None of the functions here log or print the text they inspect.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .schemas import (
    COMMIT_KEYS,
    COMMIT_MODEL_KEYS,
    COMMIT_VOCAB,
    EVENT_KEYS,
    EVENT_MODEL_KEYS,
    EVENT_VOCAB,
)

NGRAM_CHARS = 8          # a shared run of 8 characters (case and spacing ignored) counts as verbatim


class GuardError(Exception):
    """A digest (or a model reply) failed a guard. ``code`` is a short stable token; the message never contains input text."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ---------------------------------------------------------------------------------------------------------------- PII
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+"),
    "url": re.compile(r"\b(https?|ftp|ssh|git)://[^\s]+|\bwww\.[a-z0-9\-]+\.[a-z]{2,}", re.IGNORECASE),
    "phone": re.compile(r"(?<![\w.])(\+?\d{1,3}[\s.\-]?)?(\(?\d{2,4}\)?[\s.\-]?)\d{3,4}[\s.\-]?\d{3,4}(?![\w.])"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "unix_path": re.compile(r"(?<![\w])(/(Users|home|var|etc|opt|tmp|private|srv|mnt|Volumes)/[^\s\"']+|~/[^\s\"']+)"),
    "windows_path": re.compile(r"\b[A-Za-z]:\\[^\s\"']+"),
    "secret_token": re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
                               r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})\b"),
    "long_hex": re.compile(r"\b[0-9a-fA-F]{24,}\b"),
    "uk_nino": re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE),
    "card_number": re.compile(r"\b(?:\d[ \-]?){13,19}\b"),
}


def scan_pii(text: str) -> list[str]:
    """Names of the PII patterns found in ``text`` (empty when none). The text itself is never returned."""
    return sorted(name for name, rx in PII_PATTERNS.items() if rx.search(text))


# ------------------------------------------------------------------------------------------------------ verbatim spans
def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _grams(text: str, n: int) -> set[str]:
    t = _norm(text)
    return {t[i:i + n] for i in range(0, max(0, len(t) - n + 1))}


def verbatim_overlap(value: str, source: str, n: int = NGRAM_CHARS) -> int:
    """How many n-character grams of ``value`` also occur in ``source`` (letters and digits only, case ignored)."""
    v = _grams(value, n)
    if not v:
        return 0
    return len(v & _grams(source, n))


def check_no_verbatim(value: str, source: str, n: int = NGRAM_CHARS) -> None:
    if verbatim_overlap(value, source, n) > 0:
        raise GuardError("verbatim_span")


# ------------------------------------------------------------------------------------------------------ schema checks
def _vocab_for(task: str) -> tuple[Mapping[str, tuple[str, ...]], tuple[str, ...], tuple[str, ...]]:
    if task == "commit_digest":
        return COMMIT_VOCAB, COMMIT_KEYS, COMMIT_MODEL_KEYS
    if task == "event_digest":
        return EVENT_VOCAB, EVENT_KEYS, EVENT_MODEL_KEYS
    raise ValueError(f"unknown task {task!r}")


_BOOL_KEYS = {"touches_tests", "recurring", "needs_prep"}


def validate_digest(task: str, d: Any, *, model_only: bool = False, source: str | None = None) -> dict[str, Any]:
    """Strict check of a digest (or, with ``model_only``, of the model's partial reply). Exact key set, enum values from the
    fixed vocabulary, real booleans, nothing else. With ``source`` given, a string outside its vocabulary is classified as a
    verbatim leak when it overlaps the source, otherwise as an invalid value; either way the digest is rejected."""
    vocab, full_keys, model_keys = _vocab_for(task)
    keys = model_keys if model_only else full_keys
    if not isinstance(d, dict):
        raise GuardError("not_an_object")
    if set(d) != set(keys):
        raise GuardError("bad_keys")
    out: dict[str, Any] = {}
    for k in keys:
        v = d[k]
        if k in _BOOL_KEYS:
            if not isinstance(v, bool):
                raise GuardError("bad_bool", k)
            out[k] = v
            continue
        if not isinstance(v, str):
            raise GuardError("bad_type", k)
        if v not in vocab[k]:
            if source is not None and verbatim_overlap(v, source) > 0:
                raise GuardError("verbatim_span", k)
            raise GuardError("not_in_vocabulary", k)
        out[k] = v
    return out


def guard_digest(task: str, d: Any, source: str) -> dict[str, Any]:
    """The full gate for one finished digest: schema, vocabulary, no verbatim span, PII backstop. Raises ``GuardError``."""
    clean = validate_digest(task, d, source=source)
    for k, v in clean.items():
        if isinstance(v, str):
            pii = scan_pii(v)
            if pii:
                raise GuardError("pii", ",".join(pii))
    return clean


def guard_model_reply(task: str, obj: Any, source: str, fields: tuple[str, ...] | None = None) -> dict[str, Any]:
    """The gate for the model's parsed reply (its partial schema), before code adds the computed fields. ``fields`` is the
    subset the model was asked for (default: all of the task's model fields)."""
    if fields is not None:
        vocab, _full, _m = _vocab_for(task)
        if not isinstance(obj, dict):
            raise GuardError("not_an_object")
        if set(obj) != set(fields):
            raise GuardError("bad_keys")
        clean: dict[str, Any] = {}
        for k in fields:
            v = obj[k]
            if k in _BOOL_KEYS:
                if not isinstance(v, bool):
                    raise GuardError("bad_bool", k)
            elif not isinstance(v, str):
                raise GuardError("bad_type", k)
            elif v not in vocab[k]:
                raise GuardError("verbatim_span" if verbatim_overlap(v, source) > 0 else "not_in_vocabulary", k)
            clean[k] = v
        for v in clean.values():
            if isinstance(v, str) and scan_pii(v):
                raise GuardError("pii")
        return clean
    clean = validate_digest(task, obj, model_only=True, source=source)
    for v in clean.values():
        if isinstance(v, str) and scan_pii(v):
            raise GuardError("pii")
    return clean


def audit_text_for_leaks(text: str, canaries: list[str]) -> list[str]:
    """Canaries (planted strings) that occur in ``text``, case-insensitively. Used by the leak tests and the evaluation."""
    low = text.lower()
    return [c for c in canaries if c and c.lower() in low]
