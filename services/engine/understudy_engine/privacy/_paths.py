"""Where the privacy layer keeps its files. Environment first, repo defaults second (same rules as the store).

Kept local so this layer has no import-time dependency on the store (which would pull in pandas and friends).
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    # .../services/engine/understudy_engine/privacy/_paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def is_mock() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes")


def schema_dir() -> Path:
    return repo_root() / "packages" / "schema"
