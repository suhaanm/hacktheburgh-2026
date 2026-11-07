"""Every word the attention layer says (REQ-8), from fixed templates. Never model text, never screen text, never a name.

A template is filled only with slots this module computes itself from enums and small numbers (a count, a duration rounded to five
minutes, a fixed label). ``lint`` is the house style as code, and a test runs it over every template and every rendered sample:

* plain and short: a title of at most 8 words, a body of at most 22 (a reason line at most 20);
* says what happened and what the worker can do;
* names its source (one of ``vocab.SOURCES``);
* no exclamation marks, no emoji, no urgency theatre, no guilt, no stock phrases ("just", "heads up", "reminder:", "don't forget" ...);
* sentence case, ends with a full stop.

Cue's chips, questions and whispers and the help-level glance are the producer's own text (a pack label chosen by id): the layer admits
them and never words them, so they have no template here.
"""
from __future__ import annotations

import re
from typing import Any

from . import vocab as V

TITLE_MAX_WORDS, BODY_MAX_WORDS, REASON_MAX_WORDS = 8, 22, 20

# (title, body). {src} is the source name; every other slot is a phrase this module builds from an int or an enum.
TEMPLATES: dict[str, tuple[str, str]] = {
    "kill_engaged": ("Everything is stopped", "Understudy: nothing is running. Resume from the menu bar when you are ready."),
    "injection_pause": ("An agent run paused", "{src} paused because a page tried to instruct it. It ignored that and changed nothing. Open the run to decide."),
    "irreversible_decision": ("A run needs your decision", "{src} reached a step that cannot be undone. It has not done it. Open the queue to decide."),
    "run_blocked_target": ("A run is waiting for you", "{src} could not find the right button on the page. Open the run to point it there or stop it."),
    "run_blocked_error": ("A run is waiting for you", "{src} reached an error page. Open the run to retry or stop it."),
    "run_blocked_reminder": ("One run is still waiting", "{src} is paused until you decide. This is the only reminder."),
    "approval_blocking": ("An approval is waiting", "Approval queue: {approvals} waiting. A running job is paused until you decide."),
    "approval_reminder": ("An approval is still waiting", "Approval queue: the job is paused until you decide. This is the only reminder."),
    "calendar_deadline": ("A deadline is coming up", "Your calendar: a deadline {in_minutes}."),
    "deadline_reminder": ("A deadline is close", "Your calendar: a deadline {in_minutes}. This is the only reminder."),
    "routine_proposal": ("A routine you could hand over", "Briefing: {routines_phrase} worth handing over. Open the routines page when you want to look."),
    "briefing_ready": ("Your briefing is ready", "Briefing: {cards_phrase}. Open it when you want to look."),
    "approval_waiting": ("An approval is waiting", "Approval queue: {approvals} waiting. Nothing is paused for it."),
    "run_finished": ("A run finished", "{src}: {runs_phrase}. Open the report to see what each one did."),
    "morning_report": ("Your overnight report is ready", "Your overnight run: the report is ready. Open it when you want to look."),
    "service_degraded": ("A service is not reachable", "Understudy: {service_phrase}. Runs that need it will not start until it is back."),
    "digest_morning": ("Overnight summary", "{src}: {ran}, {needs}, {wait}. Open the summary."),
    "digest_return": ("While you were away", "{src}: {ran}, {needs}, {wait}. Open the summary."),
    "digest_rollup": ("A few things are waiting", "Understudy: {items_phrase}. {needs}. Open the summary."),
}
PASSTHROUGH = "passthrough"
REMINDER_TEXT = {"run_blocked_target": "run_blocked_reminder", "run_blocked_error": "run_blocked_reminder", "approval_blocking": "approval_reminder",
                 "calendar_deadline": "deadline_reminder"}

# The one-line "why" for every reason code. These are the whole of the transparency promise: fixed, plain, and checked by the linter.
REASONS: dict[str, str] = {
    "shown_safety": "Shown at once because it needs you. It is shown once; the marker stays until it is resolved.",
    "safety_on_return": "You were away, so it is marked now and will be the first thing you see when you are back.",
    "shown_now": "Shown at once because nothing was in the way.",
    "shown_break": "Held until now because you were busy. Shown at your pause.",
    "shown_asked": "Shown because you asked for help.",
    "shown_reminder": "The one reminder for this item, shown at a pause. There will not be another.",
    "shown_digest": "Shown as one summary instead of several separate notices.",
    "held_dnd": "Held because you asked for quiet. It stays counted and is shown when quiet ends.",
    "held_screen_sharing": "Held because your screen is being shared. It stays counted and is shown afterwards.",
    "held_on_call": "Held because you are on a call. It stays counted and is shown afterwards.",
    "held_in_meeting": "Held because your calendar shows a meeting. It stays counted and is shown afterwards.",
    "held_away": "Held because you were away. It is waiting for you to come back.",
    "held_typing": "Held because you were typing. Shown at your next pause.",
    "held_deep_work": "Held because you were in the middle of focused work. Shown at your next pause.",
    "held_not_a_break": "Held until you reach a pause, so it does not interrupt your work.",
    "held_lock": "Held because something else was on screen. One thing at a time.",
    "held_spacing": "Held so two notices do not arrive close together.",
    "held_state_unknown": "Held because Understudy could not tell whether you were busy.",
    "log_only": "Recorded in the log only. It needs nothing from you.",
    "passive_badge": "Counted in the menu bar. Nothing was shown on screen.",
    "passive_banner": "Left as a note on the dashboard. Nothing was shown on screen.",
    "passive_digest": "Folded into the next summary instead of a separate notice.",
    "passive_budget": "Folded into the next summary because the day's attention budget is spent.",
    "passive_learned": "Quieter than usual because you rarely open this kind of notice at this time.",
    "passive_mode": "Quieter because of your setting for this kind of notice.",
    "dropped_resolved": "Dropped because the situation was resolved.",
    "dropped_expired": "Dropped because it stopped being relevant.",
    "dropped_superseded": "Replaced by a newer item about the same thing.",
    "dropped_never_subject": "Not shown because you chose never for this.",
    "dropped_dnd": "Not shown because you asked for quiet, and it would be out of date by the time quiet ends.",
    "dropped_screen_sharing": "Not shown because your screen is being shared.",
    "dropped_on_call": "Not shown because you are on a call.",
    "dropped_in_meeting": "Not shown because your calendar shows a meeting.",
    "dropped_away": "Not shown because you were away and it would be out of date on return.",
    "dropped_flow": "Not shown because you were typing or had only paused for a moment.",
    "dropped_lock": "Not shown because something else was on screen.",
    "dropped_spacing": "Not shown because another notice had been shown a moment before.",
    "dropped_budget": "Not shown because the day's attention budget is spent.",
    "dropped_mode": "Not shown because of your setting for this kind of notice.",
    "dropped_learned": "Not shown because you rarely open this kind of notice at this time.",
    "dropped_state_unknown": "Not shown because Understudy could not tell whether you were busy.",
}
REASON_CODES = tuple(REASONS)
CHANNEL_TEXT = {"toast": "Shown as a small notice at the top right.", "chip": "Shown in context as a chip.", "question_card": "Shown as one question.", "voice": "Spoken, because you asked or a voice session was open.",
                "badge": "Counted in the menu bar. Nothing was shown on screen.", "banner": "Left as a note on the dashboard. Nothing was shown on screen."}

ACTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "kill_engaged": (("open_menu", "Open the menu"),),
    "injection_pause": (("open_run", "Open the run"), ("dismiss", "Close")),
    "irreversible_decision": (("open_queue", "Open the queue"), ("dismiss", "Close")),
    "run_blocked_target": (("open_run", "Open the run"), ("dismiss", "Close")),
    "run_blocked_error": (("open_run", "Open the run"), ("dismiss", "Close")),
    "approval_blocking": (("open_queue", "Open the queue"), ("dismiss", "Close")),
    "calendar_deadline": (("open_calendar", "Open the calendar"), ("dismiss", "Close")),
    "routine_proposal": (("open_routines", "Look at it"), ("not_now", "Not now"), ("never", "Never for this")),
    "briefing_ready": (("open_briefing", "Open the briefing"), ("dismiss", "Close")),
    "approval_waiting": (("open_queue", "Open the queue"), ("dismiss", "Close")),
    "run_finished": (("open_report", "Open the report"), ("dismiss", "Close")),
    "morning_report": (("open_report", "Open the report"), ("dismiss", "Close")),
    "service_degraded": (("open_settings", "Open settings"),),
    "attention_digest": (("open_summary", "Open the summary"), ("dismiss", "Close")),
}

_BANNED = (r"\bjust\b", r"\bsimply\b", r"\burgent(ly)?\b", r"\bhurry\b", r"\bimmediately\b", r"\basap\b", r"don'?t forget", r"do not forget", r"reminder:",
           r"heads[- ]up", r"\boops\b", r"\bwhoops\b", r"\bfriendly\b", r"great news", r"congrat", r"you missed", r"you forgot", r"still waiting for you",
           r"\boverdue\b", r"last chance", r"only today", r"right now", r"\bsorry\b", r"unfortunately", r"don'?t worry", r"no worries", r"hang tight",
           r"\bquick(ly)?\b", r"\bping\b", r"you should", r"you need to", r"you must", r"you have to", r"\bnotification\b", r"welcome back")
_BANNED_RE = [re.compile(p, re.I) for p in _BANNED]
_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿️]")


def words(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'.:-]*", s))


def lint(title: str | None, body: str | None, *, source_required: bool = True, reason: bool = False) -> list[str]:
    """House-style violations as ids (empty means clean)."""
    out: list[str] = []
    for label, s in (("title", title), ("body", body)):
        if s is None:
            continue
        if "!" in s:
            out.append(f"{label}:exclamation")
        if _EMOJI.search(s):
            out.append(f"{label}:emoji")
        for rx in _BANNED_RE:
            if rx.search(s):
                out.append(f"{label}:banned:{rx.pattern}")
        if s and not s[0].isupper() and not s[0].isdigit():
            out.append(f"{label}:not_sentence_case")
        if label == "body" and s and not s.rstrip().endswith("."):
            out.append("body:no_full_stop")
        if label == "title" and s.rstrip().endswith("."):
            out.append("title:full_stop")
    if title is not None and words(title) > TITLE_MAX_WORDS:
        out.append("title:too_long")
    if body is not None and words(body) > (REASON_MAX_WORDS if reason else BODY_MAX_WORDS):
        out.append("body:too_long")
    if source_required and not reason and not any(src in f"{title or ''} {body or ''}" for src in V.SOURCES):
        out.append("source:missing")
    return out


# ------------------------------------------------------------------------------------------------ slots
def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def phrase_minutes(minutes: float) -> str:
    """'in 45 minutes', rounded to five; under five is 'in less than 5 minutes'; a day or more is not given to the minute."""
    m = max(0.0, float(minutes))
    if m < 5:
        return "in less than 5 minutes"
    if m < 120:
        return f"in {int(round(m / 5.0) * 5)} minutes"
    if m < 24 * 60:
        return f"in {int(round(m / 60.0))} hours"
    return "in more than a day"


def source_name(run_mode: str | None) -> str:
    return {"overnight": "Your overnight run", "background": "Your background run"}.get(run_mode or "", "Your agent run")


SERVICE_PHRASE = {"engine": "the engine is not responding", "agent": "the agent service is not responding", "model": "the model provider is not reachable",
                  "calendar": "the calendar source is not reachable"}


def slots_for(type_id: str, *, count: int = 1, minutes: float | None = None, run_mode: str | None = None, service: str | None = None,
              deadline_in_s: float | None = None, payload: dict[str, Any] | None = None) -> dict[str, str]:
    n = max(1, int(count))
    pl = payload or {}
    ran_n, needs_n, wait_n = int(pl.get("ran", 0)), int(pl.get("needs_you", 0)), int(pl.get("can_ignore", 0))
    return {
        "src": source_name(run_mode),
        "approvals": _plural(n, "approval", "approvals"),
        "in_minutes": phrase_minutes((deadline_in_s if deadline_in_s is not None else (minutes or 0.0) * 60.0) / 60.0),
        "routines_phrase": "One routine looks" if n == 1 else f"{n} routines look",
        "cards_phrase": "1 card is ready" if n == 1 else f"{n} cards are ready",
        "runs_phrase": f"{n} run finished" if n == 1 else f"{n} runs finished",
        "service_phrase": SERVICE_PHRASE.get(service or "", "a service is not reachable"),
        "ran": "nothing ran" if ran_n == 0 else f"{ran_n} finished",
        "needs": "nothing needs a decision" if needs_n == 0 else (f"{needs_n} needs a decision" if needs_n == 1 else f"{needs_n} need a decision"),
        "wait": "nothing else to look at" if wait_n == 0 else f"{wait_n} can wait",
        "items_phrase": _plural(max(ran_n + needs_n + wait_n, n), "item", "items") + " arrived",
    }


def render(text_id: str, *, src: str | None = None, **kw: Any) -> tuple[str, str]:
    """(title, body) for a template id and the slot inputs. Raises KeyError for an id with no template."""
    title, body = TEMPLATES[text_id]
    s = slots_for(text_id, **kw)
    if src:
        s["src"] = src
    return title.format(**s), body.format(**s)


def text_id_for(type_id: str, *, digest_kind: str | None = None, reminder: bool = False) -> str:
    if reminder:
        return REMINDER_TEXT[type_id]
    if type_id == "attention_digest":
        return {"morning": "digest_morning", "rollup": "digest_rollup"}.get(digest_kind or "return", "digest_return")
    if V.TYPES[type_id].passthrough:
        return PASSTHROUGH
    return type_id


def digest_source(payload: dict[str, Any], kind: str) -> str:
    return "Your overnight run" if kind == "morning" and int(payload.get("ran", 0)) > 0 else "Understudy"


def render_item(item: Any, *, now: float | None = None, reminder: bool = False) -> dict[str, Any]:
    """The words for one item as ``{text_id, title, body, source}``. A pass-through type has no words of ours (title and body are None).

    ``now`` fixes the "in 45 minutes" of a deadline at the moment of delivery."""
    digest = item.type == "attention_digest"
    kind = item.payload.get("kind") if digest else None
    tid = text_id_for(item.type, digest_kind=kind, reminder=reminder)
    if tid == PASSTHROUGH:
        return {"text_id": tid, "title": None, "body": None, "source": "Cue" if item.family == "cue" else "Understudy"}
    kw: dict[str, Any] = dict(count=item.count, minutes=item.minutes, run_mode=item.run_mode, service=item.service, payload=item.payload)
    if item.type == "calendar_deadline":
        kw["deadline_in_s"] = max(0.0, item.expires_at - (now if now is not None else item.first_t))
    src = digest_source(item.payload, kind or "return") if digest else None
    title, body = render(tid, src=src, **kw)
    return {"text_id": tid, "title": title, "body": body, "source": next((s for s in V.SOURCES if s in f"{title} {body}"), "Understudy")}


def reason_text(code: str) -> str:
    return REASONS.get(code, "No reason was recorded.")


def actions_for(type_id: str) -> list[dict[str, str]]:
    return [{"id": i, "label": label} for i, label in ACTIONS.get(type_id, ())]
