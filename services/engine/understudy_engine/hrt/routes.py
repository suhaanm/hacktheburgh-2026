"""HRT routes: the live prediction ledger. Flag ``UNDERSTUDY_X_HRT=1`` or ``UNDERSTUDY_X=1`` (api/flags.py), 404 ``extension_off`` otherwise.

    GET  /hrt/ledger                    counts per origin and kind, the head hash, and whether each chain still verifies
    POST /hrt/ledger/predictions        {origin, kind, subject, horizon_s, forecasts, primary, version?, unit?}  -> {pid, made_at, origin}
    POST /hrt/ledger/outcomes           {origin, pid, outcome}                                                   -> {pid, resolved_at, origin}
    GET  /hrt/ledger/score?origin=&kind=   log loss, Brier, ECE, reliability and calibration of the model and each naive predictor, from the
                                        record only; or a refusal that says why (fewer than 200 resolved, a gap, a broken chain)

The engine's clock stamps every entry; a caller cannot send a time. A subject is hashed before it is stored. No text is stored or returned.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .ledger import KINDS, LedgerError
from .live import ORIGINS, live_ledgers

router = APIRouter(tags=["hrt"])
FLAG = "UNDERSTUDY_X_HRT"


def enabled() -> bool:
    from understudy_engine.api.flags import env_on

    return env_on(FLAG) or env_on("UNDERSTUDY_X")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse:
    return _error(404, "extension_off", "The HRT layer is off. Set UNDERSTUDY_X_HRT=1 (or UNDERSTUDY_X=1) and restart the engine.")


class PredictionIn(BaseModel):
    origin: str = Field(pattern=r"^(real|synthetic)$")
    kind: str = Field(pattern=r"^(stuck_hazard|time_to_progress|error_risk)$")
    subject: str = Field(min_length=1, max_length=120)
    horizon_s: float = Field(gt=0, le=86400)
    forecasts: dict[str, Any]
    primary: str = Field(min_length=1, max_length=60)
    version: str = Field(default="", max_length=120)
    unit: str | None = Field(default=None, max_length=120)


class OutcomeIn(BaseModel):
    origin: str = Field(pattern=r"^(real|synthetic)$")
    pid: int = Field(ge=0)
    outcome: Any


@router.get("/hrt/ledger")
def get_ledger():
    if not enabled():
        return _off()
    return {"data": live_ledgers().summary(), "note": "Forecasts are written before their outcomes and scored only from this record. Subjects are hashed; no text is stored."}


@router.post("/hrt/ledger/predictions")
def post_prediction(body: PredictionIn):
    if not enabled():
        return _off()
    try:
        return live_ledgers().predict(body.origin, kind=body.kind, subject=body.subject, horizon_s=body.horizon_s, forecasts=body.forecasts, primary=body.primary,
                                      version=body.version, unit=body.unit)
    except LedgerError as e:
        return _error(422, "ledger_refused", str(e))


@router.post("/hrt/ledger/outcomes")
def post_outcome(body: OutcomeIn):
    if not enabled():
        return _off()
    try:
        return live_ledgers().resolve(body.origin, body.pid, body.outcome)
    except LedgerError as e:
        return _error(422, "ledger_refused", str(e))


@router.get("/hrt/ledger/score")
def get_score(origin: str = "real", kind: str = "stuck_hazard"):
    if not enabled():
        return _off()
    if origin not in ORIGINS or kind not in KINDS:
        return _error(422, "bad_request", f"origin is one of {ORIGINS} and kind one of {KINDS}")
    return {"data": live_ledgers().score(origin, kind)}
