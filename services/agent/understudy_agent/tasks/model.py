"""The task record and its API row (docs/TASKS.md, docs/API_CONTRACT.md "Tasks API").

A `Task` is what the worker asked for in their own words. The words (`text`) are kept only in the task's own local file
(mode 0600) so a restart does not lose a task that is waiting for a click; they are never returned by the API, never logged
and never written to the audit log. What the API shows is the `row`: a short title made by code from the worker's first
words, the current step line, one result line and the times.

Everything a child writes back is UNTRUSTED text: `one_line` cuts it down by code (control characters out, whitespace
collapsed, at most N characters) and the dashboard shows it as plain text.
"""
from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATES = ("planning", "waiting_consent", "running", "done", "stopped", "failed")
FINISHED = frozenset({"done", "stopped", "failed"})
ACTIVE = frozenset({"planning", "running"})
ROUTES = ("answer", "browser", "desktop", "claude_agent", "unclear")
SOURCES = ("typed", "voice")
SCOPES = ("none", "files_and_commands", "everything")

TITLE_MAX = 60
RESULT_MAX = 140
STEP_MAX = 90
STEPS_KEPT = 200
TEXT_MAX = 4000

_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")
# Obvious secrets and identifiers that must never reach a title, a pill or a log: provider keys, long hex or base64 runs,
# card-like digit runs and e-mail addresses. The title is the worker's own words shown back to them; it is still cleaned.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9\-]{10,}"
    r"|(?:eyJ[A-Za-z0-9_\-]{10,}\.){1,2}[A-Za-z0-9_\-]{5,}|[A-Fa-f0-9]{32,}|\b[A-Za-z0-9+/=_\-]{40,}\b"
    r"|\b(?:\d[ -]?){13,19}\b|[\w.+\-]+@[\w\-]+\.[\w.\-]+)")
_SECRET_IN_REQUEST = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9\-]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|passwd|api[_ -]?key|secret|token)\s*[:=]\s*\S{8,})")


def now_iso(t: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if t is None else t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_task_id() -> str:
    return "tk_" + secrets.token_hex(4)


def one_line(text: Any, limit: int, *, redact: bool = True) -> str:
    """Untrusted or free text as ONE plain line of at most `limit` characters. Controls out, spaces collapsed, obvious secrets
    replaced, a trailing ellipsis when it was cut. Never raises."""
    s = _CTRL.sub(" ", str(text or ""))
    s = " ".join(s.split())
    if redact:
        s = _SECRET.sub("…", s)
    if len(s) <= limit:
        return s
    cut = s[: max(1, limit - 1)].rstrip()
    return cut + "…"


def make_title(text: str) -> str:
    return one_line(text, TITLE_MAX) or "Task"


def first_sentence(text: Any, limit: int = RESULT_MAX) -> str:
    """The result line from a child's final message: the first sentence (or the first line), cut by code to `limit`."""
    s = ""
    for line in str(text or "").splitlines():
        clean = _CTRL.sub(" ", line).strip().lstrip("#*->• ").strip()
        if clean:
            s = clean
            break
    m = re.match(r"(.{12,}?[.!?])(?:\s|$)", s)
    if m:
        s = m.group(1)
    return one_line(s, limit)


def looks_like_secret(text: str) -> bool:
    """True when a request contains something that looks like a key or a password. Such a request is not sent anywhere."""
    return bool(_SECRET_IN_REQUEST.search(text or ""))


@dataclass
class Task:
    task_id: str
    text: str                                  # the worker's own words; local file only, never in a row
    source: str = "typed"
    route: str = "unclear"
    state: str = "planning"
    title: str = ""
    attended: bool = True
    latest: str | None = None
    steps: list[str] = field(default_factory=list)
    steps_done: int = 0
    result: str | None = None
    answer: str | None = None                  # the full text of an inline answer (route answer); shown in the detail only
    reason: str | None = None
    started: str = field(default_factory=now_iso)
    finished: str | None = None
    open: dict[str, str] | None = None
    consent: dict[str, Any] | None = None      # the card shown while state is waiting_consent
    question: dict[str, Any] | None = None
    # private working fields (never in the row)
    folder: str | None = None
    scope: str = "none"
    skills: list[str] = field(default_factory=list)
    skills_cfg: dict[str, Any] | None = None   # the skill switches pinned when the card was shown: {"use": bool, "off": [names]}
    hashes: dict[str, str] = field(default_factory=dict)   # scope -> command hash pinned on the card
    session_id: str | None = None
    pid: int | None = None
    max_minutes: int = 30
    stop_requested: bool = False
    out_bytes: int = 0

    # ---- the API shapes
    def row(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "title": self.title, "route": self.route, "source": self.source, "state": self.state,
            "attended": self.attended, "latest": self.latest, "steps_done": self.steps_done, "result": self.result,
            "reason": self.reason, "started": self.started, "finished": self.finished, "open": self.open,
            "needs_consent": self.consent if self.state == "waiting_consent" else None,
            "question": self.question if self.state == "waiting_consent" else None,
        }

    def detail(self) -> dict[str, Any]:
        return {**self.row(), "steps": list(self.steps[-STEPS_KEPT:]), "answer": self.answer if self.route == "answer" else None}

    # ---- file form (local, mode 0600)
    def to_json(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["steps"] = list(self.steps[-STEPS_KEPT:])
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Task":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    def add_step(self, line: str) -> str:
        line = one_line(line, STEP_MAX, redact=False)
        if line:
            self.steps.append(line)
            if len(self.steps) > STEPS_KEPT * 2:
                del self.steps[: len(self.steps) - STEPS_KEPT]
            self.steps_done += 1
            self.latest = line
        return line
