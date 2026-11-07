"""Fakes for the models tests: a scripted Gemini client, a scripted routing backend, a fake clock, a synthetic image."""
from __future__ import annotations

import json
from typing import Any

from understudy_agent.models.gemini_http import GeminiReply
from understudy_agent.models.imaging import make_test_png, prepare_frame
from understudy_agent.models.routing import BackendOut
from understudy_engine.privacy.image import ImageGate, SafeImage

SECRET_PIXELS = b"SECRET-PIXELS-MARKER"   # never appears in any record, error or repr; used by the leak tests


def make_image(kind: str = "point", source: str = "sandbox", label: str = "Calculate") -> SafeImage:
    return SafeImage(prepare_frame(make_test_png(1280, 800, label)), kind, source=source)


def sandbox_gate(**kw: Any) -> ImageGate:
    base = dict(consent=False, denylisted_app=False, secure_input=False, unattended=True, source="sandbox")
    base.update(kw)
    return ImageGate(**base)  # type: ignore[arg-type]


POINT_OK = {"found": True, "confidence": 0.95, "box_2d": [419, 419, 501, 581]}
POINT_NONE = {"found": False, "confidence": 0.9}


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def reply(obj: Any, *, tin: int | None = 1200, tout: int | None = 40, think: int | None = 0, ms: int = 100,
          model: str = "m", calls: tuple[dict[str, Any], ...] = ()) -> GeminiReply:
    return GeminiReply(text=obj if isinstance(obj, str) else json.dumps(obj), input_tokens=tin, output_tokens=tout,
                       thought_tokens=think, latency_ms=ms, api="interactions", model=model, finish="completed", calls=calls)


class FakeGeminiClient:
    """Scripted stand-in for GeminiClient: pops one reply (or raises one exception) per generate()."""

    api = "interactions"

    def __init__(self, *replies: Any) -> None:
        self.queue = list(replies)
        self.calls: list[dict[str, Any]] = []

    def generate(self, model: str, parts: list[Any], **kw: Any) -> GeminiReply:
        self.calls.append({"model": model, "parts": parts, **kw})
        r = self.queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def list_models(self) -> dict[str, list[str]]:  # pragma: no cover - not used here
        return {}


class FakeBackend:
    """A routing backend that replays a script per tier. An item is a dict answer, an Exception, or ("clock", seconds, item)."""

    def __init__(self, provider: str, script: dict[str, list[Any]], *, models: dict[str, str] | None = None,
                 available: bool = True, clock: Clock | None = None) -> None:
        self.provider = provider
        self.script = {k: list(v) for k, v in script.items()}
        self.models = models or {"fast": f"{provider}-fast", "accurate": f"{provider}-accurate"}
        self._available = available
        self.clock = clock
        self.calls: list[dict[str, Any]] = []

    def available(self) -> bool:
        return self._available

    def model_for(self, tier: str) -> str:
        return self.models[tier]

    def vision(self, tier: str, image: bytes, prompt: str, schema: dict[str, Any], *, thinking: Any, timeout_s: float) -> BackendOut:
        self.calls.append({"tier": tier, "prompt": prompt, "schema": schema, "timeout_s": timeout_s, "n_bytes": len(image)})
        item = self.script[tier].pop(0)
        if isinstance(item, tuple) and item[0] == "clock":
            if self.clock:
                self.clock.advance(item[1])
            item = item[2]
        if isinstance(item, BaseException):
            raise item
        return BackendOut(item, 1000, 40, 0, "interactions")
