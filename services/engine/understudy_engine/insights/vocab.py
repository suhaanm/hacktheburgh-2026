"""Closed vocabularies of the insights layer (REQ-9): kinds, polarities, glyphs, reason codes, sources, role names.

Everything that can reach a response is an id from here, an enum, a number or a fixed template text (``texts.py``). There is no free-text
field anywhere. ``packages/schema/insight.schema.json`` repeats the enums; a test keeps the two in step.
"""
from __future__ import annotations

from dataclasses import dataclass

AUDIENCES = ("worker", "admin")
POLARITIES = ("positive", "attention", "tradeoff", "note")
POLARITY_LABEL = {"positive": "Going well", "attention": "Worth a look", "tradeoff": "Trade-off", "note": "Note"}
GLYPHS = ("clock", "trend_up", "trend_down", "check", "refresh", "repeat", "calendar", "branch", "start", "scale", "pause", "alert", "people",
          "gauge", "bolt", "layers")
ORIGINS = ("real", "synthetic", "mixed")
BADGES = ("live", "synthetic", "made-up firm", "simulated")
CLASSES = ("effect", "state")
LEVELS = ("expert", "junior")
TREND_CLASSES = ("improving", "cannot_tell_yet", "needs_attention", "not_enough_data")
TREND_LABEL = {"improving": "Improving", "cannot_tell_yet": "Cannot tell yet", "needs_attention": "Needs attention", "not_enough_data": "Not enough data"}
STATUSES_WORKER = ("ok", "nothing_stands_out", "onboarding", "stale", "no_data", "role_changed")
STATUSES_PERSON = ("ok", "onboarding", "stale", "no_data")
TENURE_BANDS = ("lt_4w", "1_3m", "3_6m", "6_12m", "12m_plus")
FEEDBACK_EVENTS = ("useful", "not_useful", "dismissed", "done", "never_show", "hide_kind", "show_kind")
STATEMENT = "For coaching and onboarding, not for evaluating individuals."


@dataclass(frozen=True)
class KindSpec:
    id: str
    audience: str
    cls: str                  # effect: a test with an interval and a floor. state: a threshold on counts
    polarity: str             # the default polarity (a guard metric can turn an improvement into a trade-off)
    action_id: str | None
    glyph: str
    source: str               # a key of SOURCE_NAMES
    n_min: int
    improvement: bool = False  # carries guard metrics and may become a trade-off
    reserved: bool = False     # may take the admin's reserved slot


# kind -> spec. The worker kinds first, then the admin kinds.
KINDS: dict[str, KindSpec] = {k.id: k for k in (
    KindSpec("time_loss_habit", "worker", "effect", "attention", "open_growth", "clock", "ledger", 6),
    KindSpec("habit_improved", "worker", "effect", "positive", None, "trend_up", "ledger", 5, improvement=True),
    KindSpec("independence_milestone", "worker", "state", "positive", None, "check", "ledger", 20),
    KindSpec("retention_due", "worker", "state", "note", "open_practice", "refresh", "ledger", 8),
    KindSpec("relapse", "worker", "effect", "attention", "open_growth", "trend_down", "ledger", 6),
    KindSpec("automation_opportunity", "worker", "state", "note", "open_routines", "repeat", "routines", 3),
    KindSpec("calendar_pointer", "worker", "effect", "note", "open_week", "calendar", "calendar", 1),
    KindSpec("git_pointer", "worker", "effect", "note", "open_git", "branch", "git", 5),
    KindSpec("onboarding", "worker", "state", "note", None, "start", "ledger", 0),
    KindSpec("stale_data", "worker", "state", "note", None, "pause", "ledger", 0),
    KindSpec("trade_off", "worker", "effect", "tradeoff", "open_growth", "scale", "ledger", 5),
    KindSpec("role_gap", "admin", "effect", "attention", "open_roles", "layers", "ledger", 10),
    KindSpec("cohort_trend", "admin", "effect", "positive", "open_firm", "trend_up", "ledger", 5, improvement=True),
    KindSpec("bottleneck_skill", "admin", "effect", "attention", "open_roles", "gauge", "ledger", 5),
    KindSpec("onboarding_speed", "admin", "effect", "positive", "open_onboarding", "start", "ledger", 5, improvement=True),
    KindSpec("unit_attention", "admin", "effect", "attention", "open_firm", "people", "ledger", 5),
    KindSpec("automation_value", "admin", "state", "positive", "open_routines", "bolt", "offloaded", 3, improvement=True),
    KindSpec("automation_pending", "admin", "state", "note", None, "repeat", "routines", 3),
    KindSpec("risk_signal", "admin", "state", "attention", "open_queue", "alert", "risk_feed", 1, reserved=True),
    KindSpec("coverage", "admin", "state", "note", "open_firm", "people", "ledger", 1),
    KindSpec("data_stale", "admin", "state", "note", None, "pause", "ledger", 0, reserved=True),
)}
WORKER_KINDS = tuple(k for k, s in KINDS.items() if s.audience == "worker")
ADMIN_KINDS = tuple(k for k, s in KINDS.items() if s.audience == "admin")
# kinds that read the independence stream: only ever fed with assist rows (a test checks they never see delegated or automation rows)
INDEPENDENCE_KINDS = ("independence_milestone", "retention_due", "relapse", "habit_improved", "time_loss_habit", "trade_off", "cohort_trend",
                      "bottleneck_skill", "onboarding_speed", "unit_attention", "role_gap")

# action id -> (button label, the dashboard screen it opens, an optional query)
ACTIONS: dict[str, tuple[str, str, str | None]] = {
    "open_growth": ("Open Growth", "growth", None),
    "open_practice": ("Open practice", "growth", "practice"),
    "open_routines": ("Open Routines", "routines", None),
    "open_repeats": ("Open the repeat list", "repeats", None),
    "open_week": ("Open your week", "week", None),
    "open_git": ("Open Git habits", "git", None),
    "open_roles": ("Open role comparison", "firm", "roles"),
    "open_firm": ("Open the firm view", "firm", None),
    "open_onboarding": ("Open onboarding speed", "firm", "onboarding"),
    "open_queue": ("Open the queue", "queue", None),
}

SOURCE_NAMES = {
    ("worker", "ledger"): "Your assist ledger", ("worker", "routines"): "Your routines", ("worker", "hitlist"): "Your repeat list",
    ("worker", "calendar"): "Your calendar", ("worker", "git"): "Your git history", ("worker", "offloaded"): "Your routines",
    ("worker", "risk_feed"): "Understudy",
    ("admin", "ledger"): "Firm assist ledgers", ("admin", "routines"): "Firm routines", ("admin", "offloaded"): "Firm routines",
    ("admin", "risk_feed"): "Firm risk feeds", ("admin", "calendar"): "Firm assist ledgers", ("admin", "git"): "Firm assist ledgers",
    ("admin", "hitlist"): "Firm routines",
}
SOURCE_SET = frozenset(SOURCE_NAMES.values()) | {"Understudy"}
BADGE_PHRASE = {"live": "", "synthetic": "generated data", "made-up firm": "made-up firm data", "simulated": "generated data"}

# Suppression reasons and selection reasons (closed). The fixed sentence for each is in ``REASON_TEXT``.
SUPPRESSED = ("not_enough_data", "no_expert_reference", "stale", "interval_spans_zero", "below_effect_floor", "not_persistent",
              "not_significant_after_family_control", "group_too_small", "short_absence", "role_changed", "onboarding", "repeat_recently",
              "same_kind_lower_score", "same_subject_lower_score", "over_cap", "hidden_by_feedback")
SELECTED = ("selected_top_score", "selected_positive_slot", "selected_reserved_risk", "selected_trade_off")
REASONS = SUPPRESSED + SELECTED + ("unknown_insight",)
REASON_TEXT: dict[str, str] = {
    "not_enough_data": "There is not enough data yet to say anything reliable about this.",
    "no_expert_reference": "There is no expert reference to compare against, so no comparison was made.",
    "stale": "The newest data behind this is too old to be worth reporting.",
    "interval_spans_zero": "The data cannot tell this apart from no difference, so it is not reported.",
    "below_effect_floor": "The difference is too small to be worth a pointer.",
    "not_persistent": "It showed up in one week only, so it is not treated as a habit.",
    "not_significant_after_family_control": "Several things were checked at once, and this one did not stand clear of chance after allowing for that.",
    "group_too_small": "The group is smaller than 5 people, so it is not compared.",
    "short_absence": "A recent break explains this, so it is not read as a decline.",
    "role_changed": "The role changed recently, so comparisons start fresh.",
    "onboarding": "There is too little history for comparisons, so only a starting note is given.",
    "repeat_recently": "It was shown recently and nothing material has changed.",
    "same_kind_lower_score": "A stronger insight of the same kind about the same subject was chosen instead.",
    "same_subject_lower_score": "A stronger insight about the same subject was chosen instead.",
    "over_cap": "It passed every check but the list is full, and others scored higher.",
    "hidden_by_feedback": "Hidden because of earlier feedback on this insight or its kind.",
    "selected_top_score": "Selected: it passed every check and scored among the highest.",
    "selected_positive_slot": "Selected: the list keeps one place for something going well.",
    "selected_reserved_risk": "Selected: a risk or data-feed signal always keeps a place on the list.",
    "selected_trade_off": "Selected: an improvement that came with a worse quality measure, shown as a trade-off.",
    "unknown_insight": "There is no such insight for this audience.",
}

ROLE_NAMES = {"benefits-processor": "Benefits processor", "data-analyst": "Data analyst", "programmer": "Programmer", "other": "Other roles (merged)"}
ROLE_CODES = {"benefits-processor": "BP", "data-analyst": "DA", "programmer": "PG"}


def role_name(role: str) -> str:
    return ROLE_NAMES.get(role) or role.replace("-", " ").capitalize()


def role_code(role: str) -> str:
    return ROLE_CODES.get(role) or "".join(w[:1] for w in role.split("-"))[:2].upper() or "XX"


def tenure_band(weeks: float | None) -> str:
    w = 0.0 if weeks is None else float(weeks)
    if w < 4:
        return "lt_4w"
    if w < 13:
        return "1_3m"
    if w < 26:
        return "3_6m"
    if w < 52:
        return "6_12m"
    return "12m_plus"


# Short noun phrases for sentences. A pack's curriculum label is a sentence of its own ("Inspect the rows, not just the total") and never goes
# into a template; the labels are used in tables only. An id with no phrase becomes "the <words> step".
SKILL_PHRASE = {
    "reads-error-first": "reading the error first", "enter-household-once": "entering the household once", "check-the-cliff": "the cliff check",
    "reconcile-before-noting": "reconciling before the note", "note-with-evidence": "the note with its evidence",
    "profile-before-querying": "profiling before querying", "inspect-before-trusting": "inspecting the rows", "compare-to-last-period": "comparing with last period",
    "reconcile-to-control": "reconciling with the control figure",
    "read-the-trace-first": "reading the error trace first", "smallest-change": "the smallest change", "confirm-the-fix": "confirming the fix", "inspect-the-inputs": "inspecting the inputs",
}


def skill_phrase(skill: str) -> str:
    return SKILL_PHRASE.get(skill) or "the " + skill.replace("-", " ").replace("_", " ") + " step"
