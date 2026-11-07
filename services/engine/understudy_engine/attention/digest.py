"""The digest (REQ-8): one calm summary instead of N pings. Built by code from the held items, never by a model.

``summarise(items, kind, now)`` is pure: it reads items (ids, enums, counts) and returns the payload and the lines. Shape::

    {kind, built_t, needs_you, needs_you_unshown, needs_you_items: [{type, count}], ran, ran_outcomes: {outcome: n},
     can_ignore, can_ignore_by_type: {type: n}, lines: [str], counts: {...}}

* **Needs you** first, ordered by urgency (safety, then time, then decisions the worker can take), one line per type with a count, at
  most ``needs_max_lines``; more are folded into one "N more" line.
* **What ran**: one line of counts by outcome, never one line per run.
* **You could ignore**: one line of counts by kind, so the worker sees what was left out and where it lives.
* At most ``digest_max_lines`` lines in all. Items the digest lists as needing the worker are NOT folded (they stay counted until they
  are resolved); can-wait items are folded (state ``digested``) when a delivered digest is built.

The toast says counts only. The lines say the same with a source named and a next step; they are fixed templates checked by the linter.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from . import texts
from . import vocab as V
from .events import Item
from .state import DEFAULT, Params

# type -> (one, many) line templates; {n} is the count
NEEDS_LINES: dict[str, tuple[str, str]] = {
    "kill_engaged": ("Understudy: everything is stopped. Resume from the menu bar when you are ready.", "Understudy: everything is stopped. Resume from the menu bar when you are ready."),
    "injection_pause": ("Your agent run: 1 run paused because a page tried to instruct it.", "Your agent run: {n} runs paused because a page tried to instruct them."),
    "irreversible_decision": ("Your overnight run: 1 step that cannot be undone needs your decision.", "Your overnight run: {n} steps that cannot be undone need your decision."),
    "run_blocked_target": ("Your agent run: 1 run is waiting for you.", "Your agent run: {n} runs are waiting for you."),
    "run_blocked_error": ("Your agent run: 1 run is waiting for you.", "Your agent run: {n} runs are waiting for you."),
    "approval_blocking": ("Approval queue: 1 approval is holding up a job.", "Approval queue: {n} approvals are holding up jobs."),
    "calendar_deadline": ("Your calendar: 1 deadline is coming up.", "Your calendar: {n} deadlines are coming up."),
    "approval_waiting": ("Approval queue: 1 approval is waiting.", "Approval queue: {n} approvals are waiting."),
}
IGNORE_NOUN: dict[str, tuple[str, str]] = {
    "briefing_ready": ("briefing card", "briefing cards"), "routine_proposal": ("routine suggestion", "routine suggestions"),
    "service_degraded": ("service note", "service notes"), "morning_report": ("report", "reports"),
}
OUTCOME_WORD = {"done": "finished", "failed": "failed", "paused": "paused", "yielded": "stopped early", "stopped": "stopped"}
_ORDER = {t: (V.CLASS_ORDER[V.TYPES[t].cls], i) for i, t in enumerate(V.EVENT_TYPES)}


def _open(it: Item) -> bool:
    return it.state not in V.TERMINAL


def needs_items(items: Iterable[Item]) -> list[Item]:
    return [i for i in items if _open(i) and i.spec.needs_you and i.type != "attention_digest"]


def foldable(items: Iterable[Item]) -> list[Item]:
    """Can-wait items that have not been shown as an interruption and need nothing from the worker: they go into the digest."""
    return [i for i in items if i.state in ("held", "shown") and not i.interrupted and i.spec.cls == V.WAIT and not i.spec.needs_you
            and i.type != "attention_digest"]


def summarise(items: Iterable[Item], kind: str, now: float, p: Params = DEFAULT) -> dict[str, Any]:
    items = list(items)
    needs = needs_items(items)
    fold = foldable(items)
    by_type: dict[str, int] = Counter()
    ids: dict[str, list[str]] = {}
    for i in needs:
        by_type[i.type] += max(1, i.count)
        ids.setdefault(i.type, []).append(i.id)
    ran = Counter()
    ignore = Counter()
    for i in fold:
        if i.type == "run_finished":
            ran[i.outcome or "done"] += max(1, i.count)
        else:
            ignore[i.type] += max(1, i.count)
    ordered = sorted(by_type, key=lambda t: _ORDER[t])
    lines: list[str] = []
    for t in ordered[: p.needs_max_lines]:
        one, many = NEEDS_LINES[t]
        n = by_type[t]
        lines.append(one if n == 1 else many.format(n=n))
    if len(ordered) > p.needs_max_lines:
        rest = sum(by_type[t] for t in ordered[p.needs_max_lines:])
        lines.append(f"Understudy: {rest} more need you.")
    if ran:
        parts = [f"{n} {OUTCOME_WORD[o]}" for o, n in ran.items()]
        lines.append(f"Your overnight run: {', '.join(parts)}.")
    if ignore:
        parts = [f"{n} {(noun_forms(ignore_t))[0 if n == 1 else 1]}" for ignore_t, n in ignore.items()]
        lines.append(f"Understudy: {sum(ignore.values())} can wait: {', '.join(parts)}.")
    if len(lines) > p.digest_max_lines:
        extra = len(lines) - (p.digest_max_lines - 1)
        lines = lines[: p.digest_max_lines - 1] + [f"Understudy: {extra} more lines are on the dashboard."]
    unshown = [i for i in needs if i.state == "held"]
    return {"kind": kind, "built_t": round(now, 3), "needs_you": sum(by_type.values()), "needs_you_unshown": len(unshown),
            "needs_you_items": [{"type": t, "count": by_type[t], "id": ids[t][0], "ids": ids[t][:5]} for t in ordered], "ran": sum(ran.values()), "ran_outcomes": dict(ran),
            "can_ignore": sum(ignore.values()), "can_ignore_by_type": dict(ignore), "lines": lines,
            "counts": {"needs_you": sum(by_type.values()), "ran": sum(ran.values()), "can_ignore": sum(ignore.values()), "lines": len(lines)}}


def noun_forms(type_id: str) -> tuple[str, str]:
    return IGNORE_NOUN.get(type_id, ("item", "items"))


def lint_lines(payload: dict[str, Any]) -> list[str]:
    return [v for line in payload["lines"] for v in texts.lint(None, line, source_required=True, reason=False)]
