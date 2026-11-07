"""Fields that are never read or typed into (CAP-4, SEC-11). The list is data: packages/schema/sensitive_fields.json.

Names, ids, labels, placeholders, autocomplete and aria-labels are matched as case-insensitive regexes after
splitting camelCase and punctuation. Only text-entry controls count: a button called "Password reset help" is
not a secret field. A field is judged by what it IS, never by the value in it.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .paths import sensitive_fields_path

_NON_TEXT_INPUT_TYPES = {"button", "submit", "reset", "image", "checkbox", "radio", "file", "range", "color"}
_NON_TEXT_ROLES = {"button", "link", "menuitem", "tab", "img", "image", "checkbox", "radio", "switch"}


@lru_cache(maxsize=1)
def _policy() -> dict[str, Any]:
    with open(sensitive_fields_path(), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def sensitive_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in _policy()["patterns"])


def _norm(*parts: str | None) -> str:
    joined = " ".join(p for p in parts if p)
    joined = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", joined)  # cardNumber -> card Number
    return re.sub(r"[_\-.:/]+", " ", joined).lower()


def is_sensitive_field(*, name: str | None = None, id: str | None = None, label: str | None = None,
                       placeholder: str | None = None, autocomplete: str | None = None,
                       aria_label: str | None = None, input_type: str | None = None,
                       role: str | None = None) -> bool:
    pol = _policy()
    itype = (input_type or "").strip().lower()
    if itype in {t.lower() for t in pol.get("input_types", [])}:
        return True
    ac_tokens = {t.lower() for t in pol.get("autocomplete_tokens", [])}
    if autocomplete and any(tok in ac_tokens for tok in autocomplete.lower().split()):
        return True
    if itype in _NON_TEXT_INPUT_TYPES or (role or "").lower() in _NON_TEXT_ROLES:
        return False
    text = _norm(name, id, label, placeholder, autocomplete, aria_label)
    return any(p.search(text) for p in sensitive_patterns())


def is_sensitive_attrs(attrs: dict[str, Any] | None) -> bool:
    """Convenience for dicts from the extension: keys name, id, label, placeholder, autocomplete, aria_label, type, role."""
    if not attrs:
        return False
    return is_sensitive_field(
        name=attrs.get("name"), id=attrs.get("id"), label=attrs.get("label"),
        placeholder=attrs.get("placeholder"), autocomplete=attrs.get("autocomplete"),
        aria_label=attrs.get("aria_label") or attrs.get("aria-label"),
        input_type=attrs.get("type") or attrs.get("input_type"), role=attrs.get("role"),
    )


def filter_readable_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop sensitive controls from an extraction list before anything reads their values."""
    return [f for f in fields if not is_sensitive_attrs(f)]
