"""Calendar routes (CAL-2, CAL-3). ``api/app.py`` includes ``router`` when importable; the router answers 404 unless
``UNDERSTUDY_X_CALENDAR=1`` or ``UNDERSTUDY_X=1`` (checked on every request, so it is safe to include unconditionally).

  GET /calendar/week?person=&week=            the week ribbon: blocks per day, features, expert reference and nearest expert week,
                                               feature gaps with intervals, ribbon distance and placebo
  GET /calendar/suggestions?person=&week=     catalogue suggestions chosen by code, each with its numbers and the expert reference
  GET /calendar/people                        who has a calendar (additive)
  GET /calendar/catalogue                     the fixed suggestion catalogue (additive)

Every analytic GET returns ``{meta, data}`` (docs/API_CONTRACT.md). Nothing here carries a title, a name, an address or any text from
a calendar: values are numbers, booleans and enums. Nothing here calls a model unless ``reword=1`` is asked for and the privacy layer
is on; the wording then goes through ``privacy.egress`` from bucketed aggregates only (templated text otherwise).
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .calendar import flag_enabled, service, suggest
from .calendar.store import CalendarStore, default_store

router = APIRouter(tags=["calendar"])
DEFAULT_PERSON = "p_ninetofive"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse:
    return _error(404, "not_found", "The calendar layer is off. Set UNDERSTUDY_X_CALENDAR=1 (or UNDERSTUDY_X=1) to turn it on.")


def _store() -> CalendarStore:
    return default_store()


@router.get("/calendar/week")
def get_week(person: str = Query("", description="person id; default is the demo persona"), week: str = Query("", description="2026-W44 or a date")):
    if not flag_enabled():
        return _off()
    try:
        rep = service.week_report(_store(), person or DEFAULT_PERSON, week or None)
    except service.CalendarError as exc:
        return _error(exc.status, exc.code, exc.message)
    return {"meta": service.week_meta(rep), "data": rep}


def _reword_allowed() -> bool:
    try:
        from .privacy import flags
        return flags.enabled("privacy")
    except ImportError:                                     # pragma: no cover
        return False


@router.get("/calendar/suggestions")
def get_suggestions(person: str = Query(""), week: str = Query(""), reword: int = Query(0, ge=0, le=1), limit: int = Query(0, ge=0, le=20)):
    if not flag_enabled():
        return _off()
    do_reword = bool(reword) and _reword_allowed()
    try:
        rep = service.suggestions_report(_store(), person or DEFAULT_PERSON, week or None, reword=do_reword, max_n=limit or None)
    except service.CalendarError as exc:
        return _error(exc.status, exc.code, exc.message)
    meta = service.suggestions_meta(rep)
    if reword and not do_reword:
        meta["note"] += " Rewording was asked for but the privacy layer is off, so the templated text is shown."
    return {"meta": meta, "data": rep["suggestions"]}


@router.get("/calendar/people")
def get_people():
    if not flag_enabled():
        return _off()
    st = _store()
    from .calendar.model import week_label
    rows = []
    for p in st.people():
        info = st.info(p) or {}
        pc = st.get(p)
        rows.append({"person": p, "group": info.get("group"), "role": info.get("role"), "label": info.get("label"),
                     "weeks": [week_label(m) for m in (pc.weeks if pc else [])]})
    return {"meta": {"origin": "synthetic", "n": len(rows), "n_unit": "people", "split": None, "interval_level": 0.95,
                     "note": "Synthetic calendars: 4 personas, 8 experts, 16 novices.", "generated_at": None}, "data": rows}


@router.get("/calendar/catalogue")
def get_catalogue():
    if not flag_enabled():
        return _off()
    return {"meta": {"origin": "synthetic", "n": len(suggest.TEMPLATES), "n_unit": "decisions", "split": None, "interval_level": 0.95,
                     "note": "The fixed suggestion catalogue; code selects, the model may only reword from safe aggregates.", "generated_at": None},
            "data": suggest.catalogue()}
