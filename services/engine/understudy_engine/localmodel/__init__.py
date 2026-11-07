"""Local model and digests (REQ-2, LOC-1 to LOC-3): raw git and calendar items become safe digests on this Mac.

The fixed interface other tracks call:

    from understudy_engine.localmodel import mode                       # "model" | "rules"
    from understudy_engine.localmodel.digest import commit_digest, event_digest

Everything is off by default: the model is used only when ``UNDERSTUDY_X_LOCALMODEL=1`` (or ``UNDERSTUDY_X=1``), never in mock
mode, and any missing piece falls back to the deterministic rules in ``rules.py``. Importing this package starts nothing.
"""
from __future__ import annotations

from typing import Any

from .server import get_server, mode, shutdown

__all__ = ["mode", "shutdown", "get_server", "commit_digest", "event_digest", "evaluate_localmodel"]


def commit_digest(items: Any) -> list[dict[str, Any]]:
    from .digest import commit_digest as f

    return f(items)


def event_digest(items: Any) -> list[dict[str, Any]]:
    from .digest import event_digest as f

    return f(items)


def evaluate_localmodel(fast: bool = False) -> dict[str, Any]:
    from .evaluate import evaluate_localmodel as f

    return f(fast=fast)
