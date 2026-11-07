"""Raw calendar items to ``Block`` objects. **This is where text stops.**

``to_blocks`` reads a ``RawItem``'s title, organiser and attendee addresses in memory, decides a kind (meeting, focus,
break, offscreen) with keyword rules, counts attendees and external domains, and returns blocks that carry none of that
text. After this function there is no title, name or address anywhere in the calendar layer.

Classification rules (code, not a model), applied to events that have **no other attendee** (``n_attendees <= 1``) and no
join link, because a solo hold is time the person owns:

* focus words (focus, deep work, heads down, no meetings, do not book) -> ``focus``
* batch words (batch, processing block, admin block) -> ``focus`` tagged ``batch``
* review words (review slot, queue review, end of day review, inbox review) -> ``focus`` tagged ``review``
* lunch, gym, walk, school run, appointment, commute and similar -> ``offscreen``; break, coffee, stretch -> ``break``
* any other solo hold -> ``focus`` (own time)

Everything with another attendee or a join link is a ``meeting``. Timed out-of-office entries are ``offscreen``. Cancelled,
declined, free-time and all-day entries are not meetings (all-day out-of-office marks a day off).
"""
from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from ..plugins.base import RawItem
from .model import Block, WorkConfig

_SALT = secrets.token_bytes(8)       # per process: series keys cannot be correlated across runs

_FOCUS = re.compile(r"\b(focus|deep[ -]work|heads[ -]?down|no meetings?|do not book|dnb|quiet time|think time)\b", re.I)
_BATCH = re.compile(r"\b(batch|processing block|admin block|admin hour|casework block|queue block)\b", re.I)
_REVIEW = re.compile(r"\b(review slot|queue review|end[- ]of[- ]day review|eod review|inbox review|review time|check[- ]?out review)\b", re.I)
_OFFSCREEN = re.compile(r"\b(lunch|gym|walk|run|workout|swim|yoga|school run|pick[- ]?up|drop[- ]?off|dentist|doctor|gp|appointment|"
                        r"commute|off[- ]?screen|offline|family|errand|haircut|physio)\b", re.I)
_BREAK = re.compile(r"\b(break|coffee|stretch|breather|tea)\b", re.I)


def _series_key(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=8, key=_SALT).hexdigest()


def _explicit_focus(title: str) -> bool:
    return bool(_FOCUS.search(title) or _BATCH.search(title) or _REVIEW.search(title))


def classify(title: str, n_attendees: int, show_as: str, online: bool, minutes: float) -> tuple[str, str]:
    """(kind, tag) from the title and shape of an event. Pure; the title is read, never returned."""
    if show_as == "oof":
        return "offscreen", ""
    if online or n_attendees > 1:
        return "meeting", ""
    if _REVIEW.search(title):
        return "focus", "review"
    if _BATCH.search(title):
        return "focus", "batch"
    if _FOCUS.search(title):
        return "focus", ""
    if _BREAK.search(title) and not _OFFSCREEN.search(title):
        return "break", ""
    if _OFFSCREEN.search(title):
        return "offscreen", ""
    return "focus", ""


@dataclass
class NormStats:
    """Counts only. Safe to show, log and return."""

    read: int = 0
    cancelled: int = 0
    declined: int = 0
    free_skipped: int = 0
    all_day_skipped: int = 0
    days_off: int = 0
    blocks: int = 0
    by_kind: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict[str, int | dict[str, int]]:
        return {"read": self.read, "cancelled": self.cancelled, "declined": self.declined, "free_skipped": self.free_skipped,
                "all_day_skipped": self.all_day_skipped, "days_off": self.days_off, "blocks": self.blocks,
                "by_kind": dict(self.by_kind)}


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[1] if "@" in addr else ""


LOCALMODEL_KIND = {"focus": ("focus", ""), "review": ("focus", "review"), "social": ("offscreen", ""), "travel": ("offscreen", ""), "admin": ("focus", "batch")}
SOLO_ONLY = {"review", "social", "travel", "admin", "focus"}          # these categories only make sense for time the owner owns
MEETING_CATEGORIES = {"one_to_one", "team_meeting", "external"}


def _localmodel_categories(items: list[RawItem]) -> list[str] | None:
    """Categories from the local-model digest (``understudy_engine.localmodel``) when it is running in model mode, else None (the keyword rules
    then decide). Titles go in only in memory; only a fixed-vocabulary category comes out. Never used in mock mode."""
    try:
        from ..localmodel import event_digest, mode
        if mode() != "model":
            return None
        payload = [{"title": i.fields.get("title", ""), "start": i.t0.isoformat(), "end": i.t1.isoformat(), "attendee_count": int(i.fields.get("n_attendees", 1) or 1),
                    "recurring": bool(i.fields.get("recurring")), "online": bool(i.fields.get("online")), "all_day": bool(i.fields.get("all_day"))} for i in items]
        return [str(d.get("category", "unknown")) for d in event_digest(payload)]
    except Exception:                                   # any problem: fall back to the rules, never fail a read
        return None


def to_blocks(items: Iterable[RawItem], cfg: WorkConfig | None = None, *, internal_domains: Iterable[str] | None = None,
              classifier: str = "rules") -> tuple[list[Block], frozenset[date], NormStats]:
    """-> (blocks, local dates marked out of office all day, counts). ``cfg`` supplies the zone for the day-off dates.

    ``classifier="rules"`` (default, the evaluation baseline) decides meeting, focus, break or off-screen from keywords and attendee counts;
    ``classifier="localmodel"`` asks the local-model digest for a category when it is running and falls back to the rules otherwise."""
    cfg = cfg or WorkConfig()
    items = [i for i in items if i.kind == "calendar_event"]
    cats = _localmodel_categories(items) if classifier == "localmodel" else None
    stats = NormStats()
    # the internal domain is the most common one among organisers and attendees unless told otherwise
    if internal_domains is None:
        c: Counter[str] = Counter()
        for it in items:
            f = it.fields
            for a in [f.get("organizer", ""), *f.get("attendees", [])]:
                d = _domain(a or "")
                if d:
                    c[d] += 1
        internal = {c.most_common(1)[0][0]} if c else set()
    else:
        internal = {d.lower() for d in internal_domains}
    blocks: list[Block] = []
    off: set[date] = set()
    for idx, it in enumerate(items):
        f = it.fields
        stats.read += 1
        if f.get("status") == "cancelled":
            stats.cancelled += 1
            continue
        if f.get("response") == "declined":
            stats.declined += 1
            continue
        if f.get("all_day"):
            if f.get("show_as") == "oof":
                d0 = it.t0.astimezone(cfg.tz).date()
                d1 = it.t1.astimezone(cfg.tz).date()
                d = d0
                while d < d1 or d == d0:
                    off.add(d)
                    d += timedelta(days=1)
            else:
                stats.all_day_skipped += 1
            continue
        minutes = it.duration_s / 60.0
        if minutes <= 0:
            continue
        n = int(f.get("n_attendees", 1) or 1)
        online = bool(f.get("online"))
        kind, tag = classify(str(f.get("title", "")), n, str(f.get("show_as", "busy")), online, minutes)
        if cats is not None and idx < len(cats) and f.get("show_as") != "oof":
            cat = cats[idx]
            if cat in MEETING_CATEGORIES or (cat in SOLO_ONLY and (online or n > 1)):
                kind, tag = "meeting", ""
            elif cat in LOCALMODEL_KIND and n <= 1 and not online:
                kind, tag = LOCALMODEL_KIND[cat]
        if f.get("show_as") == "free" and (kind == "meeting" or (kind == "focus" and not _explicit_focus(str(f.get("title", ""))))):
            stats.free_skipped += 1                     # free time does not commit anyone: a placeholder or an unrecognised solo hold
            continue
        people = [a for a in [f.get("organizer", ""), *f.get("attendees", [])] if a]
        external = bool(internal) and any(_domain(a) and _domain(a) not in internal for a in people)
        recurring = bool(f.get("recurring"))
        sid = str(f.get("series_id") or "")
        series = ""
        if recurring:
            series = _series_key(sid or f"{str(f.get('title', ''))}|{it.t0.astimezone(cfg.tz).weekday()}|{it.t0.astimezone(cfg.tz).strftime('%H%M')}")
        blocks.append(Block(it.t0, it.t1, kind, tag, n, recurring, series, external if kind == "meeting" else False, online))
        stats.by_kind[kind] += 1
    stats.blocks = len(blocks)
    stats.days_off = len(off)
    blocks.sort(key=lambda b: (b.start, b.end))
    return blocks, frozenset(off), stats
