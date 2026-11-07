"""Policy for the agent runtime (BGA-1): the caps that CODE enforces on every parent plan before anything starts.

The model proposes a plan; nothing here is up to the model. Every number below is checked by `spec.validate_plan`.
SEC-10 still holds: a child's tool list scopes the child's tools, it is not a site allowlist.
"""
from __future__ import annotations

import os
from typing import Final

MAX_CHILDREN: Final = 4          # per parent
MAX_DEPTH: Final = 1             # children never spawn children (there is no spawn tool)
MAX_STEPS: Final = 30            # per child, including the final emit_result
MAX_SECONDS: Final = 300.0       # per child (active time)
MAX_TOKENS: Final = 60_000       # per child (estimated: characters / 4)
RUN_MAX_SECONDS: Final = 900.0   # a whole run, parent included
WORKSPACE_KINDS: Final = ("tmp", "worktree", "none")

# workspace limits (code-enforced by workspace.py)
MAX_FILE_BYTES: Final = 400_000
MAX_WORKSPACE_BYTES: Final = 8_000_000
MAX_WORKSPACE_FILES: Final = 400
MAX_READ_BYTES: Final = 20_000
MAX_INPUT_BYTES: Final = 5_000_000

# run_python limits (code-enforced by sandbox.py)
PY_TIMEOUT_S: Final = 30.0
PY_CPU_S: Final = 20
PY_FSIZE_BYTES: Final = 20_000_000
PY_RSS_MB: Final = 700
PY_NOFILE: Final = 128
PY_OUT_CAP: Final = 64_000       # bytes kept of stdout and of stderr


def agents_enabled(env: dict[str, str] | None = None) -> bool:
    """Feature flag: UNDERSTUDY_X_AGENTS=1 or the master UNDERSTUDY_X=1. Off by default (NFR-10)."""
    e = os.environ if env is None else env
    on = ("1", "true", "yes", "on")
    return e.get("UNDERSTUDY_X_AGENTS", "").strip().lower() in on or e.get("UNDERSTUDY_X", "").strip().lower() in on


def estimate_tokens(text: str) -> int:
    """Token budgets are estimates (characters / 4). Reported as such; the real provider counts are not per child."""
    return (len(text) + 3) // 4


# Typed signals a vetted script may report after a step (status file); only these names, only numbers. They are the only
# thing about a step's RESULT that goes back to the model, and they pass the egress guard as registered features.
SIGNAL_NAMES: Final = (
    "tests_total", "tests_failing", "suspects_left", "classes_tried", "fixes_kept", "backtracks", "rows_in", "rows_out",
    "duplicates_found", "duplicates_removed", "unit_suspects", "unit_fixes", "outliers_found", "outliers_flagged",
    "reconcile_gap_cents", "reconciled", "phases_done", "script_crashed",
)
MAX_RECOVERIES: Final = 3        # failed script runs a child may recover from (retry or change course) before it stops
STATUS_FILE: Final = "status.json"
