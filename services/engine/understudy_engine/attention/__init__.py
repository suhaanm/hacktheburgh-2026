"""The attention layer (REQ-8): one deterministic router for every notification the worker could receive.

Pure Python. No model calls, no network, no subprocess, no clock of its own (the service takes one). Events carry ids and enums only.
See ``docs/ATTENTION_DESIGN.md`` and ``router.py``. Off by default (``UNDERSTUDY_X_ATTENTION`` or ``UNDERSTUDY_X``).
"""
from __future__ import annotations

from .paths import FLAG, enabled
from .router import AttentionRouter, Decision, is_natural_break
from .state import DEFAULT, History, Lock, Params, Settings, WorkerState

__all__ = ["AttentionRouter", "Decision", "is_natural_break", "DEFAULT", "History", "Lock", "Params", "Settings", "WorkerState", "FLAG", "enabled"]
