"""The awareness layer (REQ-5, AWR-1 to AWR-6): what the desktop app's always-on, on-device observation sends to the engine, and what the
engine does with it.

* ``schema``    the closed schema (``packages/schema/awareness.schema.json``) and the enums read from it,
* ``store``     a typed, append-only, on-device store of awareness events per person (JSONL; no coordinates, titles, text or pixels),
* ``features``  ``awareness_features(window)``: extra columns for the stuck hazard (the hazard track wires and evaluates them),
* ``synth``     deterministic, labelled-synthetic awareness events for the four personas (for an ablation),
* ``routes``    ``POST /awareness/events`` and friends, behind ``UNDERSTUDY_X_AWARENESS`` (or ``UNDERSTUDY_X``),
* ``purposes``  the image purpose ``awareness.glance`` (closed answer) registered with the privacy spine,
* ``glance_service``  a framework-free handler for the desktop's ``POST /glance`` call: gate, ``SafeImage``, ``egress.send_image``.

Everything is off by default. This package holds no model client and no network client: a frame reaches a model only through
``privacy.egress.send_image`` (the static guard scans this directory). Importing the package is cheap and has no side effects.
"""
from __future__ import annotations

import os

_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def flag_enabled() -> bool:
    """``UNDERSTUDY_X_AWARENESS=1`` or the master ``UNDERSTUDY_X=1``. Read on every call, never cached."""
    return _on("UNDERSTUDY_X") or _on("UNDERSTUDY_X_AWARENESS")


__all__ = ["flag_enabled"]
