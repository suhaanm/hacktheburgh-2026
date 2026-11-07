"""WorkingMemory: the code-maintained state of a long run, in a bounded number of tokens.

A 150-step run must not cost 150 steps of history. This keeps three things, all built by code from TYPED step records (ids, enums,
numbers; never free model text and never page text):

  TASK STATE   the source of truth after a resume or a restart: the goal id, the fact handles on offer, the postconditions code
               verified, the handles entered on the current page, the page state, open problems, what is pending, step and tier.
  RECENT       the last K steps verbatim, one short line each (default K = 6).
  SUMMARY      older steps folded into a template over counters ("click ok 12, type_fact refused 1; pages form 9, result 2").

The prompt cost is a function of the caps (K, the number of verified ids kept, the pending list), not of the number of steps:
`tests/context/test_working.py` pins that over 1000 steps. A snapshot is JSON of the same typed fields; `restore` validates every
id, so a checkpoint can be written by code and read back after a restart (the model's own words are never the checkpoint).

An id is a SHAPE check (letter first, short, no spaces), not a secrecy guarantee: `StepRecord.from_history` reads only the `handle`,
`param`, `ref` and `kind` fields, never typed text, so a value cannot arrive through it; a caller that put a value in `target`
would pass the shape check. Callers must pass handle names, never values.

Why typed: a rolling summary written by a model would carry whatever an injected page persuaded it to say into every later step.
A template over enums cannot. The trust boundary stays where it is: page text goes to the quarantined reader only.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .packet import Item, Keep, Section, Trust

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:\-]{0,59}$")   # starts with a letter: a bare number or an amount such as 955.00 is not an id
SNAPSHOT_VERSION = 1
_ENTRY_KINDS = ("type_fact", "type", "fill", "select")   # steps that enter a fact (tier 3 history uses "type" with a handle)


class TypedIdError(ValueError):
    """A value that should be a short id is not one. The message never contains the value."""


class PageState(str, Enum):
    UNKNOWN = "unknown"
    FORM = "form"
    RESULT = "result"
    ERROR = "error"
    SAVED_NOTE = "saved_note"
    DIALOG = "dialog"
    LOADING = "loading"
    OTHER = "other"


class Outcome(str, Enum):
    OK = "ok"
    FAILED = "failed"
    REFUSED = "refused"      # a fact-handle or action-validation refusal
    BLOCKED = "blocked"      # a gate verdict
    UNCERTAIN = "uncertain"


def _id(value: str, what: str, *, allow_empty: bool = True) -> str:
    if value == "" and allow_empty:
        return ""
    if not isinstance(value, str) or not ID_RE.match(value):
        raise TypedIdError(f"{what} is not a short id")
    return value


def code_of(raw: Any, default: str = "other") -> str:
    """Free-ish reason text (an exception message, a model's `why`) to a short code, or `default`. Anything that does not already
    look like an id is replaced, so no text can pass through a StepRecord."""
    return raw if isinstance(raw, str) and ID_RE.match(raw) else default


@dataclass(frozen=True)
class StepRecord:
    n: int
    kind: str                         # action kind or tool id: click, type_fact, fill, select, scroll, key, wait, finish ...
    target: str = ""                  # a fact handle, an element ref or a menu id
    outcome: Outcome = Outcome.OK
    tier: int = 0
    page: PageState = PageState.UNKNOWN
    verified: str = ""                # id of the postcondition code verified after this step
    code: str = ""                    # short reason code when the step did not go through
    t: float | None = None

    def __post_init__(self) -> None:
        _id(self.kind, "kind", allow_empty=False)
        _id(self.target, "target")
        _id(self.verified, "verified")
        _id(self.code, "code")
        if not isinstance(self.n, int) or self.n < 0:
            raise TypedIdError("n must be a non-negative integer")

    @classmethod
    def from_history(cls, h: Mapping[str, Any], n: int, *, tier: int = 0, page: PageState = PageState.UNKNOWN) -> "StepRecord":
        """From the dicts the tiers already keep (`{"kind", "args", "ok", "handle", "why"}` for tier 3 and
        `{"tool", "param", "ref", "ok", "why"}` for tier 2). Anything that is not a short id becomes `other`."""
        kind = code_of(h.get("kind") or h.get("tool") or h.get("action"), "step")
        target = code_of(h.get("handle") or h.get("param") or h.get("ref") or "", "")
        ok = h.get("ok")
        why = code_of(h.get("why") or "", "")
        if ok is False and why in ("literal_text", "unknown_handle", "key_types_text"):
            outcome = Outcome.REFUSED
        elif ok is False:
            outcome = Outcome.FAILED
        else:
            outcome = Outcome.OK
        return cls(n=n, kind=kind, target=target, outcome=outcome, tier=tier, page=page, code=why if ok is False else "")

    def line(self) -> str:
        bits = [f"{self.n}.", self.kind]
        if self.target:
            bits.append(self.target)
        bits.append(self.outcome.value)
        if self.code:
            bits.append(f"({self.code})")
        if self.verified:
            bits.append(f"verified:{self.verified}")
        return " ".join(bits)

    def to_json(self) -> dict[str, Any]:
        return {"n": self.n, "kind": self.kind, "target": self.target, "outcome": self.outcome.value, "tier": self.tier,
                "page": self.page.value, "verified": self.verified, "code": self.code, "t": self.t}

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "StepRecord":
        return cls(n=d["n"], kind=d["kind"], target=d.get("target", ""), outcome=Outcome(d["outcome"]), tier=int(d.get("tier", 0)),
                   page=PageState(d.get("page", "unknown")), verified=d.get("verified", ""), code=d.get("code", ""), t=d.get("t"))


@dataclass(frozen=True)
class TaskState:
    goal_id: str
    handles: tuple[str, ...]
    done: tuple[str, ...]             # verified postconditions, oldest first (bounded)
    done_more: int                    # older verified ids folded into a count
    entered: tuple[str, ...]          # handles entered on the current page
    page: PageState
    open_problems: tuple[str, ...]
    pending: tuple[str, ...]
    step: int
    tier: int
    resumed: int


class WorkingMemory:
    """See the module docstring. Not thread-safe by itself (one run, one owner)."""

    def __init__(self, goal_id: str, *, handles: Iterable[str] = (), pending: Iterable[str] = (), last_k: int = 6,
                 max_done: int = 40, max_pending: int = 20, max_open: int = 8, max_summary_kinds: int = 8) -> None:
        self.goal_id = _id(goal_id, "goal_id", allow_empty=False)
        self.handles = tuple(_id(h, "handle", allow_empty=False) for h in handles)
        self.last_k, self.max_done, self.max_pending, self.max_open = last_k, max_done, max_pending, max_open
        self.max_summary_kinds = max_summary_kinds
        self._recent: deque[StepRecord] = deque()
        self._older: Counter[tuple[str, str]] = Counter()
        self._older_pages: Counter[str] = Counter()
        self._older_range: list[int] = []         # [first step, last step] folded into the summary
        self._done: list[str] = []
        self._done_more = 0
        self._entered: list[str] = []
        self._page = PageState.UNKNOWN
        self._page_key = ""
        self._open: list[str] = []
        self._pending = [_id(p, "pending", allow_empty=False) for p in pending][:max_pending]
        self._step = 0
        self._tier = 0
        self._resumed = 0

    # ------------------------------------------------------------------ writing (all typed)
    def record(self, rec: StepRecord) -> None:
        self._step = max(self._step, rec.n)
        if rec.tier:
            self._tier = rec.tier
        if rec.page is not PageState.UNKNOWN:
            self._page = rec.page
        self._recent.append(rec)
        while len(self._recent) > self.last_k:
            old = self._recent.popleft()
            self._older[(old.kind, old.outcome.value)] += 1
            self._older_pages[old.page.value] += 1
            self._older_range = [self._older_range[0] if self._older_range else old.n, old.n]
        if rec.outcome is Outcome.OK and rec.kind in _ENTRY_KINDS and rec.target and rec.target not in self._entered:
            self._entered.append(rec.target)
        if rec.verified:
            self.mark_done(rec.verified)
        if rec.target in self._pending and rec.outcome is Outcome.OK and rec.kind in _ENTRY_KINDS:
            self._pending.remove(rec.target)

    def mark_done(self, postcondition_id: str) -> None:
        pid = _id(postcondition_id, "postcondition", allow_empty=False)
        if pid in self._done:
            return
        self._done.append(pid)
        while len(self._done) > self.max_done:
            self._done.pop(0)
            self._done_more += 1

    def set_page(self, state: PageState, key: str = "") -> None:
        """A new page (a different `key`, such as the URL path id) starts blank: handles entered are cleared. Same key, same page."""
        key = _id(key, "page key")
        if key != self._page_key:
            self._entered.clear()
            self._page_key = key
        self._page = state

    def add_problem(self, code: str) -> None:
        c = _id(code, "problem", allow_empty=False)
        if c not in self._open:
            self._open.append(c)
            while len(self._open) > self.max_open:
                self._open.pop(0)

    def resolve_problem(self, code: str) -> None:
        if code in self._open:
            self._open.remove(code)

    def set_pending(self, ids: Iterable[str]) -> None:
        self._pending = [_id(p, "pending", allow_empty=False) for p in ids][: self.max_pending]

    def mark_resumed(self) -> None:
        """After a restart or a yield: nothing is assumed about the page. The verified list and pending list stay."""
        self._resumed += 1
        self._page = PageState.UNKNOWN
        self._page_key = ""
        self._entered.clear()

    # ------------------------------------------------------------------ reading
    @property
    def step(self) -> int:
        return self._step

    def state(self) -> TaskState:
        return TaskState(self.goal_id, self.handles, tuple(self._done), self._done_more, tuple(self._entered), self._page,
                         tuple(self._open), tuple(self._pending), self._step, self._tier, self._resumed)

    def recent(self) -> tuple[StepRecord, ...]:
        return tuple(self._recent)

    def summary_text(self) -> str:
        """Older steps as a template over counters. Empty when nothing has been folded yet."""
        if not self._older:
            return ""
        ranked = sorted(self._older.items(), key=lambda kv: (-kv[1], kv[0]))      # a total order: ties never depend on insertion order
        top = ranked[: self.max_summary_kinds]
        rest = sum(self._older.values()) - sum(n for _, n in top)
        parts = [f"{k} {o} {n}" for (k, o), n in top]
        if rest:
            parts.append(f"other {rest}")
        pages = ", ".join(f"{p} {n}" for p, n in sorted(self._older_pages.items(), key=lambda kv: (-kv[1], kv[0])) if p != "unknown")
        lo, hi = (self._older_range + [0, 0])[:2]
        text = f"Earlier steps {lo} to {hi} (counts by action and outcome): " + "; ".join(parts) + "."
        return text + (f" Pages seen: {pages}." if pages else "")

    def task_state_text(self) -> str:
        s = self.state()
        done = ", ".join(s.done) if s.done else "none yet"
        if s.done_more:
            done += f" (+{s.done_more} earlier)"
        lines = [
            "TASK STATE (kept by code; it is the source of truth if anything above disagrees)",
            f"goal: {s.goal_id} | step {s.step} | tier {s.tier or 'n/a'} | page: {s.page.value}"
            + (f" | resumed {s.resumed}x: the page is not known until the next look" if s.resumed else ""),
            f"verified by code: {done}",
            f"entered on this page: {', '.join(s.entered) if s.entered else 'nothing'}",
            f"still to do: {', '.join(s.pending) if s.pending else 'nothing listed'}",
        ]
        if s.open_problems:
            lines.append(f"open problems: {', '.join(s.open_problems)}")
        return "\n".join(lines)

    def sections(self, *, order_base: int = 200) -> list[Section]:
        """The three sections for a ContextPacket. The task state is required (never dropped); the recent steps outrank the summary."""
        out = [Section.of_text("task_state", Trust.CODE, "context.working_memory", self.task_state_text(), kind="task_state",
                               t=0.0, required=True, priority=100, order=order_base)]
        summ = self.summary_text()
        if summ:
            out.append(Section.of_text("rolling_summary", Trust.CODE, "context.working_memory", summ, priority=30, order=order_base + 10))
        if self._recent:
            out.append(Section(name="recent_steps", trust=Trust.CODE, source="context.working_memory",
                               items=[Item(r.line(), id=f"n{r.n}") for r in self._recent], priority=80, order=order_base + 20,
                               keep=Keep.NEWEST, header=f"Last {len(self._recent)} steps (oldest first):"))
        return out

    # ------------------------------------------------------------------ checkpoint
    def snapshot(self) -> dict[str, Any]:
        return {"v": SNAPSHOT_VERSION, "goal_id": self.goal_id, "handles": list(self.handles), "pending": list(self._pending),
                "done": list(self._done), "done_more": self._done_more, "entered": list(self._entered), "page": self._page.value,
                "page_key": self._page_key, "open": list(self._open), "step": self._step, "tier": self._tier,
                "resumed": self._resumed, "recent": [r.to_json() for r in self._recent],
                "older": [[k, o, n] for (k, o), n in sorted(self._older.items())], "older_pages": dict(self._older_pages),
                "older_range": list(self._older_range),
                "caps": {"last_k": self.last_k, "max_done": self.max_done, "max_pending": self.max_pending,
                         "max_open": self.max_open, "max_summary_kinds": self.max_summary_kinds}}

    @classmethod
    def restore(cls, d: Mapping[str, Any]) -> "WorkingMemory":
        """Validate and rebuild. Raises TypedIdError or ValueError on anything that is not what `snapshot` writes."""
        if not isinstance(d, Mapping) or d.get("v") != SNAPSHOT_VERSION:
            raise ValueError("not a working-memory snapshot of this version")
        caps = d.get("caps") or {}
        wm = cls(d["goal_id"], handles=d.get("handles", ()), pending=d.get("pending", ()), last_k=int(caps.get("last_k", 6)),
                 max_done=int(caps.get("max_done", 40)), max_pending=int(caps.get("max_pending", 20)),
                 max_open=int(caps.get("max_open", 8)), max_summary_kinds=int(caps.get("max_summary_kinds", 8)))
        for x in d.get("done", ()):
            wm._done.append(_id(x, "done", allow_empty=False))
        wm._done_more = max(0, int(d.get("done_more", 0)))
        wm._entered = [_id(x, "entered", allow_empty=False) for x in d.get("entered", ())]
        wm._page, wm._page_key = PageState(d.get("page", "unknown")), _id(d.get("page_key", ""), "page key")
        wm._open = [_id(x, "problem", allow_empty=False) for x in d.get("open", ())]
        wm._step, wm._tier, wm._resumed = int(d.get("step", 0)), int(d.get("tier", 0)), int(d.get("resumed", 0))
        wm._recent = deque(StepRecord.from_json(r) for r in d.get("recent", ()))
        for k, o, n in d.get("older", ()):
            wm._older[(_id(k, "kind", allow_empty=False), Outcome(o).value)] = max(0, int(n))
        for p, n in dict(d.get("older_pages", {})).items():
            wm._older_pages[PageState(p).value] = max(0, int(n))
        wm._older_range = [int(x) for x in d.get("older_range", ())][:2]
        return wm
