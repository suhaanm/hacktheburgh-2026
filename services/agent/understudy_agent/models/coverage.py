"""Ledger coverage: which provider instances exist, how each is reached, and how many calls went around the ledger.

Every remote model call must leave a metadata-only ledger line. The paths are:

* `factory`  a port from `get_model_port()` (wrapped in the privacy track's `LedgeredPort`: one line per call; mock ports excepted),
* `egress`   a one-step port handed to `egress.send_image` / `egress.send` (the guard writes the row itself),
* `direct`   anything else: a provider object built by hand. The bake-off does this on purpose (synthetic sandbox screenshots only).

Providers register themselves on construction as `direct`; the factory and the router's backends re-label them. `snapshot()` counts the
calls made by `direct` providers: `all_ledgered` is true only when that number is zero. No content, no key: names, paths and counts.
"""
from __future__ import annotations

import threading
import weakref
from typing import Any

_lock = threading.Lock()
_items: list[tuple[weakref.ReferenceType[Any], str]] = []
_paths: dict[int, str] = {}


def register(provider: Any, path: str = "direct") -> None:
    with _lock:
        _paths[id(provider)] = path
        _items.append((weakref.ref(provider), str(getattr(provider, "name", type(provider).__name__))))


def mark(provider: Any, path: str) -> Any:
    """Say how a provider is reached (`factory` or `egress`). Returns the provider."""
    with _lock:
        _paths[id(provider)] = path
    return provider


def snapshot() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with _lock:
        live = [(ref(), name) for ref, name in _items]
        for obj, name in live:
            if obj is None:
                continue
            calls = int((getattr(obj, "stats", None) or {}).get("calls", 0))
            rows.append({"provider": name, "path": _paths.get(id(obj), "direct"), "calls": calls})
    direct_calls = sum(r["calls"] for r in rows if r["path"] == "direct")
    return {
        "providers": rows, "unledgered_calls": direct_calls, "all_ledgered": direct_calls == 0,
        "note": ("get_model_port() wraps every non-mock port so each call writes one metadata-only ledger line; image calls go through "
                 "egress.send_image (the row is written before the send); a provider built by hand ('direct') is not ledgered and its "
                 "calls are counted in unledgered_calls"),
    }


def reset() -> None:
    with _lock:
        _items.clear()
        _paths.clear()
