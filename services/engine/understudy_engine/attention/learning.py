"""Learning from reactions (REQ-8; the idea of Pupil's implicit labels, re-implemented). It can only make the router quieter.

A worker's next move labels what was shown, with no questionnaire:

  followed         opened or acted within 10 s            positive (weight 1; later than 10 s, weight 0.5)
  dismissed_fast   closed within 4 s: unwelcome            negative (weight 1)
  dismissed        closed after 4 s                        mildly negative (0.5): a dismissal can mean "I already knew"
  ignored          timed out untouched                     mildly negative (0.5): it may not have been seen
  never            "never for this"                        strongly negative (3)

Per person and per type: a Beta(2, 2) prior and the weighted counts of the last ``label_window`` labels, smoothed across hours (the hour
itself counts 1, one hour away 0.5, two away 0.25, any other hour 0.1), so a type that is welcome in the morning and not in the
afternoon is quietened only in the afternoon, and a sparse hour borrows from its neighbours rather than guessing. The estimate is the
posterior mean ``p`` with ``n_eff`` the summed kernel weights.

The learned drop is 0 unless ``n_eff >= n_min``; 1 rung when ``p <= quiet_thr1``; 2 rungs when ``p <= quiet_thr2``; and 2 whenever the
worker said never on ``never_subjects_for_max`` distinct subjects of the type. The router applies it to helpful-now and can-wait
types only, never below a type's floor and never to safety or an approval that blocks a job. There is no way for a label to raise a
rung: the function returns a non-negative drop and nothing else.

A label is a noisy proxy for "was this welcome". The evaluation says so in numbers and does not treat it as truth about people.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import vocab as V
from .state import DEFAULT, Params

FOLLOW_S = 10.0
DISMISS_S = 4.0
KERNEL = {0: 1.0, 1: 0.5, 2: 0.25}
OTHER_HOUR = 0.1
PRIOR_A = PRIOR_B = 2.0
# label -> (positive weight, negative weight)
WEIGHTS = {"followed": (1.0, 0.0), "dismissed_fast": (0.0, 1.0), "dismissed": (0.0, 0.5), "ignored": (0.0, 0.5), "never": (0.0, 3.0)}


def label_of(event: str, seconds: float | None) -> str | None:
    """The implicit label for a reaction, or None when the event is not a reaction (shown)."""
    s = 1e9 if seconds is None else max(0.0, float(seconds))
    if event in ("followed", "opened"):
        return "followed"
    if event == "dismissed":
        return "dismissed_fast" if s <= DISMISS_S else "dismissed"
    if event == "ignored":
        return "ignored"
    if event == "never":
        return "never"
    return None


def label_weights(label: str, seconds: float | None) -> tuple[float, float]:
    pos, neg = WEIGHTS[label]
    if label == "followed" and (seconds is None or seconds > FOLLOW_S):
        pos = 0.5
    return pos, neg


def hour_kernel(a: int, b: int) -> float:
    d = abs(int(a) - int(b)) % 24
    d = min(d, 24 - d)
    return KERNEL.get(d, OTHER_HOUR)


@dataclass
class Label:
    type: str
    hour: int
    label: str
    seconds: float | None = None
    subject: str | None = None
    t: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "hour": self.hour, "label": self.label, "seconds": self.seconds, "subject": self.subject, "t": self.t}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Label:
        return cls(type=d["type"], hour=int(d["hour"]), label=d["label"], seconds=d.get("seconds"), subject=d.get("subject"), t=float(d.get("t", 0.0)))


class Acceptance:
    """Per-type, per-hour acceptance estimates for one person. Deterministic; no randomness."""

    def __init__(self, labels: Iterable[Label] = (), params: Params = DEFAULT) -> None:
        self.p = params
        self._labels: dict[str, deque[Label]] = defaultdict(lambda: deque(maxlen=params.label_window))
        self._never: dict[str, set[str]] = defaultdict(set)
        self._cache: dict[tuple[str, int], tuple[float, float]] = {}
        for lb in labels:
            self._add(lb)

    def _add(self, lb: Label) -> None:
        self._labels[lb.type].append(lb)
        if lb.label == "never" and lb.subject:
            self._never[lb.type].add(lb.subject)

    def add(self, lb: Label) -> None:
        self._add(lb)
        self._cache = {k: v for k, v in self._cache.items() if k[0] != lb.type}

    def reset(self, types: Iterable[str] | None = None) -> None:
        for t in list(self._labels) if types is None else list(types):
            self._labels.pop(t, None)
            self._never.pop(t, None)
        self._cache.clear()

    def labels(self) -> list[Label]:
        return [lb for dq in self._labels.values() for lb in dq]

    def estimate(self, type_id: str, hour: int) -> tuple[float, float]:
        """(posterior mean, n_eff) for a type at an hour."""
        key = (type_id, int(hour) % 24)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        pos = neg = n = 0.0
        for lb in self._labels.get(type_id, ()):
            k = hour_kernel(lb.hour, hour)
            wp, wn = label_weights(lb.label, lb.seconds)
            pos += k * wp
            neg += k * wn
            n += k
        out = ((PRIOR_A + pos) / (PRIOR_A + PRIOR_B + pos + neg), n)
        self._cache[key] = out
        return out

    def learned_drop(self, type_id: str, hour: int) -> int:
        """How many rungs quieter than its table value this type should be at this hour: 0, 1 or 2. Never negative."""
        sp = V.TYPES.get(type_id)
        if sp is None or sp.cls not in (V.HELPFUL, V.WAIT) or type_id == "approval_blocking":
            return 0
        if len(self._never.get(type_id, ())) >= self.p.never_subjects_for_max:
            return 2
        p, n = self.estimate(type_id, hour)
        if n < self.p.n_min:
            return 0
        if p <= self.p.quiet_thr2:
            return 2
        if p <= self.p.quiet_thr1:
            return 1
        return 0

    def summary(self) -> dict[str, Any]:
        """Per type: how many labels, the pooled-hour mean, and the drop at each hour that is not zero. Counts and enums only."""
        out: dict[str, Any] = {}
        for t, dq in self._labels.items():
            drops = {h: self.learned_drop(t, h) for h in range(24)}
            out[t] = {"n": len(dq), "never_subjects": len(self._never.get(t, ())), "drop_hours": [h for h, d in drops.items() if d],
                      "max_drop": max(drops.values(), default=0)}
        return out
