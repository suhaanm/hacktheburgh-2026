"""FastAPI router for the voice module. agent-core's server.py includes it if importable:

    POST /voice/speak  {line_id, slots?}          -> audio bytes (audio/mpeg, or audio/wav silence)   THE way to speak
    POST /voice/speak  {text, kind}               -> 422 free_text_refused, unless UNDERSTUDY_VOICE_DEBUG_TEXT=1 (worker-only debug)
    GET  /voice/lines                             -> the fixed line ids and the shape of their slots (no free text is ever a slot)
    GET  /voice/status -> {enabled, mock, voice_configured, voice, free_text, cache_hits}

A caller names a fixed line and typed slots (bounded numbers, ids from a closed set); the sentence is produced in code (lines.py), so
nothing a caller sends can carry a name, an address or screen text to the speech service. Every real call to that service writes a
metadata-only ledger row. Response headers say where the audio came from (X-Voice-Source) so a client can tell silence from speech.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import lines, tts

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakIn(BaseModel):
    # extra fields are refused: a caller cannot smuggle text in under another name.
    model_config = ConfigDict(extra="forbid")
    line_id: str | None = Field(default=None, max_length=90)
    slots: dict[str, int | str] | None = None
    # Free text exists only for the debug flag; with the flag off it is a 422 whatever the voice setting.
    text: str | None = Field(default=None, max_length=4000)
    kind: Literal["nudge", "briefing"] = "nudge"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@router.post("/speak")
def speak_endpoint(body: SpeakIn) -> Response:
    if body.line_id is not None and body.text is not None:
        return _error(422, "ambiguous", "Send either line_id or text, not both.")
    if body.line_id is None and body.text is None:
        return _error(422, "no_line", "Send a line_id (see GET /voice/lines).")
    if body.line_id is not None:
        if body.slots is not None:
            for k, v in body.slots.items():
                # A string slot is an id from a closed set: short, lower-case. Anything else is refused before it is looked at.
                if isinstance(v, str) and (len(v) > 40 or not v.replace("_", "").replace("-", "").replace(".", "").isalnum() or v != v.lower()):
                    return _error(422, "bad_slot", "A string slot must be an id from the line's list.")
        try:
            res = tts.speak_line(body.line_id, body.slots)
        except lines.LineError as e:
            return _error(422, e.code, str(e))
    else:
        if not tts.debug_text_enabled():
            return _error(422, "free_text_refused", "Free-form text is not spoken. Ask for a fixed line by id (GET /voice/lines).")
        if not body.text:
            return _error(422, "no_line", "The text is empty.")
        try:
            res = tts.speak_detailed(body.text, body.kind)
        except tts.FreeTextRefused:
            return _error(422, "free_text_refused", "Free-form text is not spoken. Ask for a fixed line by id (GET /voice/lines).")
    return Response(content=res.audio, media_type=res.mime, headers={"X-Voice-Source": res.source, "Cache-Control": "no-store"})


@router.get("/lines")
def lines_endpoint() -> dict:
    return {"data": lines.catalogue()}


@router.get("/status")
def status_endpoint() -> dict:
    return {**tts.status(), **tts.diagnostics()}
