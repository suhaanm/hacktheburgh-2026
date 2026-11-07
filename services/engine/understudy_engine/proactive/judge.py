"""The judge: code ranks, code caps. No model decides what is surfaced (PR1).

Every candidate gets a transparent score in 0..1:

    score = 0.35 * value + 0.25 * urgency + 0.15 * freshness + 0.25 * acceptance - 0.15 * effort

``value``, ``urgency``, ``freshness`` and ``effort`` come from the collector (each in 0..1, with the raw numbers on the
candidate); ``acceptance`` is the person's learned probability of pressing a card of this kind (``acceptance.py``,
started at the role prior). The weights are fixed constants chosen by hand before any evaluation and are not fitted to
the planted truth.

Then three rules, applied in order, each recorded as the candidate's ``decision``:

1. ``suppressed``: the worker dismissed this subject ("not now" waits out a cooldown), said "never" to it (the subject and
   the whole card kind with its source are not proposed again), or it was fired recently.
2. ``below_threshold``: score under ``MIN_SCORE``. "Fewer, even zero, when nothing is worth surfacing": an empty
   briefing is a valid result.
3. ``kind_limit`` and ``over_cap``: at most ``MAX_PER_KIND`` of any kind and at most ``CAP`` cards in all, best first.
   Scarcity is the point: three cards is a morning, ten is a to-do list.

Cards the worker has already edited are *pinned*: they keep their slot while they still verify, so an edit is never
thrown away by a re-rank, and they count toward the cap.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .candidates import Candidate

CAP = 3
MIN_SCORE = 0.30
WEIGHTS = {"value": 0.35, "urgency": 0.25, "freshness": 0.15, "acceptance": 0.25}
EFFORT_PENALTY = 0.15
MAX_PER_KIND = {"practice": 1, "automate": 2, "focus_block": 1, "git_habit": 1, "agent_result": 2}
COOLDOWN_DAYS = 2.0          # a "not now" waits this long; a fired subject too


@dataclass
class Ranked:
    candidate: Candidate
    score: float
    parts: dict[str, dict[str, float]]
    decision: str = "pending"
    rank: int = 0
    pinned: bool = False

    def explain(self) -> dict[str, Any]:
        """Everything needed to say why this one is (or is not) on the card list."""
        return {"score": round(self.score, 4), "rank": self.rank, "decision": self.decision, "pinned": self.pinned,
                "parts": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in self.parts.items()},
                "min_score": MIN_SCORE, "cap": CAP}


@dataclass
class JudgeResult:
    selected: list[Ranked] = field(default_factory=list)
    considered: list[Ranked] = field(default_factory=list)      # everything, best first, each with its decision

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.considered:
            out[r.decision] = out.get(r.decision, 0) + 1
        return out


def score_candidate(c: Candidate, p_accept: float) -> tuple[float, dict[str, dict[str, float]]]:
    xs = {"value": c.value, "urgency": c.urgency, "freshness": c.freshness, "acceptance": p_accept}
    parts = {k: {"x": xs[k], "w": WEIGHTS[k], "contribution": WEIGHTS[k] * xs[k]} for k in WEIGHTS}
    parts["effort"] = {"x": c.effort, "w": -EFFORT_PENALTY, "contribution": -EFFORT_PENALTY * c.effort}
    return sum(p["contribution"] for p in parts.values()), parts


def is_suppressed(subject: str, suppress: dict[str, dict[str, Any]], now_ts: float) -> bool:
    s = suppress.get(subject)
    if not s:
        return False
    until = s.get("until")
    return until is None or now_ts < float(until)


def rank(candidates: Iterable[Candidate], *, p_accept: Callable[[str], float], now_ts: float,
         suppress: dict[str, dict[str, Any]] | None = None, pinned: Iterable[str] = (), cap: int = CAP,
         min_score: float = MIN_SCORE, max_per_kind: dict[str, int] | None = None) -> JudgeResult:
    """Score, order and cut. Deterministic: ties break on kind then id. ``pinned`` is a set of card ids that keep a slot."""
    suppress = suppress or {}
    pin = set(pinned)
    limits = max_per_kind or MAX_PER_KIND
    seen: set[str] = set()
    ranked: list[Ranked] = []
    for c in candidates:
        if c.id in seen:        # the same opportunity from two readers counts once
            continue
        seen.add(c.id)
        s, parts = score_candidate(c, p_accept(c.kind))
        ranked.append(Ranked(c, s, parts, pinned=c.id in pin))
    ranked.sort(key=lambda r: (-int(r.pinned), -r.score, r.candidate.kind, r.candidate.id))
    kinds: dict[str, int] = {}
    chosen: list[Ranked] = []
    for i, r in enumerate(ranked, 1):
        r.rank = i
        c = r.candidate
        if is_suppressed(c.subject, suppress, now_ts) or is_suppressed(f"kind:{c.kind}", suppress, now_ts):
            r.decision = "suppressed"
        elif r.score < min_score and not r.pinned:
            r.decision = "below_threshold"
        elif kinds.get(c.kind, 0) >= limits.get(c.kind, 1) and not r.pinned:
            r.decision = "kind_limit"
        elif len(chosen) >= cap:
            r.decision = "over_cap"
        else:
            r.decision = "selected"
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
            chosen.append(r)
    return JudgeResult(selected=chosen, considered=ranked)
