"""The deterministic fallback: keyword and diffstat rules (LOC-1, used when no model is present, in mock mode and in tests).

No model, no network, no randomness. The same input always gives the same digest. These are plain heuristics a
developer would write in an afternoon; the evaluation reports how far they get against planted labels and what the
model adds (or does not).
"""
from __future__ import annotations

import re
from typing import Any

from .schemas import (
    CommitItem,
    EventItem,
    is_chore_path,
    is_doc_path,
    is_test_path,
    normalise_commit,
    normalise_event,
)

# ------------------------------------------------------------------------------------------------------------ commits
_CONVENTIONAL = re.compile(r"^\s*(?P<type>[a-z]+)(\([^)]*\))?(?P<bang>!)?\s*:\s*", re.IGNORECASE)
_PREFIX_MAP = {
    "feat": "feature", "feature": "feature", "add": "feature",
    "fix": "fix", "bugfix": "fix", "hotfix": "fix",
    "refactor": "refactor", "refact": "refactor", "cleanup": "refactor", "clean": "refactor",
    "test": "test", "tests": "test",
    "docs": "docs", "doc": "docs", "readme": "docs",
    "chore": "chore", "ci": "chore", "build": "chore", "deps": "chore", "style": "chore", "release": "chore", "bump": "chore",
    "revert": "revert", "perf": "other",
}
_REVERT = re.compile(r"^\s*(revert\b|this reverts commit|back out\b|backed out\b|roll ?back\b|undo\b)", re.IGNORECASE)
_KW = (
    ("fix", re.compile(r"\b(fix(es|ed|ing)?|bug|crash(es|ed|ing)?|error|regression|resolve[sd]?|patch(ed)?|broken|wrong|incorrect|"
                       r"repair|prevent|avoid|workaround|no longer|stop(s)? (it|the|from)|handle[sd]?|guard against|null|off-by-one|leak)\b", re.I)),
    ("refactor", re.compile(r"\b(refactor(ed|ing)?|rename[sd]?|clean ?up|simplif(y|ied)|extract(ed)?|restructure[sd]?|reorgani[sz]e[sd]?|"
                            r"dedupe|deduplicate|tidy|move[sd]? \S+ (to|into)|split (up )?\S+|inline|consolidate|decouple)\b", re.I)),
    ("test", re.compile(r"\b(tests?|specs?|coverage|fixture[s]?|mock[s]?|e2e|flaky)\b", re.I)),
    ("docs", re.compile(r"\b(docs?|documentation|readme|comment[s]?|typo[s]?|changelog|docstring[s]?|tutorial|guide)\b", re.I)),
    ("chore", re.compile(r"\b(bump|upgrade[sd]?|dependenc(y|ies)|deps|lint(er|ing)?|format(ting)?|version|release|merge|"
                         r"gitignore|ci|pipeline|config(uration)?|lockfile|pin(ned)?)\b", re.I)),
    ("feature", re.compile(r"\b(add(s|ed|ing)?|implement(s|ed|ing)?|introduce[sd]?|support(s|ed|ing)?|new|feature|enable[sd]?|allow(s|ed)?|"
                           r"let(s)? (users?|the)|create[sd]?|wire up|expose[sd]?|ship)\b", re.I)),
)
_SENSITIVE_PATH = re.compile(
    r"auth|login|password|passwd|secret|token|credential|crypto|payment|billing|invoice|migrat|\.sql$|terraform|infra|deploy|"
    r"k8s|kubernetes|helm|prod(uction)?[/_.-]|permission|acl\b|security|oauth|session|\.github/workflows|release|iam\b",
    re.IGNORECASE,
)
_RISKY_WORDS = re.compile(
    r"\b(security|vuln(erability)?|cve|prod(uction)?|hotfix|migration|breaking|drop (table|column)|force[- ]push|disable[sd]? "
    r"(the )?(check|auth|validation|limit|rate|ssl|tls|verification|signature)|bypass|skip(ped)? (the )?(check|auth|validation)|"
    r"credentials?|secrets?|rotate|permissions?|delete[sd]? (all|the)|rollback|downtime|data loss)\b",
    re.IGNORECASE,
)
_VAGUE_EXACT = {
    "wip", "update", "updates", "fix", "fixes", "fixed", "stuff", "changes", "misc", "tmp", "test", "tests", "asdf", ".", "..",
    "more", "minor", "minor changes", "small changes", "cleanup", "oops", "typo", "ok", "done", "work", "commit", "save",
    "update stuff", "misc fixes", "fix stuff", "more work", "wip commit", "final", "final fix", "address comments",
    "address review comments", "review comments", "pr feedback", "various fixes", "fix things", "some changes", "tweaks",
}
_RATIONALE = re.compile(r"\b(because|so that|so we|in order to|to avoid|to prevent|to ensure|instead of|rather than|since|otherwise|"
                        r"which (caused|means|led)|caused by|due to|previously|before this|this (way|means)|as a result|why|fixes #\d+|"
                        r"closes #\d+|was (causing|returning|dropping|failing))\b", re.IGNORECASE)


def _subject(message: str) -> str:
    return next((ln.strip() for ln in message.splitlines() if ln.strip()), "")


def is_revert_like(c: CommitItem) -> bool:
    """True when the message itself says it undoes something (git's own wording or a plain "back out")."""
    return bool(_REVERT.match(_subject(c.clean))) or "this reverts commit" in c.message.lower()


def commit_category(c: CommitItem) -> str:
    subject = _subject(c.clean)
    if _REVERT.match(subject):
        return "revert"
    m = _CONVENTIONAL.match(subject)
    if m and m.group("type").lower() in _PREFIX_MAP:
        return _PREFIX_MAP[m.group("type").lower()]
    paths = c.paths
    if paths:
        if all(is_test_path(p) for p in paths):
            return "test"
        if all(is_doc_path(p) for p in paths):
            return "docs"
        if all(is_chore_path(p) or is_doc_path(p) for p in paths) and not all(is_doc_path(p) for p in paths):
            return "chore"
    for name, rx in _KW:
        if rx.search(subject):
            return name
    for name, rx in _KW:                                   # body text, weaker evidence
        if rx.search(c.clean):
            return name
    return "other"


def commit_risk(c: CommitItem, category: str) -> str:
    size = c.facts()["size_bucket"]
    if category == "revert" or size == "huge":
        return "high"
    if any(_SENSITIVE_PATH.search(p) for p in c.paths) or _RISKY_WORDS.search(c.clean):
        return "high"
    if category in ("docs", "test", "chore") and size in ("tiny", "small"):
        return "low"
    if size == "tiny":
        return "low"
    if category in ("docs", "test", "chore"):
        return "medium" if size in ("large",) else "low"
    return "medium"


def commit_message_quality(c: CommitItem) -> str:
    msg = c.clean
    subject = _subject(msg)
    low = re.sub(r"[^a-z0-9 ]+", "", subject.lower()).strip()
    words = low.split()
    if _REVERT.match(subject) and len(words) >= 2:          # git writes these itself: fine, but says nothing of why
        return "clear" if _RATIONALE.search(msg) else "ok"
    if not words or low in _VAGUE_EXACT or len(words) <= 2 and not _CONVENTIONAL.match(subject):
        return "vague"
    if len(subject) < 12:
        return "vague"
    body = msg[len(subject):].strip()
    if len(body) >= 40 or _RATIONALE.search(msg) or len(words) >= 12:
        return "clear"
    return "ok"


def digest_commit(item: Any, category: str | None = None) -> dict[str, Any]:
    """``category`` lets a caller whose category came from elsewhere (the model) get risk computed from that category."""
    c = normalise_commit(item)
    cat = category or commit_category(c)
    facts = c.facts()
    if not c.paths and re.search(r"\b(tests?|spec)\b", c.clean, re.I):
        facts["touches_tests"] = True
    return {
        "category": cat,
        "size_bucket": facts["size_bucket"],
        "touches_tests": bool(facts["touches_tests"]),
        "risk": commit_risk(c, cat),
        "message_quality": commit_message_quality(c),
    }


# ------------------------------------------------------------------------------------------------------------ events
_E_TRAVEL = re.compile(r"\b(flight|fly(ing)?|train to|train from|commute|travel(ling|ing)?|airport|transit|drive to|taxi|"
                       r"transfer to|ferry|journey|trip to|layover|boarding)\b", re.I)
_E_FOCUS = re.compile(r"\b(focus|deep work|heads[- ]down|no meetings?|do not book|dnd|writing time|thinking time|coding block|"
                      r"make time|maker time|quiet time|work block|hold for work|catch-?up on (work|email))\b", re.I)
_E_SOCIAL = re.compile(r"\b(lunch|coffee|drinks|pub|happy hour|birthday|party|social|quiz|games?|dinner|breakfast|"
                       r"celebrat\w+|farewell|leaving do|cake|picnic|bbq|team building|offsite fun|karaoke|walk)\b", re.I)
_E_ADMIN = re.compile(r"\b(expenses?|timesheets?|admin|inbox|email triage|paperwork|training|compliance|enrol(l)?ment|payroll|"
                      r"hr\b|onboarding checklist|invoice[s]?|receipts?|approvals?|budget submission|weekly planning|plan my week|"
                      r"mandatory|policy|appraisal form|benefits|tax)\b", re.I)
_E_EXTERNAL = re.compile(r"\b(client|customer|vendor|supplier|partner|prospect|candidate|interview|sales|discovery call|"
                         r"investor|external|agency|contractor|demo for|onsite with|reseller|procurement)\b", re.I)
_E_REVIEW = re.compile(r"\b(review|post-?mortem|post-?incident|demo|walk-?through|show and tell|critique|"
                       r"audit|sign-?off|qa session|design crit|architecture board|steering)\b", re.I)
_E_TEAM = re.compile(r"\b(stand-?up|sync|retro(spective)?|all[- ]hands|town ?hall|planning|sprint|team meeting|weekly|kick-?off|roadmap|"
                     r"leads|guild|huddle|scrum|refinement|grooming|offsite|summit|brown ?bag)\b", re.I)
_E_ONE = re.compile(r"(\b1[:\-/ ]?1\b|one[- ]on[- ]one|1-2-1|skip[- ]level|check-?in with|catch-?up with|mentor(ing|ship)?\b|"
                    r"career chat|coaching)", re.I)
_E_UNKNOWN_TITLES = {"meeting", "call", "hold", "tbd", "busy", "block", "sync", "catch up", "catchup", "catch-up", "chat", "event",
                     "appointment", "private appointment", "tentative", "?", "", "no title", "(no title)", "untitled", "placeholder"}
_E_PREP = re.compile(r"\b(demo|present(ation)?|pitch|interview|workshop|kick-?off|proposal|review|board|planning|prep|"
                     r"discovery|steering|budget|roadmap|audit|sign-?off|investor|quarterly)\b", re.I)


def event_category(e: EventItem) -> str:
    title = e.title.strip()
    low = title.lower()
    if low in _E_UNKNOWN_TITLES:
        return "unknown"
    if _E_TRAVEL.search(title):
        return "travel"
    if _E_FOCUS.search(title) and e.attendee_count <= 1:
        return "focus"
    if _E_EXTERNAL.search(title):
        return "external"
    if _E_ONE.search(title):
        return "one_to_one"
    if _E_REVIEW.search(title):
        return "review"
    if _E_SOCIAL.search(title):
        return "social"
    if _E_ADMIN.search(title):
        return "admin"
    if _E_TEAM.search(title):
        return "team_meeting"
    if _E_FOCUS.search(title):
        return "focus"
    if e.attendee_count == 2:
        return "one_to_one"
    if e.attendee_count >= 5:
        return "team_meeting"
    if e.attendee_count <= 1 and (e.duration_min or 0) >= 60:
        return "focus"
    return "unknown"


def event_needs_prep(e: EventItem, category: str) -> bool:
    if category in ("focus", "social", "travel", "unknown", "admin"):
        return False
    if category in ("review", "external"):
        return True
    return bool(_E_PREP.search(e.title))


def digest_event(item: Any, category: str | None = None) -> dict[str, Any]:
    e = normalise_event(item)
    cat = category or event_category(e)
    facts = e.facts()
    return {
        "category": cat,
        "recurring": facts["recurring"],
        "duration_bucket": facts["duration_bucket"],
        "attendee_bucket": facts["attendee_bucket"],
        "needs_prep": event_needs_prep(e, cat),
    }
