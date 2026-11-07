"""Proposal timing (HND-7): when to raise a card, how many a day, and learning what this person accepts.

* A card is raised only at an **episode boundary**: the last task has ended and a pause has passed without the worker
  starting another. Never while a task is open.
* At most ``daily_budget`` cards per person per day.
* A routine the worker declined with "not now" waits ``cooldown_days``; "never" is never raised again.
* ``P(accept)`` is learned per person: a Beta posterior over accepts and declines (a decline is a label), started from the
  role prior (``priors.yaml: accept``), with a time-of-day adjustment shrunk toward the person's overall rate. The
  card is raised only if ``P(accept)`` is at least ``min_p_accept`` and the routine's expected value is positive.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


def bucket(hour: float) -> str:
    return MORNING if hour < 12 else AFTERNOON if hour < 17 else EVENING


@dataclass
class AcceptModel:
    alpha0: float = 2.0     # role prior: Beta(2, 3), mean 0.4, from priors.yaml accept
    beta0: float = 3.0
    shrink: float = 3.0     # pseudo-observations pulling a time-of-day estimate toward the person's overall rate
    acc: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dec: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    acc_b: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    dec_b: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    @classmethod
    def from_prior(cls, prior: dict[str, float] | None) -> AcceptModel:
        return cls(alpha0=float((prior or {}).get("alpha", 2.0)), beta0=float((prior or {}).get("beta", 3.0)))

    def observe(self, person: str, accepted: bool, hour: float | None = None) -> None:
        (self.acc if accepted else self.dec)[person] += 1
        if hour is not None:
            (self.acc_b if accepted else self.dec_b)[(person, bucket(hour))] += 1

    def p_accept(self, person: str, hour: float | None = None) -> float:
        a, d = self.acc[person], self.dec[person]
        p = (self.alpha0 + a) / (self.alpha0 + self.beta0 + a + d)
        if hour is None:
            return p
        k = (person, bucket(hour))
        ab, db = self.acc_b[k], self.dec_b[k]
        return (ab + self.shrink * p) / (ab + db + self.shrink)

    def n_labels(self, person: str) -> int:
        return self.acc[person] + self.dec[person]


@dataclass
class Candidate:
    routine_id: str
    value_hours: float           # expected hours saved over the horizon
    status: str = "proposed"
    proposable: bool = True
    declined_not_now_at: float | None = None   # unix seconds of the last "not now"


@dataclass
class ProposalScheduler:
    accept: AcceptModel = field(default_factory=AcceptModel)
    daily_budget: int = 2
    cooldown_days: float = 2.0
    min_p_accept: float = 0.15
    pause_s: float = 20.0       # quiet time after a task ends before it counts as a break
    shown: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    @staticmethod
    def _day(ts: float) -> str:
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()

    @staticmethod
    def _hour(ts: float) -> float:
        d = datetime.fromtimestamp(ts, timezone.utc)
        return d.hour + d.minute / 60

    def offer(self, person: str, now: float, candidates: Sequence[Candidate], *, at_boundary: bool) -> Candidate | None:
        """The card to raise now, or None. ``at_boundary`` must be true: no card mid-task, whatever the budget says."""
        if not at_boundary:
            return None
        if self.shown[(person, self._day(now))] >= self.daily_budget:
            return None
        p = self.accept.p_accept(person, self._hour(now))
        if p < self.min_p_accept:
            return None
        ok = []
        for c in candidates:
            if c.status != "proposed" or not c.proposable or c.value_hours <= 0:
                continue
            if c.declined_not_now_at is not None and now - c.declined_not_now_at < self.cooldown_days * 86400:
                continue
            ok.append(c)
        if not ok:
            return None
        best = max(ok, key=lambda c: (p * c.value_hours, c.routine_id))
        self.shown[(person, self._day(now))] += 1
        return best

    def decline_or_accept(self, person: str, now: float, accepted: bool) -> None:
        self.accept.observe(person, accepted, self._hour(now))


def boundaries(events: Iterable[Any], pause_s: float = 20.0) -> list[float]:
    """Episode boundaries in an event stream: ``task_end`` followed by ``pause_s`` of no new task start or input.

    Returns the unix time at which the break is confirmed (task_end + pause_s). Used by the replay test: a card is only
    ever raised at one of these times, never between a ``task_start`` and its ``task_end``.
    """
    rows = []
    for e in events:
        get = (lambda k, d=None: e.get(k, d)) if isinstance(e, dict) else (lambda k, d=None: getattr(e, k, d))
        t = get("t")
        ts = t.timestamp() if hasattr(t, "timestamp") else datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()
        rows.append((ts, str(get("type")), str(get("actor", "human"))))
    rows.sort()
    out = []
    for i, (ts, typ, actor) in enumerate(rows):
        if typ != "task_end":
            continue
        nxt = next((r[0] for r in rows[i + 1:] if r[2] == "human" and r[1] not in ("progress", "stuck")), None)
        if nxt is None or nxt - ts >= pause_s:
            out.append(ts + pause_s)
    return out
