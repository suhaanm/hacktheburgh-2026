"""Layer 8: protected settings (SEC-8).

Page content, tool output and model text can never change the worker's memory, denylist, consent, quiet hours or
kill switch, and the agent cannot click or navigate to the places where those are changed. Only a write whose origin
is the worker's own UI action is accepted.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from .paths import data_dir, kill_path


class Setting(str, Enum):
    MEMORY = "memory"
    DENYLIST = "denylist"
    CONSENT = "consent"
    QUIET_HOURS = "quiet_hours"
    KILL_SWITCH = "kill_switch"
    AUTONOMY = "autonomy"  # the rung: the agent may never raise its own


class Origin(str, Enum):
    HUMAN_UI = "human_ui"   # the worker's own click or approval in the Understudy UI
    AGENT = "agent"
    PAGE = "page"
    TOOL = "tool"
    MODEL = "model"
    SYSTEM = "system"       # code paths such as a detector hit LOWERING a rung


@dataclass(frozen=True)
class SettingsDecision:
    allowed: bool
    setting: Setting | None = None
    reason: str = ""


_ALLOW = SettingsDecision(True)

# Understudy's own control plane. Ports come from env with the documented defaults.
def _control_ports() -> set[int]:
    ports = {7700, 7710, 5173}
    for var in ("ENGINE_PORT", "AGENT_PORT", "DASHBOARD_PORT"):
        v = os.environ.get(var, "").strip()
        if v.isdigit():
            ports.add(int(v))
    return ports


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_PROTECTED_PATHS = re.compile(
    r"^/(kill(/clear)?|memory(/forget|/proposals.*)?|routines/[^/]+/(consent|shadow)|presence/quiet_hours|"
    r"queue/[^/]+/(approve|reject)|denylist.*|settings.*|onboarding|offhours.*)(/.*)?$", re.I)
_SETTING_LABELS = re.compile(
    r"\b(kill ?switch|quiet hours|deny ?list|never list|consent|autonomy|rung|memory( file)?|forget (that|this)|"
    r"run while i.?m away|unattended|opt[- ]?in|settings|preferences)\b", re.I)
_OWN_APPS = {"understudy", "understudy desktop", "understudy dashboard"}


class SettingsGuard:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    # ---- writes
    def authorise_write(self, setting: Setting, origin: Origin) -> SettingsDecision:
        """Only the worker's own UI action may write a protected setting. Origin.SYSTEM may only lower autonomy."""
        if not self.enabled:
            return _ALLOW
        if origin is Origin.HUMAN_UI:
            return SettingsDecision(True, setting, "worker action")
        if origin is Origin.SYSTEM and setting is Setting.AUTONOMY:
            return SettingsDecision(True, setting, "system may lower the rung")
        return SettingsDecision(False, setting, f"{setting.value} can only be changed by the worker, not by {origin.value} content")

    # ---- navigation and clicks by the agent
    def check_navigation(self, url: str) -> SettingsDecision:
        if not self.enabled:
            return _ALLOW
        try:
            parts = urlsplit(url)
        except ValueError:
            return SettingsDecision(False, None, "unparseable address")
        host = (parts.hostname or "").lower()
        try:
            port = parts.port
        except ValueError:
            port = None
        if parts.scheme == "file":
            return self.check_path(parts.path)
        if host in _LOCAL_HOSTS and port in _control_ports():
            return SettingsDecision(False, None, "the agent cannot open Understudy's own control pages or APIs")
        if host in _LOCAL_HOSTS and port is None and _PROTECTED_PATHS.match(parts.path or "/"):
            return SettingsDecision(False, None, "the agent cannot open Understudy's own settings endpoints")
        return _ALLOW

    def check_target(self, *, label: str | None = None, role: str | None = None, url: str | None = None,
                     app: str | None = None) -> SettingsDecision:
        """Clicks and keystrokes aimed at Understudy's own settings are refused."""
        if not self.enabled:
            return _ALLOW
        if app and app.strip().lower() in _OWN_APPS:
            return SettingsDecision(False, None, "the agent cannot operate the Understudy app")
        if url:
            nav = self.check_navigation(url)
            if not nav.allowed:
                return nav
        if label and _SETTING_LABELS.search(label) and (role or "").lower() in ("", "button", "switch", "checkbox", "toggle", "menuitem", "link", "tab", "radio"):
            # Only when the surrounding app/page is ours; a calculator site's "Settings" link is not protected.
            if self._is_own_surface(url, app):
                return SettingsDecision(False, None, "this control changes a protected setting")
        return _ALLOW

    @staticmethod
    def _is_own_surface(url: str | None, app: str | None) -> bool:
        if app and app.strip().lower() in _OWN_APPS:
            return True
        if url:
            try:
                p = urlsplit(url)
                return (p.hostname or "").lower() in _LOCAL_HOSTS and p.port in _control_ports()
            except ValueError:
                return False
        return False

    # ---- file system
    def check_path(self, path: str | os.PathLike[str]) -> SettingsDecision:
        """Refuse agent access to the kill flag, memory file, denylist, consent store and the shared queue."""
        if not self.enabled:
            return _ALLOW
        try:
            p = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return SettingsDecision(False, None, "unreadable path")
        protected = [kill_path(), data_dir() / "denylist.json", data_dir() / "queue", data_dir() / "routines",
                     data_dir() / "audit.jsonl"]
        home = os.environ.get("UNDERSTUDY_HOME", "").strip()
        protected.append(Path.home() / ".understudy")  # the default location is protected even when another home is configured
        if home:
            protected.append(Path(home).expanduser())
        for q in protected:
            try:
                q = q.resolve()
            except OSError:
                continue
            if p == q or q in p.parents:
                kind = Setting.KILL_SWITCH if q.name == "KILL" else Setting.MEMORY if q.name == ".understudy" else None
                return SettingsDecision(False, kind, "the agent cannot touch Understudy's own settings or logs")
        return _ALLOW
