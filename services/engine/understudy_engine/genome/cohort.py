"""Reference choice, gaps, controls and bootstrap intervals for a cohort of experts and novices (ANA-2 to 4).

Statistics here are descriptive and honest about what they are:
- the reference for an episode is its nearest expert (never the same person) or a consensus of the experts;
- intervals come from a cluster bootstrap over **people** (resample people with replacement), 1000 draws;
- ``placebo`` aligns each expert against its nearest other expert: a procedure with no true gap;
- ``null`` permutes the novice/expert labels across people and repeats the whole procedure: the gap you get
  when the label carries no information. Both should sit near zero while the real gap does not.
"""
from __future__ import annotations

import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..core import Cog, Episode
from .align import DEFAULT_COST, Alignment, CostModel, align
from .labels import LABEL_ORDER, components

B_BOOT = 1000
B_NULL = 300


def pct(xs: Sequence[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def interval(xs: Sequence[float]) -> list[float]:
    return [round(pct(xs, 0.025), 3), round(pct(xs, 0.975), 3)]


def cluster_bootstrap(per_person: dict[str, float], B: int = B_BOOT, seed: int = 0) -> list[float]:
    """95% interval of the mean of per-person values, resampling people with replacement."""
    people = sorted(per_person)
    if len(people) < 2:
        v = per_person[people[0]] if people else float("nan")
        return [round(v, 3), round(v, 3)]
    rnd = random.Random(seed)
    vals = [per_person[p] for p in people]
    means = []
    for _ in range(B):
        means.append(statistics.fmean(rnd.choice(vals) for _ in people))
    return interval(means)


@dataclass
class Cohort:
    """Episodes of one task plus who is an expert and who is a novice."""

    episodes: list[Episode]
    levels: dict[str, str]                # person -> "expert" | "novice"
    cost: CostModel = DEFAULT_COST
    _cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.episodes = [e for e in self.episodes if e.person in self.levels and e.cogs]
        self.experts = [e for e in self.episodes if self.levels[e.person] == "expert"]
        self.novices = [e for e in self.episodes if self.levels[e.person] == "novice"]
        self.by_task = {e.task_id: e for e in self.episodes}

    # ------------------------------------------------------------------ pairwise
    def align(self, ref: Episode, ep: Episode) -> Alignment:
        key = (ref.task_id, ep.task_id)
        al = self._cache.get(key)
        if al is None:
            al = self._cache[key] = align(ref.cogs, ep.cogs, self.cost)
        return al

    def nearest(self, ep: Episode, pool: Iterable[Episode] | None = None) -> tuple[Episode, Alignment]:
        """Nearest reference by (unit alignment cost, then absolute seconds); never the same person."""
        best = None
        for ref in (self.experts if pool is None else pool):
            if ref.person == ep.person:
                continue
            al = self.align(ref, ep)
            score = (al.unit_cost, al.abs_seconds)
            if best is None or score < best[0]:
                best = (score, ref, al)
        if best is None:
            raise ValueError("no reference episode from another person")
        return best[1], best[2]

    def consensus(self) -> list[Cog]:
        return consensus(self.experts, self.cost)

    # ------------------------------------------------------------------- results
    def novice_alignments(self, reference: str = "nearest_expert") -> list[tuple[Episode, str | None, Alignment]]:
        out = []
        if reference == "consensus":
            cons = self.consensus()
            for ep in self.novices:
                out.append((ep, None, align(cons, ep.cogs, self.cost)))
        else:
            for ep in self.novices:
                ref, al = self.nearest(ep)
                out.append((ep, ref.person, al))
        return out

    def real_gap(self, reference: str = "nearest_expert", seed: int = 1) -> dict:
        als = self.novice_alignments(reference)
        per_person: dict[str, list[float]] = defaultdict(list)
        for ep, _, al in als:
            per_person[ep.person].append(al.gap_s)
        pp = {p: statistics.fmean(v) for p, v in per_person.items()}
        return {"gap_s": round(statistics.fmean(pp.values()), 3), "ci": cluster_bootstrap(pp, seed=seed), "n_people": len(pp), "per_person": pp}

    def placebo(self, seed: int = 2) -> dict:
        per_person: dict[str, list[float]] = defaultdict(list)
        for ep in self.experts:
            _, al = self.nearest(ep)
            per_person[ep.person].append(al.gap_s)
        pp = {p: statistics.fmean(v) for p, v in per_person.items()}
        return {"gap_s": round(statistics.fmean(pp.values()), 3), "ci": cluster_bootstrap(pp, seed=seed), "n_people": len(pp)}

    def null(self, B: int = B_NULL, seed: int = 3, observed: float | None = None) -> dict:
        """Permute the expert/novice label across people; repeat the nearest-reference procedure."""
        people = sorted({e.person for e in self.episodes})
        n_exp = len({e.person for e in self.experts})
        eps_by_person: dict[str, list[Episode]] = defaultdict(list)
        for e in self.episodes:
            eps_by_person[e.person].append(e)
        rnd = random.Random(seed)
        gaps: list[float] = []
        for _ in range(B):
            perm = people[:]
            rnd.shuffle(perm)
            pseudo_exp = set(perm[:n_exp])
            refs = [e for p in pseudo_exp for e in eps_by_person[p]]
            per_person = []
            for p in perm[n_exp:]:
                g = []
                for ep in eps_by_person[p]:
                    ref, al = self.nearest(ep, refs)
                    g.append(al.gap_s)
                per_person.append(statistics.fmean(g))
            gaps.append(statistics.fmean(per_person))
        out = {"gap_s": round(statistics.fmean(gaps), 3), "ci": interval(gaps), "draws": B}
        if observed is not None:
            out["p_value"] = round((1 + sum(1 for g in gaps if g >= observed)) / (1 + B), 4)
        return out

    def waterfall(self, reference: str = "nearest_expert", B: int = B_BOOT, seed: int = 4) -> dict:
        """Mean seconds lost per case, by named behaviour, over novices; cluster bootstrap by person."""
        per_person: dict[str, list[dict[str, float]]] = defaultdict(list)
        for ep, _, al in self.novice_alignments(reference):
            per_person[ep.person].append(components(al))
        labels = [l for l in LABEL_ORDER if any(l in c for cs in per_person.values() for c in cs)]
        pp_vals = {l: {p: statistics.fmean(c.get(l, 0.0) for c in cs) for p, cs in per_person.items()} for l in labels}
        rows = []
        for l in labels:
            vals = pp_vals[l]
            rows.append({"label": l, "seconds": round(statistics.fmean(vals.values()), 3), "ci": cluster_bootstrap(vals, B, seed=seed)})
        totals = {p: sum(pp_vals[l][p] for l in labels) for p in per_person}
        return {
            "rows": rows,
            "total_gap_s": round(statistics.fmean(totals.values()), 3),
            "total_gap_ci": cluster_bootstrap(totals, B, seed=seed),
            "per_person": {p: {l: pp_vals[l][p] for l in labels} for p in per_person},
        }


def consensus(experts: Sequence[Episode], cost: CostModel = DEFAULT_COST) -> list[Cog]:
    """Star-alignment consensus: align every expert to the medoid; keep positions most experts have.

    Label = most common cog at the position, dwell = median dwell of the experts that have it. Returns Cogs on a
    synthetic clock starting at 0.
    """
    if not experts:
        return []
    seqs = [e.cogs for e in experts]
    best, best_score = 0, None
    for a, sa in enumerate(seqs):
        score = sum(align(sa, sb, cost).unit_cost for b, sb in enumerate(seqs) if b != a)
        if best_score is None or score < best_score:
            best, best_score = a, score
    med = seqs[best]
    votes: list[list[tuple[str, float]]] = [[] for _ in med]
    for k, s in enumerate(seqs):
        al = align(med, s, cost) if k != best else None
        if al is None:
            for i, c in enumerate(med):
                votes[i].append((c.id, c.dwell))
            continue
        for col in al.columns:
            if col.i is not None and col.j is not None:
                votes[col.i].append((s[col.j].id, s[col.j].dwell))
    out: list[Cog] = []
    t = 0.0
    for i, v in enumerate(votes):
        if len(v) * 2 < len(seqs):
            continue
        labels = [x for x, _ in v]
        top = max(sorted(set(labels)), key=labels.count)
        dwell = statistics.median(d for x, d in v if x == top)
        out.append(Cog(t, t + dwell, top))
        t += dwell
    return out
