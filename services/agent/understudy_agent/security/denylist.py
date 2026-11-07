"""The worker's optional denylist (SEC-9). Checked before any navigation or app launch.

There is NO list of permitted places anywhere in this product (D12, SEC-10): the agent may go anywhere the worker has
not denied. The denylist is data the worker edits; the agent and page content can never change it (settings.py).
An optional starter list is offered once at opt-in; nothing is on by default.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .paths import data_dir

STARTER_ENTRIES: tuple[dict[str, str], ...] = (
    # password managers
    {"kind": "domain", "value": "1password.com", "why": "password manager"},
    {"kind": "domain", "value": "bitwarden.com", "why": "password manager"},
    {"kind": "domain", "value": "lastpass.com", "why": "password manager"},
    {"kind": "domain", "value": "dashlane.com", "why": "password manager"},
    {"kind": "domain", "value": "keepersecurity.com", "why": "password manager"},
    {"kind": "domain", "value": "passwords.google.com", "why": "password manager"},
    {"kind": "app", "value": "1Password", "why": "password manager"},
    {"kind": "app", "value": "Bitwarden", "why": "password manager"},
    {"kind": "app", "value": "Keychain Access", "why": "password manager"},
    {"kind": "app", "value": "Passwords", "why": "password manager"},
    # system security and privacy settings
    {"kind": "app", "value": "System Settings", "why": "system security settings"},
    {"kind": "app", "value": "System Preferences", "why": "system security settings"},
    {"kind": "url_prefix", "value": "x-apple.systempreferences:", "why": "system security settings"},
    {"kind": "domain", "value": "myaccount.google.com", "why": "account security settings"},
    {"kind": "domain", "value": "appleid.apple.com", "why": "account security settings"},
    {"kind": "domain", "value": "account.microsoft.com", "why": "account security settings"},
)

_KINDS = {"domain", "url_prefix", "app"}


def _host(url: str) -> str:
    try:
        parts = urlsplit(url if "://" in url or url.startswith("x-") else "//" + url)
    except ValueError:
        return ""
    return (parts.hostname or "").lower().rstrip(".")


@dataclass(frozen=True)
class DenyDecision:
    denied: bool
    entry: dict[str, Any] | None = None
    reason: str = ""


class Denylist:
    def __init__(self, entries: Iterable[dict[str, Any]] = ()) -> None:
        self.entries: list[dict[str, Any]] = []
        for e in entries:
            kind, value = e.get("kind"), str(e.get("value", "")).strip()
            if kind not in _KINDS or not value:
                raise ValueError(f"bad denylist entry: {e!r}")
            self.entries.append({"kind": kind, "value": value, **({"why": e["why"]} if e.get("why") else {})})

    # ---- checks
    def check_url(self, url: str) -> DenyDecision:
        host = _host(url)
        for e in self.entries:
            v = e["value"]
            if e["kind"] == "domain":
                d = v.lower().lstrip(".")
                if host and (host == d or host.endswith("." + d)):
                    return DenyDecision(True, e, f"{host} is on the worker's denylist")
            elif e["kind"] == "url_prefix":
                if url.lower().startswith(v.lower()):
                    return DenyDecision(True, e, "this address is on the worker's denylist")
        return DenyDecision(False)

    def check_app(self, app_name: str) -> DenyDecision:
        name = (app_name or "").strip().lower()
        for e in self.entries:
            if e["kind"] == "app" and name and name == e["value"].lower():
                return DenyDecision(True, e, f"{app_name} is on the worker's denylist")
        return DenyDecision(False)

    # ---- persistence (the worker's own edits arrive through the UI/engine, never through the agent)
    @staticmethod
    def default_path() -> Path:
        return data_dir() / "denylist.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "Denylist":
        p = path or cls.default_path()
        if not p.exists():
            return cls()
        with open(p, encoding="utf-8") as f:
            return cls(json.load(f).get("entries", []))

    def save(self, path: Path | None = None) -> Path:
        p = path or self.default_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"entries": self.entries}, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return p

    @classmethod
    def starter(cls) -> "Denylist":
        """The optional starter list (password managers, system security settings). Offered at opt-in only."""
        return cls(STARTER_ENTRIES)
