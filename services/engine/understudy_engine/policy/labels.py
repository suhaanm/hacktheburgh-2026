"""Implicit labels for coach prompts (ANA-6; the idea follows Pupil's reaction labels, re-implemented).

For each `coach_shown` event, look at what the worker did next. Windows (seconds after the prompt):

  followed    a `coach_followed` event within 10 s
  dismissed   a `coach_dismissed` event within 4 s (closed before it could be read: the prompt was unwelcome)
  repeated    the same issue came back within 10 s (another prompt or a `stuck` event with the same `issue`)
  undone      an `undo` within 10 s of the prompt (or of the follow, if it was followed)
  ignored     none of the above

Precedence when several apply: undone > dismissed > repeated > followed > ignored. A label is a noisy proxy for
"did it help": a dismissal can mean "I already knew". The reward model below says so in numbers rather than
hiding it.

Expected `meta` keys on `coach_shown` (numbers or enums only, per the event schema): `action` in
{nudge, annotate, takeover}, `issue` (an enum or integer naming the stuck issue), and optionally `propensity`.
"""
from __future__ import annotations

from dataclasses import dataclass

from understudy_engine.core import Event
from understudy_engine.policy.context import (
    ACTIONS, INTERRUPTION_COST, PROGRESS_WINDOW_S, RELIANCE_PENALTY_TAKEOVER, TAKEOVER,
)

FOLLOW_S = 10.0
DISMISS_S = 4.0
REPEAT_S = 10.0
UNDO_S = 10.0

LABELS = ("followed", "ignored", "repeated", "dismissed", "undone")
# subtracted from the reward on top of interruption cost: a dismissed or undone prompt cost the worker more
LABEL_PENALTY = {"followed": 0.0, "ignored": 0.0, "repeated": 0.20, "dismissed": 0.30, "undone": 0.60}


@dataclass(frozen=True)
class PromptLabel:
    t: float
    person: str
    action: str
    issue: str | None
    label: str
    reaction_t: float | None


def _issue(ev: Event) -> str | None:
    v = ev.meta.get("issue")
    if v is not None:
        return str(v)
    if ev.target and ev.target.label_hash:
        return ev.target.label_hash
    return None


def label_prompts(events: list[Event]) -> list[PromptLabel]:
    evs = sorted(events, key=lambda e: e.t)
    out: list[PromptLabel] = []
    for i, ev in enumerate(evs):
        if ev.type != "coach_shown":
            continue
        ts = ev.t.timestamp()
        issue = _issue(ev)
        action = str(ev.meta.get("action", "nudge"))
        followed_t = dismissed_t = repeated_t = undone_t = None
        later = [e for e in evs[i + 1:] if e.person == ev.person]
        for e in later:
            dt = e.t.timestamp() - ts
            if dt > max(FOLLOW_S, REPEAT_S, UNDO_S) + FOLLOW_S:  # beyond every window (undo may follow a follow)
                break
            if e.type == "coach_followed" and dt <= FOLLOW_S and followed_t is None:
                followed_t = ts + dt
            elif e.type == "coach_dismissed" and dt <= DISMISS_S and dismissed_t is None:
                dismissed_t = ts + dt
            elif e.type in ("coach_shown", "stuck") and dt <= REPEAT_S and repeated_t is None \
                    and issue is not None and _issue(e) == issue:
                repeated_t = ts + dt
        anchor = followed_t if followed_t is not None else ts
        for e in later:
            dt = e.t.timestamp() - anchor
            if dt > UNDO_S:
                if e.t.timestamp() - ts > UNDO_S + FOLLOW_S:
                    break
                continue
            if e.type == "undo" and dt >= 0:
                undone_t = anchor + dt
                break
        if undone_t is not None:
            label, rt = "undone", undone_t
        elif dismissed_t is not None:
            label, rt = "dismissed", dismissed_t
        elif repeated_t is not None:
            label, rt = "repeated", repeated_t
        elif followed_t is not None:
            label, rt = "followed", followed_t
        else:
            label, rt = "ignored", None
        out.append(PromptLabel(ts, ev.person, action, issue, label, rt))
    return out


def reward(progress_events_in_window: int, action: int | str, label: str | None = None, *,
           surcharge: float = 0.0) -> float:
    """Reward for one decision: progress in the next two minutes, minus interruption cost, minus a reliance
    penalty on takeover, minus a label penalty for how the worker reacted (when there was a prompt).

    `surcharge` is the extra interruption cost for prompting right after another prompt (the simulator uses it).
    """
    a = ACTIONS.index(action) if isinstance(action, str) else int(action)
    r = float(progress_events_in_window) - INTERRUPTION_COST[a] * (1.0 + surcharge)
    if a == TAKEOVER:
        r -= RELIANCE_PENALTY_TAKEOVER
    if label is not None:
        r -= LABEL_PENALTY[label]
    return r


def progress_in_window(events: list[Event], t0: float, person: str, window_s: float = PROGRESS_WINDOW_S) -> int:
    """Number of `progress` events by `person` in (t0, t0 + window_s]."""
    return sum(1 for e in events if e.person == person and e.type == "progress" and t0 < e.t.timestamp() <= t0 + window_s)
