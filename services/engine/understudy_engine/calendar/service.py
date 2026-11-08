"""Assembles the calendar API payloads from the store, the expert reference and the suggestion catalogue. No text anywhere: every
value is a number, a boolean or an enum. ``routes_calendar`` is a thin wrapper over these functions."""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Any

from . import suggest as sug
from .expert import ALL_KEYS, ExpertReference, build_reference, gap_rows, load_template
from .features import week_blocks_json
from .model import parse_week, week_label
from .store import CalendarStore, PersonCalendar

_lock = threading.Lock()


class CalendarError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def reference_for(store: CalendarStore, role: str) -> ExpertReference:
    """The expert reference for a role: the expert cohort in the store when it has one, else the role's template week. Cached on the store."""
    cache = store.__dict__.setdefault("_refs", {})
    with _lock:
        if role not in cache:
            cohort = [pc for pc in store.cohort("expert") if pc.role == role]
            cache[role] = build_reference(role, cohort)
        return cache[role]


def resolve(store: CalendarStore, person: str, week: str | None) -> tuple[PersonCalendar, date]:
    pc = store.get(person)
    if pc is None:
        known = ", ".join(store.people()[:6])
        raise CalendarError(404, "unknown_person", f"No calendar for {person!r}. Try one of: {known}, ...")
    if not pc.weeks:
        raise CalendarError(404, "no_data", f"The calendar for {person!r} has no events.")
    try:
        monday = parse_week(week) if week else pc.weeks[-1]
    except (ValueError, TypeError):
        raise CalendarError(422, "bad_week", "week must look like 2026-W44 or a date such as 2026-10-26.") from None
    if monday not in pc.weeks:
        have = ", ".join(week_label(m) for m in pc.weeks)
        raise CalendarError(404, "no_such_week", f"{person!r} has no events in {week_label(monday)}. Weeks with data: {have}.")
    return pc, monday


def _round(f: dict[str, Any]) -> dict[str, Any]:
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()}


def week_report(store: CalendarStore, person: str, week: str | None = None, *, n_boot: int = 300) -> dict[str, Any]:
    pc, monday = resolve(store, person, week)
    wa = pc.week(monday)
    ref = reference_for(store, pc.role)
    exclude = person if person in ref.people else None            # an expert is compared with the others (the placebo case)
    ex_week, rib = ref.nearest(wa, exclude=exclude)
    rows = gap_rows(wa.features, ref, exclude=exclude, n_boot=n_boot)
    placebo = ref.placebo(n_boot=min(n_boot, 300))
    ref_feats = ref.features(exclude)
    ex_label = ex_week.person if ref.source == "cohort" else "template"
    expert = {k: round(ref_feats[k], 2) for k in ALL_KEYS}
    expert.update({"days": week_blocks_json(ex_week.wa), "person": ex_label, "week": week_label(ex_week.monday), "source": ref.source,
                   "n_experts": ref.n_experts - (1 if exclude else 0) if ref.source == "cohort" else 0,
                   "reference": ("mean over the expert cohort; the ribbon is the nearest expert week" if ref.source == "cohort"
                                 else "the role template's own week (no expert cohort for this role)")})
    return {
        "person": person, "role": pc.role, "group": pc.group, "week": week_label(monday), "weeks_available": [week_label(m) for m in pc.weeks],
        "timezone": pc.work.tz_name,
        "days": week_blocks_json(wa),
        "features": _round(wa.features),
        "expert": expert,
        "gap": {"rows": rows, "interval": ("cluster bootstrap over experts (uncertainty in the reference only)" if ref.source == "cohort"
                                           else "none: a template has no spread"),
                "ribbon": {"distance": rib.distance, "placebo": placebo, "nearest_expert": ex_label, "alignment": rib.rows(40)}},
        "counts": {"events_read": pc.stats.read, "blocks": pc.stats.blocks, "cancelled_ignored": pc.stats.cancelled,
                   "declined_ignored": pc.stats.declined, "free_time_ignored": pc.stats.free_skipped},
    }


def week_meta(report: dict[str, Any], origin: str = "synthetic") -> dict[str, Any]:
    src = report["expert"]["source"]
    note = ("Generated calendar with planted structure; the expert reference is " + (f"{report['expert']['n_experts']} experts generated from the role template. "
            if src == "cohort" else "the role template only. ") +
            "Intervals cover the uncertainty in the expert reference only. Nothing here is validated on real people.")
    return {"origin": origin, "n": report["features"]["days_worked"], "n_unit": "days", "split": None, "interval_level": 0.95, "note": note,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def suggestions_report(store: CalendarStore, person: str, week: str | None = None, *, reword: bool = False, port: Any = None,
                       max_n: int | None = None) -> dict[str, Any]:
    pc, monday = resolve(store, person, week)
    tpl = load_template(pc.role)
    ref = reference_for(store, pc.role)
    exclude = person if person in ref.people else None
    weeks = [pc.week(m) for m in pc.weeks if m <= monday]
    feats = weeks[-1].features
    history = [w.features for w in weeks]
    out = sug.suggest(feats, ref.features(exclude), tpl.targets, history=history, person=person, week=week_label(monday), max_n=max_n,
                      days_expected=len(tpl.work.days))
    if reword:
        out = [sug.reword(s, pc.role, ref.features(exclude), feats, port=port) for s in out]
    return {"person": person, "week": week_label(monday), "suggestions": out, "n_weeks": len(weeks), "role": pc.role,
            "reference": ref.source, "reworded": reword}


def suggestions_meta(rep: dict[str, Any], origin: str = "synthetic") -> dict[str, Any]:
    return {"origin": origin, "n": rep["n_weeks"], "n_unit": "days", "split": None, "interval_level": 0.95,
            "note": ("Chosen by code from fixed thresholds against the expert reference; text is templated" + (" and may be reworded from bucketed aggregates only" if rep["reworded"] else "")
                     + ". Generated calendar; every suggestion is opt-in and low risk."),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
