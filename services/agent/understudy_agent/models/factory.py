"""get_model_port(): choose the provider from the environment.

UNDERSTUDY_MOCK=1            -> MockProvider (scenario from UNDERSTUDY_MOCK_SCENARIO, default benefits_clean)
UNDERSTUDY_PROVIDER=gemini   -> GeminiProvider stub (needs GEMINI_API_KEY)
otherwise                    -> OpenAIProvider (model ids from OPENAI_MODEL_* env)
"""
from __future__ import annotations

import os
import threading

from .config import mock_enabled
from .port import ModelPort

_lock = threading.Lock()
_cache: dict[tuple[str, str], ModelPort] = {}


def get_model_port(*, mock: bool | None = None, scenario: str | None = None, provider: str | None = None,
                   fresh: bool = False) -> ModelPort:
    """Return the configured ModelPort. Cached per (provider, scenario); `fresh=True` builds a new instance
    (tests that script a mock should use `fresh=True` or construct `MockProvider` directly)."""
    use_mock = mock_enabled() if mock is None else mock
    if use_mock:
        from .mock_provider import DEFAULT_SCENARIO, MockProvider

        sc = scenario or os.environ.get("UNDERSTUDY_MOCK_SCENARIO", "").strip() or DEFAULT_SCENARIO
        key = ("mock", sc)
        build = lambda: MockProvider(sc)  # noqa: E731
    else:
        prov = (provider or os.environ.get("UNDERSTUDY_PROVIDER", "").strip() or "openai").lower()
        key = (prov, "")
        if prov == "openai":
            from .openai_provider import OpenAIProvider

            build = OpenAIProvider  # type: ignore[assignment]
        elif prov == "gemini":
            from .gemini_provider import GeminiProvider

            build = GeminiProvider  # type: ignore[assignment]
        else:
            raise ValueError(f"unknown provider {prov!r}; use openai, gemini or set UNDERSTUDY_MOCK=1")
    if fresh:
        return build()
    with _lock:
        if key not in _cache:
            _cache[key] = build()
        return _cache[key]


def reset_model_port() -> None:
    with _lock:
        _cache.clear()
