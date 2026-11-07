"""Feature flags for the extension layers (docs/API_CONTRACT.md, "Extensions API").

``UNDERSTUDY_X=1`` turns every layer on; ``UNDERSTUDY_X_<LAYER>=1`` turns one on. Read on every call, never cached, so
a flag flipped in a test or a restart takes effect at once. Everything is off by default (NFR-10).
"""
from __future__ import annotations

import os

LAYERS = ("privacy", "localmodel", "calendar", "git", "proactive", "agents", "awareness", "cue", "evidence", "mlv2", "personas_v2", "attention", "context")
_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled(layer: str = "privacy") -> bool:
    if layer not in LAYERS:
        raise ValueError(f"unknown extension layer {layer!r}; known: {', '.join(LAYERS)}")
    return _on("UNDERSTUDY_X") or _on(f"UNDERSTUDY_X_{layer.upper()}")


def all_flags() -> dict[str, bool]:
    return {layer: enabled(layer) for layer in LAYERS}
