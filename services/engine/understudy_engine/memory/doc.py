"""The memory file as a document: parse, render, stable line ids (MEM-1).

Format (section 6.4 of the implementation spec)::

    ---
    role: benefits-processor
    revision: 12
    ---
    ## Preferences
    - Summaries: short. Tone: plain.  <!-- id:l_1a2b3c4d | note -->

Rules this module keeps:

* Six known sections, in a fixed order. Any other section the worker adds is kept verbatim.
* Every bullet in a known section has a stable id in a trailing HTML comment. A bullet typed by hand
  without one gets a deterministic id on the next parse; an id the worker leaves alone never changes.
* Parsing then rendering is idempotent, and the worker's own wording is never rewritten.
* Text that goes in through code is flattened to one line and stripped of comment markers, so a line
  can never open a new section or hide a second line inside a comment.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

SECTIONS: tuple[str, ...] = ("Preferences", "Procedure", "Routines", "Corrections", "Skill state", "Never")
_CANON = {s.lower(): s for s in SECTIONS}

_HEADING = re.compile(r"^##\s+(?P<name>.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(?P<body>\S.*?)\s*$")
_TRAILING_COMMENT = re.compile(r"\s*<!--(?P<c>.*?)-->\s*$")
_ID_META = re.compile(r"^\s*id:(?P<id>[A-Za-z0-9_.\-]+)\s*(?:\|\s*(?P<note>.*?))?\s*$", re.S)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁠﻿]")

MAX_TEXT = 400


def clean_text(text: str, limit: int = MAX_TEXT) -> str:
    """Flatten to one safe line: no newlines, no control or invisible characters, no comment markers."""
    t = _CTRL.sub("", str(text).replace("\r", "\n"))
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("<!--", "").replace("-->", "").replace("<!", "").strip()
    t = re.sub(r"^[#>*\-\s]+", "", t)  # nothing that could read as a heading or a quote at line start
    return t[:limit].rstrip(" ,;:")


def derive_id(section: str, text: str, taken: set[str]) -> str:
    base = "l_" + hashlib.sha1(f"{section}\x00{text}".encode()).hexdigest()[:8]
    cand, k = base, 2
    while cand in taken:
        cand = f"{base}-{k}"
        k += 1
    return cand


@dataclass
class Line:
    id: str
    text: str
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text, "note": self.note}


@dataclass
class Section:
    name: str
    known: bool = True
    items: list[Line | str] = field(default_factory=list)  # known sections: Line, or raw str kept verbatim
    raw: str = ""                                          # unknown sections: the body, verbatim

    def lines(self) -> list[Line]:
        return [i for i in self.items if isinstance(i, Line)]


@dataclass
class MemoryDoc:
    front: dict[str, Any] = field(default_factory=dict)
    preamble: str = ""
    sections: list[Section] = field(default_factory=list)

    # ----- front matter -----
    @property
    def role(self) -> str:
        return str(self.front.get("role") or "unknown")

    @role.setter
    def role(self, value: str) -> None:
        self.front["role"] = value

    @property
    def revision(self) -> int:
        try:
            return int(self.front.get("revision", 0))
        except (TypeError, ValueError):
            return 0

    @revision.setter
    def revision(self, value: int) -> None:
        self.front["revision"] = int(value)

    # ----- sections -----
    def section(self, name: str, create: bool = True) -> Section | None:
        canon = _CANON.get(name.lower(), name)
        for s in self.sections:
            if s.name == canon:
                return s
        if not create:
            return None
        sec = Section(canon, known=canon in SECTIONS)
        self.sections.append(sec)
        return sec

    def all_ids(self) -> set[str]:
        return {ln.id for s in self.sections for ln in s.lines()}

    def find(self, line_id: str) -> tuple[Section, Line] | None:
        for s in self.sections:
            for ln in s.lines():
                if ln.id == line_id:
                    return s, ln
        return None

    def add(self, section: str, text: str, note: str = "", line_id: str | None = None) -> Line:
        sec = self.section(section)
        assert sec is not None
        if not sec.known:
            raise ValueError(f"cannot add structured lines to unknown section {section!r}")
        t = clean_text(text)
        if not t:
            raise ValueError("empty line")
        lid = line_id or derive_id(sec.name, t, self.all_ids())
        if lid in self.all_ids():
            raise ValueError(f"line id {lid!r} already exists")
        ln = Line(lid, t, clean_text(note, 200))
        sec.items.append(ln)
        return ln

    def remove(self, line_id: str) -> Line | None:
        for s in self.sections:
            for i, it in enumerate(s.items):
                if isinstance(it, Line) and it.id == line_id:
                    del s.items[i]
                    return it
        return None

    def by_section(self) -> dict[str, list[dict[str, str]]]:
        out: dict[str, list[dict[str, str]]] = {name: [] for name in SECTIONS}
        for s in self.sections:
            if s.known:
                out[s.name].extend(ln.to_dict() for ln in s.lines())
        return out

    def unknown_sections(self) -> list[str]:
        return [s.name for s in self.sections if not s.known]


# ---------------------------------------------------------------------------------------------
def _parse_front(fm: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(fm) if fm.strip() else {}
    except yaml.YAMLError:
        data = {}
    return dict(data) if isinstance(data, dict) else {}


def parse(markdown: str) -> MemoryDoc:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    front: dict[str, Any] = {}
    body = text
    if text.startswith("---\n") or text.startswith("---\r"):
        end = text.find("\n---", 3)
        if end != -1:
            front = _parse_front(text[4:end])
            nl = text.find("\n", end + 4)
            body = text[nl + 1:] if nl != -1 else ""
    doc = MemoryDoc(front=front)
    pre: list[str] = []
    cur: Section | None = None
    raw_buf: list[str] = []
    taken: set[str] = set()

    def flush_raw() -> None:
        nonlocal raw_buf
        if cur is not None and not cur.known:
            cur.raw = "\n".join(raw_buf).strip("\n")
        raw_buf = []

    for ln in body.split("\n"):
        m = _HEADING.match(ln)
        if m:
            flush_raw()
            name = m.group("name").strip()
            canon = _CANON.get(name.lower())
            if canon is not None:
                existing = next((s for s in doc.sections if s.name == canon), None)
                cur = existing or Section(canon, known=True)
                if existing is None:
                    doc.sections.append(cur)
            else:
                cur = Section(name, known=False)
                doc.sections.append(cur)
            continue
        if cur is None:
            pre.append(ln)
            continue
        if not cur.known:
            raw_buf.append(ln)
            continue
        if not ln.strip():
            continue
        b = _BULLET.match(ln)
        if not b:
            cur.items.append(ln.rstrip())
            continue
        body_txt = b.group("body")
        note, lid = "", ""
        cm = _TRAILING_COMMENT.search(body_txt)
        if cm:
            meta = cm.group("c")
            body_txt = body_txt[: cm.start()].rstrip()
            im = _ID_META.match(meta)
            if im:
                lid, note = im.group("id"), (im.group("note") or "").strip()
            else:
                note = meta.strip()
        if not body_txt:
            continue
        if not lid or lid in taken:
            lid = derive_id(cur.name, body_txt, taken | doc.all_ids())
        taken.add(lid)
        cur.items.append(Line(lid, body_txt, note))
    flush_raw()
    doc.preamble = "\n".join(pre).strip("\n")
    return doc


def render(doc: MemoryDoc) -> str:
    out: list[str] = ["---"]
    front = dict(doc.front)
    role = front.pop("role", "unknown")
    rev = front.pop("revision", 0)
    out.append(f"role: {_scalar(role)}")
    out.append(f"revision: {int(rev)}")
    for k, v in front.items():
        out.append(f"{k}: {_scalar(v)}")
    out.append("---")
    if doc.preamble:
        out.append(doc.preamble)
    present = {s.name for s in doc.sections if s.known}
    sections = list(doc.sections)
    for name in SECTIONS:
        if name not in present:
            sections.append(Section(name, known=True))
    for s in sections:
        out.append("")
        out.append(f"## {s.name}")
        if s.known:
            for it in s.items:
                if isinstance(it, Line):
                    meta = f"id:{it.id}" + (f" | {it.note}" if it.note else "")
                    out.append(f"- {it.text}  <!-- {meta} -->")
                else:
                    out.append(it)
        elif s.raw:
            out.append(s.raw)
    return "\n".join(out).rstrip("\n") + "\n"


def _scalar(v: Any) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    s = str(v)
    if re.fullmatch(r"[A-Za-z0-9_.\-/ :]+", s) and not s.strip().lower() in {"true", "false", "null", "yes", "no"}:
        return s
    return yaml.safe_dump(s, default_flow_style=True).strip().removesuffix("...").strip()


# ----- helpers on specific sections ---------------------------------------------------------
_SKILL = re.compile(
    r"^(?P<skill>[A-Za-z0-9_\-]+):\s*L(?P<level>[1-4])(?:,\s*streak\s*(?P<streak>\d+))?(?:,\s*last seen\s*(?P<seen>[0-9\-]+|never))?",
)


def parse_skill_line(text: str) -> dict[str, Any] | None:
    m = _SKILL.match(text.strip())
    if not m:
        return None
    return {
        "skill": m.group("skill"),
        "level": int(m.group("level")),
        "streak": int(m.group("streak") or 0),
        "last_seen": m.group("seen") if m.group("seen") not in (None, "never") else None,
    }


def skill_levels(doc: MemoryDoc) -> dict[str, dict[str, Any]]:
    sec = doc.section("Skill state", create=False)
    out: dict[str, dict[str, Any]] = {}
    if sec is None:
        return out
    for ln in sec.lines():
        p = parse_skill_line(ln.text)
        if p:
            out[p["skill"]] = p
    return out
