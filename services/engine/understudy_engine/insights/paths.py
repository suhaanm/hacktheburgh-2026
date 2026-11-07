"""Where the insights layer keeps its state and how it is switched on (REQ-9). Imports nothing heavy.

* ``UNDERSTUDY_DATA_DIR``: shared data root. State lives in ``<data>/insights/state.json`` (feedback, what was shown, the week's pins).
* ``UNDERSTUDY_X_INSIGHTS=1`` or the master ``UNDERSTUDY_X=1`` turns the layer on. Off by default (NFR-10). Read on every call.
* ``UNDERSTUDY_MOCK=1``: the default source becomes the synthetic firm (``?source=firm``); otherwise ``local`` (this device's own ledger).
"""
from __future__ import annotations

import os
from pathlib import Path

FLAG = "UNDERSTUDY_X_INSIGHTS"
_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    return _on("UNDERSTUDY_X") or _on(FLAG)


def repo_root() -> Path:
    # .../services/engine/understudy_engine/insights/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def insights_dir() -> Path:
    return data_dir() / "insights"


def state_path() -> Path:
    return insights_dir() / "state.json"


def schema_path() -> Path:
    return repo_root() / "packages" / "schema" / "insight.schema.json"


def is_mock() -> bool:
    return _on("UNDERSTUDY_MOCK")
