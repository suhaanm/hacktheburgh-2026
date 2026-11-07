"""Where things live on disk. Environment first, repo defaults second.

- ``UNDERSTUDY_DATA_DIR``: root of ``real/``, ``synthetic/``, ``queue/``, ``audit.jsonl``, ``KILL``
  (default: ``<repo>/data``; the contract calls this ``data/``).
- ``UNDERSTUDY_HOME``: per-install private state such as the salt (default ``~/.understudy``).
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    # .../services/engine/understudy_engine/store/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def home_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_HOME")
    return Path(env).expanduser() if env else Path.home() / ".understudy"


def schema_dir() -> Path:
    return repo_root() / "packages" / "schema"


def evals_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_EVALS_DIR")
    return Path(env).expanduser() if env else repo_root() / "evals"


def is_mock() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes")
