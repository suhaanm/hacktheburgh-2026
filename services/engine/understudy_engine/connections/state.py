"""The worker's connection state: consent, status, revoke (CONNECTIONS).

``<data>/connections/state.json`` (mode 600, written atomically) holds, per connection: whether it is on, the mode (example or real), when the
worker agreed, the command hash they agreed to, the non-secret values they chose (a folder, a site address), the NAMES of the secrets stored
(never a value), the last probe's counts and a short list of events. Both services read it on every call: the engine writes it from the
worker's click, the agent reads it before it starts anything.

Rules, all in code:

* Nothing is ever on until ``connect`` is called with ``confirm=True``. There is no default, no auto-connect in mock mode, tests, demos or
  first run: a missing record means OFF.
* A stored consent is for ONE command hash. If the manifest (or a stand-in script) changes, the hash differs and ``status`` says
  ``needs_reconfirm``; the agent starts nothing in that state until ``reconfirm`` is called with ``confirm=True``.
* ``revoke`` forgets the secrets, turns the connection off and records when. The agent is asked to stop the process by the route.
* A routine may use a connection unattended only if the worker opted THAT routine in for THAT connection (``set_routine``).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import secrets as sec
from .manifest import MODES, Preset, command_hash, consent
from .paths import state_path

_lock = threading.RLock()
_TEXT = re.compile(r"^[\w.@+\- ]{1,120}$")
_ID = re.compile(r"^[a-z][a-z0-9_\-]{1,40}$")
MAX_EVENTS = 30


class ConnectError(Exception):
    """A refusal with a short stable code (and a plain sentence). Never contains a secret or a path the worker typed."""

    def __init__(self, code: str, message: str | None = None, status: int = 400) -> None:
        super().__init__(message or code)
        self.code, self.status = code, status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------------------------------------- the file
def _read() -> dict[str, Any]:
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "connections": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("connections"), dict):
        return {"version": 1, "connections": {}}
    return raw


def _write(doc: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise ConnectError("state_write_failed", "The connection state could not be saved. Nothing was changed.", 500) from None


def record(conn_id: str) -> dict[str, Any] | None:
    rec = _read()["connections"].get(conn_id)
    return rec if isinstance(rec, dict) else None


def _event(rec: dict[str, Any], event: str, **extra: Any) -> None:
    ev = rec.setdefault("events", [])
    ev.append({"t": now_iso(), "event": event, **extra})
    del ev[:-MAX_EVENTS]


# --------------------------------------------------------------------------------------------------------- inputs
def _clean_params(preset: Preset, params: dict[str, Any] | None) -> dict[str, str]:
    """The worker's non-secret choices, validated by kind. Unknown names are refused; every declared one is required."""
    given = {k: v for k, v in (params or {}).items()}
    declared = {p["name"]: p for p in preset.params}
    extra = set(given) - set(declared)
    if extra:
        raise ConnectError("unknown_param", "That field is not part of this connection.")
    out: dict[str, str] = {}
    for name, spec in declared.items():
        v = given.get(name)
        if not isinstance(v, str) or not v.strip():
            raise ConnectError("missing_param", f"{spec['label']} is needed.")
        v = v.strip()
        if "\x00" in v or "\n" in v or len(v) > 400:
            raise ConnectError("bad_param", f"{spec['label']} has a character we cannot use.")
        if spec["kind"] == "path":
            if not v.startswith("/") or ".." in Path(v).parts:
                raise ConnectError("bad_param", f"{spec['label']} must be a full folder path.")
        elif spec["kind"] == "url":
            u = urlsplit(v)
            if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
                raise ConnectError("bad_param", f"{spec['label']} must be an address like https://example.org.")
        elif not _TEXT.match(v):
            raise ConnectError("bad_param", f"{spec['label']} has a character we cannot use.")
        out[name] = v
    return out


def _clean_secrets(preset: Preset, mode: str, values: dict[str, Any] | None) -> dict[str, str]:
    wanted = preset.credential_envs if mode == "real" else []
    given = dict(values or {})
    if set(given) - set(wanted):
        raise ConnectError("unknown_secret", "That token is not part of this connection." if mode == "real" else "An example connection takes no token.")
    missing = [e for e in wanted if not isinstance(given.get(e), str) or not given[e].strip()]
    if missing:
        label = next((c["label"] for c in preset.real["credentials"] if c["env"] == missing[0]), "A token") if preset.real else "A token"
        raise ConnectError("missing_secret", f"{label} is needed.")
    out = {e: given[e].strip() for e in wanted}
    for v in out.values():
        try:
            sec.check_token(v)
        except sec.SecretError:
            raise ConnectError("bad_secret", "The token has a space, a quote or a backslash, or is too short. Paste it again without them.") from None
    return out


# --------------------------------------------------------------------------------------------------------- the verbs
def connect(preset: Preset, *, mode: str, confirm: bool, params: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None,
            store: sec.SecretStore | None = None) -> dict[str, Any]:
    """The worker's click, with the consent shown. Records the consent, stores the tokens, pins the command hash. Raises ``ConnectError``."""
    if confirm is not True:
        raise ConnectError("consent_required", "Connecting needs your click on the consent line.")
    if mode not in MODES:
        raise ConnectError("bad_mode", "Choose Example or Real.")
    if mode == "real" and not preset.has_real:
        raise ConnectError("no_real_mode", "This connection has only an example.")
    clean = _clean_params(preset, params) if mode == "real" else {}
    toks = _clean_secrets(preset, mode, secrets)
    chash = command_hash(preset, mode)
    text = consent(preset, mode, clean)
    with _lock:
        doc = _read()
        old = doc["connections"].get(preset.id)
        names: list[str] = []
        if toks:
            try:
                names = sec.store_all(preset.id, toks, store)
            except sec.SecretError as e:
                raise ConnectError("secret_store_failed", "The token could not be saved. Nothing was connected." + (" The Keychain was not reachable." if e.code.startswith("keychain") else ""), 500) from None
        if isinstance(old, dict):                         # a switch of mode forgets the other mode's secrets
            stale = [n for n in old.get("secrets", []) if n not in names]
            if stale:
                sec.forget(preset.id, stale, store)
        rec = {"mode": mode, "enabled": True, "consented_at": now_iso(), "pinned_hash": chash, "preset_version": preset.version,
               "consent_text": text["summary"], "params": clean, "secrets": names, "revoked_at": None,
               "probe": None, "routines": (old or {}).get("routines", []) if isinstance(old, dict) else [], "events": (old or {}).get("events", []) if isinstance(old, dict) else []}
        _event(rec, "connected", mode=mode)
        doc["connections"][preset.id] = rec
        _write(doc)
    return rec


def reconfirm(preset: Preset, *, confirm: bool) -> dict[str, Any]:
    """The worker confirms again after the manifest (or a stand-in script) changed. Re-pins the hash; keeps the tokens."""
    if confirm is not True:
        raise ConnectError("consent_required", "Confirming needs your click on the consent line.")
    with _lock:
        doc = _read()
        rec = doc["connections"].get(preset.id)
        if not isinstance(rec, dict) or not rec.get("enabled"):
            raise ConnectError("not_connected", "This connection is off. Connect it first.", 409)
        rec["pinned_hash"] = command_hash(preset, rec["mode"])
        rec["preset_version"] = preset.version
        rec["consented_at"] = now_iso()
        rec["consent_text"] = consent(preset, rec["mode"], rec.get("params") or {})["summary"]
        rec["probe"] = None
        _event(rec, "reconfirmed", mode=rec["mode"])
        _write(doc)
    return rec


def revoke(preset: Preset, store: sec.SecretStore | None = None) -> dict[str, Any]:
    """One click: off, tokens forgotten. The caller (the route) also asks the agent to stop the process. Idempotent."""
    with _lock:
        doc = _read()
        rec = doc["connections"].get(preset.id)
        forgot = 0
        if isinstance(rec, dict):
            forgot = sec.forget(preset.id, list(rec.get("secrets", [])), store)
            rec.update({"enabled": False, "revoked_at": now_iso(), "secrets": [], "probe": None, "routines": []})
            _event(rec, "revoked", mode=rec.get("mode"))
            _write(doc)
    return {"id": preset.id, "revoked": True, "secrets_forgotten": forgot}


def mark_probe(conn_id: str, probe: dict[str, Any]) -> None:
    """The last start-up check: counts and an error code only (never a tool description, a result or an argument)."""
    safe = {"at": now_iso(), "ok": bool(probe.get("ok")), "tools": int(probe.get("tools", 0)),
            "counts": {k: int(v) for k, v in dict(probe.get("counts", {})).items() if re.fullmatch(r"[a-z]{3,12}", str(k))},
            "code": str(probe.get("code", ""))[:40] if probe.get("code") else None}
    with _lock:
        doc = _read()
        rec = doc["connections"].get(conn_id)
        if isinstance(rec, dict):
            rec["probe"] = safe
            _write(doc)


def set_routine(preset: Preset, routine_id: str, allowed: bool) -> list[str]:
    """The worker opts ONE routine in (or out) for ONE connection. Only a read is ever allowed unattended, whatever is stored here."""
    if not _ID.match(routine_id or ""):
        raise ConnectError("bad_routine", "That routine id is not valid.")
    with _lock:
        doc = _read()
        rec = doc["connections"].get(preset.id)
        if not isinstance(rec, dict) or not rec.get("enabled"):
            raise ConnectError("not_connected", "Connect it first.", 409)
        ids = [r for r in rec.get("routines", []) if r != routine_id]
        if allowed:
            ids.append(routine_id)
        rec["routines"] = sorted(ids)
        _event(rec, "routine_allowed" if allowed else "routine_removed")
        _write(doc)
        return rec["routines"]


# --------------------------------------------------------------------------------------------------------- reading it back
def status(preset: Preset, rec: dict[str, Any] | None = None, store: sec.SecretStore | None = None) -> dict[str, Any]:
    """``{state, mode, reason}``. state is off, connected, needs_reconfirm, needs_setup or error. The agent starts a process only in
    ``connected`` (or ``error``, to try again)."""
    rec = rec if rec is not None else record(preset.id)
    if not rec or not rec.get("enabled"):
        return {"state": "off", "mode": None, "reason": None}
    mode = rec.get("mode")
    if mode not in MODES or (mode == "real" and not preset.has_real):
        return {"state": "off", "mode": None, "reason": "mode_gone"}
    if rec.get("pinned_hash") != command_hash(preset, mode):
        return {"state": "needs_reconfirm", "mode": mode, "reason": "changed"}
    if mode == "real" and preset.credential_envs:
        have = set(rec.get("secrets", []))
        st = store or sec.backend()
        try:
            missing = [e for e in preset.credential_envs if e not in have or st.get(preset.id, e) is None]
        except sec.SecretError:
            missing = list(preset.credential_envs)
        if missing:
            return {"state": "needs_setup", "mode": mode, "reason": "token_missing"}
    probe = rec.get("probe")
    if isinstance(probe, dict) and probe.get("ok") is False:
        return {"state": "error", "mode": mode, "reason": probe.get("code") or "probe_failed"}
    return {"state": "connected", "mode": mode, "reason": None}


def is_connected(preset: Preset) -> bool:
    return status(preset)["state"] in ("connected", "error")


def routine_allows(conn_id: str, routine_id: str | None) -> bool:
    rec = record(conn_id)
    return bool(rec and rec.get("enabled") and routine_id and routine_id in rec.get("routines", []))


def public_record(rec: dict[str, Any] | None) -> dict[str, Any] | None:
    """The record as the dashboard may see it: no secrets (there are none here, only names), no file paths."""
    if not rec:
        return None
    return {"mode": rec.get("mode"), "enabled": bool(rec.get("enabled")), "consented_at": rec.get("consented_at"), "revoked_at": rec.get("revoked_at"),
            "preset_version": rec.get("preset_version"), "probe": rec.get("probe"), "routines": list(rec.get("routines", [])),
            "secrets_stored": list(rec.get("secrets", [])), "param_names": sorted((rec.get("params") or {}).keys())}
