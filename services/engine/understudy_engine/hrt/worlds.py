"""Pools and seeds for the HRT evaluation (``evals/hrt/PLAN.md`` section 2), and the worlds built from them.

Every seed below is new: a test asserts it is disjoint from every seed an earlier evaluation used, and from each other. Worlds are generated
in memory from the repo's own seeded generators and cached under the temp directory (a cache hit is byte-identical to a fresh draw).
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

HELDOUT_ENV = "UNDERSTUDY_HRT_HELDOUT"
BASES = {"nine-to-five": 1101, "night-owl": 2202, "shift-worker": 3303, "irregular": 4404}
FAMILIES = ("markov", "latent_skill", "process_trace")             # personas_v2.FAMILY_ORDER
V1_STEP, V2_BASE, ROUTE_BASE, DECIDE_BASE = 100_003, 6_100_000, 7_200_000, 9_300_000
TRAIN_K = (1, 2, 3, 4)
DEV_K = (5, 6)
HELD_K = tuple(range(11, 19))
ROUTE_TRAIN_K, ROUTE_DEV_K, ROUTE_HELD_K = 1, (2, 3), tuple(range(11, 19))
ROUTE_TRAIN_N, ROUTE_STREAM_N, ROUTE_DRIFT_AT, REVIEW_LAG = 1500, 4000, 1500, 50
V2_PEOPLE, V2_DAYS = 20, 14
DECIDE_ROWS = {"ski": 0, "routing": 1, "presence": 2, "nudge": 3}
DECIDE_DEV_K = (1, 2, 3)


def v1_seed(slug: str, k: int) -> int:
    return BASES[slug] + V1_STEP * k


def v2_seed(family: str, k: int) -> int:
    return V2_BASE + 1009 * k + 100 * FAMILIES.index(family)


def route_seed(k: int) -> int:
    return ROUTE_BASE + 313 * k


def decide_seed(row: str, k: int) -> int:
    return DECIDE_BASE + 211 * k + 10_000 * DECIDE_ROWS[row]


def all_seeds() -> dict[str, list[int]]:
    """Every seed this plan uses, by pool, for the disjointness test."""
    ks = {"train": TRAIN_K, "dev": DEV_K, "held": HELD_K}
    out: dict[str, list[int]] = {}
    for pool, kk in ks.items():
        out[f"v1_{pool}"] = [v1_seed(s, k) for k in kk for s in BASES]
    for pool, kk in (("dev", DEV_K[:2]), ("held", HELD_K)):
        out[f"v2_{pool}"] = [v2_seed(f, k) for k in kk for f in FAMILIES]
    out["route"] = [route_seed(ROUTE_TRAIN_K), *[route_seed(k) for k in ROUTE_DEV_K], *[route_seed(k) for k in ROUTE_HELD_K]]
    out["decide"] = [decide_seed(r, k) for r in DECIDE_ROWS for k in (*DECIDE_DEV_K, *range(11, 11 + 45))]
    return out


def known_used_seeds() -> set[int]:
    """What earlier evaluations used (PLAN.md section 2): mlv2 replicates, the realism formula, the routing and OPE re-draws, and every five-to-nine
    digit integer found next to the word seed in the engine and evals sources on 8 Nov 00:30."""
    used: set[int] = {10000, 10059, 12345, 20000, 46656, 100000, 104729, 964049, 5696411, 101, 2026, 8808}
    for b in BASES.values():
        used.update(b + 10 * r for r in range(0, 4))
        used.update(b + 1000 * r for r in range(1, 17))
    for f in range(3):
        for q in range(3):
            for k in range(3):
                for kind in (0, 1):
                    used.add(20261107 + 1000 * f + 100 * q + 10 * k + kind)
    used.update(range(0, 2100))                                      # routing and sandbox seeds, small integers
    used.update(1000 + i + s for i in range(0, 48) for s in range(0, 2100))
    return used


def _cache_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_HRT_CACHE")
    p = Path(env) if env else Path(tempfile.gettempdir()) / "understudy_hrt_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cached(key: str, make) -> Any:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    path = _cache_dir() / f"{key.split('|')[0]}-{h}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:                                            # noqa: BLE001 - a corrupt cache entry is regenerated
            pass
    val = make()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(val))
    os.replace(tmp, path)
    return val


# ----------------------------------------------------------------------------------------------------- hazard worlds
def v1_persona_episodes(slug: str, k: int, n_days: int = 21) -> list:
    """One v1 persona stream (a replicate draw with a new seed; person ids carry the replicate so people are distinct clusters)."""
    from understudy_engine.mlv2.splits import episodes_for
    from understudy_engine.personas import PERSONA_BY_SLUG

    def make():
        spec = dataclasses.replace(PERSONA_BY_SLUG[slug], slug=f"{slug}-hrt{k}", person=f"{PERSONA_BY_SLUG[slug].person}hrt{k}", seed=v1_seed(slug, k))
        return episodes_for(spec, n_days)

    return _cached(f"v1ep|{slug}|{k}|{n_days}|{v1_seed(slug, k)}", make)


def v1_deployment_episodes(k: int) -> list:
    """A v1 deployment: one persona stream of each of the four types, replicate ``k``."""
    return [e for slug in BASES for e in v1_persona_episodes(slug, k)]


def v2_deployment_episodes(family: str, k: int, role: str = "benefits-processor") -> list:
    """A shifted-world deployment: ``V2_PEOPLE`` people working ``V2_DAYS`` days, drawn from one v2 generator family."""
    from understudy_engine.personas_v2 import generate_workweeks

    def make():
        ww = generate_workweeks(family, role, n_people=V2_PEOPLE, n_days=V2_DAYS, seed=v2_seed(family, k))
        return ww.episodes()

    return _cached(f"v2ep|{family}|{k}|{role}|{V2_PEOPLE}|{V2_DAYS}|{v2_seed(family, k)}", make)


def train_episodes() -> list:
    """The deployment history the hazard models are fitted on: v1 persona streams, TRAIN replicates."""
    return [e for k in TRAIN_K for slug in BASES for e in v1_persona_episodes(slug, k)]


# ---------------------------------------------------------------------------------------------------- routing worlds
def simulate_cases_stream(n: int, seed: int, drift_at: int | None = None, drift_intercept: float = 1.0, drift_cliff: float = 1.5):
    """The routing generator (``routing.cases.simulate_cases``) with an optional rule change at case ``drift_at``: from then on the error logit's
    intercept rises by ``drift_intercept`` and the near-cliff x self-employed term grows by ``drift_cliff`` (it doubles). The random stream is consumed
    exactly as in the original, so with ``drift_at=None`` the result equals ``simulate_cases(n, seed)``."""
    from understudy_engine.routing.cases import Cases, FEATURES, AGENT_FEATURES, COMPLEXITY_FEATURES, TRACE_FEATURES
    from understudy_engine.trust.calibration import sigmoid

    rng = np.random.default_rng(seed)
    n_adults = rng.choice([1, 2], n, p=[0.45, 0.55]).astype(float)
    n_children = np.minimum(rng.poisson(1.1, n), 5).astype(float)
    income_sources = np.minimum(1 + rng.poisson(0.7, n), 5).astype(float)
    self_emp = (rng.random(n) < 0.18).astype(float)
    housing = rng.choice([0, 1, 2], n, p=[0.15, 0.55, 0.30]).astype(float)
    disability = (rng.random(n) < 0.15).astype(float)
    scotland = (rng.random(n) < 0.09).astype(float)
    benefits = np.minimum(1 + rng.poisson(1.2, n) + (n_children > 0), 6).astype(float)
    near_cliff = (rng.random(n) < 0.12).astype(float)
    c = np.clip(0.10 * n_adults + 0.07 * n_children + 0.12 * (income_sources - 1) + 0.10 * (housing > 0)
                + 0.06 * (benefits - 1) + 0.10 * self_emp + 0.05 * disability + rng.normal(0, 0.05, n), 0.0, 1.0)
    z = -3.4 + 2.3 * c + 1.5 * near_cliff * self_emp + 0.9 * scotland * disability + 0.5 * (income_sources >= 3)
    if drift_at is not None:
        after = np.arange(n) >= drift_at
        z = z + after * (drift_intercept + drift_cliff * near_cliff * self_emp)
    p_true = sigmoid(z)
    y = (rng.random(n) < p_true).astype(int)
    time_s = np.exp(rng.normal(np.log(240) + 0.5 * c + 0.15 * y, 0.35))
    retries = rng.poisson(0.4 + 1.2 * c + 0.3 * y).astype(float)
    backtracks = rng.poisson(0.3 + 0.8 * c).astype(float)
    noticed = rng.random(n) < np.where(y == 1, 0.55, 0.10)
    disagree = np.where(noticed, np.clip(rng.lognormal(-1.0, 0.6, n), 0.02, 3.0), 0.0)
    conf = np.clip(0.93 - 0.10 * y - 0.12 * c + rng.normal(0, 0.09, n), 0.05, 0.999)
    X = np.column_stack([n_adults, n_children, income_sources, self_emp, housing, disability, scotland, benefits, near_cliff,
                         np.log(time_s), retries, backtracks, disagree, conf])
    return Cases(X, y, p_true, groups={"complexity_only": COMPLEXITY_FEATURES, "worker_trace_only": TRACE_FEATURES,
                                       "agent_signals_only": AGENT_FEATURES, "all_features": FEATURES})
