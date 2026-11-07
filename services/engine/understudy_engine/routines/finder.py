"""Routine finder (ANA-10): episodes -> alignment distance -> average-linkage clusters -> candidate routines.

1. Each episode's cog sequence is reduced to a **skeleton**: idle gaps, reverts and reformulations are dropped (they
   are how someone wanders, not what the routine is) and runs of the same cog collapse to one. Judgement cogs such
   as ``SEARCH`` and ``DECIDE`` stay, so a judgement-heavy routine looks judgement-heavy.
2. Distance between two episodes = edit distance between their skeletons (insert, delete, substitute, each cost 1)
   divided by the longer length: 0 for identical, 1 for nothing in common. This is a normalised global-alignment
   distance with unit costs.
3. Average-linkage agglomerative clustering, cut at a distance ``threshold``. A cluster with at least
   ``min_support`` episodes is a candidate routine; everything else is one-off work.

Cost is quadratic in the number of episodes, so only unique skeletons are aligned (pairs are computed in numpy,
vectorised over pairs) and at most ``max_episodes`` of the most recent episodes are clustered.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from ..core import Episode

DROP_COGS = frozenset({"IDLE", "REVERT", "REFORMULATE"})
MAX_LEN = 40


@dataclass(frozen=True)
class FinderConfig:
    threshold: float = 0.35       # cut height for average linkage (normalised distance)
    min_support: int = 3
    min_len: int = 4              # skeletons shorter than this are never a routine
    max_episodes: int = 2500
    drop: frozenset[str] = DROP_COGS


def skeleton(ep: Episode, drop: frozenset[str] = DROP_COGS) -> tuple[str, ...]:
    out: list[str] = []
    for c in ep.cogs:
        if c.id in drop:
            continue
        if out and out[-1] == c.id:
            continue
        out.append(c.id)
    return tuple(out[:MAX_LEN])


def collapse(seq: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for c in seq:
        if not out or out[-1] != c:
            out.append(c)
    return tuple(out)


def edit_distance(a: Sequence[str], b: Sequence[str]) -> float:
    """Unit-cost edit distance divided by the longer length (0 identical, 1 nothing shared)."""
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 0.0
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[lb] / max(la, lb)


def pairwise_distances(seqs: Sequence[Sequence[str]]) -> np.ndarray:
    """Full (U, U) normalised distance matrix between unique sequences, vectorised over pairs."""
    u = len(seqs)
    vocab = {c: i for i, c in enumerate(sorted({c for s in seqs for c in s}))}
    L = max((len(s) for s in seqs), default=0)
    arr = np.full((u, max(L, 1)), -1, dtype=np.int16)
    lens = np.array([len(s) for s in seqs], dtype=np.int32)
    for i, s in enumerate(seqs):
        arr[i, : len(s)] = [vocab[c] for c in s]
    iu, ju = np.triu_indices(u, k=1)
    out = np.zeros((u, u), dtype=np.float32)
    chunk = 8000
    for s0 in range(0, len(iu), chunk):
        ia, ja = iu[s0 : s0 + chunk], ju[s0 : s0 + chunk]
        A, B = arr[ia], arr[ja]
        la, lb = lens[ia], lens[ja]
        P = len(ia)
        D = np.zeros((L + 1, L + 1, P), dtype=np.int16)
        D[:, 0, :] = np.arange(L + 1, dtype=np.int16)[:, None]
        D[0, :, :] = np.arange(L + 1, dtype=np.int16)[:, None]
        for i in range(1, L + 1):
            for j in range(1, L + 1):
                sub = D[i - 1, j - 1] + (A[:, i - 1] != B[:, j - 1])
                D[i, j] = np.minimum(np.minimum(D[i - 1, j] + 1, D[i, j - 1] + 1), sub)
        d = D[la, lb, np.arange(P)].astype(np.float32) / np.maximum(np.maximum(la, lb), 1)
        out[ia, ja] = d
        out[ja, ia] = d
    return out


@dataclass
class Cluster:
    members: list[int]            # indices into the episode list given to ``find_routines``
    medoid: tuple[str, ...]       # skeleton of the member closest to all others
    mean_dist: float              # mean distance of members to the medoid
    episodes: list[Episode] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)


def find_routines(episodes: Sequence[Episode], cfg: FinderConfig | None = None) -> list[Cluster]:
    """Cluster episodes by skeleton distance. Returns candidate routines (support >= ``min_support``), largest first."""
    cfg = cfg or FinderConfig()
    idx = sorted(range(len(episodes)), key=lambda i: episodes[i].t0)[-cfg.max_episodes:]
    skel = {i: skeleton(episodes[i], cfg.drop) for i in idx}
    keep = [i for i in idx if len(skel[i]) >= cfg.min_len]
    if len(keep) < cfg.min_support:
        return []
    uniq: dict[tuple[str, ...], int] = {}
    useq: list[tuple[str, ...]] = []
    owner = []
    for i in keep:
        s = skel[i]
        if s not in uniq:
            uniq[s] = len(useq)
            useq.append(s)
        owner.append(uniq[s])
    D = pairwise_distances(useq)
    owner_a = np.asarray(owner)
    full = D[np.ix_(owner_a, owner_a)].astype(np.float64)
    np.fill_diagonal(full, 0.0)
    Z = linkage(squareform(full, checks=False), method="average")
    labels = fcluster(Z, t=cfg.threshold, criterion="distance")
    groups: dict[int, list[int]] = defaultdict(list)
    for pos, lab in enumerate(labels):
        groups[int(lab)].append(pos)
    out: list[Cluster] = []
    for pos_list in groups.values():
        if len(pos_list) < cfg.min_support:
            continue
        sub = full[np.ix_(pos_list, pos_list)]
        m = int(np.argmin(sub.sum(axis=1)))
        members = [keep[p] for p in pos_list]
        out.append(Cluster(members=members, medoid=skel[keep[pos_list[m]]], mean_dist=float(sub[m].mean()),
                           episodes=[episodes[i] for i in members]))
    out.sort(key=lambda c: (-c.size, c.medoid))
    return out
