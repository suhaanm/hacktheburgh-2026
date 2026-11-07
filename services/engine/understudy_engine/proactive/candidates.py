"""Candidates: the things that might be worth putting in front of the worker this morning.

A candidate is *evidence plus a proposal*: what we saw (numbers, source tags), what we would offer (a title, a reason,
a template for the editable content) and what pressing the button would do (the ``fire`` spec). Nothing here decides
whether it is shown (``judge.py``), whether it is still true (``verify.py``) or what the final words are
(``prepare.py``); it only turns what the other layers already computed into a uniform shape.

Collectors read through a ``Readers`` bundle (``sources.py``): one small function per source that returns a ``Reading``
(plain dicts, plus whether the source was reachable at all). A missing source gives an empty list and a diagnostic, never
an error, so a track that has not landed yet costs nothing. Every title and reason is built here, from our own
templates, the pack's own skill labels and numbers; no free text from a calendar, a repository or a document is copied
onto a card.

Scales: ``value``, ``urgency``, ``freshness`` and ``effort`` are all in 0..1 and every collector writes the raw numbers it
used into ``numbers`` so the ranking can be explained. The saturating curve ``sat(x, s) = 1 - exp(-x / s)`` turns an
amount (hours, minutes) into a 0..1 value; the scale ``s`` is the amount that gives about 0.63.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .text import MAX_TITLE, MAX_WHY, clean_line, safe_numbers

KINDS = ("practice", "automate", "focus_block", "git_habit", "agent_result")
RISK_CLASSES = ("normal", "outward", "irreversible")
FIRE_TYPES = ("queue", "agent", "draft")
SOURCE_TAGS = ("routines", "skills", "calendar", "git", "agents", "memory", "pack", "local_model")


def sat(x: float, scale: float) -> float:
    """Saturating value curve in 0..1: 0 at 0, about 0.63 at ``scale``."""
    if scale <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - math.exp(-max(0.0, x) / scale)))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def half_life(age_days: float | None, hl: float) -> float:
    """0.5 ** (age / hl): 1.0 when brand new, 0.5 after one half-life. Unknown age counts as middling (0.5)."""
    if age_days is None:
        return 0.5
    return 0.5 ** (max(0.0, age_days) / hl)


# --------------------------------------------------------------------------------------------- context and readings
@dataclass
class Ctx:
    """Who and when. ``now`` is always passed in (never read from the clock inside a collector) so replays are exact."""

    person: str
    now: datetime
    role: str | None = None
    repo: str | None = None          # a git repo reference for the git habit reader (synthetic repo id or path)
    allow_http: bool = False         # may a reader call the agent service (:7710)? Off in tests and replays
    viewed_runs: frozenset[str] = frozenset()   # agent runs the worker has already looked at (from the briefing store)

    @property
    def now_ts(self) -> float:
        return self.now.timestamp()


@dataclass
class Reading:
    """What a source reader found. ``available`` False means the source could not be read at all (module missing,
    service down): different from an empty list, which means 'looked, nothing there'."""

    items: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True
    note: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)     # e.g. {"digest": "model" | "rules"} for sources built from digests


Reader = Callable[[Ctx], Reading]


# --------------------------------------------------------------------------------------------- the candidate
@dataclass
class FireSpec:
    """What pressing the button does. ``type``: ``queue`` (an approval-queue item), ``agent`` (a background agent run),
    ``draft`` (save the prepared content as a local draft and queue it for approval). ``payload_ref`` names what to
    create, never the content itself (the content is the card's ``prepared``, fired verbatim)."""

    type: str
    payload_ref: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in FIRE_TYPES:
            raise ValueError(f"fire type must be one of {FIRE_TYPES}")

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload_ref": dict(self.payload_ref)}


@dataclass
class Candidate:
    kind: str
    title: str
    why: str
    numbers: dict[str, Any]
    source_tags: list[str]
    risk_class: str
    value: float                 # 0..1 how much it is worth if the worker acts
    urgency: float               # 0..1 how soon it stops being worth
    freshness: float             # 0..1 how recent the evidence is
    prepared_template: dict[str, Any]   # {"template": id, "params": {...}} rendered by prepare.py
    fire: FireSpec
    subject: str                 # stable reference: routine id, skill id, calendar template, habit id, run id
    person: str = ""
    effort: float = 0.25         # 0..1 how much of the worker's attention it costs
    observed_at: float | None = None     # unix seconds of the newest evidence
    meta: dict[str, Any] = field(default_factory=dict)   # collector notes (value_source and the like), numbers only

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if self.risk_class not in RISK_CLASSES:
            raise ValueError(f"risk_class must be one of {RISK_CLASSES}")
        if self.risk_class == "irreversible" and self.fire.type != "queue":
            raise ValueError("an irreversible card can only fire into the approval queue")
        self.title = clean_line(self.title, MAX_TITLE)
        self.why = clean_line(self.why, MAX_WHY)
        self.numbers = safe_numbers(self.numbers)
        self.source_tags = [t for t in self.source_tags if t in SOURCE_TAGS]
        for f in ("value", "urgency", "freshness", "effort"):
            setattr(self, f, round(clamp01(getattr(self, f)), 4))

    @property
    def id(self) -> str:
        return card_id(self.person, self.kind, self.subject)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "title": self.title, "why": self.why, "numbers": dict(self.numbers),
                "source_tags": list(self.source_tags), "risk_class": self.risk_class, "value": self.value,
                "urgency": self.urgency, "freshness": self.freshness, "effort": self.effort,
                "prepared_template": self.prepared_template, "fire": self.fire.to_dict(), "subject": self.subject,
                "person": self.person, "observed_at": self.observed_at, "meta": dict(self.meta)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Candidate:
        return cls(kind=d["kind"], title=d["title"], why=d["why"], numbers=d.get("numbers", {}),
                   source_tags=d.get("source_tags", []), risk_class=d["risk_class"], value=d["value"],
                   urgency=d["urgency"], freshness=d["freshness"], prepared_template=d["prepared_template"],
                   fire=FireSpec(d["fire"]["type"], d["fire"].get("payload_ref", {})), subject=d["subject"],
                   person=d.get("person", ""), effort=d.get("effort", 0.25), observed_at=d.get("observed_at"),
                   meta=d.get("meta", {}))


def card_id(person: str, kind: str, subject: str) -> str:
    """Stable: the same opportunity gets the same id every morning, so a decline or a press attaches to it."""
    return "c_" + hashlib.sha1(f"{person}|{kind}|{subject}".encode()).hexdigest()[:12]


def _age_days(ctx: Ctx, ts: float | None) -> float | None:
    return None if ts is None else max(0.0, (ctx.now_ts - ts) / 86400.0)


def _date_ts(s: Any) -> float | None:
    """'2026-11-07' or an ISO time to unix seconds (UTC); None when unknown."""
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if v == v else default


# --------------------------------------------------------------------------------------------- automate (routines)
def automate_candidates(ctx: Ctx, rd: Reading) -> list[Candidate]:
    """A routine the engine proposes (``status == proposed``, ``proposable``). Value is the hours saved over the horizon;
    urgency rises with the minutes a week it costs and when the ski-rental rule says buying now beats waiting."""
    out: list[Candidate] = []
    for r in rd.items:
        if r.get("status") != "proposed" or not r.get("proposable", False) or not r.get("automatable", True):
            continue
        lo, hi = _f(r.get("hours_lo")), _f(r.get("hours_hi"))
        mid = (lo + hi) / 2.0
        if mid <= 0:
            continue
        weeks = int(r.get("horizon_weeks") or 4)
        mpw = _f(r.get("minutes_per_week"))
        eps = int(r.get("episodes") or 0)
        buy_after = r.get("buy_after_runs")
        buy_now = bool(buy_after is not None and eps >= int(buy_after))
        urgency = clamp01(mpw / 120.0 + (0.3 if buy_now else 0.0))
        age = _age_days(ctx, _date_ts(r.get("last_seen")))
        title = clean_line(f"Automate: {r.get('title') or r['id']}")
        why = (f"It came up {eps} times, about {mpw:.0f} minutes a week. Doing it for you could save {lo:.1f} to {hi:.1f} "
               f"hours over the next {weeks} weeks, and you stay in charge: it starts by watching, never by acting.")
        out.append(Candidate(
            kind="automate", title=title, why=why,
            numbers={"episodes": eps, "minutes_per_week": round(mpw, 1), "hours_saved_lo": round(lo, 2),
                     "hours_saved_hi": round(hi, 2), "confidence": round(_f(r.get("confidence")), 2),
                     "horizon_weeks": weeks, "buy_now": buy_now},
            source_tags=["routines", "pack"], risk_class="normal",
            value=sat(mid, 4.0), urgency=urgency, freshness=half_life(age, 10.0),
            prepared_template={"template": "automation_consent", "params": {
                "routine_id": r["id"], "title": r.get("title") or r["id"], "episodes": eps, "minutes_per_week": round(mpw, 1),
                "hours_lo": round(lo, 1), "hours_hi": round(hi, 1), "horizon_weeks": weeks,
                "touches": list(r.get("touches") or [])[:6], "never": list(r.get("never") or [])[:6],
                "irreversible_classes": list(r.get("irreversible_classes") or [])[:6]}},
            fire=FireSpec("queue", {"queue_kind": "batch_result", "action": "routine_consent", "routine_id": r["id"],
                                    "requested_mode": "shadow"}),
            subject=f"routine:{r['id']}", person=ctx.person, effort=0.3,
            observed_at=_date_ts(r.get("last_seen")), meta={"hours_mid": round(mid, 2)}))
    return out


# --------------------------------------------------------------------------------------------- practice (skills)
def practice_candidates(ctx: Ctx, rd: Reading, routines: Reading | None = None) -> list[Candidate]:
    """A skill below level 4 that is next in teaching order. Value is the gap (low mastery, low level) with a bonus when the
    skill is the only thing standing between the worker and an automation; urgency is the decay clock (a level that is
    about to drop) and how long it has been since the worker practised it."""
    skills = sorted(rd.items, key=lambda s: (s.get("order", 99), str(s.get("id"))))
    level = {s["id"]: int(s.get("level", 1)) for s in skills}
    blocking: dict[str, str] = {}
    for r in (routines.items if routines else []):
        if r.get("status") == "proposed" and r.get("automatable", True) and not r.get("skill_gate_ok", True):
            for c in r.get("skill_cogs", []):
                blocking.setdefault(c, str(r["id"]))
    out: list[Candidate] = []
    for s in skills:
        lv = int(s.get("level", 1))
        if lv >= 4:
            continue
        if any(level.get(p, 1) < 2 for p in s.get("prerequisites", [])):
            continue        # teach in order: a skill whose prerequisite is still at level 1 waits
        mastery = clamp01(_f(s.get("mastery"), 0.2))
        idle = s.get("days_idle")
        idle = None if idle is None else max(0.0, _f(idle))
        drop = s.get("days_until_drop")
        drop_urg = 0.0 if drop is None else clamp01(1.0 - _f(drop) / 3.0)
        idle_urg = 0.0 if idle is None else 0.4 * clamp01(idle / 7.0)
        unlocks = next((blocking[c] for c in s.get("cogs", []) if c in blocking), None)
        value = clamp01(0.6 * (1.0 - mastery) + 0.4 * ((4 - lv) / 3.0) + (0.2 if unlocks else 0.0))
        label = clean_line(s.get("label") or s["id"])
        bits = [f"It is at level {lv} of 4 and your mastery is about {mastery:.0%}."]
        if idle is not None:
            bits.append(f"You last practised it {idle:.0f} day{'s' if round(idle) != 1 else ''} ago.")
        if unlocks:
            bits.append("Getting it to level 4 is what lets an automation be offered.")
        out.append(Candidate(
            kind="practice", title=f"Practice: {label}", why=" ".join(bits),
            numbers={"level": lv, "mastery": round(mastery, 2), **({"days_idle": round(idle, 1)} if idle is not None else {}),
                     **({"days_until_drop": round(_f(drop), 1)} if drop is not None else {}), "unlocks_automation": bool(unlocks)},
            source_tags=["skills", "pack"] + (["routines"] if unlocks else []), risk_class="normal",
            value=value, urgency=max(drop_urg, idle_urg, 0.15), freshness=half_life(idle, 14.0),
            prepared_template={"template": "practice_plan", "params": {
                "skill_id": s["id"], "label": label, "level": lv, "expert_signal": clean_line(s.get("expert_signal") or "", 200),
                "prompts": {k: clean_line(v, 200) for k, v in (s.get("prompts") or {}).items() if k in ("L1", "L2", "L3")},
                "cogs": list(s.get("cogs") or [])[:6]}},
            fire=FireSpec("queue", {"queue_kind": "batch_result", "action": "practice_session", "skill_id": s["id"]}),
            subject=f"skill:{s['id']}", person=ctx.person, effort=0.35,
            observed_at=None if idle is None else ctx.now_ts - idle * 86400.0, meta={"unlocks": unlocks or ""}))
    return out


# --------------------------------------------------------------------------------------------- focus block (calendar)
#: titles and reasons for the fixed suggestion catalogue (CAL-3). The calendar layer picks the template; we only word it.
CAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "focus": {"title": "Protect a focus block", "risk": "outward", "draft": True,
              "why": "Your week has no long uninterrupted stretch for deep work. A recurring hold keeps one free."},
    "batch": {"title": "Batch similar work", "risk": "normal", "draft": False,
              "why": "Similar tasks are spread through the week. Grouping them saves the cost of switching."},
    "review": {"title": "Add a review slot", "risk": "outward", "draft": True,
               "why": "Work goes out without a set time to check it. A short review slot catches slips early."},
    "hold": {"title": "Let scheduling hold time for you", "risk": "outward", "draft": True,
             "why": "Booking time by hand is a recurring chore. An automatic hold can do it, after you approve each one."},
    "break": {"title": "Schedule a break away from the screen", "risk": "outward", "draft": True,
              "why": "Long unbroken screen stretches show up in your week. A scheduled break or handoff gives you a rest."},
    "back": {"title": "Reduce back-to-back meetings", "risk": "normal", "draft": False,
             "why": "Meetings run into each other with no gap. A buffer between them helps."},
}
_CAL_ORDER = ("focus", "batch", "review", "hold", "break", "back")


def calendar_family(template: Any) -> str | None:
    t = str(template or "").lower()
    for key, hints in (("focus", ("focus",)), ("batch", ("batch",)), ("review", ("review",)), ("hold", ("hold", "automate", "auto_")),
                       ("break", ("break", "offscreen", "off_screen", "off-screen", "handoff", "away")), ("back", ("back", "b2b"))):
        if any(h in t for h in hints):
            return key
    return None


def _hours_from(numbers: dict[str, Any]) -> float | None:
    for k in ("gain_h", "hours_gain", "delta_h", "hours_recoverable", "recoverable_h"):
        if k in numbers:
            return abs(_f(numbers[k]))
    for k in ("gain_min", "delta_min", "minutes_gain", "recoverable_min"):
        if k in numbers:
            return abs(_f(numbers[k])) / 60.0
    return None


def calendar_candidates(ctx: Ctx, rd: Reading) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for s in rd.items:
        fam = calendar_family(s.get("template"))
        tid = re.sub(r"[^a-z0-9_\-]", "", str(s.get("template") or "").lower())[:40]
        if not tid or tid in seen:
            continue
        seen.add(tid)
        cat = CAL_TEMPLATES.get(fam or "", {"title": "A calendar suggestion", "risk": "normal", "draft": False,
                                            "why": "Your week's shape suggests a change."})
        nums = safe_numbers(s.get("numbers"))
        gain_h = _hours_from(nums)
        value = sat(gain_h, 3.0) if gain_h is not None else 0.45
        bits = [cat["why"]]
        shown = [f"{k.replace('_', ' ')} {v}" for k, v in nums.items() if isinstance(v, (int, float)) and not isinstance(v, bool)][:3]
        if shown:
            bits.append("The numbers: " + ", ".join(shown) + ".")
        ref = safe_numbers(s.get("expert_ref"))
        if ref:
            bits.append("The expert reference is on the card.")
        risk = "outward" if (cat["risk"] == "outward" or s.get("can_draft")) and fam in ("focus", "review", "hold", "break") else "normal"
        out.append(Candidate(
            kind="focus_block", title=cat["title"], why=" ".join(bits),
            numbers={**nums, **{f"expert_{k}": v for k, v in ref.items()}},
            source_tags=["calendar"] + (["local_model"] if rd.meta.get("digest") == "model" else []), risk_class=risk, value=value,
            urgency=0.5, freshness=0.9,
            prepared_template={"template": "calendar_hold", "params": {"family": fam or "other", "template_id": tid, "numbers": nums}},
            fire=FireSpec("draft", {"queue_kind": "outward_step" if risk == "outward" else "batch_result", "action": "calendar_draft",
                                    "template": tid}),
            subject=f"cal:{tid}", person=ctx.person, effort=0.2, observed_at=ctx.now_ts,
            meta={"value_source": "calendar numbers" if gain_h is not None else "default"}))
    return out


# --------------------------------------------------------------------------------------------- git habits
GIT_HABITS: dict[str, dict[str, str]] = {
    "huge": {"title": "Make commits smaller", "why": "A large share of your commits change a lot of lines at once, more than the expert reference, which makes review and rollback harder.",
             "agent": "programming.commit_analyst"},
    "test": {"title": "Touch a test with the change", "why": "Many of your feature and fix commits change code without touching a test, more often than the expert reference.",
             "agent": "programming.test_gap"},
    "revert": {"title": "Run the tests before you commit", "why": "Fixes often follow fixes, or commits get reverted, more than the expert reference. A pause to check before committing helps.",
               "agent": "programming.commit_analyst"},
    "message": {"title": "Write clearer commit messages", "why": "A share of your commit messages are very short or generic, more than the expert reference.",
                "agent": "programming.commit_analyst"},
    "late": {"title": "Protect late nights", "why": "More of your commits land in the small hours than the expert reference. Stopping earlier, or reading late changes again in the morning, helps.",
             "agent": "programming.commit_analyst"},
    "refactor": {"title": "Separate refactors from features", "why": "Refactoring and feature work land in the same commits, which hides both.",
                 "agent": "programming.refactor_suggest"},
}


def git_family(habit_id: Any) -> str | None:
    t = str(habit_id or "").lower()
    for key, hints in (("test", ("test",)), ("huge", ("huge", "large", "big", "size", "smaller")), ("revert", ("revert", "fix_after", "fixafter", "loop")),
                       ("message", ("message", "vague", "clearer")), ("late", ("late", "night")), ("refactor", ("refactor",))):
        if any(h in t for h in hints):
            return key
    return None


def _share(x: float) -> str:
    return f"{x:.0%}"


def git_candidates(ctx: Ctx, rd: Reading) -> list[Candidate]:
    out: list[Candidate] = []
    for h in rd.items:
        hid = re.sub(r"[^a-z0-9_\-]", "", str(h.get("id") or "").lower())[:40]
        if not hid:
            continue
        fam = git_family(hid)
        cat = GIT_HABITS.get(fam or "", {"title": "A commit habit worth a look", "why": "Your commit pattern differs from the expert reference.",
                                         "agent": "programming.commit_analyst"})
        delta, learner, expert = _f(h.get("delta")), _f(h.get("learner")), _f(h.get("expert"))
        ci = h.get("ci") or [None, None]
        sig = isinstance(ci, (list, tuple)) and len(ci) == 2 and ci[0] is not None and ci[1] is not None and (_f(ci[0]) > 0 or _f(ci[1]) < 0)
        rel = abs(delta) / (abs(learner) + abs(expert) + 1e-9)
        value = (0.5 + 0.5 * clamp01(rel)) if sig else 0.15
        nums = {"learner": round(learner, 3), "expert": round(expert, 3), "delta": round(delta, 3), "ci_excludes_zero": bool(sig),
                "n_commits": int(h.get("n_commits") or 0)}
        out.append(Candidate(
            kind="git_habit", title=cat["title"],
            why=cat["why"] + (f" Yours is {_share(learner)}, the experts' is {_share(expert)}." if (0 <= learner <= 1 and 0 <= expert <= 1 and (learner or expert)) else ""),
            numbers=nums, source_tags=["git"] + (["local_model"] if rd.meta.get("digest") == "model" else []), risk_class="normal",
            value=value, urgency=0.35, freshness=0.8,
            prepared_template={"template": "git_habit_note", "params": {"family": fam or "other", "habit_id": hid, "numbers": nums,
                                                                         "agent_kind": cat["agent"]}},
            fire=FireSpec("agent", {"agent_kind": cat["agent"], "mode": "foreground", "habit": hid}),
            subject=f"git:{hid}", person=ctx.person, effort=0.25, observed_at=ctx.now_ts,
            meta={"significant": bool(sig)}))
    return out


# --------------------------------------------------------------------------------------------- finished agent runs
def agent_candidates(ctx: Ctx, rd: Reading) -> list[Candidate]:
    out: list[Candidate] = []
    for r in rd.items:
        if r.get("viewed") or str(r.get("state")) not in ("done", "succeeded", "complete", "completed"):
            continue
        rid = re.sub(r"[^A-Za-z0-9_.\-]", "", str(r.get("run_id") or ""))[:64]
        if not rid:
            continue
        fin = r.get("finished_at")
        age_h = None if fin is None else max(0.0, (ctx.now_ts - _f(fin)) / 3600.0)
        out.append(Candidate(
            kind="agent_result", title="A background run finished", why=("A run you or the system started has finished and its result is waiting. "
                                                                     "Nothing was changed outside its own workspace."),
            numbers={**({"age_h": round(age_h, 1)} if age_h is not None else {}), "children": int(r.get("children") or 0)},
            source_tags=["agents"], risk_class="normal", value=0.55, urgency=0.7 if (age_h is not None and age_h < 6) else 0.4,
            freshness=half_life(None if age_h is None else age_h / 24.0, 1.0),
            prepared_template={"template": "agent_result_review", "params": {"run_id": rid, "kind": str(r.get("kind") or "")[:40],
                                                                              "children": int(r.get("children") or 0)}},
            fire=FireSpec("queue", {"queue_kind": "batch_result", "action": "review_result", "run_id": rid}),
            subject=f"run:{rid}", person=ctx.person, effort=0.15, observed_at=None if fin is None else _f(fin)))
    return out


# --------------------------------------------------------------------------------------------- collect
@dataclass
class Collected:
    candidates: list[Candidate]
    diagnostics: dict[str, dict[str, Any]]      # source -> {available, n, note}
    readings: dict[str, Reading] = field(default_factory=dict)     # what each reader returned (for verification)


def collect(ctx: Ctx, readers: Any, *, only: tuple[str, ...] | None = None) -> Collected:
    """Run every collector. A reader that raises or is unavailable gives an empty list and a diagnostic. The note is a plain
    reason from our own code, never source text."""
    cands: list[Candidate] = []
    diag: dict[str, dict[str, Any]] = {}

    def read(name: str) -> Reading:
        fn = getattr(readers, name, None)
        if fn is None:
            return Reading([], False, "no reader")
        try:
            rd = fn(ctx)
        except Exception as exc:  # a broken sibling track must not take the briefing down
            return Reading([], False, f"{type(exc).__name__} while reading")
        return rd if isinstance(rd, Reading) else Reading(list(rd or []), True, None)

    want = lambda n: only is None or n in only  # noqa: E731
    routines = read("routines") if (want("routines") or want("skills")) else Reading([], False, "skipped")
    skills = read("skills") if want("skills") else Reading([], False, "skipped")
    calendar = read("calendar") if want("calendar") else Reading([], False, "skipped")
    git = read("git") if want("git") else Reading([], False, "skipped")
    runs = read("runs") if want("runs") else Reading([], False, "skipped")
    readings = {"routines": routines, "skills": skills, "calendar": calendar, "git": git, "runs": runs}
    for name, build in (("routines", lambda: automate_candidates(ctx, routines)),
                        ("skills", lambda: practice_candidates(ctx, skills, routines)),
                        ("calendar", lambda: calendar_candidates(ctx, calendar)),
                        ("git", lambda: git_candidates(ctx, git)),
                        ("runs", lambda: agent_candidates(ctx, runs))):
        if not want(name):
            continue
        made: list[Candidate] = []
        try:
            made = build()
        except Exception as exc:
            diag[name] = {"available": readings[name].available, "n": 0, "note": f"{type(exc).__name__} while building"}
            continue
        cands.extend(made)
        diag[name] = {"available": readings[name].available, "n": len(made), "note": readings[name].note}
    return Collected(cands, diag, readings)
