"""Built-in vocabularies, features and purposes, so the other tracks can integrate on day one.

Tracks extend rather than replace: ``register_vocabulary("calendar.template", [...], extend=True)`` adds ids,
``register_feature("meeting_h", "hours")`` adds a named number, ``register_payload(...)`` adds a purpose. A track that needs
a different payload shape registers its own purpose name with its own ``SafePayload`` subclass.

The four built-in purposes (names from docs/SPEC_LIST.md 14.1 and the brief):

* ``calendar.suggestion_wording``: reword a code-selected calendar suggestion from learner and expert aggregates,
* ``git.habit_wording``: reword a code-detected git habit from ratios and a commit count,
* ``briefing.card_wording``: reword a morning-briefing card from its kind, risk, source tags and numbers,
* ``digest.meta``: a weekly summary line from digest counts and durations per fixed category.

Each returns ``{"text": "<one plain sentence>"}``; the caller must have a deterministic template sentence to use when the
call fails or no model is configured (the egress guard fails closed).
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .bucket import Count, DurationMin, Numbers, Ratio, register_feature
from .payload import SafePayload, Vocab, register_payload, register_vocabulary

# ------------------------------------------------------------------------------------------------ vocabularies
_BASE_COGS = ["READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "IDLE",
              "REVERT", "ASK"]
register_vocabulary("role", ["benefits-processor", "data-analyst", "programmer"], extend=True)
register_vocabulary("risk", ["low", "normal", "outward", "irreversible"], extend=True)
register_vocabulary("cog", _BASE_COGS + ["CODE", "TEST", "REFACTOR", "COMMIT"], extend=True)
register_vocabulary("hashed_id", pattern=r"[hd]:[0-9a-f]{4,16}", extend=True)  # label_hash / domain_hash shape
register_vocabulary("calendar.template", [
    "protect_focus_block", "batch_similar_work", "add_review_slot", "auto_hold_scheduling", "offcomputer_break",
    "reduce_back_to_back"], extend=True)
register_vocabulary("git.habit", [
    "huge_commits", "no_tests", "fix_after_fix", "many_reverts", "bursty_commits", "late_night_commits"], extend=True)
register_vocabulary("card.kind", ["practice", "automate", "focus_block", "git_habit", "agent_result"], extend=True)
register_vocabulary("source_tag", ["calendar", "git", "routine", "skill", "agent", "presence", "memory"], extend=True)
register_vocabulary("digest.category", [
    "feature", "bugfix", "refactor", "test", "docs", "chore", "revert", "meeting", "focus", "admin", "review", "other"], extend=True)

# ------------------------------------------------------------------------------------------------ named numbers
for _name, _kind in (
    ("meeting_h", "hours"), ("focus_blocks_60", "count"), ("focus_blocks_90", "count"), ("longest_focus_min", "duration_min"),
    ("fragmentation", "ratio"), ("back_to_back_runs", "count"), ("work_span_h", "hours"), ("offscreen_h", "hours"),
    ("n_commits", "count"), ("n_meetings", "count"), ("meeting_share", "ratio"), ("focus_share", "ratio"),
    ("test_touch_share", "ratio"), ("revert_share", "ratio"),
):
    register_feature(_name, _kind)


# ------------------------------------------------------------------------------------------------ payload models
class CalendarSuggestionWording(SafePayload):
    """A calendar suggestion chosen by code, with the learner's and the expert reference's aggregates."""

    description = "Reword a calendar suggestion from learner and expert aggregates (no titles, names or free text)."
    template: Annotated[str, Vocab("calendar.template")]
    role: Annotated[str, Vocab("role")]
    risk: Annotated[str, Vocab("risk")]
    learner: Numbers
    expert: Numbers


class GitHabitWording(SafePayload):
    """A git habit detected by code: the learner's and the expert's ratio, and how many commits it rests on."""

    description = "Reword a git habit from two ratios and a commit count (no messages, paths or names)."
    habit: Annotated[str, Vocab("git.habit")]
    learner_ratio: Ratio
    expert_ratio: Ratio
    n_commits: Count


class BriefingCardWording(SafePayload):
    """A morning-briefing card chosen by code."""

    description = "Reword a briefing card from its kind, risk class, source tags and numbers."
    kind: Annotated[str, Vocab("card.kind")]
    risk: Annotated[str, Vocab("risk")]
    sources: list[Annotated[str, Vocab("source_tag")]]
    numbers: Numbers


class DigestMeta(SafePayload):
    """Counts and durations per fixed digest category over a window (the digest, never the items)."""

    description = "A summary line from digest counts and minutes per fixed category."
    kind: Literal["commit", "event"]
    window_days: Annotated[int, Field(ge=1, le=366)]
    counts: dict[Annotated[str, Vocab("digest.category")], Count]
    minutes: dict[Annotated[str, Vocab("digest.category")], DurationMin]


WORDING_RESPONSE = {
    "type": "object",
    "properties": {"text": {"type": "string", "maxLength": 280}},
    "required": ["text"],
    "additionalProperties": False,
}
_WORDING = (
    "Write one plain sentence of at most 40 words that suggests or summarises what the codes and numbers say. "
    "Use only the numbers given. Do not mention any person, meeting, place, customer or tool by name."
)

register_payload("calendar.suggestion_wording", CalendarSuggestionWording, instructions=_WORDING, response_schema=WORDING_RESPONSE)
register_payload("git.habit_wording", GitHabitWording, instructions=_WORDING, response_schema=WORDING_RESPONSE)
register_payload("briefing.card_wording", BriefingCardWording, instructions=_WORDING, response_schema=WORDING_RESPONSE)
register_payload("digest.meta", DigestMeta, instructions=_WORDING, response_schema=WORDING_RESPONSE)

BUILTIN_PURPOSES = ("calendar.suggestion_wording", "git.habit_wording", "briefing.card_wording", "digest.meta")
