"""Shared files between engine and agent: approval queue, audit log, kill flag, run evidence.

The real implementations live in the agent package (hash-chained audit, signed queue items); the engine does not
depend on it, so they are imported lazily. Without the agent package the engine falls back to read-only access and
answers writes with 503 and a plain message. The engine never appends to the audit file by hand.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..store.paths import data_dir
from .errors import ApiError

_RUN = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_FILE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}\.(png|json)$")
MEDIA = {"png": "image/png", "json": "application/json"}


def agent_modules():
    """(queue module, audit module, killflag module, Origin) or None when the agent package is not importable."""
    try:
        from understudy_agent import audit as audit_mod
        from understudy_agent import queue as queue_mod
        from understudy_agent.security import killflag
        from understudy_agent.security.settings import Origin

        return queue_mod, audit_mod, killflag, Origin
    except ImportError:
        return None


def _no_agent() -> ApiError:
    return ApiError(503, "agent_package_missing", "Run the engine in the agent environment (uv run --package understudy-agent understudy serve) to enable approvals.")


# --------------------------------------------------------------------------- queue
def queue_list(status: str) -> list[dict]:
    mods = agent_modules()
    if mods:
        return mods[0].ApprovalQueue().list(status)
    qdir = data_dir() / "queue"
    items = []
    for p in sorted(qdir.glob("q_*.json")) if qdir.exists() else []:
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda i: (i.get("created_at", ""), i.get("id", "")))
    return items if status == "all" else [i for i in items if i.get("status") == status]


def queue_decide(item_id: str, action: str, auth: dict | None) -> dict:
    """Approve or reject as the worker. ``auth`` is {method, sub_hash?} (absent means a local click); the queue validates
    it before any state change and records auth_method / sub_hash on the item and in its audit line."""
    mods = agent_modules()
    if not mods:
        raise _no_agent()
    queue_mod, audit_mod, _, Origin = mods
    q = queue_mod.ApprovalQueue(audit=audit_mod.AuditLog())
    try:
        fn = q.approve if action == "approve" else q.reject
        return fn(item_id, origin=Origin.HUMAN_UI, decided_by="worker", auth=auth or {"method": "local"})
    except queue_mod.InvalidAuth as exc:
        raise ApiError(422, "invalid_auth", f"{exc}.")
    except queue_mod.NotFound:
        raise ApiError(404, "no_such_item", f"There is no queue item {item_id}.")
    except queue_mod.AlreadyDecided as exc:
        raise ApiError(409, "already_decided", f"Nothing changed: {exc}.")
    except queue_mod.NotPermitted as exc:
        raise ApiError(403, "not_permitted", str(exc))


# --------------------------------------------------------------------------- audit
def audit_read(limit: int) -> list[dict]:
    mods = agent_modules()
    if mods:
        return mods[1].AuditLog().read(limit=limit)
    p = data_dir() / "audit.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


# --------------------------------------------------------------------------- kill
def kill_path() -> Path:
    return data_dir() / "KILL"


def kill_state() -> dict:
    p = kill_path()
    if not p.exists():
        return {"killed": False, "at": None}
    first = ""
    try:
        first = p.read_text(encoding="utf-8").splitlines()[0].strip()
        datetime.fromisoformat(first.replace("Z", "+00:00"))
    except (OSError, IndexError, ValueError):
        first = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()
    return {"killed": True, "at": first}


def kill_set(reason: str = "worker pressed the kill switch") -> None:
    mods = agent_modules()
    if mods:
        mods[2].set_kill(reason)
        return
    p = kill_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"{datetime.now(timezone.utc).isoformat()}\n{reason[:120]}\n", encoding="utf-8")
    os.replace(tmp, p)


def kill_clear() -> None:
    mods = agent_modules()
    if mods:
        mods[2].clear_kill()
        return
    try:
        kill_path().unlink()
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------- run evidence
def evidence_path(run_id: str, file: str) -> tuple[Path, str]:
    """Resolve data/runs/<run_id>/<file> for serving. Only png and json; no traversal, no symlinks."""
    if not _RUN.match(run_id) or run_id in (".", "..") or not _FILE.match(file) or file.startswith("."):
        raise ApiError(404, "not_found", "No such evidence file.")
    base = (data_dir() / "runs").resolve()
    folder = base / run_id
    path = folder / file
    for p in (folder, path):
        if p.is_symlink():
            raise ApiError(404, "not_found", "No such evidence file.")
    try:
        real = path.resolve(strict=True)
        real.relative_to(base)
    except (FileNotFoundError, ValueError, OSError):
        raise ApiError(404, "not_found", "No such evidence file.")
    if not real.is_file():
        raise ApiError(404, "not_found", "No such evidence file.")
    return real, MEDIA[file.rsplit(".", 1)[1]]
