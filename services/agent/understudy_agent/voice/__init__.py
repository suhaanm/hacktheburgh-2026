"""Optional narration (P2, off by default). See tts.py and lines.py. `router` is a FastAPI APIRouter for the agent server.

Callers name a FIXED LINE (`speak_line`, `prewarm_line`); free text is refused unless UNDERSTUDY_VOICE_DEBUG_TEXT=1."""
from .lines import LineError
from .router import router
from .tts import FreeTextRefused, prewarm, prewarm_line, speak, speak_detailed, speak_line, status

__all__ = ["FreeTextRefused", "LineError", "prewarm", "prewarm_line", "router", "speak", "speak_detailed", "speak_line", "status"]
