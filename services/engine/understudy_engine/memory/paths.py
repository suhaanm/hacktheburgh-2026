"""Where the handoff modules keep state. Same environment variables as the store module.

- ``UNDERSTUDY_HOME``: per-install private state (default ``~/.understudy``). Holds ``memory.md``.
- ``UNDERSTUDY_DATA_DIR``: shared data root (default ``<repo>/data``).
- ``UNDERSTUDY_PACKS_DIR``: role packs (default ``<repo>/packages/packs``).

Kept local to this track so the memory, presence and routine modules import nothing from the others.
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    # .../services/engine/understudy_engine/memory/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def home_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_HOME")
    return Path(env).expanduser() if env else Path.home() / ".understudy"


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def packs_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_PACKS_DIR")
    return Path(env).expanduser() if env else repo_root() / "packages" / "packs"


def is_mock() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes")
