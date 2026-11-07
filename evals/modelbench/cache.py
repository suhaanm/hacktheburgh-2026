"""Result cache keyed by (kind, contender, model, api, prompt hash, image hash, schema, repeat). Append-only JSONL, resumable.

A key never contains image bytes (the image is its sha256), prompt text (its hash) or any key. A cached entry holds only the model's
closed answer, tokens, latency and cost. Failed calls are cached with `ok: false` and an `attempts` count, so a resumed run retries
them at most `max_attempts` times.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any


def sha(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode() if not isinstance(p, (bytes, str)) else
                 (p if isinstance(p, bytes) else p.encode()))
        h.update(b"\x00")
    return h.hexdigest()


def make_key(*, kind: str, contender: str, model: str, api: str, prompt: str, image_sha: str, schema_name: str, rep: int = 0,
             extra: str = "") -> str:
    return sha(kind, contender, model, api, sha(prompt)[:16], image_sha, schema_name, rep, extra)[:40]


class ResultCache:
    def __init__(self, path: Path | None, *, max_attempts: int = 2) -> None:
        self.path, self.max_attempts = path, max_attempts
        self._lock = threading.Lock()
        self._d: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            for line in path.read_text().splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                self._d[row["key"]] = row

    def get(self, key: str) -> dict[str, Any] | None:
        """A usable cached row: a success, or a failure that has used up its attempts (so it is not retried again)."""
        with self._lock:
            row = self._d.get(key)
        if row is None:
            return None
        if row["ok"] or row.get("attempts", 1) >= self.max_attempts:
            return row
        return None

    def peek(self, key: str) -> dict[str, Any] | None:
        """The stored row for a key whatever its state (success, or a failure still awaiting a retry)."""
        with self._lock:
            return self._d.get(key)

    def attempts(self, key: str) -> int:
        with self._lock:
            return int(self._d.get(key, {}).get("attempts", 0))

    def put(self, key: str, row: dict[str, Any]) -> dict[str, Any]:
        row = {**row, "key": key}
        with self._lock:
            row["attempts"] = int(self._d.get(key, {}).get("attempts", 0)) + 1
            self._d[key] = row
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as f:
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
        return row

    def rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._d.values())

    def __len__(self) -> int:
        return len(self._d)
