"""The registry of every variant tried (PLAN.md section 7): the garden of forking paths, counted.

``REGISTRY`` lists each variant with its family, whether it can replace v1, and the plan section. ``count_tested()`` is the number reported with every
result (15 candidates that can replace v1 under the plan: A 7, C 2, E 4, Q 2). A variant scored on any split that is not in this table must be added here
with a dated amendment in PLAN.md before its result is read.
"""
from __future__ import annotations

from dataclasses import dataclass

from understudy_engine.mlv2.envelope import VARIANTS as E_VARIANTS
from understudy_engine.mlv2.models import A7_CANDIDATES, BASELINE_SPECS, FAMILY_A


@dataclass(frozen=True)
class Entry:
    id: str
    family: str
    kind: str          # reference | candidate | baseline | control | head
    label: str
    plan: str


REGISTRY: tuple[Entry, ...] = (
    *(Entry(k, "A", "reference" if k == "A0" else "candidate", v.label, "6.2") for k, v in FAMILY_A.items()),
    Entry("A7", "A", "candidate", "A6 shift on the dev-better of A1 and A4 (one of " + ", ".join(A7_CANDIDATES) + " is picked on DEV)", "6.2"),
    *(Entry(k, "A", "baseline", v.label, "6.2") for k, v in BASELINE_SPECS.items()),
    Entry("TTE", "B", "head", "discrete-time survival head, expected minutes until progress (no replacement rule)", "6.3"),
    Entry("C0", "C", "reference", "v1 alarm rule", "6.4"),
    Entry("C1", "C", "candidate", "Learn-then-Test fixed sequence, exact Poisson bound", "6.4"),
    Entry("C2", "C", "candidate", "person-cluster bootstrap upper bound", "6.4"),
    *(Entry(k, "E", "reference" if k == "E0" else "candidate", v.label, "6.5") for k, v in E_VARIANTS.items()),
    Entry("Q0", "Q", "reference", "v1 alignment attribution (equal to E0)", "6.6"),
    Entry("Q1", "Q", "candidate", "ensemble splice, pace-scaled pricing", "6.6"),
    Entry("Q1b", "Q", "candidate", "ensemble splice, unscaled expert dwell (v1 pricing; numerically equal to E4)", "6.6"),
    Entry("SHAPLEY", "Q", "control", "exact Shapley allocation of the replay (an allocation, not a new estimate)", "6.6"),
    Entry("AWARE", "M1", "control", "awareness feature groups: cursor, app_kind, glance, all (+ placebo and noise controls)", "6.1"),
)


def count_tested() -> dict[str, int]:
    cand = [e for e in REGISTRY if e.kind == "candidate"]
    out = {f: sum(1 for e in cand if e.family == f) for f in ("A", "C", "E", "Q")}
    out["total"] = sum(out.values())
    return out


def ids(family: str, kind: str | None = None) -> list[str]:
    return [e.id for e in REGISTRY if e.family == family and (kind is None or e.kind == kind)]
