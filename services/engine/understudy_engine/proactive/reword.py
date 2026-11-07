"""Optional model wording for a card's reason line, only ever through the egress guard.

The card always renders without a model: the templated ``why`` is the fallback for every failure (privacy layer absent, no
model configured, the call blocked or failed, an answer that does not fit). The model never sees a name, a title, a path or
any text from a source: the payload is ``briefing.card_wording`` from the privacy layer, a ``SafePayload`` with the card's
kind, risk class, source tags and a few named numbers, generalised (counts under 5, durations to 5 minutes, ratios to 10%)
before they leave. Every call is one line in the egress ledger.

Only the display-only ``why`` is ever reworded. ``prepared`` (what fires) stays the template: a model never writes the thing
that runs. A reworded sentence is also refused if it mentions a number that is not in the templated reason or the payload
(the instructions say to use only the numbers given; this checks it).

Nothing in this package imports a model client or calls a model port directly; ``egress.send`` is the only way out.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .candidates import Candidate
from .paths import _on, is_mock
from .text import MAX_WHY, clean_line

#: our source tags in the privacy layer's ``source_tag`` vocabulary; tags with no entry (``pack``, ``local_model``) are not sent
SOURCE_MAP = {"routines": "routine", "skills": "skill", "agents": "agent", "calendar": "calendar", "git": "git", "memory": "memory"}
#: named numbers this layer sends, and how the privacy layer generalises each (registered on first use)
FEATURES = {"episodes": "count", "minutes_per_week": "duration_min", "hours_saved_lo": "hours", "hours_saved_hi": "hours",
            "confidence": "ratio", "horizon_weeks": "raw", "level": "raw", "mastery": "ratio", "days_idle": "raw",
            "days_until_drop": "raw", "learner": "raw", "expert": "raw", "delta": "raw", "n_commits": "count", "age_h": "hours",
            "children": "count"}
PURPOSE = "briefing.card_wording"
_NUM = re.compile(r"\d+(?:\.\d+)?")


def privacy_on() -> bool:
    return _on("UNDERSTUDY_X") or _on("UNDERSTUDY_X_PRIVACY")


def ensure_features() -> dict[str, str]:
    """Register our named numbers with the privacy layer (idempotent). Returns the registry as the privacy layer has it."""
    from understudy_engine.privacy.bucket import feature_kinds, register_feature

    for name, kind in FEATURES.items():
        try:
            register_feature(name, kind)
        except ValueError:       # already registered with another kind by another track: that registration stands
            pass
    return feature_kinds()


def payload_for(c: Candidate, kinds: dict[str, str]) -> dict[str, Any]:
    """What would be sent: kind, risk, mapped source tags, and the numbers that are registered features. No text."""
    numbers = {k: v for k, v in c.numbers.items() if k in kinds and isinstance(v, (int, float)) and not isinstance(v, bool)}
    return {"kind": c.kind, "risk": c.risk_class, "sources": sorted({SOURCE_MAP[t] for t in c.source_tags if t in SOURCE_MAP}),
            "numbers": numbers}


def _allowed_numbers(c: Candidate, payload: dict[str, Any]) -> set[str]:
    ok = set(_NUM.findall(c.why))
    for v in payload["numbers"].values():
        if isinstance(v, (int, float)):
            f = float(v)
            ok.update({f"{f:g}", f"{f:.1f}", f"{f:.2f}", str(int(round(f)))})
            ok.add(f"{f * 100:g}")          # a ratio spoken as a percentage
    return ok


def reword_why(c: Candidate, *, port: Any = None) -> str | None:
    """One reworded reason sentence, or None (the template stands). Never raises."""
    try:
        from understudy_engine.privacy import egress
        from understudy_engine.privacy.egress import EgressError
    except Exception:
        return None
    try:
        payload = payload_for(c, ensure_features())
        res = egress.send(PURPOSE, payload, port=port)
    except EgressError:
        return None
    except Exception:
        return None
    out = res.output
    text = out.get("text") if isinstance(out, dict) else None
    if not isinstance(text, str):
        return None
    text = clean_line(text, MAX_WHY)
    if not text or len(text.split()) > 60:
        return None
    if any(n not in _allowed_numbers(c, payload) for n in _NUM.findall(text)):
        return None
    return text


def default_reword_why() -> Callable[[Candidate], str | None] | None:
    """The hook the routes use: on only when the privacy layer is on and not in mock mode (mock mode has no real model)."""
    if not privacy_on() or is_mock():
        return None
    return reword_why
