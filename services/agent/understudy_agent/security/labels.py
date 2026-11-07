"""Destructive-label helpers: classify what a click, key press or menu item would do from its label.

The model never decides this. A label we cannot read is "unresolved", and the gate handles that separately.
Patterns are word-bounded and deliberately broad for outward-facing and irreversible verbs: the cost of an extra
queue item is one tap, the cost of a missed send is not undoable.
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum


class ActionClass(str, Enum):
    READ = "read"
    NAVIGATE = "navigate"
    FILL = "fill"
    SUBMIT = "submit"
    SEND = "send"
    POST = "post"
    PAY = "pay"
    DELETE = "delete"
    INSTALL = "install"
    PERMISSION = "permission"
    CREDENTIAL = "credential"
    SYSTEM = "system"


NORMAL_CLASSES = {ActionClass.READ, ActionClass.NAVIGATE, ActionClass.FILL}
OUTWARD_CLASSES = {ActionClass.SEND, ActionClass.POST}
IRREVERSIBLE_CLASSES = {ActionClass.SUBMIT, ActionClass.PAY, ActionClass.DELETE, ActionClass.INSTALL,
                        ActionClass.PERMISSION, ActionClass.CREDENTIAL, ActionClass.SYSTEM}
# The worker may opt a routine into these (D11). The others always need a human click.
OPT_IN_ELIGIBLE = {ActionClass.SUBMIT, ActionClass.SEND, ActionClass.POST, ActionClass.DELETE}

_SEVERITY = [ActionClass.SYSTEM, ActionClass.CREDENTIAL, ActionClass.PERMISSION, ActionClass.INSTALL,
             ActionClass.PAY, ActionClass.DELETE, ActionClass.SUBMIT, ActionClass.SEND, ActionClass.POST,
             ActionClass.FILL, ActionClass.NAVIGATE, ActionClass.READ]

_P = lambda s: re.compile(s, re.I)  # noqa: E731

LABEL_PATTERNS: dict[ActionClass, re.Pattern[str]] = {
    ActionClass.PAY: _P(r"\b(pay|buy|purchase|check ?out|place (your |the )?order|order now|donate|subscribe|"
                        r"add (a )?(payment|card)|confirm payment|top ?up|transfer (funds|money))\b"),
    ActionClass.DELETE: _P(r"\b(delete|remove|erase|discard|destroy|wipe|trash|clear (all|history|data|cache)|"
                           r"uninstall|deactivate|close (my )?account|cancel (my )?(subscription|account|claim)|"
                           r"factory reset|reset all|format)\b"),
    ActionClass.SEND: _P(r"\b(send|reply( all)?|forward|share|invite|e-?mail (this|the|to)|message (him|her|them))\b"),
    ActionClass.POST: _P(r"\b(post(?!\s*-?codes?)|publish|tweet|comment|upload|go live)\b"),
    ActionClass.SUBMIT: _P(r"\b(submit|confirm|finali[sz]e|finish|file (a |the )?(claim|return)|lodge|approve|"
                           r"authori[sz]e|sign[- ]?off|complete (the )?(application|claim|order|purchase|booking)|"
                           r"apply now|accept (and|&) (continue|submit))\b"),
    ActionClass.INSTALL: _P(r"\b(install|download and run|run installer|add to (chrome|browser)|enable extension)\b"),
    ActionClass.PERMISSION: _P(r"\b(allow|grant|permissions?|authori[sz]e access|full disk access|accessibility|"
                               r"screen recording|privacy (settings|&)|security settings|firewall|turn off protection|"
                               r"disable)\b"),
    ActionClass.CREDENTIAL: _P(r"\b(passwords?|sign[- ]?in|log[- ]?in|log[- ]?out|api keys?|tokens?|2fa|two[- ]factor|"
                               r"passkeys?|recovery (code|email|phone)|change (my )?(email|password|phone))\b"),
}

# key combinations (lower-case, '+'-joined, modifiers sorted) that quit, close, delete or wipe
_SYSTEM_KEYS = {"cmd+q", "cmd+alt+esc", "ctrl+alt+delete", "alt+f4", "cmd+ctrl+q", "cmd+shift+q", "cmd+alt+power"}
_DELETE_KEYS = {"cmd+delete", "cmd+backspace", "cmd+shift+delete", "ctrl+shift+delete", "cmd+alt+delete"}

_MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd"]
_MODIFIER_ALIASES = {"control": "ctrl", "ctl": "ctrl", "option": "alt", "opt": "alt", "meta": "cmd", "command": "cmd",
                     "super": "cmd", "win": "cmd", "windows": "cmd", "return": "enter", "escape": "esc", "del": "delete"}


def normalise_label(label: str | None) -> str:
    if not label:
        return ""
    s = unicodedata.normalize("NFKC", label)
    return " ".join(s.split())[:200]


def classify_label(label: str | None) -> set[ActionClass]:
    """Action classes suggested by a button, link or menu label. Empty set = nothing risky recognised."""
    text = normalise_label(label)
    return {cls for cls, pat in LABEL_PATTERNS.items() if text and pat.search(text)}


def canonical_keys(keys: list[str]) -> str:
    parts = [_MODIFIER_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in keys]
    mods = [m for m in _MODIFIER_ORDER if m in parts]
    rest = [p for p in parts if p not in _MODIFIER_ORDER]
    return "+".join(mods + rest)


def classify_keys(keys: list[str]) -> set[ActionClass]:
    combo = canonical_keys(keys)
    if combo in _SYSTEM_KEYS:
        return {ActionClass.SYSTEM}
    if combo in _DELETE_KEYS:
        return {ActionClass.DELETE}
    return set()


def highest(classes: set[ActionClass]) -> ActionClass | None:
    for c in _SEVERITY:
        if c in classes:
            return c
    return None


def risk_class(cls: ActionClass | None) -> str:
    """Contract risk_class for a queue item: normal | outward | irreversible."""
    if cls is None or cls in NORMAL_CLASSES:
        return "normal"
    if cls in OUTWARD_CLASSES:
        return "outward"
    return "irreversible"


_SENSITIVE_PATH = re.compile(
    r"(\.ssh\b|id_(rsa|ed25519|ecdsa)|\.env(\.\w+)?\b|\.aws[\\/]credentials|\.netrc|\.pgpass|\.npmrc|"
    r"\.git-credentials|credentials\.json|keychain|login\.keychain|\bcookies?\.sqlite\b|"
    r"Library[\\/]Application Support[\\/](Google[\\/]Chrome|Firefox)[\\/].*(Login Data|Cookies))", re.I)


def sensitive_path(text: str | None) -> bool:
    """True if a path or typed text points at credential material. Used to stop uploads and typed paths."""
    return bool(text and _SENSITIVE_PATH.search(text))
