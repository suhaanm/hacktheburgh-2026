"""Destructive-label helpers: classify what a click, key press or menu item would do from its label.

The model never decides this. A label we cannot read is "unresolved", and the gate handles that separately.
Patterns are word-bounded and deliberately broad for outward-facing and irreversible verbs: the cost of an extra
queue item is one tap, the cost of a missed send is not undoable.
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum

from .sanitize import strip_invisible


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
    ActionClass.PAY: _P(r"\b(pay(ments?|ing)?|buy|purchase|check ?out|place (your |the )?order|order( now)?|donate|subscribe|"
                        r"add (a )?(payment|card)|add to (my )?(basket|cart|bag|trolley)|book( now| a| your)?|reserve|"
                        r"confirm payment|top ?up|transfer (funds|money)|invoices?|refunds?|wire (transfers?|funds|money)|"
                        r"bezahlen|zahlen|kaufen|kostenpflichtig|pagar|pago|comprar|acheter|payer|paiement)\b"
                        r"|支付|付款|购买|下单|结账|買う|支払"),
    ActionClass.DELETE: _P(r"\b(delete|remove|erase|discard|destroy|wipe|trash|clear (all|history|data|cache)|"
                           r"uninstall|deactivate|close (my )?account|cancel (my )?(subscription|account|claim)|"
                           r"factory reset|reset all|format|withdraw|revoke|unsubscribe|disconnect|unlink|"
                           r"l(oe|ö)schen|entfernen|eliminar|borrar|supprimer|effacer)\b|删除|移除|清除|刪除"),
    ActionClass.SEND: _P(r"\b(send|reply( all)?|forward|share|invite|e-?mail (this|the|to)|message (him|her|them)|"
                         r"absenden|senden|enviar|envoyer)\b|发送|發送|送信"),
    ActionClass.POST: _P(r"\b(post(?!\s*-?codes?)|publish|tweet|comment|upload|go live)\b"),
    ActionClass.SUBMIT: _P(r"\b(submit|confirm|finali[sz]e|finish|file (a |the )?(claim|return)|lodge|approve|"
                           r"authori[sz]e|sign[- ]?off|complete (the )?(application|claim|order|purchase|booking)|"
                           r"apply now|accept( all| and| &)?( continue| submit| cookies| terms)?|i agree|agree( and| &)?( continue)?|"
                           r"declare|register|sign[- ]?up|create (an |my |your )?account|join( now| us)?|enrol(l)?|"
                           r"best(ae|ä)tigen|confirmar|valider|enviar solicitud)\b|确认|確認|提交|同意|注册|申报"),
    ActionClass.INSTALL: _P(r"\b(install|download and run|run installer|add to (chrome|browser)|enable extension)\b"),
    ActionClass.PERMISSION: _P(r"\b(allow|grant|permissions?|authori[sz]e access|full disk access|accessibility|"
                               r"screen recording|privacy (settings|&)|security settings|firewall|turn off protection|"
                               r"disable|revoke access)\b"),
    ActionClass.CREDENTIAL: _P(r"\b(passwords?|pass-?codes?|sign[- ]?in|log[- ]?in|api keys?|tokens?|2fa|two[- ]factor|"
                               r"otps?|one[- ]?time (pass-?)?(codes?|passwords?|pins?)|login codes?|seed phrases?|"
                               r"(private|secret) keys?|passkeys?|recovery (code|email|phone)|change (my )?(email|password|phone))\b"),
    # the machine or the session itself: quit, restart, sign out. Never opt-in eligible.
    ActionClass.SYSTEM: _P(r"\b(shut ?down|restart|reboot|quit|exit|power off|sign[- ]?out|log[- ]?out|force quit)\b"),
}

# Verbs that are fine on a submit-type control. A submit control whose label is NOT recognised as risky and is NOT one of
# these is treated as unknown, and unknown outward-capable controls are a human's call (the gate is allow-by-listing here,
# not block-by-listing). Calculators, wizards and searches are what ordinary work looks like.
BENIGN_SUBMIT = _P(r"^\s*(calculate|continue|next|back|previous|go( back)?|try again|start again|search|find( out)?|show|view|see|"
                   r"get|check|work( it)? out|estimate|compute|save( draft)?|update|apply filters?|reset|clear form|"
                   r"reject|decline|dismiss|no,? thanks|not now|close|open|expand|more|learn more|read)\b")

_MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd"]
_MODIFIER_ALIASES = {"control": "ctrl", "ctl": "ctrl", "option": "alt", "opt": "alt", "meta": "cmd", "command": "cmd",
                     "super": "cmd", "win": "cmd", "windows": "cmd", "return": "enter", "escape": "esc", "del": "delete"}


def _canon(spec: str) -> str:
    """The chord as `canonical_keys` will compute it (modifiers in the fixed order ctrl, alt, shift, cmd), so a set spelled in any
    order matches (S-25: the sets used to be written in an order the code never produces, so they never matched)."""
    parts = [_MODIFIER_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in spec.split("+")]
    return "+".join([m for m in _MODIFIER_ORDER if m in parts] + [p for p in parts if p not in _MODIFIER_ORDER])


def _canon_set(*specs: str) -> set[str]:
    return {_canon(x) for x in specs}


# chords that quit, lock, log out, switch away, write a file or leave the app: the SYSTEM class (always a human's call)
_SYSTEM_KEYS = _canon_set("cmd+q", "cmd+alt+esc", "ctrl+alt+delete", "alt+f4", "cmd+ctrl+q", "cmd+shift+q", "cmd+alt+power",
                          "cmd+space", "cmd+tab", "cmd+s", "cmd+shift+s", "cmd+w", "cmd+n", "cmd+o", "cmd+p", "cmd+h", "cmd+m",
                          "cmd+shift+3", "cmd+shift+4", "cmd+shift+5", "cmd+alt+d", "cmd+shift+n")
_DELETE_KEYS = _canon_set("cmd+delete", "cmd+backspace", "cmd+shift+delete", "ctrl+shift+delete", "cmd+alt+delete")
# a paste puts whatever is on the clipboard (maybe a password the owner just copied) into the target: a human's call
_PASTE_KEYS = _canon_set("cmd+v", "ctrl+v", "cmd+shift+v", "ctrl+shift+v", "cmd+alt+shift+v", "shift+insert", "ctrl+insert")


# Cyrillic and Greek letters that read as a Latin letter (code point, Latin letter). A control named with some of them ("Pаy now" with a
# Cyrillic а) would slip past the word lists, so labels are folded to Latin before they are matched (review hardening note).
_LOOKALIKES = [(0x430, "a"), (0x435, "e"), (0x43E, "o"), (0x440, "p"), (0x441, "c"), (0x445, "x"), (0x443, "y"), (0x456, "i"),
               (0x458, "j"), (0x455, "s"), (0x501, "d"), (0x4BB, "h"), (0x51B, "q"), (0x51D, "w"), (0x475, "v"),
               (0x410, "A"), (0x412, "B"), (0x415, "E"), (0x41A, "K"), (0x41C, "M"), (0x41D, "H"), (0x41E, "O"), (0x420, "P"),
               (0x421, "C"), (0x422, "T"), (0x425, "X"), (0x406, "I"), (0x405, "S"), (0x408, "J"),
               (0x3B1, "a"), (0x3BF, "o"), (0x3C1, "p"), (0x3BD, "v"), (0x3C5, "u"), (0x3B9, "i"), (0x3BA, "k"), (0x3C4, "t"),
               (0x3C7, "x"), (0x391, "A"), (0x392, "B"), (0x395, "E"), (0x396, "Z"), (0x397, "H"), (0x399, "I"), (0x39A, "K"),
               (0x39C, "M"), (0x39D, "N"), (0x39F, "O"), (0x3A1, "P"), (0x3A4, "T"), (0x3A5, "Y"), (0x3A7, "X")]
_CONFUSABLES = {cp: ch for cp, ch in _LOOKALIKES}


def _script(ch: str) -> str:
    try:
        return unicodedata.name(ch).split(" ", 1)[0]
    except ValueError:
        return ""


def mixed_script(label: str | None) -> bool:
    """True when ONE word mixes Latin letters with Cyrillic or Greek ones: the signature of a look-alike spelling meant to pass a
    word list. Zero-width characters are removed first. A whole word in one script is not flagged."""
    if not label:
        return False
    s, _ = strip_invisible(unicodedata.normalize("NFKC", label))
    for word in re.findall(r"\w+", s):
        scripts = {_script(c) for c in word if c.isalpha()}
        if "LATIN" in scripts and scripts & {"CYRILLIC", "GREEK"}:
            return True
    return False


def normalise_label(label: str | None) -> str:
    if not label:
        return ""
    s = unicodedata.normalize("NFKC", label)
    s, _ = strip_invisible(s)                     # zero-width and bidi characters inside a word ("Pa<ZWSP>y now")
    s = s.translate(_CONFUSABLES)                 # look-alike letters
    return " ".join(s.split())[:200]


def is_benign_submit_label(label: str | None) -> bool:
    return bool(BENIGN_SUBMIT.search(normalise_label(label)))


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
    if combo in _PASTE_KEYS:
        return {ActionClass.CREDENTIAL}
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
