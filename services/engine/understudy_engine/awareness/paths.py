"""Where the awareness layer keeps its files (same rules as the event store: environment first, repo defaults second)."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    # .../services/engine/understudy_engine/awareness/paths.py -> the repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def store_dir() -> Path:
    return data_dir() / "awareness"


def schema_path() -> Path:
    return repo_root() / "packages" / "schema" / "awareness.schema.json"
