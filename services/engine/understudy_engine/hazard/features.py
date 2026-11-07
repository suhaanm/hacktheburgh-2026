"""Binning and features for the stuck hazard (ANA-5).

A *bin* is a 30 s tick inside one episode. For the bin starting at time b:

  label    y = 1  iff no `progress` event falls in (b, b + 60]       (the person is "stuck" for the next minute)
  features use ONLY what has happened up to b:
    - last three cogs as hashed n-grams (unigram, bigram, trigram), signed-free count features
    - dwell: seconds since the current cog started
    - repeat count: how many times in a row the current cog id has appeared
    - reformulations: REFORMULATE cogs since the last progress
    - time since progress (or since the episode start when nothing has progressed yet)
    - role prior: the role's base stuck rate, computed from TRAINING people only (see model.py)

Bins whose 60 s look-ahead would run past the end of the episode are dropped, because their label
is not observed.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np

from understudy_engine.core import Cog, Episode

BIN_S = 30.0
HORIZON_S = 60.0
N_HASH = 64
DENSE_NAMES = ("log_dwell", "repeat_run", "reformulations", "log_tsp", "tsp_lin")
TSP_COLS = (3, 4)  # indices into DENSE_NAMES used by the time-since-progress baseline
REPEAT_CAP = 8
REFORM_CAP = 10
TSP_LIN_CAP_S = 600.0


@dataclass
class BinTable:
    """Struct-of-arrays over all bins of all episodes. Rows of one episode are contiguous."""

    t: np.ndarray                 # bin start, unix seconds
    y: np.ndarray                 # 0/1
    person: np.ndarray            # str
    role: np.ndarray              # str
    episode: np.ndarray           # global episode index (cluster id)
    hashed: np.ndarray            # (n, N_HASH) float32 counts
    dense: np.ndarray             # (n, len(DENSE_NAMES)) float
    tsp_s: np.ndarray             # raw seconds since progress
    ep_offsets: np.ndarray        # (n_episodes + 1,) row offsets
    ep_person: list[str] = field(default_factory=list)
    ep_task: list[str] = field(default_factory=list)
    bin_s: float = BIN_S
    horizon_s: float = HORIZON_S

    @property
    def n(self) -> int:
        return int(self.y.size)

    @property
    def people(self) -> list[str]:
        return sorted(set(self.person.tolist()))

    def rows_of(self, people: list[str] | set[str]) -> np.ndarray:
        return np.where(np.isin(self.person, list(people)))[0]


def _hash_gram(gram: tuple[str, ...], n_hash: int) -> int:
    key = f"{len(gram)}:" + ">".join(gram)
    return zlib.crc32(key.encode("utf-8")) % n_hash  # crc32 is stable across processes (unlike hash())


def _cog_hash_rows(ids: list[str], n_hash: int) -> np.ndarray:
    """Row i = hashed n-gram counts for the last three cogs ending at cog i."""
    out = np.zeros((len(ids), n_hash), dtype=np.float32)
    cache: dict[tuple[str, ...], int] = {}
    for i in range(len(ids)):
        for k in (1, 2, 3):
            if i - k + 1 < 0:
                break
            gram = tuple(ids[i - k + 1 : i + 1])
            h = cache.get(gram)
            if h is None:
                h = cache[gram] = _hash_gram(gram, n_hash)
            out[i, h] += 1.0
    return out


def episode_bins(
    ep: Episode, *, bin_s: float = BIN_S, horizon_s: float = HORIZON_S, n_hash: int = N_HASH,
    reform_ids: tuple[str, ...] = ("REFORMULATE",),
) -> dict[str, np.ndarray]:
    cogs: list[Cog] = sorted(ep.cogs, key=lambda c: c.t0)
    starts = np.array([c.t0 for c in cogs], dtype=float)
    ids = [c.id for c in cogs]
    pt = np.sort(np.asarray(ep.progress_t, dtype=float))
    k_max = int(np.floor((ep.t1 - horizon_s - ep.t0) / bin_s)) + 1 if ep.t1 - ep.t0 >= horizon_s else 0
    if k_max <= 0:
        return {}
    b = ep.t0 + bin_s * np.arange(k_max)

    # label: no progress in (b, b + horizon]
    n_in = np.searchsorted(pt, b + horizon_s, side="right") - np.searchsorted(pt, b, side="right")
    y = (n_in == 0).astype(np.int8)

    # current cog = last cog started at or before b
    cur = np.searchsorted(starts, b, side="right") - 1  # -1: nothing has started yet
    hrows = _cog_hash_rows(ids, n_hash) if ids else np.zeros((0, n_hash), dtype=np.float32)
    hashed = np.zeros((b.size, n_hash), dtype=np.float32)
    has = cur >= 0
    if has.any():
        hashed[has] = hrows[cur[has]]

    dwell = np.where(has, b - starts[np.maximum(cur, 0)], 0.0) if starts.size else np.zeros(b.size)

    # trailing run of the same id ending at the current cog
    run = np.zeros(len(ids), dtype=float)
    for i in range(len(ids)):
        run[i] = 1.0 if i == 0 or ids[i] != ids[i - 1] else run[i - 1] + 1.0
    repeat = np.where(has, run[np.maximum(cur, 0)] if run.size else 0.0, 0.0)
    repeat = np.minimum(repeat, REPEAT_CAP)

    # last progress at or before b (episode start if none)
    j = np.searchsorted(pt, b, side="right") - 1
    last_prog = np.where(j >= 0, pt[np.maximum(j, 0)] if pt.size else ep.t0, ep.t0)
    tsp = b - last_prog

    # reformulations since last progress: cogs started after last_prog and at or before b
    is_ref = np.array([1.0 if c in reform_ids else 0.0 for c in ids])
    cum = np.concatenate([[0.0], np.cumsum(is_ref)])
    j0 = np.searchsorted(starts, last_prog, side="right")
    hi = cur + 1
    reform = np.where(hi > j0, cum[hi] - cum[j0], 0.0)
    reform = np.minimum(reform, REFORM_CAP)

    dense = np.column_stack([
        np.log1p(np.maximum(dwell, 0.0)), repeat, reform, np.log1p(np.maximum(tsp, 0.0)),
        np.minimum(np.maximum(tsp, 0.0), TSP_LIN_CAP_S) / 60.0,
    ])
    return {"t": b, "y": y, "hashed": hashed, "dense": dense, "tsp_s": tsp}


def build_bins(
    episodes: list[Episode], *, bin_s: float = BIN_S, horizon_s: float = HORIZON_S, n_hash: int = N_HASH,
    reform_ids: tuple[str, ...] = ("REFORMULATE",),
) -> BinTable:
    parts = []
    offsets = [0]
    ep_person: list[str] = []
    ep_task: list[str] = []
    person, role, epi = [], [], []
    for ep in episodes:
        d = episode_bins(ep, bin_s=bin_s, horizon_s=horizon_s, n_hash=n_hash, reform_ids=reform_ids)
        if not d:
            continue
        k = d["t"].size
        parts.append(d)
        person.extend([ep.person] * k)
        role.extend([ep.role] * k)
        epi.extend([len(ep_person)] * k)
        ep_person.append(ep.person)
        ep_task.append(ep.task_id)
        offsets.append(offsets[-1] + k)
    if not parts:
        z = np.zeros(0)
        return BinTable(z, z.astype(np.int8), np.array([], dtype=object), np.array([], dtype=object),
                        z.astype(int), np.zeros((0, n_hash), dtype=np.float32), np.zeros((0, len(DENSE_NAMES))),
                        z, np.array([0]), [], [], bin_s, horizon_s)
    return BinTable(
        t=np.concatenate([p["t"] for p in parts]),
        y=np.concatenate([p["y"] for p in parts]).astype(np.int8),
        person=np.array(person, dtype=object),
        role=np.array(role, dtype=object),
        episode=np.array(epi, dtype=int),
        hashed=np.vstack([p["hashed"] for p in parts]),
        dense=np.vstack([p["dense"] for p in parts]),
        tsp_s=np.concatenate([p["tsp_s"] for p in parts]),
        ep_offsets=np.array(offsets, dtype=int),
        ep_person=ep_person, ep_task=ep_task, bin_s=bin_s, horizon_s=horizon_s,
    )
