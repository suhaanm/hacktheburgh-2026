"""The canary kit (PRV-1 acceptance): plant unique tokens in fixtures, run a flow, scan every outbound request.

    from understudy_engine.privacy.canary import plant, scan, assert_no_canaries
    planted = plant(fixtures)                  # fixtures: nested dicts and lists, changed in place
    ... run the flow with a CapturingPort ...
    assert_no_canaries(port, planted)          # raises AssertionError naming the kinds and request numbers that leaked

Kinds planted: person names, emails, meeting titles, file paths, commit messages and customer names. Every token is built
from invented words plus a short unique core, so it cannot occur in a payload by accident; the scan looks for each invented
word and each core, case-insensitively, also with separators removed (``zephyra_quillmoor``), URL-encoded, and as base64
or hex of the whole token.

What the scan does not catch: a paraphrase, a translation, a hash or a character-code encoding of a token. It measures
"these exact planted strings did not reach the model", which is the claim the project makes, and nothing larger.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import random
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import unquote

from . import ledger

KINDS = ("person_name", "email", "meeting_title", "file_path", "commit_message", "customer_name")

_FIRST = ["Zephyr", "Quill", "Brann", "Velth", "Orsin", "Tamsel", "Marl", "Ixion", "Corvane", "Ostrel", "Dunmar", "Pellow"]
_MID = ["a", "o", "e", "in", "an", "or", "el", "ith", "und", "yr"]
_END = ["ine", "ock", "moor", "thorpe", "wick", "ley", "stone", "vane", "crest", "fell", "gate", "mere"]
_SECRET = ["ledger", "payroll", "merger", "redundancy", "acquisition", "salary", "appeal", "audit"]
_ALPHA = "abcdefghjkmnpqrstuvwxyz"
_DIGIT = "23456789"


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    needles: tuple[str, ...]


@dataclass
class Planted:
    """The tokens planted for one run. Build with ``plant(...)`` or call the generators below for hand-built fixtures."""

    seed: int = 0
    tokens: list[Token] = field(default_factory=list)
    _rng: random.Random = field(init=False, repr=False)
    _words: set[str] = field(default_factory=set, init=False, repr=False)
    _cores: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ---- generators (each registers its token and returns the string to put in a fixture)
    def _word(self) -> str:
        for _ in range(1000):
            w = self._rng.choice(_FIRST) + self._rng.choice(_MID) + self._rng.choice(_END)
            if w.lower() not in self._words:
                self._words.add(w.lower())
                return w
        raise RuntimeError("canary vocabulary exhausted")

    def _core(self) -> str:
        for _ in range(1000):
            c = "".join(self._rng.choice(_ALPHA) for _ in range(3)) + "".join(self._rng.choice(_DIGIT) for _ in range(3))
            c = "".join(self._rng.sample(c, len(c)))
            if c not in self._cores:
                self._cores.add(c)
                return c
        raise RuntimeError("canary cores exhausted")

    def _register(self, kind: str, value: str, needles: Iterable[str]) -> str:
        ns = tuple(dict.fromkeys(n.lower() for n in needles if len(n) >= 5))
        self.tokens.append(Token(kind, value, ns))
        return value

    def person_name(self) -> str:
        a, b = self._word(), self._word()
        return self._register("person_name", f"{a} {b}", [a, b])

    def email(self) -> str:
        a, b, c = self._word().lower(), self._word().lower(), self._core()
        return self._register("email", f"{a}.{b}.{c}@canary-mail.example", [a, b, c, "canary-mail.example"])

    def meeting_title(self) -> str:
        code, other, c = self._word(), self._word(), self._core()
        topic = self._rng.choice(["renewal", "restructure", "pricing", "handover", "offsite", "roadmap"])
        return self._register("meeting_title", f"Project {code}: {other} {topic} review {c}", [code, other, c])

    def file_path(self) -> str:
        user, code, sec, c = self._word().lower(), self._word().lower(), self._rng.choice(_SECRET), self._core()
        return self._register("file_path", f"/Users/{user}/Projects/{code}-{c}/{sec}_{c}.py", [user, code, c])

    def commit_message(self) -> str:
        code, cust, c = self._word(), self._word(), self._core()
        sec = self._rng.choice(_SECRET)
        return self._register("commit_message", f"fix {code} {sec} rounding for {cust} ({c})", [code, cust, c])

    def customer_name(self) -> str:
        a, b, c = self._word(), self._word(), self._core()
        return self._register("customer_name", f"{a} & {b} Holdings {c}", [a, b, c])

    def make(self, kind: str) -> str:
        return {
            "person_name": self.person_name, "email": self.email, "meeting_title": self.meeting_title,
            "file_path": self.file_path, "commit_message": self.commit_message, "customer_name": self.customer_name,
        }[kind]()

    def add_text(self, text: str, kind: str = "person_name") -> str:
        """Register an existing sensitive string from a hand-written fixture (for example a real-looking name already in it).
        Words of 4 or more letters are searched for, case-insensitively."""
        words = [w for w in re.split(r"[^A-Za-z0-9]+", text) if len(w) >= 4]
        self.tokens.append(Token(kind, text, tuple(dict.fromkeys(w.lower() for w in words + ([text] if len(text) >= 5 else [])))))
        return text

    # ---- views
    def __len__(self) -> int:
        return len(self.tokens)

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in self.tokens:
            out[t.kind] = out.get(t.kind, 0) + 1
        return out


# --------------------------------------------------------------------------------------------------------- planting
_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"^(e[-_]?mail|mail|email_?address|from_?address|to_?address)$", re.I)),
    ("commit_message", re.compile(r"^(message|msg|commit_?message|commit_?msg|body|log)$", re.I)),
    ("file_path", re.compile(r"^(path|paths|file|files|filename|file_?name|filepath|file_?path|dir|directory|repo|repo_?path|cwd|touched|changed_?files)$", re.I)),
    ("customer_name", re.compile(r"^(customer|client|company|org|organi[sz]ation|account|vendor|employer|tenant)(_?name)?$", re.I)),
    ("meeting_title", re.compile(r"^(title|subject|summary|topic|event_?name|meeting|meeting_?title|location|description|notes|agenda)$", re.I)),
    ("person_name", re.compile(r"^(name|full_?name|first_?name|last_?name|person|author|committer|organi[sz]er|owner|attendees?|participants?|assignee|reviewer|speaker|user|contact|display_?name)$", re.I)),
]


def _kind_for(key: str) -> str | None:
    for kind, rx in _HINTS:
        if rx.match(key):
            return kind
    return None


def _plant_value(planted: Planted, kind: str, original: str, mode: str) -> str:
    canary = planted.make(kind)
    if mode == "replace" or kind == "email" or not original:
        return canary
    if kind == "file_path":
        return original.rstrip("/") + "/" + canary.rsplit("/", 1)[-1]
    return f"{original} {canary}"


def _walk(node: Any, planted: Planted, mode: str, hint: str | None) -> Any:
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            kind = _kind_for(k) if isinstance(k, str) else None
            if isinstance(v, str):
                if kind is not None and not (k.lower() == "address" and "@" not in v):
                    node[k] = _plant_value(planted, kind, v, mode)
            elif isinstance(v, (list, tuple)) and kind is not None and all(isinstance(x, str) for x in v):
                node[k] = [_plant_value(planted, kind, x, mode) for x in v]
            else:
                node[k] = _walk(v, planted, mode, kind)
        return node
    if isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and hint is not None:
                node[i] = _plant_value(planted, hint, v, mode)
            else:
                node[i] = _walk(v, planted, mode, hint)
        return node
    return node


def plant(fixtures: Any, *, seed: int = 0, mode: str = "replace", planted: Planted | None = None) -> Planted:
    """Inject unique canary tokens into ``fixtures`` (nested dicts and lists, changed in place) wherever a key looks like a
    name, email, title, path, commit message or customer. ``mode="replace"`` swaps the value; ``mode="append"`` keeps the
    original text and appends a token (use it when code reads keywords from the original). Returns the ``Planted`` record.

    Fixtures that are not dicts or lists (ICS text, files) can be built by hand with the ``Planted`` generators:
    ``p = Planted(seed); title = p.meeting_title(); email = p.email()``."""
    if mode not in ("replace", "append"):
        raise ValueError("mode must be 'replace' or 'append'")
    p = planted or Planted(seed)
    _walk(fixtures, p, mode, None)
    if len(p) == 0:
        raise AssertionError("plant() found nothing to plant: no key in the fixtures looks like a name, email, title, path, "
                             "message or customer. Build tokens by hand with Planted(...).person_name() and friends.")
    return p


# --------------------------------------------------------------------------------------------------------- scanning
@dataclass(frozen=True)
class Leak:
    request: int
    kind: str
    needle: str
    token: str


@dataclass
class CanaryReport:
    requests: int
    planted: int
    needles: int
    leaks: list[Leak]
    by_kind: dict[str, int]

    @property
    def leaked(self) -> int:
        """Distinct planted tokens that appeared in at least one request."""
        return len({(lk.kind, lk.token) for lk in self.leaks})

    @property
    def ok(self) -> bool:
        return not self.leaks

    def summary(self) -> str:
        kinds = sorted({lk.kind for lk in self.leaks})
        return (f"{self.requests} request(s) scanned, {self.planted} token(s) planted, {self.leaked} leaked"
                + (f" (kinds: {', '.join(kinds)}; requests: {sorted({lk.request for lk in self.leaks})})" if self.leaks else ""))


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _flatten(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, bytes):
        out.append(obj.decode("utf-8", "replace"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_flatten(v))
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            out.extend(_flatten(v))
    elif obj is not None:
        out.append(str(obj))
    return out


def _forms(raw: Any) -> list[str]:
    """Searchable renderings of one request body: the text, its leaves, URL-decoded, and decoded base64/hex runs."""
    leaves = _flatten(raw)
    text = "\n".join(leaves)
    if not isinstance(raw, str):
        text += "\n" + json.dumps(raw, default=str, ensure_ascii=True)
    forms = [text, unquote(text)]
    for m in re.finditer(r"[A-Za-z0-9+/_\-]{16,}={0,2}", text):
        chunk = m.group(0)
        for dec in (_b64, _hex):
            d = dec(chunk)
            if d:
                forms.append(d)
    return [f.lower() for f in forms]


def _b64(s: str) -> str | None:
    try:
        pad = "=" * (-len(s) % 4)
        return base64.b64decode(s.replace("-", "+").replace("_", "/") + pad, validate=False).decode("utf-8", "ignore") or None
    except (binascii.Error, ValueError):
        return None


def _hex(s: str) -> str | None:
    if re.fullmatch(r"(?:[0-9a-fA-F]{2})+", s):
        try:
            return bytes.fromhex(s).decode("utf-8", "ignore") or None
        except ValueError:
            return None
    return None


def request_bodies(captured: Any) -> list[Any]:
    """Normalise whatever a test has: a ``CapturingPort``, a list of captured requests, strings, dicts or bytes."""
    reqs = getattr(captured, "requests", None)
    if reqs is not None:
        return [getattr(r, "body", r) for r in reqs]
    if isinstance(captured, (list, tuple)):
        return [getattr(r, "body", r) for r in captured]
    return [getattr(captured, "body", captured)]


def scan(captured: Any, planted: Planted) -> CanaryReport:
    """Search every captured request for every planted token. Never raises on a leak; see ``assert_no_canaries``."""
    bodies = request_bodies(captured)
    leaks: list[Leak] = []
    n_needles = 0
    full_variants: list[tuple[Token, list[str]]] = []
    for t in planted.tokens:
        n_needles += len(t.needles)
        v = t.value.encode()
        full_variants.append((t, [base64.b64encode(v).decode().lower().rstrip("="), v.hex().lower(),
                                  base64.urlsafe_b64encode(v).decode().lower().rstrip("=")]))
    for i, body in enumerate(bodies):
        forms = _forms(body)
        squashed = [_squash(f) for f in forms]
        for t, variants in full_variants:
            hit = None
            for n in t.needles:
                sq = _squash(n)
                if any(n in f for f in forms) or (len(sq) >= 5 and any(sq in s for s in squashed)):
                    hit = n
                    break
            if hit is None:
                for var in variants:
                    if var and any(var in f for f in forms):
                        hit = var
                        break
            if hit is not None:
                leaks.append(Leak(i, t.kind, hit, t.value))
    return CanaryReport(len(bodies), len(planted), n_needles, leaks, planted.by_kind())


def assert_no_canaries(captured: Any, planted: Planted, *, min_requests: int = 0) -> CanaryReport:
    """Fail the test if any planted token reached any captured request (or if nothing was planted, or fewer than
    ``min_requests`` requests were captured, because then the check would prove nothing)."""
    if len(planted) == 0:
        raise AssertionError("nothing was planted, so this check would prove nothing")
    report = scan(captured, planted)
    if report.requests < min_requests:
        raise AssertionError(f"expected at least {min_requests} captured request(s), saw {report.requests}; the flow may not have run")
    if report.leaks:
        raise AssertionError("planted canary token(s) reached the model port: " + report.summary())
    return report


# --------------------------------------------------------------------------------------------------------- artifacts (PRV-4)
#: what PRV-4 says must never hold source text: the ledger files, the audit log, the approval queue and the logs.
PRV4_ARTIFACTS = ("egress_ledger.jsonl", "egress_blocked.jsonl", "audit.jsonl", "queue", "logs")


def scan_paths(paths: Iterable[Any], planted: Planted) -> CanaryReport:
    """Search files (directories are walked) for planted tokens: the PRV-4 check that logs, audit lines and queue items hold no
    source text. ``requests`` in the report counts the files read. Missing paths are skipped."""
    from pathlib import Path

    bodies: list[str] = []
    for raw in paths:
        p = Path(raw)
        files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else []
        for f in files:
            try:
                bodies.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return scan(bodies, planted)


def scan_artifacts(planted: Planted, data_dir: Any | None = None) -> CanaryReport:
    """``scan_paths`` over the PRV-4 artifacts under the data dir (default: the current one)."""
    from ._paths import data_dir as current

    root = data_dir or current()
    from pathlib import Path

    return scan_paths([Path(root) / name for name in PRV4_ARTIFACTS], planted)


# --------------------------------------------------------------------------------------------------------- recording
_rec_lock = threading.Lock()


def record_run(flow: str, report: CanaryReport) -> dict[str, Any]:
    """Add one canary run to ``<data dir>/privacy_canary.json`` (what ``GET /privacy/summary`` shows as ``canary``)."""
    return record_totals(flow, requests=report.requests, planted=report.planted, leaked=report.leaked, by_kind=report.by_kind)


def record_totals(flow: str, *, requests: int, planted: int, leaked: int, by_kind: dict[str, int] | None = None) -> dict[str, Any]:
    path = ledger.canary_path()
    with _rec_lock:
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
        flows = [f for f in cur.get("flows", []) if f.get("flow") != flow]
        flows.append({"flow": flow, "requests": requests, "planted": planted, "leaked": leaked, "by_kind": by_kind or {}})
        cur = {
            "runs": int(cur.get("runs", 0)) + 1,
            "planted": int(cur.get("planted", 0)) + planted,
            "leaked": int(cur.get("leaked", 0)) + leaked,
            "last_run": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "flows": flows[-50:],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur), encoding="utf-8")
        os.replace(tmp, path)
    return cur


def fingerprint(value: str) -> str:
    """Short stable id for a token in reports (so reports can name a token without repeating it)."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]
