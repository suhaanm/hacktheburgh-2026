"""Minimal file-backed approval queue and audit log used by agent-core until the agent-safety
`queue.ApprovalQueue` and `audit.AuditLog` land. Same file shapes as docs/API_CONTRACT.md, atomic
writes, and nothing but machine-safe fields in the audit line (no page text, no field values).

`default_sinks()` prefers the agent-safety implementations when they are importable and have the
expected methods; otherwise these.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .supervisor import data_dir

_URL = re.compile(r"https?://\S+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{secrets.token_hex(3)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def scrub(text: str, n: int = 160) -> str:
    return " ".join(_URL.sub("<url>", str(text)).split())[:n]


class FileQueue:
    """Approval queue: one JSON file per item in data/queue/ (contract QueueItem)."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root or (data_dir() / "queue")

    def enqueue(self, *, kind: str, title: str, summary: str, risk_class: str, run_id: str | None,
                routine_id: str | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        qid = "q_" + format(int(time.time() * 1000), "x") + secrets.token_hex(2)
        item = {
            "id": qid, "created_at": _now(), "routine_id": routine_id, "run_id": run_id, "kind": kind,
            "title": scrub(title, 120), "summary": scrub(summary, 200), "risk_class": risk_class,
            "evidence": evidence or {"screenshots": [], "extracted": {}, "expected": {}, "diff": [], "tier_log": []},
            "status": "pending", "decided_at": None, "decided_by": None,
        }
        _atomic_write(self.root / f"{qid}.json", json.dumps(item, indent=2, default=str))
        return item

    def get(self, qid: str) -> dict[str, Any] | None:
        p = self.root / f"{qid}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def list(self, status: str | None = "pending") -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        items = [json.loads(p.read_text()) for p in sorted(self.root.glob("q_*.json"))]
        return [i for i in items if status in (None, "all") or i.get("status") == status]


class FileAudit:
    """Append-only redacted JSONL: {t, actor, kind, routine, run_id, tier, outcome, note}."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path or (data_dir() / "audit.jsonl")

    def log(self, *, kind: str, outcome: str, actor: str = "agent", routine: str | None = None,
            run_id: str | None = None, tier: int | None = None, note: str = "") -> dict[str, Any]:
        line = {"t": _now(), "actor": actor, "kind": kind, "routine": routine, "run_id": run_id,
                "tier": tier, "outcome": outcome, "note": scrub(note)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return line

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(x) for x in lines if x.strip()]


def default_sinks(root: Path | None = None) -> tuple[FileQueue, FileAudit]:
    """File sinks. (Swap in agent-safety's ApprovalQueue / AuditLog here once their API is final.)"""
    if root is not None:
        return FileQueue(root / "queue"), FileAudit(root / "audit.jsonl")
    return FileQueue(), FileAudit()
