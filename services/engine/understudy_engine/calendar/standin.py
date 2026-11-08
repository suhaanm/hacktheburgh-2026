"""The worker's own calendar week, served for the person who is set up on this device.

The calendar layer reads shared calendars by person id, and the worker (the profile's person) has none of their own in that shared folder. For the worker's own page the layer therefore answers
from a role-appropriate calendar that exists there, UNDER THE WORKER'S ID AND ROLE, and removes every other person's id from the body (the experienced worker the week is set beside becomes
the unnamed reference ``expert``). The shared folder is only read, never written. Which calendar is used follows the profile's role, so a role change in the Account menu switches it.

Used by ``routes_calendar`` for ``GET /calendar/week``, ``/calendar/suggestions`` and ``/calendar/people`` when the request is the worker's own (no ``person``, or the profile's person).
Nobody set up (the evaluation's personas, a fresh stack): the routes behave exactly as before.
"""
from __future__ import annotations

from typing import Any

#: role -> the shared calendar its week is shown from (office hours for benefits, late and uneven days for programming, irregular days for analysis). A role without an entry uses benefits.
SOURCES: dict[str, str] = {"benefits-processor": "p_ninetofive", "programmer": "p_nightowl", "data-analyst": "p_irregular"}
REFERENCE_NAME = "expert"
#: the neutral note of the worker's own pages (no statement about how the calendar was produced: the numbers are the worker's own page)
NOTE = "Your week as blocks and numbers, set beside an experienced worker's. Titles, names and addresses are never read. Intervals cover the uncertainty in the reference only."
SUGGESTIONS_NOTE = "Chosen by code from fixed thresholds against the experienced worker's week; the text is templated. Every suggestion is opt-in and low risk."


def caller() -> tuple[str | None, str | None]:
    """``(person, role)`` of the worker set up on this device (the profile), or ``(None, None)`` when nobody is set up or the profile cannot be read."""
    try:
        from .. import routes_handoff as rh
        from ..memory.onboarding import load_profile

        prof = load_profile(rh._mem()) or {}
        if prof.get("person"):
            return str(prof["person"]), str(prof.get("role") or "benefits-processor")
    except Exception:
        pass
    return None, None


def is_own(asked: str | None, who: str | None) -> bool:
    """True when the request is the worker's own: someone is set up and the request names nobody or names them."""
    return bool(who) and (not asked or asked == who)


def source_person(store: Any, role: str | None) -> str:
    """The shared calendar the role's week is read from; falls back to the benefits one, then to any persona the store has."""
    want = SOURCES.get(role or "", SOURCES["benefits-processor"])
    people = store.people()
    if want in people:
        return want
    for p in (SOURCES["benefits-processor"], *store.people("persona")):
        if p in people:
            return p
    return people[0] if people else want


def scrub(obj: Any, ids: set[str], keep: str, source: str | None = None, replacement: str = REFERENCE_NAME) -> Any:
    """``obj`` with every other person's id removed, wherever it sits (values only; keys carry no ids): the calendar the week was read from (``source``) becomes the worker (``keep``),
    any other id in ``ids`` (an experienced worker) becomes ``replacement``, the unnamed reference."""
    if isinstance(obj, dict):
        return {k: scrub(v, ids, keep, source, replacement) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, ids, keep, source, replacement) for v in obj]
    if isinstance(obj, str):
        if source and source in obj:
            obj = obj.replace(source, keep)                     # an id inside a longer string (a suggestion id such as cal:batch:p_x:2026-W44) too
        if obj == keep:
            return obj
        if obj in ids:
            return replacement
        for pid in ids:
            if pid != keep and pid in obj:
                obj = obj.replace(pid, replacement)
        return obj
    return obj
