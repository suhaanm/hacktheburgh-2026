"""Keyed retrieval from the worker's memory file. Never the whole file.

The model needs the few lines of the worker's memory that bear on THIS step, not the file. A caller names the keys it is working
on (the role, skill ids, step ids, routine ids) and gets at most `cap` lines back, chosen by rule:

  Never          always included (up to `cap_never`, shortest first): they are the worker's hard constraints and short.
  Skill state,   included only when a key appears in the line as a whole token (case-insensitive; ids such as `reads-error-first`
  Procedure,     or `CHECK_CLIFF`). Most specific section first, then newest.
  Corrections,
  Routines
  Preferences    the first `cap_prefs` lines (tone and length live at the top of the file); never keyed, never more.

Freshness: a `last seen YYYY-MM-DD` on a skill-state line (or an ISO date in the line's note) is the reading time `t`. Older than
`freshness.MAX_AGE_S["skill_state"]` and the line is NOT given to the model; it is counted and reported as stale, so the prompt says
"skill_state (too old)" rather than quietly using a fact about a skill the worker may have lost. A line with no date has no age limit.
If the file's role is not the role asked for, nothing is returned and `memory_line` is reported missing.

Lines longer than `max_chars` are skipped whole (a line is never cut mid-sentence); the count is reported. The adapter reads
`understudy_engine.memory.doc.MemoryDoc` by duck typing (`.role`, `.sections`, each with `.name`, `.lines()`, and lines with `.id`,
`.text`, `.note`), so this module imports nothing from the engine. The file is the worker's: nothing here writes to it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from .freshness import MAX_AGE_S
from .packet import Item, Keep, Section, Trust

_TOKEN = re.compile(r"[A-Za-z0-9_.\-]+")
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_LAST_SEEN = re.compile(r"last seen\s+(\d{4}-\d{2}-\d{2})", re.I)
KEYED_SECTION_RANK = {"Skill state": 0, "Procedure": 1, "Corrections": 2, "Routines": 3}


@dataclass(frozen=True)
class MemoryLine:
    id: str
    section: str
    text: str
    t: float | None = None           # reading time, unix seconds (from a date in the line or its note)


@dataclass(frozen=True)
class Retrieval:
    lines: tuple[MemoryLine, ...]
    stale: tuple[str, ...]           # ids of lines withheld as too old
    over_cap: int                    # matching lines left out by the cap
    too_long: int                    # lines skipped whole for length
    missing: tuple[str, ...]         # ("memory_line",) when the file's role did not match

    def as_section(self, *, name: str = "worker_memory", stable: bool = False, order: int = 150, priority: int = 60) -> Section | None:
        """A WORKER section for a planner or computer-use prompt; None when there is nothing to say."""
        if not self.lines:
            return None
        return Section(name=name, trust=Trust.WORKER, source="memory.file", items=[Item(f"- {ln.text}", id=ln.id) for ln in self.lines],
                       kind="memory_line", t=0.0, priority=priority, stable=stable, order=order, keep=Keep.TOP,
                       header="From the worker's memory (only the lines that bear on this step):")


def _t_of(text: str, note: str = "") -> float | None:
    m = _LAST_SEEN.search(text)
    raw = m.group(1) if m else None
    if raw is None:
        d = _DATE.search(note or "")
        raw = d.group(0) if d else None
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def lines_from_doc(doc: Any) -> tuple[str, list[MemoryLine]]:
    """(the file's role, its lines) from a MemoryDoc, by duck typing."""
    role = str(getattr(doc, "role", "") or "")
    out: list[MemoryLine] = []
    for sec in getattr(doc, "sections", ()):
        name = str(getattr(sec, "name", ""))
        for ln in sec.lines():
            text, note = str(getattr(ln, "text", "")), str(getattr(ln, "note", ""))
            out.append(MemoryLine(id=str(ln.id), section=name, text=text, t=_t_of(text, note)))
    return role, out


def retrieve(lines: Iterable[MemoryLine], *, role: str, file_role: str | None = None, keys: Sequence[str] = (), now: float,
             cap: int = 6, cap_never: int = 4, cap_prefs: int = 2, max_chars: int = 240) -> Retrieval:
    """Pick the lines for this step. `keys` are the skill, step and routine ids the step concerns; `now` is the caller's clock."""
    if file_role is not None and file_role != role:
        return Retrieval((), (), 0, 0, ("memory_line",))
    key_set = {k.lower() for k in keys if k}
    all_lines = list(lines)
    too_long = sum(1 for ln in all_lines if len(ln.text) > max_chars)
    pool = [ln for ln in all_lines if len(ln.text) <= max_chars]
    limit = MAX_AGE_S["skill_state"]

    never = sorted((ln for ln in pool if ln.section == "Never"), key=lambda ln: (len(ln.text), ln.id))[:cap_never]
    prefs = [ln for ln in pool if ln.section == "Preferences"][:cap_prefs]

    keyed: list[MemoryLine] = []
    stale: list[str] = []
    for ln in pool:
        if ln.section not in KEYED_SECTION_RANK or not key_set:
            continue
        if not (key_set & {t.lower() for t in _TOKEN.findall(ln.text)}):
            continue
        if ln.section == "Skill state" and ln.t is not None and limit is not None and max(0.0, now - ln.t) > limit:
            stale.append(ln.id)
            continue
        keyed.append(ln)
    keyed.sort(key=lambda ln: (KEYED_SECTION_RANK[ln.section], -(ln.t or 0.0), ln.id))

    chosen: list[MemoryLine] = []
    for group in (never, keyed, prefs):
        for ln in group:
            if len(chosen) < cap:
                chosen.append(ln)
    matched = len(never) + len(keyed) + len(prefs)
    return Retrieval(tuple(chosen), tuple(stale), max(0, matched - len(chosen)), too_long, ())
