"""Approval queue (HND-6): file-based, one JSON file per item at data/queue/<id>.json, atomic writes.

Items carry an evidence bundle for the one-tap approve or reject. Only the worker's own UI action may decide an item:
`approve` and `reject` need an explicit `origin`, and only Origin.HUMAN_UI is accepted (layer 8). An approval is bound
to the action signature it was raised for and can be consumed once, so an approved "submit case note" cannot be
replayed for a different step.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
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


class InvalidAuth(QueueError, ValueError):
    """The `auth` record on an approval is not one of the accepted shapes."""


DEFAULT_APPROVAL_MAX_AGE_S = 1800.0   # an approval is good for 30 minutes
ENV_APPROVAL_MAX_AGE = "UNDERSTUDY_APPROVAL_MAX_AGE_S"


def approval_max_age_s(override: float | None = None) -> float:
    """How long an approval stays usable: the argument, else env UNDERSTUDY_APPROVAL_MAX_AGE_S, else 30 minutes."""
    if override is not None:
        return float(override)
    raw = os.environ.get(ENV_APPROVAL_MAX_AGE, "").strip()
    try:
        v = float(raw)
        return v if v > 0 else DEFAULT_APPROVAL_MAX_AGE_S
    except ValueError:
        return DEFAULT_APPROVAL_MAX_AGE_S


@dataclass(frozen=True)
class ApprovalCheck:
    ok: bool
    code: str = "ok"      # ok | not_found | not_approved | consumed | signature_mismatch | expired
    reason: str = ""


AUTH_METHODS = ("local", "auth0_stepup")
_SUB_HASH = re.compile(r"^[0-9a-f]{12}$")


def validate_auth(auth: dict[str, Any] | None) -> dict[str, str] | None:
    """`{method: "local" | "auth0_stepup", sub_hash?: 12 lowercase hex}` and nothing else (never names, emails or tokens)."""
    if auth is None:
        return None
    if not isinstance(auth, dict) or set(auth) - {"method", "sub_hash"}:
        raise InvalidAuth("auth may only contain method and sub_hash")
    method = auth.get("method")
    if method not in AUTH_METHODS:
        raise InvalidAuth(f"auth.method must be one of {AUTH_METHODS}")
    out = {"method": method}
    if "sub_hash" in auth:
        sh = auth["sub_hash"]
        if not isinstance(sh, str) or not _SUB_HASH.match(sh):
            raise InvalidAuth("auth.sub_hash must be 12 lowercase hex characters")
        out["sub_hash"] = sh
    return out


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
                 clock: Callable[[], float] = time.time, max_age_s: float | None = None) -> None:
        self._root = root
        self._max_age_s = max_age_s
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

    # ---- integrity (S-11): every item carries an HMAC over its content, keyed by a per-install secret that lives BESIDE
    # the queue directory (data/.queue_key, mode 0600, which the agent's own file tools may not touch). Editing an item's
    # file (status=approved, a new signature) breaks the tag, and an approval whose tag does not verify is never honoured.
    def _key(self) -> bytes:
        p = self.root.parent / ".queue_key"
        for _ in range(3):
            try:
                return bytes.fromhex(p.read_text().strip())
            except (OSError, ValueError):
                pass
            try:
                fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue                                    # another writer made it between our read and our create
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_hex(32) + "\n")
        raise QueueError("the queue integrity key is unreadable")

    def _mac(self, item: dict[str, Any]) -> str:
        body = json.dumps({k: v for k, v in item.items() if k != "mac"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hmac.new(self._key(), body.encode("utf-8"), hashlib.sha256).hexdigest()

    def integrity(self, item: dict[str, Any]) -> str:
        """ok | unsigned (written before tags existed) | tampered (the file was edited outside the queue)."""
        tag = item.get("mac")
        if not tag:
            return "unsigned"
        return "ok" if hmac.compare_digest(str(tag), self._mac(item)) else "tampered"

    def _write(self, item: dict[str, Any]) -> None:
        item["mac"] = self._mac(item)
        p = self._file(item["id"])
        tmp = p.with_suffix(f".{secrets.token_hex(3)}.tmp")
        tmp.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)

    def _read(self, item_id: str) -> dict[str, Any]:
        p = self._file(item_id)
        if not p.exists():
            raise NotFound("no such queue item")
        return json.loads(p.read_text(encoding="utf-8"))

    def _log(self, kind: str, item: dict[str, Any], outcome: str, actor: str = "system",
             extra: dict[str, str] | None = None) -> None:
        if self.audit is not None:
            self.audit.append(actor, kind, routine=item.get("routine_id"), run_id=item.get("run_id"),
                              outcome=outcome, note_code=f"queue:{item['kind']}:{item['risk_class']}",
                              meta={"queue_id": item["id"], **(extra or {})})

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

    def _decide(self, item_id: str, status: str, decided_by: str, origin: Origin | None,
                auth: dict[str, Any] | None = None) -> dict[str, Any]:
        d = SettingsGuard().authorise_write(Setting.CONSENT, origin) if origin is not None else None
        if d is None or not d.allowed:
            raise NotPermitted("only the worker's own action can approve or reject a queue item")
        clean_auth = validate_auth(auth)  # validated before anything changes
        with self._locked():
            item = self._read(item_id)
            if self.integrity(item) == "tampered":
                raise QueueError("this item was modified outside the app; it cannot be decided")
            if item["status"] != "pending":
                raise AlreadyDecided(f"item is already {item['status']}")
            item["status"] = status
            item["decided_at"] = _iso(self._clock())
            item["decided_by"] = decided_by
            if clean_auth:
                item["auth_method"] = clean_auth["method"]
                if "sub_hash" in clean_auth:
                    item["sub_hash"] = clean_auth["sub_hash"]
            self._write(item)
        extra = {"auth_method": clean_auth["method"], **({"sub_hash": clean_auth["sub_hash"]} if "sub_hash" in clean_auth else {})} if clean_auth else None
        self._log("queue_decided", item, status, actor="human", extra=extra)
        return item

    def approve(self, item_id: str, *, origin: Origin | None = None, decided_by: str = "human",
                auth: dict[str, Any] | None = None) -> dict[str, Any]:
        """`auth` (optional): {method: "local" | "auth0_stepup", sub_hash?: 12 hex}. Stored as auth_method and sub_hash."""
        return self._decide(item_id, "approved", decided_by, origin, auth)

    def reject(self, item_id: str, *, origin: Origin | None = None, decided_by: str = "human",
               auth: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._decide(item_id, "rejected", decided_by, origin, auth)

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

    def try_consume_approval(self, item_id: str, signature: str, *, max_age_s: float | None = None,
                             run_id: str | None = None) -> ApprovalCheck:
        """Use an approval once. It must be approved, unconsumed, bound to this action signature, and not older than `max_age_s`
        (default 30 minutes, env UNDERSTUDY_APPROVAL_MAX_AGE_S): an older approval is cancelled (status becomes `expired`) and
        the step must be asked for again. Returns why it was refused."""
        limit = approval_max_age_s(max_age_s if max_age_s is not None else self._max_age_s)
        with self._locked():
            try:
                item = self._read(item_id)
            except NotFound:
                return ApprovalCheck(False, "not_found", "no such approval")
            if self.integrity(item) != "ok":
                return ApprovalCheck(False, "tampered", "this approval does not carry a valid integrity tag; ask again")
            if item["status"] != "approved":
                return ApprovalCheck(False, "not_approved", f"the item is {item['status']}, not approved")
            if run_id is not None and item.get("run_id") not in (None, run_id):
                return ApprovalCheck(False, "run_mismatch", "this approval was given for a different run")
            if item.get("consumed_at"):
                return ApprovalCheck(False, "consumed", "this approval was already used")
            if item.get("signature") != signature:
                return ApprovalCheck(False, "signature_mismatch", "this approval was given for a different step")
            decided = item.get("decided_at")
            try:
                age = self._clock() - datetime.fromisoformat(str(decided).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                age = float("inf")  # no readable time of approval: cannot show it is fresh
            if age > limit:
                item["status"] = "expired"
                item["expired_at"] = _iso(self._clock())
                item["expired_reason"] = "approval_too_old"
                self._write(item)
                expired = item
                minutes = "an unknown time" if age == float("inf") else f"{age / 60:.0f} minutes"
                reason = (f"the approval was given {minutes} ago and approvals expire after {limit / 60:.0f} minutes; "
                          "it has been cancelled, so ask again")
            else:
                item["consumed_at"] = _iso(self._clock())
                self._write(item)
                return ApprovalCheck(True)
        self._log("queue_decided", expired, "expired_old_approval", actor="system")
        return ApprovalCheck(False, "expired", reason)

    def consume_approval(self, item_id: str, signature: str, *, max_age_s: float | None = None,
                         run_id: str | None = None) -> bool:
        """True exactly once for a fresh, approved item whose signature matches (see try_consume_approval for the reason)."""
        return self.try_consume_approval(item_id, signature, max_age_s=max_age_s, run_id=run_id).ok
