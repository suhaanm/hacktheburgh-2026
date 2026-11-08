"""Words and enums for the repeated-work hit list. Everything here is fixed by code: no model writes a label, a key phrase or a sentence.

* ``stops_before``: the irreversible or outward step an automation would stop at, one of ``STOPS``. Worked out from the pack's own
  ``never`` list for a matched routine, else from the steps in the sequence. Never a raw string from the screen.
* ``family``: the kind of work a row is mostly made of (``FAMILIES``), which picks the small glyph on the page.
* ``label`` and ``key``: plain words in the role pack's vocabulary. A matched routine uses the pack template's own title; an
  unmatched one is spelled from its steps. ``key`` is the part the page prints in bold and is always a piece of ``label``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

STOPS = ("none", "submit", "payment", "message", "delete", "share", "release")
STATUSES = ("candidate", "proposed", "learning", "running", "automated")
FAMILIES = ("open", "read", "enter", "copy", "check", "run", "search", "step")
HELD_REASONS = ("irreversible_first_step", "judgement", "unstable", "denylist")
STATES = ("ok", "new_user", "too_little_data", "nothing_repeats", "all_handled", "counting_again", "capture_off")

# Worst first: when a routine's ``never`` list mixes classes, the most serious one is what it stops before.
_RISK_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("payment", frozenset({"pay", "payment", "payments", "approve", "issue", "refund", "transfer"})),
    ("delete", frozenset({"delete", "overwrite", "remove", "erase", "drop", "truncate", "purge"})),
    ("release", frozenset({"merge", "deploy", "release", "push"})),
    ("submit", frozenset({"submit", "close", "sign", "finalise", "finalize"})),
    ("message", frozenset({"send", "email", "letter", "notify", "message", "reply", "comment"})),
    ("share", frozenset({"export", "share", "upload", "publish", "post", "print", "download"})),
)
_SEVERITY = {name: i for i, (name, _) in enumerate(_RISK_RULES)}
_WORD = re.compile(r"[a-z]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(str(text).lower())


def classify_phrase(text: str) -> str | None:
    """The most serious stop class a phrase names (``"submit to claimant record"`` is ``submit``), or None."""
    toks = set(_tokens(text))
    for name, words in _RISK_RULES:
        if toks & words:
            return name
    return None


def worst(classes: Iterable[str | None]) -> str:
    seen = [c for c in classes if c in _SEVERITY]
    return min(seen, key=lambda c: _SEVERITY[c]) if seen else "none"


def stops_for_never(never: Iterable[str]) -> str:
    return worst(classify_phrase(n) for n in never)


def step_risk(cog: str) -> str | None:
    """Does a single step of a sequence (a cog id such as ``EXPORT_RESULT``) look irreversible or outward?"""
    return classify_phrase(cog.replace("_", " "))


# ----------------------------------------------------------------------------------------------- families
_FAMILY_WORDS: tuple[tuple[str, frozenset[str]], ...] = (
    ("copy", frozenset({"copy", "paste", "clipboard", "export"})),
    ("enter", frozenset({"enter", "type", "fill", "write", "edit", "input", "commit"})),
    ("read", frozenset({"read", "inspect", "view", "profile", "trace", "look"})),
    ("open", frozenset({"navigate", "open", "goto", "load", "switch", "tab"})),
    ("check", frozenset({"check", "compare", "reconcile", "verify", "review", "decide", "probe"})),
    ("run", frozenset({"run", "plot", "query", "test", "tests", "group", "agg"})),
    ("search", frozenset({"search", "reformulate", "find", "lookup"})),
)
_FAMILY_OF_WORD = {w: fam for fam, words in _FAMILY_WORDS for w in words}


def family_of(cog: str) -> str:
    """The family of one step: the first word of its id that names a kind of work (``COPY_TO_NOTE`` is ``copy``)."""
    for w in _tokens(cog.replace("_", " ")):
        if w in _FAMILY_OF_WORD:
            return _FAMILY_OF_WORD[w]
    return "step"


def family_signature(seq: Sequence[str]) -> tuple[str, ...]:
    """The sequence as kinds of work, repeats collapsed: two tools that do the same job in the same order share one signature."""
    out: list[str] = []
    for c in seq:
        f = family_of(c)
        if not out or out[-1] != f:
            out.append(f)
    return tuple(out)


def dominant_family(seq: Sequence[str]) -> str:
    counts: dict[str, int] = {}
    for c in seq:
        f = family_of(c)
        counts[f] = counts.get(f, 0) + 1
    named = {f: n for f, n in counts.items() if f != "step"}
    pool = named or counts
    if not pool:
        return "step"
    best = max(pool.values())
    return next(f for f in FAMILIES if pool.get(f) == best)


# ----------------------------------------------------------------------------------------------- labels
# (key phrase, family) for the pack templates we ship. The key is the thing being worked on, printed in bold. Each key is a piece
# of the template title (a test checks this). An unknown template falls back to ``derive_key``.
TEMPLATE_STYLE: dict[str, tuple[str, str]] = {
    "calc-entry-3x": ("household", "enter"),
    "case-note-copy": ("agreed results", "copy"),
    "cliff-recheck": ("cliff edges", "check"),
    "queue-sweep": ("case queue", "check"),
    "weekly-report": ("weekly caseload report", "copy"),
    "weekly-metric-refresh": ("weekly metrics sheet", "run"),
    "rerun-failed-ci": ("failed CI job", "run"),
    # the role-depth templates (RD, 7 Nov 2026)
    "open-pr-from-branch": ("pull request", "open"), "ci-status-sweep": ("CI", "read"), "review-queue-triage": ("review requests", "check"),
    "post-release-watch": ("logs", "read"), "rollback-after-alert": ("release alert", "check"), "profile-and-note-hot-path": ("slow endpoint", "run"),
    "bisect-regression-range": ("good and a bad commit", "run"), "reply-to-review-comments": ("review comments", "enter"),
    "migration-dry-run": ("migration", "run"), "add-failure-log-line": ("log line", "enter"), "dependency-bump-pr": ("dependency", "enter"),
    "docs-lookup-and-apply": ("same API", "search"),
    "reload-and-reprofile": ("dataset", "read"), "parameterised-weekly-query": ("saved query", "run"), "reconcile-and-note-gap": ("control", "check"),
    "join-check-and-count": ("two tables", "check"), "segment-breakdown-chart": ("segment", "run"), "magnitude-and-units-check": ("scale and units", "check"),
    "interval-for-a-rate": ("interval", "run"), "notebook-restart-and-run": ("notebook", "run"), "draft-metric-definition": ("metric definition", "enter"),
    "send-peer-check": ("second check", "check"), "schedule-refresh-with-alert": ("refresh", "run"), "send-weekly-extract": ("weekly extract", "copy"),
}
_ARTICLES = frozenset({"the", "a", "an", "all", "each", "every", "your", "this", "that"})


def derive_key(title: str) -> str | None:
    """After the opening verb and any articles, the next one or two words ("Refresh the weekly metrics sheet" gives "weekly metrics")."""
    words = title.split()
    rest = words[1:]
    while rest and rest[0].lower() in _ARTICLES:
        rest = rest[1:]
    if not rest:
        return None
    key = " ".join(rest[:2]).strip(" ,.;:")
    return key if key and key.lower() in title.lower() else None


def _words(cog: str) -> str:
    return cog.replace("_", " ").lower()


def label_for(template: dict | None, signature: Sequence[str]) -> tuple[str, str | None, str]:
    """``(label, key, family)``. A matched routine uses the pack's own title; an unmatched one is spelled from its first steps."""
    if template:
        title = str(template["title"])
        key, fam = TEMPLATE_STYLE.get(str(template["id"]), (None, None))
        if key is None or key.lower() not in title.lower():
            key = derive_key(title)
        return title, key, fam or dominant_family(signature)
    steps: list[str] = []
    for c in signature:
        w = _words(c)
        if w not in steps:
            steps.append(w)
    first = steps[:3]
    if not first:
        return "Repeated steps", None, "step"
    if len(steps) > 3:
        text = ", ".join(first) + " and more"
    elif len(first) == 1:
        text = first[0]
    else:
        text = ", ".join(first[:-1]) + " and " + first[-1]
    return text[:1].upper() + text[1:], first[0][:1].upper() + first[0][1:], dominant_family(signature)


# ----------------------------------------------------------------------------------------------- sentences (fixed text)
def sentence_new_user() -> str:
    return "Nothing to count yet. Work as you normally do, and when the same steps come up three times they will appear here."


def sentence_too_little(n_cases: int, window_days: int) -> str:
    base = f"Only {n_cases} {'case' if n_cases == 1 else 'cases'} in the last {window_days} days, too few to tell what repeats."
    return base + (" Try the 30 day view, or check back after a few more working days." if window_days < 30 else " Check back after a few more working days.")


def sentence_nothing(window_days: int) -> str:
    return f"Nothing has repeated three times in the last {window_days} days in a way that could be automated."


def sentence_all_handled() -> str:
    return "Everything that repeats is already handled, hidden, or needs your judgement."


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def human_date(iso_date: str) -> str:
    """``2026-11-07`` as ``7 November``. Anything that is not a date comes back as it was."""
    try:
        y, m, d = (int(x) for x in iso_date[:10].split("-"))
        return f"{d} {_MONTHS[m - 1]}"
    except (ValueError, IndexError):
        return iso_date


def sentence_counting_again(since: str) -> str:
    return f"Counting again since {human_date(since)}. Rows come back when the same steps repeat three times."


def sentence_capture_off() -> str:
    return "Capture is off, so nothing is being counted. Turn it on in your memory file, under Preferences, if you want this list."


def note_meta(origin: str) -> str:
    return ("Counts come from this device's own record of your work. Minutes are estimates with a 95% interval. "
            "Nothing runs unless you press Automate."
            + (" Built from synthetic data." if origin != "real" else ""))
