"""Talking to the engine for the Handoff slice: shadow comparisons, the off-hours decision, routine consent.

The engine owns the routine registry, the ladder and the consent record. The agent never keeps a private tally:
it posts code-checked verdicts and reads consent before every background or unattended run.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .supervisor import data_dir

ENGINE_URL = os.environ.get("ENGINE_URL", "http://127.0.0.1:7700")
RUNG_ORDER = ("A0", "A1", "A2", "A3")


class EngineError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"engine {status} {code}: {message}")
        self.status, self.code = status, code


class EngineClient:
    """Thin client. Pass `client=` (an httpx.Client or a Starlette TestClient) to talk to an in-process engine."""

    def __init__(self, base: str | None = None, *, client: httpx.Client | None = None, timeout: float = 3.0) -> None:
        self.base = (base or ENGINE_URL).rstrip("/")
        self._c = client or httpx.Client(timeout=timeout)

    def _req(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        headers = {"X-Understudy-Actor": "agent", **kw.pop("headers", {})}
        try:
            r = self._c.request(method, self.base + path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise EngineError(0, "unreachable", f"engine not reachable: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            try:
                e = r.json()["error"]
                raise EngineError(r.status_code, e.get("code", "error"), e.get("message", "")[:200])
            except (ValueError, KeyError):
                raise EngineError(r.status_code, "error", r.text[:200]) from None
        return r.json()

    def post_shadow(self, routine_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """results: [{run_id, matched, reason?}] or [{run_id, event: failure|undo|injection}]."""
        return self._req("POST", f"/routines/{routine_id}/shadow", json={"results": results})

    def offhours_decide(self, *, person: str, d_min: float, gain: float, loss: float, screen: str | None = None,
                        now: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"person": person, "d_min": d_min, "gain": gain, "loss": loss}
        if screen:
            body["screen"] = screen
        if now:
            body["now"] = now
        return self._req("POST", "/offhours/decide", json=body)

    def offhours_report(self, since: str | None = None) -> dict[str, Any]:
        return self._req("GET", "/offhours/report", params={"since": since} if since else None)


@dataclass(frozen=True)
class Consent:
    mode: str = "none"                  # none | not_now | never | shadow | approval | unattended
    rung: str = "A0"
    irreversible_unattended: tuple[str, ...] = ()
    revoked: bool = False
    present: bool = False


def consent_path(routine_id: str, root: Path | None = None) -> Path:
    return (root or data_dir()) / "routines" / routine_id / "consent.json"


def read_consent(routine_id: str, root: Path | None = None) -> Consent:
    """data/routines/<id>/consent.json, written by the engine. A missing or unreadable file means no consent."""
    p = consent_path(routine_id, root)
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return Consent()
    return Consent(mode=str(d.get("mode", "none")), rung=str(d.get("rung", "A0")),
                   irreversible_unattended=tuple(d.get("irreversible_unattended", [])),
                   revoked=bool(d.get("revoked", False)), present=True)


RUN_KINDS = {
    "shadow": ("shadow", "approval", "unattended"),
    "approved": ("approval", "unattended"),
    "background": ("approval", "unattended"),
    "unattended": ("unattended",),
}


def consent_allows(c: Consent, kind: str) -> tuple[bool, str]:
    """(allowed, reason). `kind`: shadow | approved | background | unattended. Fails closed."""
    if not c.present:
        return False, "no consent record for this routine"
    if c.revoked or c.mode in ("none", "not_now", "never"):
        return False, f"consent is {'revoked' if c.revoked else c.mode}"
    if c.mode not in RUN_KINDS[kind]:
        return False, f"consent mode {c.mode!r} does not allow a {kind} run"
    if kind == "unattended" and RUNG_ORDER.index(c.rung if c.rung in RUNG_ORDER else "A0") < 2:
        return False, f"the routine is on rung {c.rung}; unattended runs need A2 or A3"
    return True, "ok"
