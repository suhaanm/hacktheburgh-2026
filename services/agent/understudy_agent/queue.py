"""Approval queue (HND-6): file-based, one JSON file per item at data/queue/<id>.json, atomic writes.

Items carry an evidence bundle for the one-tap approve or reject. Only the worker's own UI action may decide an item:
`approve` and `reject` need an explicit `origin`, and only Origin.HUMAN_UI is accepted (layer 8). An approval is bound
to the action signature it was raised for and can be consumed once, so an approved "submit case note" cannot be
replayed for a different step.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .audit import AuditLog
from .security.paths import data_dir, queue_dir
from .security.sanitize import safe_label, sanitize_untrusted
from .security.settings import Origin, Setting, SettingsGuard

KINDS = ("irreversible_step", "outward_step", "batch_result", "injection_pause", "shadow_mismatch")
RISK_CLASSES = ("irreversible", "outward", "normal")
STATUSES = ("pending", "approved", "rejected", "expired")
_ID = re.compile(r"^q_[A-Za-z0-9_\-]{1,40}$")
_RUN = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


class QueueError(RuntimeError):
    pass


class NotFound(QueueError):
    pass


class AlreadyDecided(QueueError):
    pass


class NotPermitted(QueueError):
    pass


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clean_value(v: Any, depth: int = 0) -> Any:
    """Evidence is shown in the UI: sanitise every string so hidden characters and fake markup cannot ride along."""
    if depth > 6:
        return None
    if isinstance(v, str):
        return sanitize_untrusted(v, max_chars=2000).text
    if isinstance(v, dict):
        return {str(k)[:64]: _clean_value(x, depth + 1) for k, x in list(v.items())[:60]}
    if isinstance(v, (list, tuple)):
        return [_clean_value(x, depth + 1) for x in list(v)[:60]]
    if isinstance(v, (bool, int, float)) or v is None:
        return v
    return str(v)[:200]


def empty_evidence() -> dict[str, Any]:
    return {"screenshots": [], "extracted": {}, "expected": {}, "diff": [], "tier_log": []}


def save_screenshot(run_id: str, step: int, png: bytes) -> str:
    """Write an evidence screenshot to data/runs/<run_id>/s<step>.png; return the contract's relative path."""
    if not _RUN.match(run_id):
        raise ValueError("bad run id")
    d = data_dir() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"s{int(step)}.png"
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(png)
    os.replace(tmp, p)
    return f"data/runs/{run_id}/s{int(step)}.png"


class ApprovalQueue:
    def __init__(self, root: Path | None = None, *, audit: AuditLog | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._root = root
        self.audit = audit
        self._clock = clock
        self._tl = threading.Lock()

    @property
    def root(self) -> Path:
        r = self._root or queue_dir()
        r.mkdir(parents=True, exist_ok=True)
        return r

    # ---- file helpers
    def _file(self, item_id: str) -> Path:
        if not _ID.match(item_id):
            raise NotFound("no such queue item")
        return self.root / f"{item_id}.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._tl, open(self.root / ".lock", "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def _write(self, item: dict[str, Any]) -> None:
        p = self._file(item["id"])
        tmp = p.with_suffix(f".{secrets.token_hex(3)}.tmp")
        tmp.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)

    def _read(self, item_id: str) -> dict[str, Any]:
        p = self._file(item_id)
        if not p.exists():
            raise NotFound("no such queue item")
        return json.loads(p.read_text(encoding="utf-8"))

    def _log(self, kind: str, item: dict[str, Any], outcome: str, actor: str = "system") -> None:
        if self.audit is not None:
            self.audit.append(actor, kind, routine=item.get("routine_id"), run_id=item.get("run_id"),
                              outcome=outcome, note_code=f"queue:{item['kind']}:{item['risk_class']}",
                              meta={"queue_id": item["id"]})

    # ---- API
    def enqueue(self, *, kind: str, title: str, summary: str, risk_class: str = "normal", routine_id: str | None = None,
                run_id: str | None = None, evidence: dict[str, Any] | None = None, signature: str | None = None,
                dedupe_key: str | None = None) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if risk_class not in RISK_CLASSES:
            raise ValueError(f"risk_class must be one of {RISK_CLASSES}")
        with self._locked():
            if dedupe_key:
                for it in self._all():
                    if it.get("dedupe_key") == dedupe_key and it["status"] == "pending":
                        return it
            ev = empty_evidence()
            ev.update(_clean_value(evidence or {}))
            item = {
                "id": f"q_{int(self._clock() * 1000):011x}{secrets.token_hex(2)}",
                "created_at": _iso(self._clock()),
                "routine_id": routine_id,
                "run_id": run_id,
                "kind": kind,
                "title": safe_label(title, 120),
                "summary": safe_label(summary, 240),
                "risk_class": risk_class,
                "evidence": ev,
                "status": "pending",
                "decided_at": None,
                "decided_by": None,
            }
            if signature:
                item["signature"] = signature
            if dedupe_key:
                item["dedupe_key"] = dedupe_key
            self._write(item)
        self._log("queue_enqueued", item, "pending")
        return item

    def get(self, item_id: str) -> dict[str, Any] | None:
        try:
            return self._read(item_id)
        except NotFound:
            return None

    def _all(self) -> list[dict[str, Any]]:
        items = []
        for p in self.root.glob("q_*.json"):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return sorted(items, key=lambda i: (i.get("created_at", ""), i["id"]))

    def list(self, status: str = "pending") -> list[dict[str, Any]]:
        """Oldest first. status is one of pending, approved, rejected, expired, or all."""
        items = self._all()
        return items if status == "all" else [i for i in items if i["status"] == status]

    def _decide(self, item_id: str, status: str, decided_by: str, origin: Origin | None) -> dict[str, Any]:
        d = SettingsGuard().authorise_write(Setting.CONSENT, origin) if origin is not None else None
        if d is None or not d.allowed:
            raise NotPermitted("only the worker's own action can approve or reject a queue item")
        with self._locked():
            item = self._read(item_id)
            if item["status"] != "pending":
                raise AlreadyDecided(f"item is already {item['status']}")
            item["status"] = status
            item["decided_at"] = _iso(self._clock())
            item["decided_by"] = decided_by
            self._write(item)
        self._log("queue_decided", item, status, actor="human")
        return item

    def approve(self, item_id: str, *, origin: Origin | None = None, decided_by: str = "human") -> dict[str, Any]:
        return self._decide(item_id, "approved", decided_by, origin)

    def reject(self, item_id: str, *, origin: Origin | None = None, decided_by: str = "human") -> dict[str, Any]:
        return self._decide(item_id, "rejected", decided_by, origin)

    def expire_older_than(self, seconds: float) -> int:
        """Mark pending items older than `seconds` as expired (an expired approval never runs)."""
        n = 0
        cutoff = _iso(self._clock() - seconds)
        with self._locked():
            for it in self._all():
                if it["status"] == "pending" and it["created_at"] < cutoff:
                    it["status"] = "expired"
                    it["decided_at"] = _iso(self._clock())
                    it["decided_by"] = "system"
                    self._write(it)
                    n += 1
        return n

    def consume_approval(self, item_id: str, signature: str) -> bool:
        """True exactly once for an approved item whose signature matches. Used by the pipeline to let the
        approved step through a single time."""
        with self._locked():
            try:
                item = self._read(item_id)
            except NotFound:
                return False
            if item["status"] != "approved" or item.get("consumed_at") or item.get("signature") != signature:
                return False
            item["consumed_at"] = _iso(self._clock())
            self._write(item)
        return True
