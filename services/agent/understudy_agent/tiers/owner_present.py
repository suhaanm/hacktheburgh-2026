"""A one-time token that says the owner is present for THIS real-desktop run (S-14).

Not an environment variable (those are sticky and process-wide): a dry run of the check prints a token for exactly one
run description (target app, point, text, routine), the owner copies it into the real command, and using it deletes it.
It expires after ten minutes; it has 64 bits. It stops ACCIDENTAL or AUTOMATED use (a routine, a stray script, a model).
HONEST LIMIT: it does NOT prove a human is present: the process that runs the dry run for the owner can read the
token it prints and spend it. The owner-present control is the owner's own go in chat for each rung (REAL_CLICKS.md).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from ..security.paths import data_dir

TTL_S = 600.0


def _path(root: Path | None) -> Path:
    return (root or data_dir()) / "owner_tokens.json"


def _load(p: Path) -> dict[str, dict[str, float | str]]:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _save(p: Path, doc: dict[str, dict[str, float | str]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f)
    os.replace(tmp, p)


def issue_owner_token(description: str, *, root: Path | None = None, now: float | None = None) -> str:
    p, t = _path(root), (time.time() if now is None else now)
    doc = {k: v for k, v in _load(p).items() if float(v.get("expires", 0)) > t}   # drop expired ones
    token = secrets.token_hex(8)
    doc[token] = {"description": description, "expires": t + TTL_S}
    _save(p, doc)
    return token


def consume_owner_token(token: str | None, description: str, *, root: Path | None = None, now: float | None = None) -> bool:
    """True once, for the description it was issued for, before it expires. Wrong description: not consumed."""
    if not token:
        return False
    p, t = _path(root), (time.time() if now is None else now)
    doc = _load(p)
    entry = doc.get(token)
    if not entry or float(entry.get("expires", 0)) <= t or entry.get("description") != description:
        return False
    del doc[token]
    _save(p, doc)
    return True


# ----------------------------------------------------------------------------- the permit a real actuator carries (S-14b)
_PERMIT_KEY = secrets.token_bytes(32)          # per process: a permit cannot be forged by building the dataclass by hand
PERMIT_TTL_S = 1800.0


def real_run_description(target_app: str, routine_id: str | None) -> str:
    return f"desktop|{target_app}|{routine_id or '-'}"


@dataclass(frozen=True)
class RunPermit:
    """Proof that the entry point consumed the owner's one-time token (and, for an unattended run, found the routine's
    consent) for THIS target and routine. `MacActuator` takes one and refuses every action without a valid one, so no
    entry point can forget the check."""

    target_app: str
    routine_id: str | None
    unattended: bool
    issued_at: float
    sig: str

    @staticmethod
    def _sign(target_app: str, routine_id: str | None, unattended: bool, issued_at: float) -> str:
        msg = f"{target_app}|{routine_id}|{int(unattended)}|{issued_at}".encode()
        return hmac.new(_PERMIT_KEY, msg, hashlib.sha256).hexdigest()

    def valid_for(self, target_app: str, *, now: float | None = None) -> bool:
        t = time.time() if now is None else now
        return (self.target_app == target_app and t - self.issued_at <= PERMIT_TTL_S
                and hmac.compare_digest(self.sig, self._sign(self.target_app, self.routine_id, self.unattended, self.issued_at)))


def grant_run_permit(token: str | None, description: str, *, target_app: str, routine_id: str | None = None,
                     unattended: bool = False, consent_root: Path | None = None, now: float | None = None) -> RunPermit:
    """Consume the token for `description`; for an unattended run also require the routine's consent record. Raises
    PermissionError with the reason; returns the permit a real actuator needs."""
    if unattended:
        from ..handoff_io import consent_allows, read_consent

        ok, why = consent_allows(read_consent(routine_id, consent_root), "unattended") if routine_id else (False, "no routine id")
        if not ok:
            raise PermissionError(f"an unattended real-desktop run needs the routine's consent: {why}")
    if not consume_owner_token(token, description, now=now):
        raise PermissionError("a real-desktop run needs the owner's one-time token for this run (--owner-present)")
    t = time.time() if now is None else now
    return RunPermit(target_app, routine_id, unattended, t, RunPermit._sign(target_app, routine_id, unattended, t))
