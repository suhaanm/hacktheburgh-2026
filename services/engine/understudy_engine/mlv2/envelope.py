"""M3: the expert envelope (PLAN.md section 6.5): learned substitution costs, a profile of several experts, and alignment uncertainty.

v1 aligns a novice case to its **nearest single expert** with a hand-set substitution matrix (same cog 0, same family 0.5, unrelated 2.5) and
reads the seconds off the one optimal alignment. Three things can go wrong, and the variants address them one at a time:

  E1  learned costs     Experts differ legitimately (two of eight reorder the cliff checks). The substitution cost of a pair of cogs is learned
                        from how often *experts* align them to each other (relaxed alignments, co-aligned columns over opportunities), regularised
                        toward the hand-set matrix with 20 pseudo-opportunities, from the training experts only.
  E2  expert profile    The reference is not one expert but the median, per label, of the seconds attributed against the m = 3 nearest experts;
                        the interval is a bootstrap over the expert set.
  E3  alignment ties    Several alignments are near-optimal (which of two repeated reads is the "extra" one). Alignments are sampled from the
                        Boltzmann distribution exp(-cost / tau) over alignments (forward algorithm, stochastic traceback), tau = 0.25 in unit-cost
                        terms, and the labelled seconds are averaged over the samples.
  E4  all three together.

The labelling of alignment columns into waterfall bars and deficits is v1's (``genome.labels``), unchanged: this module changes the alignments
and how seconds are pooled, not what a bar is called.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from understudy_engine.core import Cog, Episode
from understudy_engine.genome.align import DEFAULT_COST, GAP_OPEN_EPS, Alignment, Column, CostModel, align
from understudy_engine.genome.labels import DEFICIT_OF_LABEL, LABEL_ORDER, components

TAU = 0.25
N_SAMPLES = 64
M_EXPERTS = 3
N0 = 20.0                      # pseudo-opportunities pulling a learned cost toward the hand-set one
RELAXED = CostModel(gap=1.0, same_family=1.0, unrelated=1.0, families=())
COST_MIN, COST_MAX = 0.25, 2.5


# ------------------------------------------------------------------------------------------ learned costs
@dataclass(frozen=True)
class LearnedCost(CostModel):
    """A CostModel whose substitution costs come from a table of (cog a, cog b, cost) with a < b (hashable, so v1's alignment cache works)."""

    table: tuple = ()

    def mismatch(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        key = (a, b) if a < b else (b, a)
        v = _table(self.table).get(key)
        return CostModel.mismatch(self, a, b) if v is None else v


@lru_cache(maxsize=64)
def _table(table: tuple) -> dict:
    return {(a, b): c for a, b, c in table}


def learn_costs(experts: list[Episode], *, n0: float = N0, hand: CostModel = DEFAULT_COST) -> tuple[LearnedCost, dict]:
    """Learn substitution costs from expert-versus-expert alignments (different people only)."""
    co_aligned: Counter = Counter()
    opp: Counter = Counter()
    n_pairs = 0
    for i, x in enumerate(experts):
        cx = Counter(c.id for c in x.cogs)
        for y in experts[i + 1:]:
            if y.person == x.person:
                continue
            n_pairs += 1
            al = align(x.cogs, y.cogs, RELAXED)
            for col in al.columns:
                if col.op == "mismatch":
                    a, b = sorted((col.cog_expert, col.cog_novice))
                    co_aligned[(a, b)] += 1
            cy = Counter(c.id for c in y.cogs)
            for a in cx:
                for b in cy:
                    if a < b:
                        opp[(a, b)] += min(cx[a], cy[b]) + min(cx[b], cy[a])
    table = []
    info = {}
    for (a, b), o in sorted(opp.items()):
        f = co_aligned[(a, b)] / o if o else 0.0
        learned = float(np.clip(COST_MAX * (1.0 - min(1.0, 2.0 * f)), COST_MIN, COST_MAX))
        hand_ab = hand.mismatch(a, b)
        cost = (n0 * hand_ab + o * learned) / (n0 + o)
        table.append((a, b, round(cost, 4)))
        info[f"{a}|{b}"] = {"hand": hand_ab, "learned": learned, "coaligned": co_aligned[(a, b)], "opportunities": o, "cost": round(cost, 4)}
    return LearnedCost(gap=hand.gap, same_family=hand.same_family, unrelated=hand.unrelated, families=hand.families, table=tuple(table)), \
        {"n_expert_pairs": n_pairs, "pairs": info}


# ---------------------------------------------------------------------------------- alignment sampling (forward)
def sample_alignments(expert: list[Cog], novice: list[Cog], cost: CostModel, *, n: int = N_SAMPLES, tau: float = TAU,
                      rng: np.random.Generator) -> list[Alignment]:
    """Alignments drawn from exp(-cost / tau) with the same Gotoh costs as v1 (linear gaps plus a tiny opening price). Forward pass in
    probability space (costs are small enough for float64), stochastic traceback."""
    a = [c.id for c in expert]
    b = [c.id for c in novice]
    na, nb = len(a), len(b)
    g, e = cost.gap, GAP_OPEN_EPS
    wg, wge = math.exp(-g / tau), math.exp(-(g + e) / tau)
    Wm = np.array([[math.exp(-cost.mismatch(ai, bj) / tau) for bj in b] for ai in a]) if na and nb else np.zeros((na, nb))
    Fm = np.zeros((na + 1, nb + 1))
    Fx = np.zeros((na + 1, nb + 1))
    Fy = np.zeros((na + 1, nb + 1))
    Fm[0, 0] = 1.0
    for i in range(1, na + 1):
        Fx[i, 0] = math.exp(-(i * g + e) / tau)
    for j in range(1, nb + 1):
        Fy[0, j] = math.exp(-(j * g + e) / tau)
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            Fm[i, j] = (Fm[i - 1, j - 1] + Fx[i - 1, j - 1] + Fy[i - 1, j - 1]) * Wm[i - 1, j - 1]
            Fx[i, j] = Fm[i - 1, j] * wge + Fx[i - 1, j] * wg + Fy[i - 1, j] * wge
            Fy[i, j] = Fm[i, j - 1] * wge + Fy[i, j - 1] * wg + Fx[i, j - 1] * wge
    out: list[Alignment] = []
    exp_s = sum(c.dwell for c in expert)
    nov_s = sum(c.dwell for c in novice)
    for _ in range(n):
        i, j = na, nb
        probs = np.array([Fm[i, j], Fx[i, j], Fy[i, j]])
        state = int(rng.choice(3, p=probs / probs.sum()))
        ops: list[tuple[int | None, int | None, str]] = []
        while i > 0 or j > 0:
            if state == 0:
                mm = cost.mismatch(a[i - 1], b[j - 1])
                ops.append((i - 1, j - 1, "match" if mm == 0 else "mismatch"))
                i, j = i - 1, j - 1
                if i == 0 and j == 0:
                    break
                pr = np.array([Fm[i, j], Fx[i, j], Fy[i, j]])
            elif state == 1:                                   # X: expert-only column (the novice skipped it)
                ops.append((i - 1, None, "gap_novice"))
                pr = np.array([Fm[i - 1, j] * wge, Fx[i - 1, j] * wg, Fy[i - 1, j] * wge])
                i -= 1
            else:                                              # Y: novice-only column (an extra step)
                ops.append((None, j - 1, "gap_expert"))
                pr = np.array([Fm[i, j - 1] * wge, Fx[i, j - 1] * wge, Fy[i, j - 1] * wg])
                j -= 1
            tot = pr.sum()
            if tot <= 0:                                        # numerically impossible boundary; fall back to the only legal move
                state = 1 if (j == 0) else 2 if (i == 0) else 0
            else:
                state = int(rng.choice(3, p=pr / tot))
            if i == 0 and j > 0:
                state = 2
            elif j == 0 and i > 0:
                state = 1
        ops.reverse()
        cols: list[Column] = []
        for ii, jj, op in ops:
            if op in ("match", "mismatch"):
                cols.append(Column(ii, jj, op, novice[jj].dwell - expert[ii].dwell, expert[ii].id, novice[jj].id))
            elif op == "gap_expert":
                cols.append(Column(None, jj, op, novice[jj].dwell, None, novice[jj].id))
            else:
                cols.append(Column(ii, None, op, -expert[ii].dwell, expert[ii].id, None))
        out.append(Alignment(cols, 0.0, exp_s, nov_s))
    return out


# ------------------------------------------------------------------------------------------------ variants
@dataclass(frozen=True)
class EnvelopeVariant:
    id: str
    learned_costs: bool = False
    m_experts: int = 1
    sample_alignments: bool = False
    label: str = ""


VARIANTS: dict[str, EnvelopeVariant] = {
    "E0": EnvelopeVariant("E0", False, 1, False, "v1: nearest expert, hand-set costs"),
    "E1": EnvelopeVariant("E1", True, 1, False, "nearest expert, learned substitution costs"),
    "E2": EnvelopeVariant("E2", False, M_EXPERTS, False, "median over the 3 nearest experts, hand-set costs"),
    "E3": EnvelopeVariant("E3", False, 1, True, "nearest expert, sampled alignments"),
    "E4": EnvelopeVariant("E4", True, M_EXPERTS, True, "learned costs + 3 nearest experts + sampled alignments"),
}


def _attr(al: Alignment) -> dict[str, float]:
    """Seconds per waterfall label of one alignment (zero for labels that do not occur)."""
    comp = components(al)
    return {l: comp.get(l, 0.0) for l in LABEL_ORDER}


def v1_functional(al: Alignment, ref: Episode, ep: Episode) -> np.ndarray:
    """v1's reading of an alignment: seconds per waterfall label (novice dwell for extras, minus expert dwell for skipped steps, dwell difference
    for shared and substituted steps)."""
    a = _attr(al)
    return np.array([a[l] for l in LABEL_ORDER])


@dataclass
class Attribution:
    """Seconds per waterfall label for one case under one variant, with an interval and the draws behind it."""

    point: dict[str, float]
    lo: dict[str, float]
    hi: dict[str, float]
    reference: str
    refs: list[str] = field(default_factory=list)
    draws: np.ndarray | None = None          # (n_draws, n_labels) bootstrap draws of the profile value (when computed)


class EnvelopeModel:
    """Attributes seconds to waterfall labels for episodes of one cohort, under any of the five variants."""

    def __init__(self, experts: list[Episode], *, seed: int = 0, n_boot: int = 200, n_samples: int = N_SAMPLES) -> None:
        self.experts = experts
        self.seed = seed
        self.n_boot = n_boot
        self.n_samples = n_samples
        self.learned, self.learn_info = learn_costs(experts)
        self._rng_cache: dict[tuple, np.random.Generator] = {}

    def cost_for(self, v: EnvelopeVariant) -> CostModel:
        return self.learned if v.learned_costs else DEFAULT_COST

    def _rng(self, key: str) -> np.random.Generator:
        import zlib

        return np.random.default_rng([self.seed, zlib.crc32(key.encode())])

    def _ranked(self, ep: Episode, cost: CostModel, pool: list[Episode] | None = None) -> list[tuple[Episode, Alignment]]:
        """Experts of other people ranked by (unit cost, absolute seconds), as v1's ``Cohort.nearest``."""
        out = []
        for ref in (self.experts if pool is None else pool):
            if ref.person == ep.person:
                continue
            al = align(ref.cogs, ep.cogs, cost)
            out.append(((al.unit_cost, al.abs_seconds), ref, al))
        out.sort(key=lambda r: r[0])
        return [(r, a) for _, r, a in out]

    def attribute(self, ep: Episode, v: EnvelopeVariant, *, with_interval: bool = True, pool: list[Episode] | None = None,
                  fn=None) -> Attribution:
        fn = fn or v1_functional
        cost = self.cost_for(v)
        ranked = self._ranked(ep, cost, pool)
        if not ranked:
            raise ValueError("no reference expert from another person")
        top = ranked[: max(1, v.m_experts)]
        # per-expert attribution: v1 reads the single optimal alignment; E3 and E4 average over sampled alignments
        per_expert: list[np.ndarray] = []
        samples_by_expert: list[np.ndarray] = []
        for ref, al in top:
            if v.sample_alignments:
                als = sample_alignments(ref.cogs, ep.cogs, cost, n=self.n_samples, rng=self._rng(f"{ep.task_id}|{ref.task_id}|{v.id}"))
                s = np.array([fn(a, ref, ep) for a in als])
                samples_by_expert.append(s)
                per_expert.append(s.mean(axis=0))
            else:
                per_expert.append(fn(al, ref, ep))
        P = np.vstack(per_expert)
        point = np.median(P, axis=0) if len(per_expert) > 1 else P[0]
        draws = None
        lo = hi = point.copy()
        if with_interval and v.sample_alignments and v.m_experts == 1:
            # E3: only the alignment ties are uncertain; the interval is the spread of the sampled alignments of the nearest expert
            draws = samples_by_expert[0]
            lo, hi = np.percentile(draws, 2.5, axis=0), np.percentile(draws, 97.5, axis=0)
        elif with_interval:
            rng = self._rng(f"{ep.task_id}|boot|{v.id}")
            pool_eps = [r for r, _ in ranked]
            people = sorted({r.person for r in pool_eps})
            # attribution of every candidate expert (cached alignments; sampled means for E3/E4 over the same number of samples)
            cand_attr: dict[str, np.ndarray] = {}
            cand_samples: dict[str, np.ndarray] = {}
            for r, al in ranked:
                if v.sample_alignments:
                    als = sample_alignments(r.cogs, ep.cogs, cost, n=self.n_samples, rng=self._rng(f"{ep.task_id}|{r.task_id}|{v.id}"))
                    s = np.array([fn(a, r, ep) for a in als])
                    cand_samples[r.task_id] = s
                    cand_attr[r.task_id] = s.mean(axis=0)
                else:
                    cand_attr[r.task_id] = fn(al, r, ep)
            by_person = defaultdict(list)
            for r, al in ranked:
                by_person[r.person].append((r, al))
            ds = []
            for _ in range(self.n_boot):
                pick = [people[k] for k in rng.integers(0, len(people), size=len(people))]
                cand = [(r, al) for p in pick for (r, al) in by_person[p]]
                cand.sort(key=lambda t: (t[1].unit_cost, t[1].abs_seconds))
                use = cand[: max(1, v.m_experts)]
                vals = []
                for r, _ in use:
                    if v.sample_alignments:
                        s = cand_samples[r.task_id]
                        vals.append(s[rng.integers(0, s.shape[0])])      # one sampled alignment per expert: carries the alignment uncertainty
                    else:
                        vals.append(cand_attr[r.task_id])
                ds.append(np.median(np.vstack(vals), axis=0) if len(vals) > 1 else vals[0])
            draws = np.vstack(ds)
            lo, hi = np.percentile(draws, 2.5, axis=0), np.percentile(draws, 97.5, axis=0)
        mk = lambda arr: {l: float(x) for l, x in zip(LABEL_ORDER, arr)}   # noqa: E731
        return Attribution(mk(point), mk(lo), mk(hi), top[0][0].person, [r.task_id for r, _ in top], draws)


def deficit_view(attr: Attribution) -> dict[str, dict[str, float]]:
    """The labels that name a planted deficit, as ``{deficit: {point, lo, hi}}``."""
    return {d: {"point": attr.point.get(lab, 0.0), "lo": attr.lo.get(lab, 0.0), "hi": attr.hi.get(lab, 0.0)}
            for lab, d in DEFICIT_OF_LABEL.items()}
