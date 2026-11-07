"""Apprentice cohorts for M3 and M4 (PLAN.md section 3): APP-DEV and APP-HELD are fresh seeds of the repo's own apprentices generator.

``understudy_engine.personas.apprentices.generate`` reads a module-level SEED; a replicate sets it for one call into a temporary directory (the
module global is restored), so nothing under ``data/`` is touched. Each cohort has 8 experts and 16 novices with 2 cases each and a truth file with
the exact planted price of every deficit of every case.
"""
from __future__ import annotations

import os
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path

from understudy_engine.mlv2.splits import HELDOUT_ENV, HeldOutLocked

BASE_SEED = 8808
DEV_REPLICATES = (1, 2, 3)
HELD_REPLICATES = tuple(range(1, 7))
RESERVE_REPLICATES = tuple(range(7, 13))
POOLS = ("APP-D0", "APP-DEV", "APP-HELD", "APP-RESERVE")


@dataclass
class AppCohort:
    seed: int
    label: str
    cohort: object          # genome.cohort.Cohort
    truth: dict


def pool_seeds(pool: str) -> list[tuple[int, str]]:
    if pool not in POOLS:
        raise ValueError(f"pool must be one of {POOLS}, got {pool!r}")
    if pool == "APP-D0":
        return [(BASE_SEED, "d0")]
    if pool == "APP-DEV":
        return [(BASE_SEED, "d0")] + [(BASE_SEED + 10 * r, f"d{r}") for r in DEV_REPLICATES]
    if pool == "APP-HELD":
        return [(BASE_SEED + 1000 * r, f"h{r}") for r in HELD_REPLICATES]
    return [(BASE_SEED + 1000 * r, f"x{r}") for r in RESERVE_REPLICATES]


def _cache() -> Path:
    env = os.environ.get("UNDERSTUDY_MLV2_CACHE")
    p = Path(env) if env else Path(tempfile.gettempdir()) / "understudy_mlv2_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_cohort(seed: int, label: str = "", *, cache: bool = True) -> AppCohort:
    from understudy_engine.eval.deficit import load_bundle
    from understudy_engine.personas import apprentices

    path = _cache() / f"apprentices-{seed}.pkl"
    if cache and path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:  # noqa: BLE001
            pass
    old = apprentices.SEED
    try:
        apprentices.SEED = seed
        with tempfile.TemporaryDirectory(prefix="mlv2-app-") as td:
            apprentices.generate(Path(td))
            b = load_bundle(Path(td))
            out = AppCohort(seed, label, b.cohort, b.truth)
    finally:
        apprentices.SEED = old
    if cache:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(out))
        os.replace(tmp, path)
    return out


def load_pool(pool: str, *, limit: int | None = None) -> list[AppCohort]:
    if pool in ("APP-HELD", "APP-RESERVE") and os.environ.get(HELDOUT_ENV, "").strip() != "1":
        raise HeldOutLocked(f"pool {pool} is held-out: set {HELDOUT_ENV}=1 and use the frozen command (PLAN.md section 5)")
    seeds = pool_seeds(pool)
    if limit is not None:
        seeds = seeds[:limit]
    return [make_cohort(s, lab) for s, lab in seeds]
