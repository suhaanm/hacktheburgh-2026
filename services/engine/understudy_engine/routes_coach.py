"""Live coach routes (COA-3, COA-4). ``api/app.py`` includes ``router`` when importable.

  GET  /coach/next?person=&now=&ask=&dry=&tone=   one CoachDecision for the person's open task  -> {meta, data}
  POST /coach/feedback                             {decision_id, outcome: followed|dismissed|repeated|undone}

No model call: the expert policy, the dignity gate and the level engine decide (PR1). Polling advances the gate (two
consecutive signals, then a cooldown), so the desktop should poll at a steady pace; ``dry=1`` changes nothing and is
for screens that only want to look. ``now`` is for replays of recorded data; the default is the wall clock.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from . import http_guard
from pydantic import BaseModel, ConfigDict

from .api.errors import ApiError
from .coach import CoachBrain, CoachError
from .core import AnalyticMeta

router = APIRouter(tags=["coach"])


def brain(request: Request) -> CoachBrain:
    b = getattr(request.app.state, "coach", None)
    if b is None:
        b = request.app.state.coach = CoachBrain(request.app.state.store)
    return b


def _parse_now(now: str | None) -> datetime | None:
    if not now:
        return None
    try:
        dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "bad_now", "now must be an ISO-8601 time such as 2026-11-07T09:30:00Z.")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/coach/next")
def coach_next(request: Request, person: str, now: str | None = None, ask: bool = False, dry: bool = False,
               tone: Literal["short", "detailed"] | None = None):
    b = brain(request)
    try:
        d = b.next_step(person, _parse_now(now), commit=not dry, ask=ask, tone=tone)
    except CoachError as exc:
        raise ApiError(exc.status, exc.code, exc.message)
    st = b._people.get(person)           # noqa: SLF001 - read the person's origin for the meta
    origin = st.origin if st else "real"
    meta = AnalyticMeta(
        origin=origin, n=1, n_unit="episodes", split=None, generated_at=datetime.now(timezone.utc),
        note="Rule-based, no model call: the expert policy, the dignity gate and the level engine decide. "
             + ("Recorded traces." if origin == "synthetic" else "Live events."),
    ).model_dump(mode="json")
    return {"meta": meta, "data": d.to_dict()}


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str
    outcome: Literal["followed", "dismissed", "repeated", "undone"]
    now: str | None = None


@router.post("/coach/feedback")
def coach_feedback(request: Request, body: Feedback):
    try:
        return brain(request).feedback(body.decision_id, body.outcome, _parse_now(body.now))
    except CoachError as exc:
        raise ApiError(exc.status, exc.code, exc.message)


# ------------------------------------------------------------------------------------------------ study mode
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _study_guard(request: Request) -> None:
    """Study mode changes what the coach does, so like every other write it is the worker's (or the facilitator's own) action:
    from this machine, naming the worker actor, and from the Understudy app, never from page content."""
    from .memory.store import WORKER_ACTORS

    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise ApiError(403, "write_refused", "Study mode can only be changed from this machine.")
    actor = http_guard.actor_of(request)
    if actor not in WORKER_ACTORS:
        raise ApiError(403, "write_refused", f"Only the worker or the facilitator can change study mode; the actor {actor[:20]!r} cannot.")
    origin = request.headers.get("origin")
    if origin is not None and not http_guard.origin_allowed(origin):
        raise ApiError(403, "write_refused", "Writes only come from the Understudy app on this machine.")


class StudyModeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person: str
    block: Literal["train", "post_test", "off"]
    skill_on: str | None = None
    level: Literal["L1", "L2", "L3", "L4"] = "L1"
    steps_off: list[str] | None = None
    participant: str | None = None
    block_no: int | None = None


@router.get("/study/mode")
def get_study_mode():
    from .study import read_state

    mode = read_state()
    return {"active": mode is not None, "mode": mode.to_dict() if mode else None}


@router.post("/study/mode")
def set_study_mode(request: Request, body: StudyModeBody):
    from .study import StudyError, write_state

    _study_guard(request)
    try:
        mode = write_state(body.person, body.block, body.skill_on, body.level, steps_off=body.steps_off,
                           participant=body.participant, block_no=body.block_no)
    except StudyError as exc:
        raise ApiError(422, "invalid_study_mode", str(exc))
    return {"active": True, "mode": mode.to_dict()}


@router.post("/study/mode/clear")
def clear_study_mode(request: Request):
    from .study import clear_state

    _study_guard(request)
    return {"active": False, "cleared": clear_state(), "mode": None}
