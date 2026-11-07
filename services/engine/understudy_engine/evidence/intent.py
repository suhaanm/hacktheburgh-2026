"""Questions to intents (REQ-6): the worker's words are reduced to a closed intent by code, and never reach a model.

The worker's question is free text, so it cannot go into a ``SafePayload`` (it may hold a name, a title, anything), and it is
untrusted input to a language model. So code maps it to one of ten fixed intents by keyword rules, and keeps at most one number
the worker typed (a duration, such as the "14 minutes" in "why did this case take 14 minutes?"), which is compared with the
packet by code. A question with no matching rule is ``unsupported``, and the answer is a fixed sentence saying what can be
asked. This costs flexibility and buys a guarantee: the model is only ever asked about a packet and an intent.
"""
from __future__ import annotations

import re

MAX_QUESTION = 400

# first match wins; the order is the priority
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("how_sure", re.compile(r"\b(?:how (?:sure|certain|confident|reliable|accurate)|confidence|interval|margin|uncertain|how many people|sample|"
                            r"can i trust (?:the|these|this) (?:numbers?|figures?|results?|estimate)|trust the (?:numbers?|figures?)|n ?=)\b", re.I)),
    ("trust_level", re.compile(r"\b(?:trust|rung|shadow|autonom|a[123]\b|earned|approval|promot|ladder)", re.I)),
    ("routine_worth", re.compile(r"\b(?:routine|automat|worth|background|repetit|repeat)", re.I)),
    ("stuck_reading", re.compile(r"\b(?:stuck|hazard|confus|nudge|alarm|struggl|coach (?:decide|say|speak|stay)|why (?:did|was) the coach)", re.I)),
    ("what_to_practise", re.compile(r"\b(?:practi[sc]e|improve|get better|coach me|what should i|advice|tips?|focus on|work on|next step|fix first)", re.I)),
    ("biggest_habit", re.compile(r"\b(?:biggest|largest|main|top|worst|most (?:of )?(?:my |the )?(?:time|loss|lost)|greatest)\b", re.I)),
    ("compare_expert", re.compile(r"\b(?:expert|compare|compared|comparison|nearest|reference|colleague|benchmark|versus|vs\b)", re.I)),
    ("why_slow", re.compile(r"\bwhy\b|\b(?:so (?:long|slow)|slow(?:er)?|took|take[sn]?|long)\b", re.I)),
    ("where_time_went", re.compile(r"\b(?:where|what happened|summary|summari[sz]e|explain|today|time went|breakdown|overview|how did)", re.I)),
]


def clean(question: str | None) -> str:
    q = "".join(ch for ch in (question or "") if ch.isprintable() or ch in " \t")
    return re.sub(r"\s+", " ", q).strip()[:MAX_QUESTION]


def classify(question: str | None) -> tuple[str, float | None]:
    """``(intent, asked_s)``. No question means the default intent, ``where_time_went``. ``asked_s`` is the first duration the
    worker wrote, in seconds (or None); it is a number the worker typed, so it is quoted back only as itself."""
    q = clean(question)
    if not q:
        return "where_time_went", None
    asked = None
    from .provenance import extract_mentions          # local import: provenance imports this package's modules

    for m in extract_mentions(q):
        if m.kind == "num" and m.is_time:
            asked = round(m.denoted(), 1)
            break
    for intent, rx in _RULES:
        if rx.search(q):
            return intent, asked
    return "unsupported", asked


def supported_text() -> str:
    """The fixed sentence that says what can be asked (used when the question matches no rule). Under the reply's 320-character limit."""
    return ("You can ask where your time went, why a case took as long as it did, the biggest habit, how you compare with the nearest "
            "expert, the stuck reading, how sure the numbers are, or about a suggested routine and its trust.")
