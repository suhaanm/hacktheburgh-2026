"""Tiny text helper for model-written one-liners (a DONE/FAILED line): strip control and invisible characters, collapse space, cap."""
from __future__ import annotations

from ..security.sanitize import sanitize_untrusted


def short_text(text: str, max_chars: int = 300) -> str:
    return sanitize_untrusted(text or "", max_chars=max_chars).text.strip()
