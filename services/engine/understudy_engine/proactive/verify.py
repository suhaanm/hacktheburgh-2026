"""Verify: re-check every candidate against the world *as it is now*, and drop what went stale.

The judge works from a snapshot; by the time the worker opens the briefing the world may have moved (the routine was
switched on from another screen, the skill reached level 4, the calendar already has the block, the run was looked at).
A card that is no longer true is worse than no card, so each one is checked against fresh readings and given a verdict:

* ``confirmed``: still true, nothing changed.
* ``updated``: still worth showing, but the numbers moved; the card is refreshed (the worker's own edits are kept).
* ``stale``: no longer true, already done, already in flight or timed out; dropped without a word.

The check is the same question for every kind: *does this opportunity still come out of the live collectors, and does it
say the same thing?* A source that cannot be read at all (a track not landed, a service down) neither confirms nor refutes:
the card stays ``confirmed`` with ``checked=False`` and a note saying it was not re-checked. Honest uncertainty beats
invented certainty. The check also catches work already in flight: a pending approval-queue item for the same card.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .candidates import Candidate, Collected, Ctx, Reading
from .cards import Card, parse_iso

KIND_SOURCE = {"automate": "routines", "practice": "skills", "focus_block": "calendar", "git_habit": "git", "agent_result": "runs"}
VERDICTS = ("confirmed", "updated", "stale")


@dataclass
class Verdict:
    verdict: str                  # confirmed | updated | stale
    note: str = ""
    checked: bool = True          # False: the source could not be read, so nothing was re-checked
    candidate: Candidate | None = None      # the refreshed candidate when updated (and the current one when confirmed)

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "note": self.note, "checked": self.checked}


def _row(reading: Reading, key: str, value: str) -> dict[str, Any] | None:
    return next((r for r in reading.items if str(r.get(key)) == value), None)


def _why_missing(kind: str, subject: str, rd: Reading) -> str:
    """A plain reason from our own wording; never text read from a source."""
    ref = subject.split(":", 1)[-1]
    if kind == "automate":
        r = _row(rd, "id", ref)
        if r is None:
            return "The routine is no longer in your list."
        if r.get("status") in ("shadow", "approval", "unattended"):
            return "You already switched this routine on."
        if r.get("status") in ("declined", "never"):
            return "You already said no to this routine."
        if not r.get("proposable", True):
            return "It is not ready to be proposed any more."
        return "It is no longer proposed."
    if kind == "practice":
        r = _row(rd, "id", ref)
        if r is None:
            return "That skill is no longer in your curriculum."
        if int(r.get("level", 1)) >= 4:
            return "You are already at level 4 on this skill."
        return "It is not the next skill to practise any more."
    if kind == "focus_block":
        return "The calendar no longer suggests this."
    if kind == "git_habit":
        return "The habit is no longer standing out from the reference."
    if kind == "agent_result":
        r = _row(rd, "run_id", ref)
        if r is None:
            return "The run is no longer there."
        if r.get("viewed"):
            return "You have already looked at this result."
        return "The run is not finished or has no result to show."
    return "It is no longer true."


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(x - y) <= 0.1 * max(abs(x), abs(y)) + 0.06


def _same(a: Candidate, b: Candidate) -> bool:
    """Did the evidence move materially? Whole numbers must match; other numbers may drift by about a tenth (a day
    passing must not make every card 'updated')."""
    if a.title != b.title or set(a.numbers) != set(b.numbers):
        return False
    return all(_close(a.numbers[k], b.numbers[k]) for k in a.numbers)


def verify_one(c: Candidate, now: Collected, ctx: Ctx, *, in_flight=None, card: Card | None = None) -> Verdict:
    """One candidate against ``now`` (a fresh ``collect``). ``in_flight(dedupe_key)`` says whether a pending approval already
    exists for this card; ``card`` supplies the expiry for a card that has been on screen."""
    if card is not None and card.expires_at and parse_iso(card.expires_at) < ctx.now_ts:
        return Verdict("stale", "The card timed out.", True)
    if in_flight is not None and in_flight(f"briefing:{c.id}"):
        return Verdict("stale", "It is already waiting in your approval queue.", True)
    src = KIND_SOURCE[c.kind]
    rd = now.readings.get(src)
    if rd is None or not rd.available:
        return Verdict("confirmed", "Not re-checked: the source could not be read right now.", False, c)
    fresh = next((x for x in now.candidates if x.id == c.id), None)
    if fresh is None:
        return Verdict("stale", _why_missing(c.kind, c.subject, rd), True)
    if c.kind == "git_habit" and not fresh.meta.get("significant"):
        return Verdict("stale", _why_missing(c.kind, c.subject, rd), True)
    if not _same(c, fresh):
        return Verdict("updated", "The numbers moved since the card was made.", True, fresh)
    return Verdict("confirmed", "Checked just now: still true.", True, fresh)


def verify_all(cands: list[Candidate], now: Collected, ctx: Ctx, *, in_flight=None,
               cards: dict[str, Card] | None = None) -> dict[str, Verdict]:
    return {c.id: verify_one(c, now, ctx, in_flight=in_flight, card=(cards or {}).get(c.id)) for c in cands}
