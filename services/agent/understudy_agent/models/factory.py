"""get_model_port(): choose the provider from the environment.

UNDERSTUDY_MOCK=1            -> MockProvider (scenario from UNDERSTUDY_MOCK_SCENARIO, default benefits_clean)
UNDERSTUDY_PROVIDER=gemini   -> GeminiProvider (needs GEMINI_API_KEY and GEMINI_MODEL_FAST / _ACCURATE; the default, D49)
UNDERSTUDY_PROVIDER=openai   -> OpenAIProvider (explicit opt-in only; model ids from OPENAI_MODEL_* env)
otherwise                    -> GeminiProvider (D49: the default)

Every remote call that bypasses the runtime still leaves a metadata-only ledger line: the port is ALWAYS returned inside
`understudy_engine.privacy.direct.LedgeredPort` (one line per call: purpose, model, byte count, never prompt text, page text, images or
replies), whatever the extension flags say (REVIEW-PRIVACY finding, 7 Nov). Exceptions, on purpose:

* a mock port (UNDERSTUDY_MOCK=1) makes no remote call, so it is returned unchanged unless the privacy flag is on (then it is wrapped
  and its lines are marked mock) or `UNDERSTUDY_LEDGER_MOCK_CALLS=1`;
* `ledgered=False`, and any call made from inside `understudy_engine.privacy.egress` (`send`, `send_image` resolve their default port
  here): the guard writes its own row, and a second line for the same call would be a duplicate.

The wrapper passes `last_call`, `model_for` and every ModelPort method through.
"""
from __future__ import annotations

import os
import sys
import threading

from . import coverage
from .config import mock_enabled
from .port import ModelPort

# D49 (owner, 7 Nov 2026): the OpenAI key was revoked and every role moved to Gemini. OpenAI stays in the code as an explicit opt-in
# (UNDERSTUDY_PROVIDER=openai) and is never the default. Argon (gemini-4-argon) is never configured for any role (see models/config.py).
DEFAULT_PROVIDER = "gemini"
_lock = threading.Lock()
_cache: dict[tuple[str, str], ModelPort] = {}


def get_model_port(*, mock: bool | None = None, scenario: str | None = None, provider: str | None = None,
                   fresh: bool = False, ledgered: bool = True) -> ModelPort:
    """Return the configured ModelPort. Cached per (provider, scenario); `fresh=True` builds a new instance
    (tests that script a mock should use `fresh=True` or construct `MockProvider` directly). With the privacy extension on
    (`UNDERSTUDY_X_PRIVACY` or `UNDERSTUDY_X`) the port is wrapped to write one metadata-only ledger line per call, unless
    `ledgered=False`."""
    use_mock = mock_enabled() if mock is None else mock
    port = _get_raw_port(mock=mock, scenario=scenario, provider=provider, fresh=fresh)
    if not ledgered or _called_from_egress():
        return port
    from understudy_engine.privacy import flags
    from understudy_engine.privacy.direct import LedgeredPort

    if use_mock and not (flags.enabled("privacy") or _env_on("UNDERSTUDY_LEDGER_MOCK_CALLS")):
        return port                                                   # nothing leaves in mock mode: the demo path is unchanged
    return port if isinstance(port, LedgeredPort) else LedgeredPort(port)


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _called_from_egress() -> bool:
    """True when `get_model_port()` was called by the egress guard itself (it resolves its default port here and writes its own row)."""
    try:
        return sys._getframe(2).f_globals.get("__name__", "") == "understudy_engine.privacy.egress"
    except ValueError:  # pragma: no cover - no caller frame
        return False


def _get_raw_port(*, mock: bool | None, scenario: str | None, provider: str | None, fresh: bool) -> ModelPort:
    use_mock = mock_enabled() if mock is None else mock
    if use_mock:
        from .mock_provider import DEFAULT_SCENARIO, MockProvider

        sc = scenario or os.environ.get("UNDERSTUDY_MOCK_SCENARIO", "").strip() or DEFAULT_SCENARIO
        key = ("mock", sc)
        build = lambda: MockProvider(sc)  # noqa: E731
    else:
        prov = (provider or os.environ.get("UNDERSTUDY_PROVIDER", "").strip() or DEFAULT_PROVIDER).lower()
        key = (prov, "")
        if prov == "openai":
            from .openai_provider import OpenAIProvider

            build = lambda: coverage.mark(OpenAIProvider(), "factory")  # type: ignore[assignment]  # noqa: E731
        elif prov == "gemini":
            from .gemini_provider import GeminiProvider

            build = lambda: coverage.mark(GeminiProvider(), "factory")  # type: ignore[assignment]  # noqa: E731
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
