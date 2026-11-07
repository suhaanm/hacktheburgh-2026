"""Layer 5: data-flow rules (SEC-5).

Values carry taint tags: `web`, `file`, `memory`, `logged_in`. Tainted or personal data cannot be typed, uploaded or put
into an address on a site the routine did not record without a queued approval. A failed check is a refusal to send,
never a silent send (the exfiltration test fails safely).

Note this layer limits where DATA may go; it does not limit where the agent may NAVIGATE (D12, SEC-10: nothing here or
anywhere restricts where the agent may navigate). `recorded_hosts` is fixed when a routine is recorded or its
plan is approved, and page content can never add to it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import parse_qsl, unquote, urlsplit

from .sanitize import strip_invisible


class Taint(str, Enum):
    WEB = "web"
    FILE = "file"
    MEMORY = "memory"
    LOGGED_IN = "logged_in"


class FlowKind(str, Enum):
    TYPE = "type"
    UPLOAD = "upload"
    NAVIGATE = "navigate"


@dataclass(frozen=True)
class Tagged:
    value: str
    tags: frozenset[Taint]
    origin: str = ""


@dataclass(frozen=True)
class FlowDecision:
    verdict: str  # "allow" | "needs_approval"
    reasons: tuple[str, ...] = ()
    tags: frozenset[Taint] = frozenset()
    host: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


_ALLOW = FlowDecision("allow")

_PERSONAL = {
    "nino": re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.I),  # also catches invalid prefixes such as QQ
    "email": re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]{2,}\b"),
    "uk_phone": re.compile(r"(?<!\d)(?:\+44\s?7\d{3}|\(?07\d{3}\)?)\s?\d{3}\s?\d{3}(?!\d)"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}\s?[A-Z0-9]{4}(?:\s?[A-Z0-9]{4}){2,7}\b"),
    "sort_code": re.compile(r"\b\d{2}-\d{2}-\d{2}\b"),
}
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
_MIN_TRACKED_LEN = 4


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def personal_kinds(text: str) -> set[str]:
    """Which personal-data patterns appear in `text` (NI number, email, phone, IBAN, sort code, card number)."""
    kinds = {k for k, p in _PERSONAL.items() if p.search(text)}
    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            kinds.add("card")
    return kinds


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s, _ = strip_invisible(s)
    return " ".join(s.lower().split())


def host_key(url_or_host: str | None) -> str:
    """host[:port] without default ports and without scheme, lower-case. '' if unparseable."""
    if not url_or_host:
        return ""
    raw = url_or_host.strip()
    try:
        p = urlsplit(raw if "://" in raw else "//" + raw)
        host = (p.hostname or "").lower().rstrip(".")
        port = p.port
    except ValueError:
        return ""
    if not host:
        return ""
    default = {"http": 80, "https": 443}.get(p.scheme)
    return f"{host}:{port}" if port and port != default else host


class DataFlowGuard:
    def __init__(self, recorded_hosts: Iterable[str] = (), *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._hosts = {host_key(h) for h in recorded_hosts if host_key(h)}
        self._tracked: list[Tagged] = []

    # ---- state
    @property
    def recorded_hosts(self) -> frozenset[str]:
        return frozenset(self._hosts)

    def is_recorded(self, url_or_host: str | None) -> bool:
        k = host_key(url_or_host)
        return bool(k) and (k in self._hosts or k.split(":")[0] in {h for h in self._hosts if ":" not in h})

    def tag(self, value: str, *tags: Taint, origin: str = "") -> Tagged:
        """Label a value and remember it so later sinks can recognise it, even when embedded in longer text."""
        t = Tagged(value, frozenset(tags or (Taint.WEB,)), origin)
        if len(_fold(value)) >= _MIN_TRACKED_LEN:
            self._tracked.append(t)
        return t

    def tag_fields(self, fields: dict[str, object], *tags: Taint, origin: str = "") -> None:
        """Tag every string and number in a reader result or a household record."""
        for v in _iter_scalars(fields):
            self.tag(str(v), *tags, origin=origin)

    # ---- analysis
    def taint_of(self, text: str) -> tuple[frozenset[Taint], list[str]]:
        """Tags and reasons for the data embedded in `text`."""
        folded = _fold(text)
        tags: set[Taint] = set()
        reasons: list[str] = []
        for t in self._tracked:
            f = _fold(t.value)
            if f and f in folded:
                tags |= t.tags
                reasons.append(f"contains data tagged {'/'.join(sorted(x.value for x in t.tags))}")
        kinds = personal_kinds(text)
        if kinds:
            tags.add(Taint.LOGGED_IN)
            reasons.append("contains personal data (" + ", ".join(sorted(kinds)) + ")")
        return frozenset(tags), reasons[:4]

    # ---- sinks
    def check_text_sink(self, text: str | Tagged, destination: str | None, kind: FlowKind = FlowKind.TYPE) -> FlowDecision:
        """`destination` is the current page address (or host) the text would be typed or uploaded into."""
        if not self.enabled:
            return _ALLOW
        raw = text.value if isinstance(text, Tagged) else text
        tags, reasons = self.taint_of(raw)
        if isinstance(text, Tagged):
            tags = tags | text.tags
            reasons.insert(0, f"tagged {'/'.join(sorted(x.value for x in text.tags))}")
        if not tags:
            return _ALLOW
        if self.is_recorded(destination):
            return FlowDecision("allow", tuple(reasons), tags, host_key(destination))
        why = f"{kind.value} of tainted data to a site the routine did not record"
        return FlowDecision("needs_approval", (why, *reasons), tags, host_key(destination))

    def check_navigation(self, url: str) -> FlowDecision:
        """Tainted or personal data inside an address (path, query or fragment) leaves the machine on load.
        Covers markdown-image and link exfiltration. Navigating itself is never restricted here."""
        if not self.enabled:
            return _ALLOW
        try:
            p = urlsplit(url)
        except ValueError:
            return FlowDecision("needs_approval", ("unparseable address",), frozenset(), "")
        carried = " ".join([unquote(p.path), unquote(p.query), unquote(p.fragment), *(v for _, v in parse_qsl(p.query))])
        tags, reasons = self.taint_of(carried)
        if not tags:
            return _ALLOW
        if self.is_recorded(url):
            return FlowDecision("allow", tuple(reasons), tags, host_key(url))
        return FlowDecision("needs_approval", ("address carries tainted data to a site the routine did not record", *reasons),
                            tags, host_key(url))

    def check_upload(self, path_or_text: str, destination: str | None) -> FlowDecision:
        """Uploading a file: the path itself may be credential material, and file contents are `file` data."""
        from .labels import sensitive_path

        if not self.enabled:
            return _ALLOW
        if sensitive_path(path_or_text):
            return FlowDecision("needs_approval", ("upload of credential material",), frozenset({Taint.FILE}), host_key(destination))
        if self.is_recorded(destination):
            return _ALLOW
        return FlowDecision("needs_approval", ("upload to a site the routine did not record",), frozenset({Taint.FILE}),
                            host_key(destination))


def _iter_scalars(obj: object) -> Iterable[object]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_scalars(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_scalars(v)
    elif isinstance(obj, (str, int, float)) and not isinstance(obj, bool):
        yield obj
