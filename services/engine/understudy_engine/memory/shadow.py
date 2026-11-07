"""Shadow comparison for personal procedures (MEM-4).

A personal procedure is an order the worker keeps choosing for the expert's checks ("child benefits first").
It is adopted only if, replayed in shadow on cases, it reaches the same outcomes as the expert policy.

The expert policy is the pack's ``expert_steps.yaml``: checks with ``after`` edges form a partial order, so
any linear extension is an allowed ordering and independent checks may be swapped (spec 6.3). A personal order
differs in outcome on a case when it puts check ``y`` before check ``x`` although ``y`` must come after ``x``
and both checks apply to that case. Required checks always apply; optional ones apply with a case-level flag.
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .packinfo import PackView

MIN_CASES = 10
MIN_MATCH = 0.90


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5)
    return 0.0 if k == 0 else max(0.0, centre - half)


@dataclass(frozen=True)
class ShadowResult:
    n: int
    matches: int
    mismatched: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        return self.matches / self.n if self.n else 0.0

    @property
    def wilson_lower(self) -> float:
        return wilson_lower(self.matches, self.n)

    @property
    def adopt(self) -> bool:
        return self.n >= MIN_CASES and self.rate >= MIN_MATCH

    def reason(self) -> str:
        if self.n < MIN_CASES:
            return f"only {self.n} shadow cases so far, need {MIN_CASES}"
        if self.rate < MIN_MATCH:
            return f"matches {self.rate:.0%} of expert outcomes in {self.n} shadow cases, need {MIN_MATCH:.0%}"
        return f"matches {self.rate:.0%} of expert outcomes in {self.n} shadow cases"


class ExpertPolicy:
    def __init__(self, checks: Sequence[dict[str, Any]]) -> None:
        self.checks = [dict(c) for c in checks]
        self.ids = [c["id"] for c in self.checks]
        self.required = {c["id"] for c in self.checks if c.get("required", True)}
        # must_precede[y] = checks that have to come before y
        self.before: dict[str, set[str]] = {c["id"]: set(c.get("after", [])) & set(self.ids) for c in self.checks}

    @classmethod
    def from_pack(cls, pack: PackView) -> ExpertPolicy | None:
        return cls(pack.expert_checks) if pack.expert_checks else None

    def topological(self) -> list[str]:
        """The expert's own order: pack order, which the schema requires to respect `after`."""
        return list(self.ids)

    def complete(self, order: Sequence[str]) -> list[str]:
        """The personal order, then every check it does not mention in the expert's order."""
        known = [o for o in dict.fromkeys(order) if o in self.before]
        return known + [i for i in self.ids if i not in known]

    def outcome_matches(self, order: Sequence[str], relevant: set[str]) -> bool:
        full = self.complete(order)
        pos = {c: i for i, c in enumerate(full)}
        for y, deps in self.before.items():
            if y not in relevant:
                continue
            for x in deps:
                if x in relevant and pos[x] > pos[y]:
                    return False
        return True

    def cases(self, seed: str, n: int = 40, p_optional: float = 0.7) -> list[set[str]]:
        rng = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:12], 16))
        out = []
        for _ in range(n):
            out.append({i for i in self.ids if i in self.required or rng.random() < p_optional})
        return out

    def compare(self, order: Sequence[str], cases: Sequence[set[str]]) -> ShadowResult:
        bad = [i for i in order if i not in self.before]
        if bad:  # an order that names checks the expert policy does not have cannot be shown to match
            return ShadowResult(len(cases), 0, tuple(f"unknown check {b}" for b in bad))
        matches = sum(1 for c in cases if self.outcome_matches(order, set(c)))
        return ShadowResult(len(cases), matches)


def parse_order(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value).split(">") if p.strip()]
