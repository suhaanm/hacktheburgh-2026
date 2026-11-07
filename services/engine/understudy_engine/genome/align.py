"""Needleman-Wunsch alignment of two cog sequences, with gaps priced in seconds (ANA-2).

The alignment is chosen on unit costs (match 0, mismatch from a cog distance, gap 1). Each aligned column is
then priced in seconds, signed so that **positive means the novice lost time**:

    match / mismatch   dwell(novice) - dwell(expert)
    gap_expert         +dwell(novice)   the novice has a cog the expert does not (an extra step)
    gap_novice         -dwell(expert)   the expert has a cog the novice skipped (time saved by skipping)

``i`` indexes the expert sequence and ``j`` the novice one; a gap has the other index ``None``. The column
seconds always sum to ``sum(novice dwell) - sum(expert dwell)``, so a total gap is exactly accounted for.

Distance matrix (a deliberate choice, tested): same cog 0, same family 0.5, unrelated 2.5 (more than the price of
two gaps), so unrelated cogs align as a pair of gaps instead of a misleading mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from typing import Sequence

from ..core import Cog

FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"READ", "READ_RESULT"}),
    frozenset({"SEARCH", "REFORMULATE"}),
    frozenset({"ENTER", "ENTER_HOUSEHOLD"}),
    frozenset({"COPY", "PASTE", "COPY_TO_NOTE"}),
    frozenset({"CHECK", "CHECK_CLIFF", "COMPARE", "RECONCILE"}),
    frozenset({"NAVIGATE", "OPEN_CALCULATOR"}),
)


@dataclass(frozen=True)
class CostModel:
    gap: float = 1.0
    same_family: float = 0.5
    unrelated: float = 2.5
    families: tuple[frozenset[str], ...] = FAMILIES

    def mismatch(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        for fam in self.families:
            if a in fam and b in fam:
                return self.same_family
        return self.unrelated


DEFAULT_COST = CostModel()


@dataclass(frozen=True)
class Column:
    i: int | None
    j: int | None
    op: str            # match | mismatch | gap_expert | gap_novice
    seconds: float
    cog_expert: str | None
    cog_novice: str | None


@dataclass
class Alignment:
    columns: list[Column]
    unit_cost: float
    expert_s: float
    novice_s: float
    meta: dict = field(default_factory=dict)

    @property
    def gap_s(self) -> float:
        """Signed total: novice minus expert time over the cogs (equals the sum of column seconds)."""
        return self.novice_s - self.expert_s

    @cached_property
    def abs_seconds(self) -> float:
        return sum(abs(c.seconds) for c in self.columns)

    def as_rows(self) -> list[dict]:
        return [{"i": c.i, "j": c.j, "op": c.op, "seconds": round(c.seconds, 3), "expert_cog": c.cog_expert, "novice_cog": c.cog_novice} for c in self.columns]


GAP_OPEN_EPS = 0.01     # tiny extra price for opening a gap: ties go to one contiguous block of extras
INF = float("inf")


@lru_cache(maxsize=200_000)
def _align_ids(a: tuple[str, ...], b: tuple[str, ...], cost: CostModel) -> tuple[float, tuple[tuple[int | None, int | None, str], ...]]:
    """Gotoh DP with linear gap cost plus a tiny opening price. States: M diagonal, X expert-only, Y novice-only."""
    n, m = len(a), len(b)
    g, e = cost.gap, GAP_OPEN_EPS
    M = [[INF] * (m + 1) for _ in range(n + 1)]
    X = [[INF] * (m + 1) for _ in range(n + 1)]
    Y = [[INF] * (m + 1) for _ in range(n + 1)]
    M[0][0] = 0.0
    for i in range(1, n + 1):
        X[i][0] = i * g + e
    for j in range(1, m + 1):
        Y[0][j] = j * g + e
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            M[i][j] = min(M[i - 1][j - 1], X[i - 1][j - 1], Y[i - 1][j - 1]) + cost.mismatch(ai, b[j - 1])
            X[i][j] = min(M[i - 1][j] + g + e, X[i - 1][j] + g, Y[i - 1][j] + g + e)
            Y[i][j] = min(M[i][j - 1] + g + e, Y[i][j - 1] + g, X[i][j - 1] + g + e)
    i, j = n, m
    state = min(("M", M[n][m]), ("X", X[n][m]), ("Y", Y[n][m]), key=lambda kv: kv[1])[0]
    best = min(M[n][m], X[n][m], Y[n][m])
    ops: list[tuple[int | None, int | None, str]] = []
    eps = 1e-9
    while i > 0 or j > 0:
        if state == "M":
            mm = cost.mismatch(a[i - 1], b[j - 1])
            ops.append((i - 1, j - 1, "match" if mm == 0 else "mismatch"))
            prev = {"M": M[i - 1][j - 1], "X": X[i - 1][j - 1], "Y": Y[i - 1][j - 1]}
            target = M[i][j] - mm
            i, j = i - 1, j - 1
            state = next((k for k in ("M", "X", "Y") if abs(prev[k] - target) < eps), "M") if (i > 0 or j > 0) else "M"
        elif state == "X":
            ops.append((i - 1, None, "gap_novice"))
            cands = {"M": M[i - 1][j] + g + e, "X": X[i - 1][j] + g, "Y": Y[i - 1][j] + g + e}
            target = X[i][j]
            i -= 1
            state = next((k for k in ("X", "M", "Y") if abs(cands[k] - target) < eps), "X")
        else:
            ops.append((None, j - 1, "gap_expert"))
            cands = {"M": M[i][j - 1] + g + e, "Y": Y[i][j - 1] + g, "X": X[i][j - 1] + g + e}
            target = Y[i][j]
            j -= 1
            state = next((k for k in ("Y", "M", "X") if abs(cands[k] - target) < eps), "Y")
    ops.reverse()
    return round(best, 6), tuple(ops)


def _prefer_first_repeat(ops: list, expert: Sequence[Cog], novice: Sequence[Cog]) -> tuple:
    """When the novice repeats a cog back to back, the first occurrence is the real step and the later ones are repeats."""
    for k in range(len(ops) - 1):
        for p, q in ((k, k + 1), (k + 1, k)):
            i1, j1, op1 = ops[p]
            i2, j2, op2 = ops[q]
            if op1 == "match" and op2 == "gap_expert" and j1 is not None and j2 is not None and abs(j1 - j2) == 1 \
                    and novice[j1].id == novice[j2].id and j2 < j1:
                ops[q], ops[p] = (i1, j2, "match"), (None, j1, "gap_expert")   # keep j increasing along the columns
    return tuple(ops)


def align(expert: Sequence[Cog], novice: Sequence[Cog], cost: CostModel = DEFAULT_COST) -> Alignment:
    """Align a novice cog sequence against an expert one and price every column in seconds."""
    ea = tuple(c.id for c in expert)
    nb = tuple(c.id for c in novice)
    unit, ops = _align_ids(ea, nb, cost)
    ops = _prefer_first_repeat(list(ops), expert, novice)
    cols: list[Column] = []
    for i, j, op in ops:
        if op in ("match", "mismatch"):
            sec = novice[j].dwell - expert[i].dwell
            cols.append(Column(i, j, op, sec, expert[i].id, novice[j].id))
        elif op == "gap_expert":
            cols.append(Column(None, j, op, novice[j].dwell, None, novice[j].id))
        else:
            cols.append(Column(i, None, op, -expert[i].dwell, expert[i].id, None))
    return Alignment(cols, unit, sum(c.dwell for c in expert), sum(c.dwell for c in novice))
