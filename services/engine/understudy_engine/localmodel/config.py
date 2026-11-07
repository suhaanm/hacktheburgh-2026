"""Settings for the local model layer: environment first, safe defaults second (LOC-1).

Everything here is read lazily so a test (or a flag flip) takes effect without re-importing.

Environment
  UNDERSTUDY_LOCAL_MODEL            path of the GGUF file (default: ``<data>/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf``)
  UNDERSTUDY_LOCAL_MODEL_SHA256     expected SHA-256 for a model other than the default
  UNDERSTUDY_LOCAL_MODEL_SIZE       expected size in bytes for a model other than the default
  UNDERSTUDY_LOCAL_MODEL_PORT       loopback port of llama-server (default 8089)
  UNDERSTUDY_LLAMA_SERVER           path of the llama-server binary (default: PATH, then Homebrew)
  UNDERSTUDY_LOCALMODEL_RULES_ONLY  1 = never use the model
  UNDERSTUDY_X_LOCALMODEL / UNDERSTUDY_X   the feature flags (the model is used only when one is on)
  UNDERSTUDY_MOCK                   1 = never start a server, rules only (NFR-2)
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL_FILE = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
DEFAULT_MODEL_SIZE = 4_683_074_240
DEFAULT_MODEL_SHA256 = "65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423"
DEFAULT_PORT = 8089
CONTEXT_SIZE = 8192
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
HOST = "127.0.0.1"          # the only address the server is ever bound to
HOMEBREW_BINARY = "/opt/homebrew/bin/llama-server"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_mock() -> bool:
    return _truthy("UNDERSTUDY_MOCK")


def flag_on() -> bool:
    """The layer's own feature flag (NFR-10): off by default, on with the master flag or the layer flag."""
    return _truthy("UNDERSTUDY_X") or _truthy("UNDERSTUDY_X_LOCALMODEL")


def rules_only() -> bool:
    return _truthy("UNDERSTUDY_LOCALMODEL_RULES_ONLY")


def repo_root() -> Path:
    # .../services/engine/understudy_engine/localmodel/config.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env).expanduser() if env else repo_root() / "data"


def model_path() -> Path:
    env = os.environ.get("UNDERSTUDY_LOCAL_MODEL", "").strip()
    if env:
        return Path(env).expanduser()
    return data_dir() / "models" / DEFAULT_MODEL_FILE


def expected_model() -> tuple[int | None, str | None]:
    """Expected (size, sha256) for the configured model: the pinned values for the default file, the environment for any
    other file, ``(None, None)`` when nothing is known (the file is then used with ``sha_ok = None``)."""
    size_env = os.environ.get("UNDERSTUDY_LOCAL_MODEL_SIZE", "").strip()
    sha_env = os.environ.get("UNDERSTUDY_LOCAL_MODEL_SHA256", "").strip().lower()
    if size_env or sha_env:
        return (int(size_env) if size_env.isdigit() else None, sha_env or None)
    if model_path().name == DEFAULT_MODEL_FILE:
        return DEFAULT_MODEL_SIZE, DEFAULT_MODEL_SHA256
    return None, None


def port() -> int:
    raw = os.environ.get("UNDERSTUDY_LOCAL_MODEL_PORT", "").strip()
    try:
        p = int(raw) if raw else DEFAULT_PORT
    except ValueError:
        p = DEFAULT_PORT
    return p if 1024 <= p <= 65535 else DEFAULT_PORT


def binary() -> str | None:
    env = os.environ.get("UNDERSTUDY_LLAMA_SERVER", "").strip()
    if env:
        return env if Path(env).is_file() and os.access(env, os.X_OK) else None
    found = shutil.which("llama-server")
    if found:
        return found
    return HOMEBREW_BINARY if Path(HOMEBREW_BINARY).is_file() else None


def log_path() -> Path:
    return data_dir() / "logs" / "llama.log"


def pid_path() -> Path:
    return data_dir() / "pids" / "llama-server.json"


def key_path() -> Path:
    return data_dir() / "pids" / "llama-server.key"


def check_cache_path() -> Path:
    return data_dir() / "localmodel" / "model_check.json"


def eval_cache_path() -> Path:
    return data_dir() / "localmodel" / "eval_cache.json"


@dataclass(frozen=True)
class Limits:
    """Per-request limits for the digest calls."""

    max_tokens: int = 64          # a digest is about 20 tokens; anything longer is a runaway
    temperature: float = 0.0
    timeout_s: float = 45.0       # first call after the load can take a few seconds
    retries: int = 1              # one retry, then fall back to the rules answer for that item
    max_message_chars: int = 1500
    max_paths: int = 12
    max_path_chars: int = 90
    max_description_chars: int = 400


LIMITS = Limits()
