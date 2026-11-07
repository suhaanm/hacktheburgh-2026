"""Where shared files live (contract: data/queue/<id>.json, data/audit.jsonl, data/KILL, data/runs/<run_id>/)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    env = os.environ.get("UNDERSTUDY_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages" / "schema" / "sensitive_fields.json").exists():
            return parent
    return here.parents[4]


def data_dir() -> Path:
    """UNDERSTUDY_DATA_DIR if set (tests use this), else <repo>/data. Not cached, so tests can monkeypatch."""
    env = os.environ.get("UNDERSTUDY_DATA_DIR", "").strip()
    return (Path(env).expanduser() if env else repo_root() / "data").resolve()


def queue_dir() -> Path:
    return data_dir() / "queue"


def audit_path() -> Path:
    return data_dir() / "audit.jsonl"


def kill_path() -> Path:
    return data_dir() / "KILL"


def runs_dir() -> Path:
    return data_dir() / "runs"


def sensitive_fields_path() -> Path:
    return repo_root() / "packages" / "schema" / "sensitive_fields.json"
