"""Data pools for the v2 evaluation (see evals/mlv2/PLAN.md section 3).

Everything is produced by the repo's own seeded generators into memory (nothing under ``data/`` is read or written):

  D0        the four personas exactly as v1 evaluates them (seeds 1101, 2202, 3303, 4404)
  DEV       D0 plus dev replicates r = 1..3, seed = base + 10 r            (16 people)
  HELD      held-out replicates r = 1..8, seed = base + 1000 r             (32 people; needs UNDERSTUDY_MLV2_HELDOUT=1)
  RESERVE   replicates r = 9..16, seed = base + 1000 r                     (needs the same token and a declared amendment)

Replicate people are named ``<person>d<r>`` (dev), ``h<r>`` (held-out) or ``x<r>`` (reserve), e.g. ``p_ninetofived1`` (the event schema allows only
lowercase letters and digits after ``p_``). A replicate is a new random draw
from the same persona spec, so it tests overfitting to one noise realisation, not "the model learned the generator".
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import pickle
import tempfile
from pathlib import Path

from understudy_engine.core import Episode, Event

HELDOUT_ENV = "UNDERSTUDY_MLV2_HELDOUT"
BASE_SEEDS = {"nine-to-five": 1101, "night-owl": 2202, "shift-worker": 3303, "irregular": 4404}
DEV_REPLICATES = (1, 2, 3)
HELD_REPLICATES = tuple(range(1, 9))
RESERVE_REPLICATES = tuple(range(9, 17))
POOL_NAMES = ("D0", "DEV", "HELD", "RESERVE")
_SPEC_VERSION = "1"


class HeldOutLocked(RuntimeError):
    """Raised when held-out or reserve data are requested without the explicit token."""


def _require_token(pool: str) -> None:
    if os.environ.get(HELDOUT_ENV, "").strip() != "1":
        raise HeldOutLocked(
            f"pool {pool} is held-out: set {HELDOUT_ENV}=1 and use `python -m understudy_engine.mlv2.run heldout` "
            "(single frozen run, see evals/mlv2/PLAN.md section 5)")


def replicate_seed(base: int, kind: str, r: int) -> int:
    if kind == "d":
        return base + 10 * r
    if kind in ("h", "x"):
        return base + 1000 * r
    raise ValueError(kind)


def pool_members(pool: str) -> list[tuple[str, int, str]]:
    """[(persona slug, replicate r or 0, kind)] for a pool; kind is '0', 'd', 'h' or 'x'."""
    if pool not in POOL_NAMES:
        raise ValueError(f"pool must be one of {POOL_NAMES}, got {pool!r}")
    slugs = list(BASE_SEEDS)
    out: list[tuple[str, int, str]] = []
    if pool in ("D0", "DEV"):
        out += [(s, 0, "0") for s in slugs]
    if pool == "DEV":
        out += [(s, r, "d") for r in DEV_REPLICATES for s in slugs]
    if pool == "HELD":
        out += [(s, r, "h") for r in HELD_REPLICATES for s in slugs]
    if pool == "RESERVE":
        out += [(s, r, "x") for r in RESERVE_REPLICATES for s in slugs]
    return out


def persona_spec(slug: str, r: int, kind: str):
    """The persona's spec with its seed and ids replaced for the replicate (r = 0 is the original)."""
    from understudy_engine.personas import PERSONA_BY_SLUG

    spec = PERSONA_BY_SLUG[slug]
    if kind == "0":
        return spec
    seed = replicate_seed(BASE_SEEDS[slug], kind, r)
    return dataclasses.replace(spec, slug=f"{slug}-{kind}{r}", person=f"{spec.person}{kind}{r}", seed=seed)


def episodes_for(spec, n_days: int = 21) -> list[Episode]:
    """Simulate one persona and turn its events into episodes (the same path v1 uses: events, cog mapper, segmentation)."""
    from understudy_engine.cogs import segment_episodes
    from understudy_engine.personas import simulate_persona

    run = simulate_persona(spec, n_days, with_mc=False)
    events = [Event.model_validate(row) for row in run.rows]      # rows carry ISO-8601 UTC strings
    return segment_episodes(events)


def _cache_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_MLV2_CACHE")
    p = Path(env) if env else Path(tempfile.gettempdir()) / "understudy_mlv2_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(spec, n_days: int) -> str:
    h = hashlib.sha1(f"{_SPEC_VERSION}|{spec.slug}|{spec.seed}|{n_days}|{dataclasses.asdict(spec)}".encode()).hexdigest()[:16]
    return f"{spec.slug}-{n_days}d-{h}.pkl"


def persona_episodes(slug: str, r: int, kind: str, n_days: int = 21, *, cache: bool = True) -> list[Episode]:
    spec = persona_spec(slug, r, kind)
    path = _cache_dir() / _cache_key(spec, n_days)
    if cache and path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:  # noqa: BLE001 - a corrupt cache entry is just regenerated
            pass
    eps = episodes_for(spec, n_days)
    if cache:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(eps))
        os.replace(tmp, path)
    return eps


def load_pool(pool: str, *, n_days: int = 21, cache: bool = True, limit_replicates: int | None = None) -> list[Episode]:
    """Episodes of every person in a pool. ``limit_replicates`` keeps only the first k replicate draws (fast mode, tests)."""
    if pool in ("HELD", "RESERVE"):
        _require_token(pool)
    members = pool_members(pool)
    if limit_replicates is not None:
        members = [m for m in members if m[1] <= limit_replicates]
    eps: list[Episode] = []
    for slug, r, kind in members:
        eps.extend(persona_episodes(slug, r, kind, n_days, cache=cache))
    return eps


def persona_type(person: str) -> str:
    """The persona type of a person id (replicate suffix removed), for stratified descriptions."""
    from understudy_engine.personas import PERSONAS

    for spec in PERSONAS:
        if person.startswith(spec.person):
            return spec.person
    return person
