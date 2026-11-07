"""Small text and number helpers for the proactive layer.

Two jobs: (1) clean what the worker types into a card so that what is stored, shown and fired are the same bytes
(the approval queue sanitises its evidence, so we apply the same cleaning first and store the result); (2) keep
``numbers`` on candidates and cards to plain numbers, booleans and short fixed tokens, so no free text from any
source can ride along on a card.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

MAX_TEXT = 1500       # one prepared text block
MAX_STEPS = 12
MAX_STEP = 240
MAX_TITLE = 120
MAX_WHY = 400

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_TOKEN = re.compile(r"^[a-z0-9_.:\-]{1,24}$")

_BRACKETS = str.maketrans({"<": "‹", ">": "›", "[": "⟦", "]": "⟧", "{": "❴", "}": "❵",
                           "`": "ˋ", "|": "∣"})


def _fallback_clean(s: str, max_chars: int) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if ch in ("\n", "\t") or unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    s = s.translate(_BRACKETS)
    return s[:max_chars]


def clean_text(s: Any, max_chars: int = MAX_TEXT) -> str:
    """Cleaned text, safe to show and to hand on. Uses the agent's sanitiser when it is importable so the approval
    queue's own pass changes nothing; otherwise an equivalent local pass. Idempotent."""
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    try:
        from understudy_agent.security.sanitize import sanitize_untrusted

        out = sanitize_untrusted(s, max_chars=max_chars).text
    except Exception:
        out = _fallback_clean(s, max_chars)
    return out.replace("\r\n", "\n").replace("\r", "\n").strip()


def clean_line(s: Any, max_chars: int = MAX_STEP) -> str:
    return " ".join(clean_text(s, max_chars).split())


def safe_numbers(d: Any, *, max_keys: int = 16) -> dict[str, int | float | bool | str]:
    """Only plain numbers, booleans and short fixed tokens under plain keys. Everything else is dropped."""
    out: dict[str, int | float | bool | str] = {}
    if not isinstance(d, dict):
        return out
    for k, v in list(d.items())[:64]:
        if len(out) >= max_keys:
            break
        if not isinstance(k, str) or not _KEY.match(k):
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, int):
            out[k] = v
        elif isinstance(v, float) and v == v and abs(v) != float("inf"):
            out[k] = round(v, 3)
        elif isinstance(v, str) and _TOKEN.match(v):
            out[k] = v
    return out


def canonical(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def prepared_hash(prepared: dict[str, Any]) -> str:
    """Hash of the exact content that fires (text, steps, artifact_ref only)."""
    core = {k: prepared[k] for k in ("text", "steps", "artifact_ref") if prepared.get(k) not in (None, "", [])}
    return "p:" + hashlib.sha256(canonical(core).encode()).hexdigest()[:16]


def clean_prepared(p: Any) -> dict[str, Any]:
    """Validate and clean an edited ``prepared`` object: ``{text?: str, steps?: [str], artifact_ref?: str}``.

    Raises ``ValueError`` with a plain message for a bad shape. Unknown keys are refused (nothing rides along)."""
    if not isinstance(p, dict):
        raise ValueError("prepared must be an object with text, steps or artifact_ref")
    extra = set(p) - {"text", "steps", "artifact_ref"}
    if extra:
        raise ValueError(f"prepared may only have text, steps and artifact_ref, not {', '.join(sorted(extra))}")
    out: dict[str, Any] = {}
    if p.get("text") not in (None, ""):
        if not isinstance(p["text"], str):
            raise ValueError("prepared.text must be a string")
        out["text"] = clean_text(p["text"], MAX_TEXT)
    if p.get("steps") not in (None, []):
        steps = p["steps"]
        if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
            raise ValueError("prepared.steps must be a list of strings")
        if len(steps) > MAX_STEPS:
            raise ValueError(f"prepared.steps may have at most {MAX_STEPS} steps")
        cleaned = [clean_line(x, MAX_STEP) for x in steps]
        out["steps"] = [x for x in cleaned if x]
    if p.get("artifact_ref") not in (None, ""):
        ref = p["artifact_ref"]
        if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_./:\-]{1,160}", ref) or ".." in ref:
            raise ValueError("prepared.artifact_ref must be a plain relative reference")
        out["artifact_ref"] = ref
    if not out:
        raise ValueError("prepared must keep some text or steps")
    return out
