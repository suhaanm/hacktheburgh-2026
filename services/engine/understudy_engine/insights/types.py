"""Shared types of the insights layer (REQ-9): the candidate, the guard, the selection result, and the person and firm records.

Nothing here carries free text. ``rows`` are assist-ledger-shaped dicts (``packages/schema/assist_ledger.schema.json``); they stay inside the
engine: an admin response is built from ``PersonSummary`` numbers and enums only (``admin.py``), never from a row.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def insight_id(audience: str, scope: str, kind: str, subject: str) -> str:
    """Stable across weeks: the same insight about the same subject has the same id, so ``why`` and ``drill`` can find it."""
    return "i_" + hashlib.sha1("|".join((audience, scope, kind, subject)).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Guard:
    """A quality measure that must not get worse for an improvement to be shown as one."""
    name: str                       # error_share | abandoned_share | time_to_progress | false_claims | rework_share
    before: float
    after: float
    n_before: int
    n_after: int
    worse: bool


@dataclass(frozen=True)
class PersonRecord:
    id: str                          # p_... slug
    role: str
    level: str                       # expert | junior
    unit: str
    tenure_weeks: int
    tz: str = "UTC"
    role_since_t: float | None = None
    pack_rev: str = "1"
    joined_t: float | None = None
    label: str = ""                  # the pseudonym an admin sees (BP-07), never a name
    origin: str = "synthetic"
    rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class FirmSnapshot:
    now: float
    people: tuple[PersonRecord, ...]
    routines: tuple[dict[str, Any], ...] = ()       # {person, id, status, support, hours_lo, hours_hi, shadow_runs, shadow_matches, t}
    approvals: tuple[dict[str, Any], ...] = ()      # {age_h} open approvals (no content)
    risk_events: tuple[dict[str, Any], ...] = ()    # {kind: injection_pause | false_claim | kill, age_days}
    feed_t: dict[str, float] = field(default_factory=dict)
    origin: str = "synthetic"
    badge: str = "made-up firm"
    source: str = "firm"
    truth: dict[str, Any] | None = None             # planted situations: for the evaluation only; no product code reads it


@dataclass(frozen=True)
class InsightCandidate:
    id: str
    kind: str
    audience: str
    subject: str                     # a skill id, a role, a unit, a role:skill pair, a signal id or "firm"
    group: str                       # the diversity group: the person (worker) or the role or "firm" (admin)
    polarity: str
    value: float | None = None       # the effect, in `unit`
    unit: str = ""
    lo: float | None = None
    hi: float | None = None
    p: float | None = None           # two-sided p-value for H0: effect = 0 (effect kinds)
    n: int = 0
    n_unit: str = "occurrences"
    split: dict[str, Any] = field(default_factory=dict)
    origin: str = "synthetic"
    badge: str = "made-up firm"
    evidence_ref: str = ""
    recency_t: float | None = None
    action_id: str | None = None
    guards: tuple[Guard, ...] = ()
    impact_raw: float = 0.0
    family: str = ""                 # "" for a state kind; otherwise the id of the test family
    floor: float | None = None
    sign: int = 1                    # the direction the effect must have (+1 or -1)
    persist_ok: bool = True
    threshold_ok: bool = True        # state kinds: the threshold held
    reason_pre: str | None = None    # a generator may pre-suppress with a closed reason (still listed for `why`)
    slots: dict[str, Any] = field(default_factory=dict)      # template slots: numbers and enums only
    extras: dict[str, Any] = field(default_factory=dict)     # admin drill-down material: numbers and enums only
    person: str | None = None

    @property
    def interval(self) -> tuple[float, float] | None:
        return None if self.lo is None or self.hi is None else (self.lo, self.hi)


@dataclass(frozen=True)
class Scored:
    cand: InsightCandidate
    score: float
    parts: dict[str, float]
    position: int
    reason: str


@dataclass(frozen=True)
class Suppressed:
    id: str
    kind: str
    subject: str
    reason: str


@dataclass
class Selection:
    audience: str
    scope: str
    selected: list[Scored] = field(default_factory=list)
    suppressed: list[Suppressed] = field(default_factory=list)
    family: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    all_candidates: dict[str, InsightCandidate] = field(default_factory=dict)

    def reason_of(self, iid: str) -> tuple[str, str] | None:
        """``(state, reason_code)`` for any candidate id this selection saw, or None."""
        for s in self.selected:
            if s.cand.id == iid:
                return "selected", s.reason
        for s in self.suppressed:
            if s.id == iid:
                return "suppressed", s.reason
        return None


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    t: float
    value: float | None = None
    level: int | None = None


@dataclass
class History:
    """What was shown before (for novelty) and what the person said about it (only ever quieter)."""
    shown: list[HistoryEntry] = field(default_factory=list)
    quiet_ids: dict[str, float] = field(default_factory=dict)       # insight id -> time of a not_useful, dismissed or done
    hidden_kinds: frozenset[str] = frozenset()
