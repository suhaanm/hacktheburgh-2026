"""FastAPI router for the voice module. agent-core's server.py includes it if importable:

    POST /voice/speak  {text, kind: "nudge"|"briefing"}  -> audio bytes (audio/mpeg, or audio/wav silence)
    GET  /voice/status -> {enabled, mock, voice_configured, voice}

Response headers say where the audio came from (X-Voice-Source) so a client can tell silence from speech.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from . import tts

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["nudge", "briefing"] = "nudge"


@router.post("/speak")
def speak_endpoint(body: SpeakIn) -> Response:
    res = tts.speak_detailed(body.text, body.kind)
    return Response(content=res.audio, media_type=res.mime, headers={"X-Voice-Source": res.source, "Cache-Control": "no-store"})


@router.get("/status")
def status_endpoint() -> dict:
    return tts.status()
