"""Where the attention layer keeps its state and how it is switched on (REQ-8). Imports nothing heavy.

* ``UNDERSTUDY_DATA_DIR``: shared data root. State lives in ``<data>/attention/state.json``; transitions (metadata only) in
  ``<data>/attention/log.jsonl``.
* ``UNDERSTUDY_X_ATTENTION=1`` or the master ``UNDERSTUDY_X=1`` turns the layer on. Off by default (NFR-10). Read on every call.
* ``UNDERSTUDY_ATTENTION_LEVEL_GLANCE=0`` switches the 2 s help-level glance off entirely, whatever the settings say.
"""
from __future__ import annotations

import os
from pathlib import Path

FLAG = "UNDERSTUDY_X_ATTENTION"
_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    return _on("UNDERSTUDY_X") or _on(FLAG)


def level_glance_env_off() -> bool:
    return os.environ.get("UNDERSTUDY_ATTENTION_LEVEL_GLANCE", "").strip().lower() in ("0", "false", "no", "off")


def repo_root() -> Path:
    # .../services/engine/understudy_engine/attention/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def attention_dir() -> Path:
    return data_dir() / "attention"


def state_path() -> Path:
    return attention_dir() / "state.json"


def log_path() -> Path:
    return attention_dir() / "log.jsonl"


def schema_path() -> Path:
    return repo_root() / "packages" / "schema" / "attention_event.schema.json"


def is_mock() -> bool:
    return _on("UNDERSTUDY_MOCK")
