"""Where connection state lives and how the layer is switched on (CONNECTIONS).

Environment first, repo defaults second, the same rules as the rest of the engine. Importing this module pulls in nothing heavy.

* ``UNDERSTUDY_DATA_DIR``: shared data root. The state file is ``<data>/connections/state.json`` (consent records, counts; never a token).
* ``UNDERSTUDY_HOME``: the worker's private home. The fallback secret file is ``<home>/connections/secrets.json`` (mode 600), used only when
  the macOS Keychain is not the backend. Never inside the repository.
* ``UNDERSTUDY_X_CONNECTIONS=1`` or the master ``UNDERSTUDY_X=1`` turns the layer on (on by default in the running product, D48; every
  connection is still OFF until the worker clicks it).
"""
from __future__ import annotations

import os
from pathlib import Path

from ..store.paths import home_dir  # noqa: F401  (re-exported: the per-install private folder; the store's own helper, so no home-folder access is added here)

FLAG = "UNDERSTUDY_X_CONNECTIONS"
_TRUE = ("1", "true", "yes", "on")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    """True when the connections layer is switched on. Never cached, so a flag flipped in a test or a restart takes effect at once."""
    return _on("UNDERSTUDY_X") or _on(FLAG)


def repo_root() -> Path:
    # .../services/engine/understudy_engine/connections/paths.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def packs_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_PACKS_DIR")
    return Path(env).expanduser() if env else repo_root() / "packages" / "packs"


def connections_dir() -> Path:
    return data_dir() / "connections"


def state_path() -> Path:
    return connections_dir() / "state.json"


def sandbox_dir() -> Path:
    """The private folder the stand-in servers use (invented files and a small database are written here on first use)."""
    return connections_dir() / "sandbox"


def synthetic_dir() -> Path:
    return data_dir() / "synthetic"


def secrets_path() -> Path:
    return home_dir() / "connections" / "secrets.json"


def agent_url() -> str:
    return os.environ.get("UNDERSTUDY_AGENT_URL", "http://127.0.0.1:7710").rstrip("/")
