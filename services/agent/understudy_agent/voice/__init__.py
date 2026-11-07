"""Optional narration (P2, off by default). See tts.py. `router` is a FastAPI APIRouter for the agent server."""
from .router import router
from .tts import prewarm, speak, speak_detailed, status

__all__ = ["prewarm", "router", "speak", "speak_detailed", "status"]
