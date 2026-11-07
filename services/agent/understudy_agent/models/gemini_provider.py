"""Optional Gemini provider: a stub. It exists so the factory can name it when GEMINI_API_KEY is set; every call
raises a clear error. OpenAI is the primary provider (D14). Implement only if time remains and a key exists."""
from __future__ import annotations

import os
from typing import Any

from .errors import ConfigError, ProviderError
from .port import Action, Done, SafetyStop


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            raise ConfigError("GEMINI_API_KEY is not set; the Gemini provider is optional and only a stub.")

    def _nope(self) -> Any:
        raise ProviderError("The Gemini provider is an optional stub and is not implemented. Use OpenAI or mock.")

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._nope()

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self._nope()

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self._nope()

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._nope()

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]],
                      *, session: str | None = None) -> Action | Done | SafetyStop:
        return self._nope()
