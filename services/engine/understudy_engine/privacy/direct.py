"""Metadata-only ledger lines for model calls the worker asked for through other paths (an agent run, the coach).

``LedgeredPort(port)`` wraps any ``ModelPort``. Every call is forwarded unchanged and one ledger line is written first:
``kind: "direct"``, the method, the model id and the byte count of the request, with ``payload: null`` and
``content_logged: false``. The content of those calls is raw (page text, screenshots) and must never be copied into a ledger,
so the line says that a call happened, when, to which model and how big, and nothing else.

This does NOT make those calls safe or generalised: they are the existing, worker-requested paths with their own protections
(the quarantined reader, SEC-1 to SEC-12). It only makes the Privacy screen's claim true that such calls are listed too.
Wrapping is the integrator's decision (``wrap_if_enabled`` is the one-line hook); nothing in the extension layers uses it,
because they must go through ``egress.send`` instead (the static guard enforces that).

If the ledger line cannot be written the call is NOT made (fail closed), same as ``egress.send``.
"""
from __future__ import annotations

import json
from typing import Any

from . import flags, ledger


def _size(*parts: Any) -> int:
    n = 0
    for p in parts:
        if isinstance(p, (bytes, bytearray)):
            n += len(p)
        elif isinstance(p, str):
            n += len(p.encode("utf-8", "replace"))
        else:
            try:
                n += len(json.dumps(p, default=str, ensure_ascii=True).encode())
            except (TypeError, ValueError):
                n += len(repr(p).encode())
    return n


class LedgeredPort:
    """Forward every call to ``inner`` after writing one metadata-only ledger line."""

    def __init__(self, inner: Any, *, purpose: str = "worker_requested") -> None:
        self._inner = inner
        self._purpose = purpose
        self.name = getattr(inner, "name", type(inner).__name__)
        self.offline = bool(getattr(inner, "offline", False))

    def __getattr__(self, item: str) -> Any:      # models, stats, calls ... of the wrapped port
        return getattr(self._inner, item)

    def _model(self, method: str) -> str:
        models = getattr(self._inner, "models", None)
        key = {"plan": "planner", "read": "fast", "check": "fast", "vision": "fast", "computer_step": "computer_use"}.get(method)
        mid = getattr(models, key, None) if models is not None and key else None
        return f"{self.name}:{mid}" if mid else str(self.name)

    def _log(self, method: str, nbytes: int) -> None:
        mock = self.offline or str(self.name) in ("mock", "capturing")
        ledger.record_direct(method=method, model=self._model(method), bytes_sent=nbytes, purpose=self._purpose, mock=mock)

    def _guard(self, method: str, nbytes: int) -> None:
        try:
            self._log(method, nbytes)
        except OSError:
            raise RuntimeError("The privacy ledger could not be written, so the model call was not made.") from None

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> Any:
        self._guard("plan", _size(messages, schema))
        return self._inner.plan(messages, schema)

    def read(self, untrusted: str, schema: dict[str, Any]) -> Any:
        self._guard("read", _size(untrusted, schema))
        return self._inner.read(untrusted, schema)

    def check(self, prompt: str, schema: dict[str, Any]) -> Any:
        self._guard("check", _size(prompt, schema))
        return self._inner.check(prompt, schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> Any:
        self._guard("vision", _size(image, prompt, schema))
        return self._inner.vision(image, prompt, schema)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]], **kw: Any) -> Any:
        self._guard("computer_step", _size(goal, screenshot, history))
        return self._inner.computer_step(goal, screenshot, history, **kw)


def wrap_if_enabled(port: Any) -> Any:
    """``port`` wrapped in a ``LedgeredPort`` when the privacy extension is on, else ``port`` itself (the P0 path unchanged)."""
    if flags.enabled("privacy") and not isinstance(port, LedgeredPort):
        return LedgeredPort(port)
    return port
