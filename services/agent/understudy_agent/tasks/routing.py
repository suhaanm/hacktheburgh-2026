"""The router: which route a free-text task takes. The set is closed and CODE decides.

Routes: `answer` (a question, answered inline), `browser` (web work in the agent's own browser window), `desktop` (the real
screen: this service never clicks, it answers "show instead"), `claude_agent` (code, data and file work through the Claude
CLI), and `unclear` (one clarifying question as a card).

How it decides, in order:

1. Weighted keyword and shape rules over the worker's words give each route a score. A clear winner (score >= 2 and ahead of
   the runner-up by >= 1) is the route. No model is called for it.
2. When the rules cannot separate the routes, an OPTIONAL model may propose one value from the closed enum (`propose_route`,
   one fast-model call through the privacy ledger; skipped offline). Code accepts the proposal only if it is `answer` (the safe
   route) or the rules already found at least some evidence for that route (score >= 1). A model can break a tie; it can never
   introduce a risky route the words do not support.
3. Otherwise the route is `unclear` and the worker answers one question (a card with a button per route).

Nothing here starts anything. Every non-answer route still waits for the worker's click.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

RISKY = ("claude_agent", "desktop", "browser")
ROUTE_IDS = ("answer", "browser", "desktop", "claude_agent")

QUESTION_OPTIONS: list[dict[str, str]] = [
    {"id": "answer", "label": "Just answer it"},
    {"id": "browser", "label": "Look it up on the web"},
    {"id": "claude_agent", "label": "Work on files or code"},
    {"id": "desktop", "label": "Show me how on my screen"},
]
QUESTION_TEXT = "What should Knack do with this?"

# (pattern, weight). Patterns run on the lower-cased text.
_RULES: dict[str, list[tuple[str, float]]] = {
    "claude_agent": [
        (r"\b(code|coding|script|program|function|class|module|library|package|api|endpoint|regex|sql|query|compile|lint)\b", 1.5),
        (r"\b(python|javascript|typescript|rust|java|golang|swift|bash|shell|html|css|react|node|pandas|numpy|jupyter|notebook)\b", 1.5),
        (r"\b(refactor|debug|implement|unit tests?|test suite|bug|stack ?trace|pull request|commit|repo|repository|git|branch|merge)\b", 1.5),
        (r"\b(csv|tsv|json|xlsx?|spreadsheet|dataset|data ?frame|parquet|log files?|logs)\b", 1.5),
        (r"\b(analy[sz]e|summari[sz]e|clean up|convert|parse|transform|merge|dedupe|deduplicate|plot|chart|graph)\b.*\b(data|file|files|folder|csv|spreadsheet|table|documents?|pdfs?|rows|columns)\b", 2.0),
        (r"\b(write|create|build|make|generate|draft)\b.*\b(script|program|app|website|tool|report|document|spreadsheet|csv|file|files|code|readme|notebook|presentation|slides)\b", 2.0),
        (r"\b(rename|organi[sz]e|sort|move|copy|delete|zip|unzip)\b.*\b(files?|folders?|downloads|documents|photos|pictures)\b", 2.0),
        (r"(?:^|\s)(?:~/|/users/|\./)\S+", 1.0),
        (r"\b[\w\-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|swift|sh|md|txt|csv|json|xlsx?|pdf|docx?|html|css|ipynb)\b", 1.5),
        (r"\b(folder|directory|file|files)\b", 0.5),
    ],
    "browser": [
        (r"https?://\S+|\bwww\.\S+|\b[\w\-]+\.(?:com|org|net|io|gov\.uk|co\.uk|ac\.uk|edu|dev|app)\b", 2.0),
        (r"\b(search|google|look up|lookup|find out|research|browse|check)\b.*\b(online|web|website|internet|site|page|news|price|prices|reviews?)\b", 2.5),
        (r"\b(search the web|search online|on the web|on the internet|go to|open the website|visit)\b", 2.5),
        (r"\b(website|web page|webpage|web site|browser|link|url|online)\b", 1.0),
        (r"\b(flights?|trains?|hotels?|tickets?|weather|forecast|cheapest|compare prices?|in stock|opening hours|reviews?|news)\b", 1.0),
        (r"\b(book|order|buy|purchase|pay|checkout|subscribe)\b", 0.5),
    ],
    "desktop": [
        (r"\b(click|double[- ]click|right[- ]click|drag|scroll|tap|press the|hit the)\b", 2.0),
        (r"\b(on my screen|on the screen|my screen|my desktop|my mac|my computer|in the app|in finder|in the dock|menu bar|system settings)\b", 2.0),
        (r"\b(open|launch|quit|close|switch to)\b.*\b(app|application|finder|safari|chrome|firefox|outlook|excel|word|powerpoint|slack|teams|zoom|notes|calendar|mail|messages|preview|terminal)\b", 2.5),
        (r"\b(type|fill in|fill out|enter)\b.*\b(into|in)\b.*\b(field|form|box|window|cell|app)\b", 2.0),
        (r"\b(window|tab|button|dialog|popup|pop-up|cursor|mouse|keyboard shortcut|menu)\b", 1.0),
    ],
    "answer": [
        (r"^\s*(what|why|how|when|who|whom|whose|where|which|is|are|was|were)\b", 1.5),
        (r"^\s*(do|does|did|can|could|should|would|will|am)\s+(i|you|we|they|he|she|it|there|this|that)\b", 1.5),
        (r"\?\s*$", 1.5),
        (r"\b(explain|define|tell me|remind me|what's|whats|how do i|how does|how to|difference between|meaning of|translate|convert \d|what time|what day|what date)\b", 2.0),
        (r"\b(opinion|advice|ideas?|suggest|recommend|brainstorm|pros and cons)\b", 1.0),
    ],
}
_RULES_C = {r: [(re.compile(p, re.I | re.S), w) for p, w in rules] for r, rules in _RULES.items()}


@dataclass(frozen=True)
class RouteDecision:
    route: str
    scores: dict[str, float]
    how: str                       # "rules" | "model" | "ask"
    options: list[dict[str, str]] = field(default_factory=list)


def score_routes(text: str) -> dict[str, float]:
    t = " ".join((text or "").split())
    out = {r: 0.0 for r in ROUTE_IDS}
    for route, rules in _RULES_C.items():
        for rx, w in rules:
            if rx.search(t):
                out[route] += w
    # A real instruction to act on something is not a question: an action route that has evidence beats a bare question mark.
    return out


def decide_by_rules(text: str) -> tuple[str | None, dict[str, float]]:
    s = score_routes(text)
    ranked = sorted(s.items(), key=lambda kv: (-kv[1], kv[0]))
    (r1, s1), (_, s2) = ranked[0], ranked[1]
    if s1 >= 2.0 and s1 - s2 >= 1.0:
        return r1, s
    # A plain question with no evidence at all for an action route is answered: the safe route. Anything else is not guessed.
    if s["answer"] >= 1.5 and all(s[r] < 1.0 for r in RISKY):
        return "answer", s
    return None, s


PROPOSE_SCHEMA: dict[str, Any] = {
    "title": "task_route",
    "type": "object",
    "required": ["route"],
    "additionalProperties": False,
    "properties": {"route": {"type": "string", "enum": list(ROUTE_IDS) + ["unclear"]}},
}
PROPOSE_SYSTEM = (
    "Pick how an assistant should handle the user's request. Reply with JSON {\"route\": one of: answer (a question to "
    "answer in words), browser (work on web pages), desktop (operate apps on the user's screen), claude_agent (write code, "
    "analyse data, create or change files), unclear (you cannot tell)}. Choose unclear rather than guess."
)


def propose_route(text: str, port: Any) -> str | None:
    """One closed-enum proposal from the fast model. Any failure is None (the router then asks)."""
    try:
        out = port.check(PROPOSE_SYSTEM + "\n\nRequest:\n" + text[:1500], PROPOSE_SCHEMA)
    except Exception:  # noqa: BLE001 - a proposal is optional; the router never depends on it
        return None
    r = out.get("route") if isinstance(out, dict) else None
    return r if r in ROUTE_IDS or r == "unclear" else None


def choose_route(text: str, *, port_factory: Callable[[], Any] | None = None, offline: bool = False) -> RouteDecision:
    route, scores = decide_by_rules(text)
    if route is not None:
        return RouteDecision(route, scores, "rules")
    if port_factory is not None and not offline and any(v > 0 for v in scores.values()):
        try:
            proposed = propose_route(text, port_factory())
        except Exception:  # noqa: BLE001
            proposed = None
        if proposed in ROUTE_IDS and (proposed == "answer" or scores.get(proposed, 0.0) >= 1.0):
            return RouteDecision(proposed, scores, "model")
    return RouteDecision("unclear", scores, "ask", options=[dict(o) for o in QUESTION_OPTIONS])


# --------------------------------------------------------------------------------------------- where a task works
_PLACE = re.compile(r"""(?:^|[\s"'(])(~/[^\s"')]*|/Users/[^/\s"']+(?:/[^\s"')]*)?|/Volumes/[^/\s"']+(?:/[^\s"')]*)?)""")


def extract_place(text: str, home: Path | None = None) -> Path | None:
    """A folder the worker named (`~/Projects/x` or an absolute path under /Users or /Volumes) that exists. A named file means
    its folder. Never the filesystem root. None when nothing existing is named: the task then gets its own folder."""
    h = home or Path.home()
    for m in _PLACE.finditer(text or ""):
        raw = m.group(1).rstrip(".,;:!?")
        try:
            p = Path(raw.replace("~", str(h), 1) if raw.startswith("~") else raw).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if p.is_file():
            p = p.parent
        if p.is_dir() and p != Path("/") and len(p.parts) >= 3:
            return p
    return None


_SLUG_STOP = frozenset("a an the to of for and or in on at my this that please can you could would me i we it with from into do make create write build".split())


def make_slug(text: str, taken: set[str] | None = None) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _SLUG_STOP][:4]
    base = "-".join(words)[:32].strip("-") or "task"
    import secrets

    for _ in range(20):
        slug = f"{base}-{secrets.token_hex(2)}"
        if not taken or slug not in taken:
            return slug
    return f"{base}-{secrets.token_hex(4)}"
