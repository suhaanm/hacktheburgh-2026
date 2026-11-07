"""Fixed vocabularies, JSON schemas, input normalisation and the facts that code (not the model) computes (LOC-2).

A digest holds only enums, booleans and numbers from these vocabularies. Free text never leaves this module in an output.
Fields that are pure functions of the input (size, tests touched, duration, attendee count, recurrence) are computed by
code in every path; the model only decides what needs reading: category, risk and message quality for a commit, category
and whether preparation is needed for a calendar entry.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

# ------------------------------------------------------------------------------------------------------- vocabularies
COMMIT_CATEGORIES = ("feature", "fix", "refactor", "test", "docs", "chore", "revert", "other")
SIZE_BUCKETS = ("tiny", "small", "medium", "large", "huge")
RISKS = ("low", "medium", "high")
MESSAGE_QUALITIES = ("vague", "ok", "clear")

EVENT_CATEGORIES = ("one_to_one", "team_meeting", "review", "focus", "social", "admin", "external", "travel", "unknown")
DURATION_BUCKETS = ("lt30", "30to59", "60to89", "90to179", "180plus", "allday")
ATTENDEE_BUCKETS = ("lt5", "5to9", "10plus")

COMMIT_KEYS = ("category", "size_bucket", "touches_tests", "risk", "message_quality")
EVENT_KEYS = ("category", "recurring", "duration_bucket", "attendee_bucket", "needs_prep")

# What the model is asked for (the rest is computed by code).
COMMIT_MODEL_KEYS = ("category", "risk", "message_quality")
EVENT_MODEL_KEYS = ("category", "needs_prep")

COMMIT_VOCAB: dict[str, tuple[str, ...]] = {
    "category": COMMIT_CATEGORIES, "size_bucket": SIZE_BUCKETS, "risk": RISKS, "message_quality": MESSAGE_QUALITIES,
}
EVENT_VOCAB: dict[str, tuple[str, ...]] = {
    "category": EVENT_CATEGORIES, "duration_bucket": DURATION_BUCKETS, "attendee_bucket": ATTENDEE_BUCKETS,
}

COMMIT_MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(COMMIT_CATEGORIES)},
        "risk": {"type": "string", "enum": list(RISKS)},
        "message_quality": {"type": "string", "enum": list(MESSAGE_QUALITIES)},
    },
    "required": list(COMMIT_MODEL_KEYS),
    "additionalProperties": False,
}
EVENT_MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(EVENT_CATEGORIES)},
        "needs_prep": {"type": "boolean"},
    },
    "required": list(EVENT_MODEL_KEYS),
    "additionalProperties": False,
}

def schema_for(task: str, fields: Sequence[str]) -> dict[str, Any]:
    """The JSON schema for a subset of the model's fields, in the task's field order."""
    full = COMMIT_MODEL_SCHEMA if task == "commit_digest" else EVENT_MODEL_SCHEMA
    order = [k for k in full["properties"] if k in fields]
    return {"type": "object", "properties": {k: full["properties"][k] for k in order}, "required": order, "additionalProperties": False}


# ----------------------------------------------------------------------------------------------------- code-computed facts
_TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|specs?|e2e|testing|fixtures?)/|(^|/)test_[^/]*$|_test\.[a-z0-9]+$|\.(test|spec)\.[a-z0-9]+$|"
    r"(^|/)conftest\.py$|Tests?\.(java|kt|cs|swift)$|_spec\.rb$",
    re.IGNORECASE,
)
_DOC_PATH = re.compile(r"(^|/)(docs?|documentation)/|\.(md|mdx|rst|adoc|txt)$|(^|/)(readme|changelog|license|contributing)[^/]*$", re.IGNORECASE)
_CHORE_PATH = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|uv\.lock|poetry\.lock|Cargo\.lock|go\.sum|Gemfile\.lock)$|"
    r"(^|/)\.github/|(^|/)\.(gitignore|editorconfig|prettierrc[^/]*|eslintrc[^/]*|pre-commit-config\.yaml)$|"
    r"(^|/)(Makefile|Dockerfile|renovate\.json|dependabot\.yml)$",
    re.IGNORECASE,
)


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path.replace("\\", "/")))


def is_doc_path(path: str) -> bool:
    return bool(_DOC_PATH.search(path.replace("\\", "/")))


def is_chore_path(path: str) -> bool:
    return bool(_CHORE_PATH.search(path.replace("\\", "/")))


def size_bucket(lines_changed: int | None) -> str:
    """tiny <= 10 lines, small <= 50, medium <= 250, large <= 1000, huge above (additions plus deletions)."""
    if lines_changed is None:
        return "small"
    n = max(0, int(lines_changed))
    if n <= 10:
        return "tiny"
    if n <= 50:
        return "small"
    if n <= 250:
        return "medium"
    if n <= 1000:
        return "large"
    return "huge"


def duration_bucket(minutes: float | None, all_day: bool = False) -> str:
    if all_day:
        return "allday"
    if minutes is None:
        return "30to59"
    m = max(0.0, float(minutes))
    if m >= 24 * 60:
        return "allday"
    if m < 30:
        return "lt30"
    if m < 60:
        return "30to59"
    if m < 90:
        return "60to89"
    if m < 180:
        return "90to179"
    return "180plus"


def attendee_bucket(count: int | None) -> str:
    n = max(0, int(count or 0))
    if n < 5:
        return "lt5"
    if n < 10:
        return "5to9"
    return "10plus"


# ----------------------------------------------------------------------------------------------------- commit input
@dataclass(frozen=True)
class CommitItem:
    message: str
    paths: tuple[str, ...] = ()
    additions: int | None = None
    deletions: int | None = None
    files_changed: int | None = None
    has_stat: bool = False

    @property
    def clean(self) -> str:
        return clean_message(self.message)

    @property
    def lines_changed(self) -> int | None:
        if self.additions is None and self.deletions is None:
            return None
        return (self.additions or 0) + (self.deletions or 0)

    @property
    def touches_tests(self) -> bool:
        if self.paths:
            return any(is_test_path(p) for p in self.paths)
        return False

    def facts(self) -> dict[str, Any]:
        """The two output fields code computes itself."""
        return {"size_bucket": size_bucket(self.lines_changed), "touches_tests": self.touches_tests}


_TRAILER = re.compile(r"^\s*(co-authored-by|signed-off-by|reviewed-by|reported-by|acked-by|tested-by|suggested-by|cc|change-id)\s*:.*$", re.I | re.M)
_THANKS = re.compile(r"^\s*(thanks|thank you|h/t|hat tip|credit)\b.*$", re.I | re.M)
_URL = re.compile(r"\b(https?|ftp)://\S+|\bwww\.\S+", re.I)
_EMAILISH = re.compile(r"<?[\w.+-]+@[\w-]+(\.[\w-]+)+>?")
_TICKET_PREFIX = re.compile(r"^\s*\[?[A-Z][A-Z0-9]{1,9}-\d{1,6}\]?\s*[:\-]?\s*")
_REPORTED_BY = re.compile(r"\s*\((reported|requested|suggested|asked) (by|for)[^)]*\)", re.I)
_PATHISH = re.compile(r"\s*\((/[^)\s]+|[A-Za-z]:\\[^)]+|~/[^)]+)\)")


def clean_message(msg: str) -> str:
    """The message minus boilerplate that says nothing about the change: trailers (Co-authored-by, Signed-off-by ...), thanks
    lines, links, e-mail addresses, a leading ticket id, "(reported by ...)" and a parenthesised path. The same text goes to the
    rules and to the model, which also means the model never sees the names and addresses in trailers."""
    t = _TRAILER.sub("", msg)
    t = _THANKS.sub("", t)
    t = _URL.sub("", t)
    t = re.sub(r"^\s*(see|link|ref|refs|via|details)\s*:?\s*$", "", t, flags=re.I | re.M)
    t = _EMAILISH.sub("", t)
    t = _REPORTED_BY.sub("", t)
    t = _PATHISH.sub("", t)
    lines = [ln.rstrip() for ln in t.splitlines()]
    t = "\n".join(lines).strip()
    t = _TICKET_PREFIX.sub("", t, count=1).strip() if _TICKET_PREFIX.match(t) and len(_TICKET_PREFIX.sub("", t, count=1).strip()) >= 3 else t
    return re.sub(r"\n{3,}", "\n\n", t)


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return None


def _pick(d: Mapping[str, Any], *names: str) -> Any:
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def parse_numstat(text: str) -> list[tuple[str, int, int]]:
    """``git log --numstat`` lines: ``added<TAB>deleted<TAB>path`` (``-`` for binary files). Renames keep the new name."""
    out: list[tuple[str, int, int]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, p = parts
        if not (a.strip().isdigit() or a.strip() == "-"):
            continue
        p = p.strip()
        if "=>" in p:                                   # "dir/{old => new}/file" or "old => new"
            p = re.sub(r"\{[^{}]*=> ([^{}]*)\}", r"\1", p).split("=>")[-1].strip().replace("//", "/")
        out.append((p, int(a) if a.strip().isdigit() else 0, int(d) if d.strip().isdigit() else 0))
    return out


def normalise_commit(item: Any) -> CommitItem:
    """Accept a message string, a ``CommitItem`` or a dict.

    Dict keys: ``message`` (or ``subject`` plus ``body``); the diffstat as ``files`` (a list of paths or of dicts with
    ``path`` and ``additions``/``deletions``), or ``numstat`` (the text), or ``paths`` plus ``additions``/``insertions``,
    ``deletions`` and ``files_changed``. Everything is optional; without a diffstat the size defaults to ``small``.
    """
    if isinstance(item, CommitItem):
        return item
    if isinstance(item, str):
        return CommitItem(message=item)
    if not isinstance(item, Mapping):
        raise TypeError("a commit is a message string or a dict")
    msg = _pick(item, "message", "msg")
    if msg is None:
        subject, body = _pick(item, "subject", "title") or "", _pick(item, "body") or ""
        msg = f"{subject}\n\n{body}".strip() if body else str(subject)
    paths: list[str] = []
    adds = dels = 0
    have_counts = False
    files = _pick(item, "files", "file_stats", "diffstat")
    if isinstance(files, str):
        for p, a, d in parse_numstat(files):
            paths.append(p)
            adds, dels, have_counts = adds + a, dels + d, True
    elif isinstance(files, Sequence):
        for f in files:
            if isinstance(f, str):
                paths.append(f)
            elif isinstance(f, Mapping):
                p = _pick(f, "path", "file", "name", "filename")
                if p is not None:
                    paths.append(str(p))
                a, d = _int(_pick(f, "additions", "added", "insertions")), _int(_pick(f, "deletions", "deleted", "removed"))
                if a is not None or d is not None:
                    adds, dels, have_counts = adds + (a or 0), dels + (d or 0), True
            elif isinstance(f, Sequence) and len(f) == 3:
                paths.append(str(f[2]))
                a, d = _int(f[0]), _int(f[1])
                adds, dels, have_counts = adds + (a or 0), dels + (d or 0), True
    numstat = _pick(item, "numstat")
    if isinstance(numstat, str):
        for p, a, d in parse_numstat(numstat):
            paths.append(p)
            adds, dels, have_counts = adds + a, dels + d, True
    explicit_paths = _pick(item, "paths")
    if isinstance(explicit_paths, Sequence) and not isinstance(explicit_paths, str):
        paths.extend(str(p) for p in explicit_paths)
    top_a, top_d = _int(_pick(item, "additions", "insertions", "added")), _int(_pick(item, "deletions", "deleted", "removed"))
    if top_a is not None or top_d is not None:
        adds, dels, have_counts = (top_a or 0), (top_d or 0), True
    n_files = _int(_pick(item, "files_changed", "n_files", "file_count"))
    if n_files is None and paths:
        n_files = len(paths)
    return CommitItem(
        message=str(msg or ""), paths=tuple(dict.fromkeys(paths)),
        additions=adds if have_counts else None, deletions=dels if have_counts else None,
        files_changed=n_files, has_stat=have_counts or bool(paths),
    )


# ------------------------------------------------------------------------------------------------------ event input
@dataclass(frozen=True)
class EventItem:
    title: str
    description: str = ""
    duration_min: float | None = None
    all_day: bool = False
    attendee_count: int = 0
    recurring: bool = False
    location: str = ""
    online: bool = False

    def facts(self) -> dict[str, Any]:
        return {
            "recurring": bool(self.recurring),
            "duration_bucket": duration_bucket(self.duration_min, self.all_day),
            "attendee_bucket": attendee_bucket(self.attendee_count),
        }


def _to_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v), tz=timezone.utc)
    if isinstance(v, Mapping):                           # Graph style {"dateTime": ..., "timeZone": ...}
        return _to_dt(_pick(v, "dateTime", "date_time", "date"))
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def normalise_event(item: Any) -> EventItem:
    """Accept a title string, an ``EventItem`` or a dict (``title``/``subject``/``summary``; ``description``/``body``;
    ``start`` and ``end``, or ``duration_min``; ``all_day``; ``attendees`` (a list or a count) or ``attendee_count``;
    ``recurring``, ``rrule``, ``recurrence`` or ``series_id``; ``location``; ``online``)."""
    if isinstance(item, EventItem):
        return item
    if isinstance(item, str):
        return EventItem(title=item)
    if not isinstance(item, Mapping):
        raise TypeError("a calendar entry is a title string or a dict")
    title = _pick(item, "title", "subject", "summary", "name") or ""
    desc = _pick(item, "description", "body", "notes", "agenda") or ""
    if isinstance(desc, Mapping):
        desc = _pick(desc, "content", "text") or ""
    all_day = bool(_pick(item, "all_day", "is_all_day", "isAllDay"))
    dur = _pick(item, "duration_min", "duration_minutes", "minutes")
    start, end = _to_dt(_pick(item, "start", "dtstart")), _to_dt(_pick(item, "end", "dtend"))
    duration: float | None = float(dur) if isinstance(dur, (int, float)) and not isinstance(dur, bool) else None
    if duration is None and start and end:
        duration = max(0.0, (end - start).total_seconds() / 60.0)
    att = _pick(item, "attendees", "participants", "invitees")
    count = _int(_pick(item, "attendee_count", "n_attendees"))
    if count is None:
        if isinstance(att, Sequence) and not isinstance(att, str):
            count = len(att)
        elif isinstance(att, (int, float)) and not isinstance(att, bool):
            count = int(att)
    recurring = any(bool(_pick(item, k)) for k in ("recurring", "is_recurring", "rrule", "recurrence", "series_id", "recurring_event_id"))
    if str(_pick(item, "type") or "").lower() in ("occurrence", "seriesmaster"):
        recurring = True
    loc = _pick(item, "location") or ""
    if isinstance(loc, Mapping):
        loc = _pick(loc, "displayName", "name") or ""
    return EventItem(
        title=str(title), description=str(desc), duration_min=duration, all_day=all_day, attendee_count=count or 0,
        recurring=recurring, location=str(loc), online=bool(_pick(item, "online", "is_online", "isOnlineMeeting")),
    )


@dataclass
class DigestBatch:
    """Digests plus how each one was made. ``source`` is ``model``, ``rules`` or ``mixed``."""

    digests: list[dict[str, Any]]
    per_item_source: list[str] = field(default_factory=list)
    fallbacks: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    model_seconds: float = 0.0           # time inside model calls
    completion_tokens: int = 0
    prompt_tokens: int = 0
    model_fields: tuple[str, ...] = ()   # which fields the model decided in this batch (the rest came from code or rules)

    @property
    def source(self) -> str:
        s = set(self.per_item_source)
        if not s:
            return "rules"
        return s.pop() if len(s) == 1 else "mixed"
