"""Where Cue keeps its state and how it is switched on (CUE-6).

Environment first, repo defaults second, the same rules as the rest of the engine. Importing this module pulls in nothing heavy.

* ``UNDERSTUDY_DATA_DIR``: shared data root. The assist ledger lives in ``<data>/assist/ledger.jsonl``.
* ``UNDERSTUDY_HOME``: the worker's private home (memory file).
* ``UNDERSTUDY_X_CUE=1`` or the master ``UNDERSTUDY_X=1`` turns Cue on. Off by default (NFR-10). Read on every call.
"""
from __future__ import annotations

import os
from pathlib import Path

FLAG = "UNDERSTUDY_X_CUE"
_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    """True when Cue is switched on. Never cached, so a flag flipped in a test or a restart takes effect at once."""
    return _on("UNDERSTUDY_X") or _on(FLAG)


def repo_root() -> Path:
    # .../services/engine/understudy_engine/cue/paths.py -> repo root is parents[4]
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


def assist_dir() -> Path:
    return data_dir() / "assist"


def ledger_path() -> Path:
    return assist_dir() / "ledger.jsonl"


def schema_path() -> Path:
    return repo_root() / "packages" / "schema" / "assist_ledger.schema.json"


def step_schema_path() -> Path:
    return repo_root() / "packages" / "schema" / "cue_step.schema.json"


def is_mock() -> bool:
    return _on("UNDERSTUDY_MOCK")
