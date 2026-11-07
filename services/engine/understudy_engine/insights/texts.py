"""Every word the insights layer says (REQ-9), from fixed templates. Never model text, never screen text, never a name.

A template is ``(title, headline, detail)`` for a worker pointer or ``(headline, detail)`` for an admin card, filled only with slots the code
computed (numbers and enums). The rendered text is ``headline + detail + "Source: <source>[, <badge phrase>]."`` and every admin text ends with
``vocab.STATEMENT``. ``lint`` is the house style as code; a test runs it over every template and every rendered sample:

* plain and short; a worker title of at most 8 words and a body of at most 40; an admin headline of at most 16 words and a body of at most 60;
* names its source (one of ``vocab.SOURCE_SET``) and, when the data is synthetic, says so;
* no exclamation marks, no emoji, no hype, no guilt, none of the banned phrases, no ranking words;
* worker text carries no percent sign and none of the words interval, confidence, significant, p-value;
* sentence case, ends with a full stop; admin text ends with the coaching sentence.

``accept_reword`` is the only door for a reworded text (the evidence layer's hook): it must keep exactly the template's numbers and pass the lint,
else the template stands. This module never calls a model.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from . import vocab as V
from .summary import skill_name
from .types import InsightCandidate

WORKER_TITLE_WORDS, WORKER_BODY_WORDS, ADMIN_HEAD_WORDS, ADMIN_BODY_WORDS = 8, 40, 16, 60

# worker: text id -> (title, headline, detail)
WORKER: dict[str, tuple[str, str, str]] = {
    "time_loss_habit": ("A habit that costs time", "On {skill}, you usually take about {seconds} seconds longer than the expert's median.", "Open Growth to see where the time goes."),
    "habit_improved": ("A habit that got faster", "On {skill}, you now take about {seconds} seconds less than you did a month ago.", ""),
    "independence_milestone": ("Needing less help", "On {skill}, you finished {k} of your last {n} cases without help.", ""),
    "retention_due": ("A skill due for practice", "It has been {days} days since {skill} last came up for you.", "A short practice keeps it sharp."),
    "relapse": ("A skill needed more help lately", "On {skill}, you needed help more often in recent weeks than before.", "Open Growth to see the recent cases."),
    "automation_opportunity": ("A routine you could hand over", "You repeated {what} {count} times recently.", "Understudy can propose handing it over, and nothing runs unless you approve it."),
    "calendar_pointer": ("A calendar habit", "Your calendar differs from the expert pattern on one point.", "Open your week to see it."),
    "git_pointer": ("A commit habit", "One of your commit habits differs from the expert pattern.", "Open Git habits to see it."),
    "onboarding": ("Getting started", "Understudy has seen {seen} of the roughly {needed} steps it needs before it can say anything about your work.", ""),
    "onboarding_role_changed": ("A new role", "You moved to a new role, so comparisons start fresh.", "Understudy has seen {seen} steps in it so far and needs about {needed}."),
    "stale_data": ("No recent work seen", "Understudy has not seen any work from you for {days} days, so there is nothing new to say.", ""),
    "trade_off": ("Faster, with a catch", "On {skill}, you take about {seconds} seconds less than before, but {guard_phrase}.", "Worth a look at quality as well as speed."),
}
GUARD_PHRASE = {
    "error_share": "errors went from {k_before} of {n_before} cases to {k_after} of {n_after}",
    "abandoned_share": "{k_after} of {n_after} cases were left unfinished, up from {k_before} of {n_before}",
    "time_to_progress": "getting moving after a prompt took {after} seconds, up from {before}",
}
NOTHING = "Nothing stands out this week. That is a normal result."
NO_DATA = "Understudy has not seen any of your work yet. Pointers start after about {needed} steps."

# admin: text id -> (headline, detail)
ADMIN: dict[str, tuple[str, str]] = {
    "role_gap": ("{role}: juniors take about {seconds} seconds longer per case than experts.", "That is within the same tasks. {habit1} and {habit2} explain most of it."),
    "role_gap_one": ("{role}: juniors take about {seconds} seconds longer per case than experts.", "That is within the same tasks. {habit1} explains most of it."),
    "cohort_trend_up": ("{role}: juniors need less help than six weeks ago.", "Independence is up about {points} points, compared within each person on the same tasks."),
    "cohort_trend_down": ("{role}: juniors need more help than six weeks ago.", "Independence is down about {points} points, compared within each person on the same tasks."),
    "cohort_trend_tradeoff": ("{role}: juniors need less help, but quality slipped.", "Errors rose from {before_pct} to {after_pct} per 100 cases over the same period."),
    "bottleneck_skill": ("{role}: {skill} is where juniors most often need help.", "About {share} in 100 occurrences needed help, {points} points above their other skills."),
    "onboarding_speed_ahead": ("{role}: new juniors are ahead of the onboarding target.", "{reached} in 100 reached independence within {occurrences} occurrences; the design target is {target_pct} in 100."),
    "onboarding_speed_behind": ("{role}: new juniors are behind the onboarding target.", "{reached} in 100 reached independence within {occurrences} occurrences; the design target is {target_pct} in 100."),
    "unit_attention": ("{role}, {unit}: juniors need more help than the rest of the role.", "Independence is about {points} points lower on the same tasks. This is where onboarding support may help."),
    "automation_value": ("Approved routines handled about {hours} hours of work in four weeks.", "That is {routines} routines and {runs} runs; shadow mode matched {matches} of {shadow_runs}."),
    "automation_value_tradeoff": ("Approved routines handled about {hours} hours of work, with a catch.", "A false claim was recorded in the same period, so check the runs before relying on the saving."),
    "automation_pending": ("{count} routine proposals are waiting for their owners.", "About {hours} hours over four weeks if they were approved. Only the worker can approve a routine."),
    "risk_approval_backlog": ("An approval has waited {hours} hours.", "{open} approvals are open."),
    "risk_injection_pauses": ("Runs paused after a page tried to instruct them: {count}.", "That was in the last {days} days. Nothing was changed."),
    "risk_false_claims": ("Agent runs that reported something their own check did not support: {count}.", "That was in the last {days} days."),
    "risk_kill_events": ("The kill switch stopped everything {times}.", "That was in the last {days} days."),
    "coverage": ("Only {enough} of {users} people have enough data to say anything.", "Read the other insights with that in mind."),
    "data_stale_ledger": ("The assist ledgers have not updated for {days} days.", "Insights that use them are not shown."),
    "data_stale_risk_feed": ("The risk feed has not updated for {days} days.", "Risk signals are not shown, so silence here does not mean all is well."),
}

BANNED = ("just", "simply", "urgent", "hurry", "obviously", "unfortunately", "great job", "well done", "poor", "worst", "underperform", "underperforming", "league",
          "rank", "ranking", "ranked", "lazy", "failing", "failure", "blame", "you should have", "asap", "immediately", "don't forget", "heads up", "oops")
WORKER_BANNED = ("interval", "confidence", "significant", "p-value", "statistic", "statistics", "%")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆⬇✅❌]")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def words(s: str) -> int:
    return len(s.split())


def _sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.])\s+", s.strip()) if x.strip()]


def lint(text: str, *, audience: str, kind: str = "body", badge: str = "live", source: str | None = None) -> list[str]:
    """Violations of the house style (an empty list is clean). ``kind`` is ``title``, ``headline`` or ``body``."""
    v: list[str] = []
    low = text.lower()
    if "!" in text:
        v.append("exclamation")
    if _EMOJI.search(text):
        v.append("emoji")
    for b in BANNED:
        if re.search(rf"(?<![a-z]){re.escape(b)}(?![a-z])", low):
            v.append(f"banned:{b}")
    if audience == "worker":
        for b in WORKER_BANNED:
            if b in low:
                v.append(f"worker_statistics:{b}")
    if kind == "title":
        if words(text) > WORKER_TITLE_WORDS:
            v.append("title_too_long")
        return v
    cap = {("worker", "body"): WORKER_BODY_WORDS, ("admin", "body"): ADMIN_BODY_WORDS, ("admin", "headline"): ADMIN_HEAD_WORDS, ("worker", "headline"): WORKER_BODY_WORDS}[(audience, kind)]
    if words(text) > cap:
        v.append("too_long")
    if not text.rstrip().endswith("."):
        v.append("no_full_stop")
    for s in _sentences(text):
        if s[:1].isalpha() and not s[:1].isupper():
            v.append("not_sentence_case")
            break
    if kind == "body":
        if not any(src in text for src in V.SOURCE_SET):
            v.append("no_source")
        if badge != "live" and V.BADGE_PHRASE.get(badge, "") not in text:
            v.append("no_badge")
        if audience == "admin" and not text.rstrip().endswith(V.STATEMENT):
            v.append("no_statement")
    return v


def cap(s: str) -> str:
    """Capitalise the first letter of every sentence (a slot such as a skill name may open one)."""
    return re.sub(r"(^|(?<=\.)\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)


def source_tail(source: str, badge: str) -> str:
    ph = V.BADGE_PHRASE.get(badge, "")
    return f"Source: {source}{', ' + ph if ph else ''}."


def slot_values(c: InsightCandidate, role: str | None) -> dict[str, Any]:
    """Slots as strings and numbers: ids become names (a skill id to its short name, a role id to its name). Never any text from outside."""
    s = dict(c.slots)
    r = role or s.get("role") or ""
    out: dict[str, Any] = {k: v for k, v in s.items()}
    for k in ("skill", "habit1", "habit2"):
        if k in out and out[k]:
            out[k] = skill_name(r, str(out[k])) if c.audience == "admin" else skill_name(r, str(out[k]))
    if c.audience == "admin" and s.get("role"):
        out["role"] = V.role_name(str(s["role"]))
    if "unit" in out:
        out["unit"] = str(out["unit"]).replace("_", " ")
    if "count" in out and isinstance(out["count"], int):
        out["times"] = "once" if out["count"] == 1 else f"{out['count']} times"
    for k in ("before", "after"):
        if k in out and isinstance(out[k], float) and out.get("guard") in ("error_share", "abandoned_share"):
            out[k + "_pct"] = int(round(out[k] * 100))
    if "guard" in out:
        out["guard_phrase"] = GUARD_PHRASE[out["guard"]].format(**{k: out.get(k, 0) for k in ("k_before", "n_before", "k_after", "n_after", "before", "after")})
    return out


def text_id(c: InsightCandidate) -> str:
    k = c.kind
    if c.audience == "worker":
        if k == "onboarding" and c.slots.get("reason") == "role_changed":
            return "onboarding_role_changed"
        return k
    if k == "role_gap":
        return "role_gap" if c.slots.get("habit2") else "role_gap_one"
    if k == "cohort_trend":
        return "cohort_trend_tradeoff" if c.polarity == "tradeoff" else ("cohort_trend_up" if c.slots.get("direction") == "up" else "cohort_trend_down")
    if k == "onboarding_speed":
        return "onboarding_speed_ahead" if c.slots.get("direction") == "ahead" else "onboarding_speed_behind"
    if k == "automation_value":
        return "automation_value_tradeoff" if c.polarity == "tradeoff" else "automation_value"
    if k == "risk_signal":
        return "risk_" + str(c.slots.get("signal"))
    if k == "data_stale":
        return "data_stale_" + str(c.slots.get("feed")) if c.slots.get("feed") in ("ledger", "risk_feed") else "data_stale_ledger"
    return k


def render(c: InsightCandidate, *, role: str | None = None, rewriter: Callable[[str, dict, str], str | None] | None = None) -> dict[str, Any]:
    """The words for one insight: ``{text_id, title, headline, detail, text, source, badge_phrase}``. Raises KeyError for an id with no template."""
    tid = text_id(c)
    spec = V.KINDS[c.kind]
    source = V.SOURCE_NAMES.get((c.audience, "hitlist" if c.action_id == "open_repeats" else spec.source), "Understudy")
    sl = slot_values(c, role)
    tail = source_tail(source, c.badge)
    if c.audience == "worker":
        title, head, det = WORKER[tid]
        headline, detail = cap(head.format(**sl)), cap(det.format(**sl))
        body = " ".join(x for x in (headline, detail, tail) if x)
    else:
        title = ""
        head, det = ADMIN[tid]
        headline, detail = cap(head.format(**sl)), cap(det.format(**sl))
        body = " ".join(x for x in (headline, detail, tail, V.STATEMENT) if x)
    if rewriter is not None:
        new = accept_reword(body, rewriter(tid, sl, body), audience=c.audience, badge=c.badge)
        body = new
    return {"text_id": tid, "title": title, "headline": headline, "detail": detail, "text": body, "source": source, "badge_phrase": V.BADGE_PHRASE.get(c.badge, "")}


def accept_reword(original: str, proposed: str | None, *, audience: str, badge: str) -> str:
    """A reworded text is accepted only if it keeps exactly the template's numbers, stays no more than half as long again, and passes the lint;
    otherwise the template stands. The evidence layer's provenance check is the intended verifier; this is the cheap local floor under it."""
    if not proposed or not isinstance(proposed, str):
        return original
    if sorted(_NUM.findall(proposed)) != sorted(_NUM.findall(original)):
        return original
    tail = re.search(r"Source: [^.]+\.", original)
    if tail and tail.group(0) not in proposed:                       # the source and the badge stay, word for word
        return original
    if len(proposed) > 1.5 * len(original):
        return original
    if lint(proposed, audience=audience, kind="body", badge=badge):
        return original
    return proposed


def a11y_label(polarity: str, headline: str) -> str:
    return f"{V.POLARITY_LABEL[polarity]}: {headline}"


def monday_note(headlines: list[str], titles: list[str]) -> str:
    if not headlines:
        return NOTHING
    n = len(headlines)
    lead = "Understudy has one pointer for your week." if n == 1 else f"Understudy has {n} pointers for your week."
    return " ".join([lead] + [h if h.endswith(".") else h + "." for h in headlines])
