"""The global kill flag: presence of data/KILL means stop everything (OFF-6). Writing and clearing are the
worker's actions (button or hotkey); the agent can only read it."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .paths import kill_path


def is_killed() -> bool:
    return kill_path().exists()


def set_kill(reason: str = "worker pressed the kill switch") -> None:
    p = kill_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"{datetime.now(timezone.utc).isoformat()}\n{reason[:120]}\n", encoding="utf-8")
    os.replace(tmp, p)


def clear_kill() -> None:
    try:
        kill_path().unlink()
    except FileNotFoundError:
        pass
