"""Where the proactive layer keeps its state and how it is switched on.

Environment first, repo defaults second, the same rules as the rest of the engine. Kept local so importing this
layer pulls in nothing heavy (no pandas, no event store).

* ``UNDERSTUDY_DATA_DIR``: shared data root. The briefing lives in ``<data>/briefing.json`` (cards, labels, suppressions).
* ``UNDERSTUDY_HOME``: the worker's private home (memory file, routine registry).
* ``UNDERSTUDY_X_PROACTIVE=1`` or the master ``UNDERSTUDY_X=1`` turns the layer on. Off by default (NFR-10).
"""
from __future__ import annotations

import os
from pathlib import Path

_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    """True when the proactive layer is switched on. Read on every call, never cached."""
    return _on("UNDERSTUDY_X") or _on("UNDERSTUDY_X_PROACTIVE")


def layer_on(layer: str) -> bool:
    """Is another extension layer (``calendar``, ``git``, ``agents``, ``privacy``) switched on? Same flags as the engine app."""
    return _on("UNDERSTUDY_X") or _on(f"UNDERSTUDY_X_{layer.upper()}")


def repo_root() -> Path:
    # .../services/engine/understudy_engine/proactive/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def home_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_HOME")
    return Path(env).expanduser() if env else Path.home() / ".understudy"


def packs_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_PACKS_DIR")
    return Path(env).expanduser() if env else repo_root() / "packages" / "packs"


def is_mock() -> bool:
    return _on("UNDERSTUDY_MOCK")


def briefing_path() -> Path:
    return data_dir() / "briefing.json"


def agent_url() -> str:
    return os.environ.get("UNDERSTUDY_AGENT_URL", "http://127.0.0.1:7710").rstrip("/")
