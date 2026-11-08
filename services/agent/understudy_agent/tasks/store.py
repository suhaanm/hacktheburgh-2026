"""Task persistence: one JSON file per task in `<data dir>/tasks/`, mode 0600, written atomically. A restart reloads them.

The files hold the worker's own words (needed to start a task that was waiting for a click) and short step lines. They never
hold a child's full output (that goes to `<id>.result.txt` next to them, also mode 0600) and nothing here is ever sent to a
model or written to a log.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Iterator

from ..security.paths import data_dir
from .model import FINISHED, Task

KEEP_FINISHED = 300
_ID = re.compile(r"^tk_[0-9a-f]{8}$")


def tasks_dir() -> Path:
    return data_dir() / "tasks"


def valid_id(task_id: str) -> bool:
    return bool(_ID.match(task_id or ""))


class TaskStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root or tasks_dir()

    def path(self, task_id: str) -> Path:
        if not valid_id(task_id):
            raise ValueError("bad task id")
        return self.root / f"{task_id}.json"

    def result_path(self, task_id: str) -> Path:
        if not valid_id(task_id):
            raise ValueError("bad task id")
        return self.root / f"{task_id}.result.txt"

    def _write(self, p: Path, data: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = p.with_name(p.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, p)

    def save(self, task: Task) -> None:
        with self._lock:
            self._write(self.path(task.task_id), json.dumps(task.to_json(), ensure_ascii=False, separators=(",", ":")))

    def save_result_text(self, task_id: str, text: str) -> None:
        with self._lock:
            self._write(self.result_path(task_id), text)

    def load(self, task_id: str) -> Task | None:
        try:
            return Task.from_json(json.loads(self.path(task_id).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def all(self) -> Iterator[Task]:
        try:
            files = sorted(self.root.glob("tk_*.json"))
        except OSError:
            return
        for p in files:
            if not valid_id(p.stem):
                continue
            t = self.load(p.stem)
            if t is not None:
                yield t

    def prune(self) -> int:
        """Keep the newest KEEP_FINISHED finished tasks; unfinished ones are never removed. Returns how many were removed."""
        finished = [t for t in self.all() if t.state in FINISHED]
        finished.sort(key=lambda t: t.started, reverse=True)
        n = 0
        for t in finished[KEEP_FINISHED:]:
            for p in (self.path(t.task_id), self.result_path(t.task_id)):
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        return n
