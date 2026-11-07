"""Commit sessions as cog sequences, so the genome alignment can compare an expert's and a learner's way of working (GIT-1).

The mapping is data: ``packages/packs/programmer/git_mapping.yaml`` (commit digest -> cogs ``CODE, TEST, REFACTOR, COMMIT,
REVERT``, plus a coarse time model). A session (commits less than ``session_gap_min`` apart) becomes an ``Episode`` of
``Cog`` segments; the existing ``understudy_engine.genome.Cohort`` then gives the gap in seconds with a cluster bootstrap by
person, the expert-versus-expert placebo and the label-permutation null, exactly as it does for the benefits tasks.

What this is and is not: git records when a commit landed, not how long the work took, so the seconds are a model
(``lead_in_s`` by size bucket, the time since the previous commit) and the gap measures the difference in *shape* of the
sessions (more CODE-COMMIT loops, reverts, fewer TEST steps), not real working time. It is an illustration of the shared
alignment machinery, reported with its controls.
"""
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..core import Cog, Episode
from ..genome import FAMILIES, Cohort, CostModel
from ..store.paths import repo_root
from .records import CommitRecord
from .stats import interval, rnd


def cluster_mean_ci(per_person: Mapping[str, float], B: int, seed: int) -> list:
    v = np.array(list(per_person.values()))
    if v.size < 2:
        return [rnd(v[0]), rnd(v[0])] if v.size else [None, None]
    rng = np.random.default_rng(seed)
    return interval(v[rng.integers(0, v.size, (B, v.size))].mean(axis=1))

MAPPING_PATH = repo_root() / "packages" / "packs" / "programmer" / "git_mapping.yaml"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_mapping(path: str | Path | None = None) -> dict:
    return _load(str(path or MAPPING_PATH))


def _matches(rule: Mapping[str, Any], rec: CommitRecord) -> bool:
    m = rule.get("match", {})
    cat = m.get("category")
    if cat is not None and rec.category not in (cat if isinstance(cat, list) else [cat]):
        return False
    t = m.get("touches_tests")
    if t is not None and bool(t) != rec.touches_tests:
        return False
    return True


def rule_for(rec: CommitRecord, mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    for rule in mapping["rules"]:
        if _matches(rule, rec):
            return rule
    return {"cogs": ["COMMIT"]}


def commit_cogs(rec: CommitRecord, mapping: Mapping[str, Any] | None = None) -> list[str]:
    """The cog ids one commit maps to (first rule that matches)."""
    return list(rule_for(rec, mapping or load_mapping())["cogs"])


def cost_model(mapping: Mapping[str, Any] | None = None) -> CostModel:
    fams = tuple(frozenset(f) for f in (mapping or load_mapping())["params"].get("families", []))
    return CostModel(families=FAMILIES + fams)


def sessions(records: Sequence[CommitRecord], gap_min: float) -> list[list[CommitRecord]]:
    recs = sorted((r for r in records if r.parents <= 1), key=lambda r: r.t)
    out: list[list[CommitRecord]] = []
    for r in recs:
        if out and r.t - out[-1][-1].t <= gap_min * 60.0:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def session_cogs(sess: Sequence[CommitRecord], mapping: Mapping[str, Any]) -> list[Cog]:
    p = mapping["params"]
    commit_s, max_work, revert_s = float(p["commit_s"]), float(p["max_work_s"]), float(p["revert_s"])
    lead = p["lead_in_s"]
    cogs: list[Cog] = []
    prev_t: float | None = None
    for rec in sess:
        rule = rule_for(rec, mapping)
        ids = list(rule["cogs"])
        if ids == ["REVERT"]:
            cogs.append(Cog(rec.t - revert_s, rec.t, "REVERT"))
            prev_t = rec.t
            continue
        work = float(lead.get(rec.size_bucket, lead["small"])) if prev_t is None else min(max_work, max(commit_s, rec.t - prev_t))
        t_commit = rec.t - commit_s
        pre = [i for i in ids if i != "COMMIT"]
        if pre:
            w = list(rule.get("weights") or [1.0] * len(ids))[: len(pre)]
            tot = sum(w) or 1.0
            t = rec.t - commit_s - max(work - commit_s, 1.0)
            for cid, wi in zip(pre, w):
                dur = max(work - commit_s, 1.0) * wi / tot
                cogs.append(Cog(t, t + dur, cid))
                t += dur
        if "COMMIT" in ids:
            cogs.append(Cog(t_commit, rec.t, "COMMIT"))
        prev_t = rec.t
    return cogs


def to_episodes(records: Sequence[CommitRecord], person: str, *, mapping: Mapping[str, Any] | None = None, origin: str = "synthetic",
                seed: int = 0) -> list[Episode]:
    mp = mapping or load_mapping()
    sess = [s for s in sessions(records, float(mp["params"]["session_gap_min"])) if s]
    cap = int(mp["params"].get("max_episodes_per_person", 0) or 0)
    if cap and len(sess) > cap:                       # a fixed-seed sample keeps the null affordable and the choice neutral
        idx = sorted(random.Random(f"{seed}:{person}").sample(range(len(sess)), cap))
        sess = [sess[i] for i in idx]
    out = []
    for k, s in enumerate(sess):
        cogs = session_cogs(s, mp)
        out.append(Episode(task_id=f"{person}#s{k}", person=person, role="programmer", origin=origin, t0=cogs[0].t0, t1=s[-1].t, cogs=cogs))
    return out


def _shape(co: Cohort, ep: Episode, pool=None) -> float:
    """Edit cost per aligned column against the nearest reference session of another person (0 = the same way of working)."""
    _, al = co.nearest(ep, pool)
    return al.unit_cost / max(1, len(al.columns))


def _by_person(co: Cohort, eps, pool=None) -> dict[str, float]:
    acc: dict[str, list[float]] = {}
    for ep in eps:
        acc.setdefault(ep.person, []).append(_shape(co, ep, pool))
    return {p: float(np.mean(v)) for p, v in acc.items()}


def _boot_diff(a: Mapping[str, float], b: Mapping[str, float], B: int, seed: int) -> list:
    rng = np.random.default_rng(seed)
    av, bv = np.array(list(a.values())), np.array(list(b.values()))
    d = av[rng.integers(0, len(av), (B, len(av)))].mean(axis=1) - bv[rng.integers(0, len(bv), (B, len(bv)))].mean(axis=1)
    return interval(d)


def genome_compare(learners: Mapping[str, Sequence[CommitRecord]], experts: Mapping[str, Sequence[CommitRecord]], *,
                   mapping: Mapping[str, Any] | None = None, null_draws: int = 200, boot: int = 1000, origin: str = "synthetic") -> dict:
    """Run the genome alignment on commit sessions. Numbers only.

    ``shape``: mean edit cost per aligned column to the nearest expert session (never the same person), learners against the
    experts' own (placebo: each expert against the other experts), cluster bootstrap by person, and a label-permutation null.
    ``seconds``: the genome's usual gap in seconds, with its placebo and null, on the modelled times."""
    mp = mapping or load_mapping()
    eps: list[Episode] = []
    levels: dict[str, str] = {}
    for p, recs in experts.items():
        eps += to_episodes(recs, p, mapping=mp, origin=origin)
        levels[p] = "expert"
    for p, recs in learners.items():
        eps += to_episodes(recs, p, mapping=mp, origin=origin)
        levels[p] = "novice"
    co = Cohort(eps, levels, cost_model(mp))
    if not co.novices or len({e.person for e in co.experts}) < 3:
        return {"status": "not_run", "reason": "needs learner sessions and at least three experts"}
    # ---- shape distance
    learner_shape = _by_person(co, co.novices)
    expert_shape = _by_person(co, co.experts)          # nearest session of ANOTHER person (the placebo)
    diff = float(np.mean(list(learner_shape.values())) - np.mean(list(expert_shape.values())))
    people = sorted({e.person for e in eps})
    n_nov = len({e.person for e in co.novices})
    by_person_eps: dict[str, list[Episode]] = {}
    for e in eps:
        by_person_eps.setdefault(e.person, []).append(e)
    rng = random.Random(7)
    null_diffs = []
    for _ in range(null_draws):
        perm = people[:]
        rng.shuffle(perm)
        pseudo_nov, pseudo_exp = perm[:n_nov], perm[n_nov:]
        refs = [e for p in pseudo_exp for e in by_person_eps[p]]
        nv = _by_person(co, [e for p in pseudo_nov for e in by_person_eps[p]], refs)
        ex = _by_person(co, refs, refs)
        null_diffs.append(float(np.mean(list(nv.values())) - np.mean(list(ex.values()))))
    p_value = (1 + sum(1 for d in null_diffs if d >= diff)) / (1 + len(null_diffs))
    shape = {
        "unit": "edit cost per aligned column (0 = identical session shape)",
        "learner": {"mean": rnd(np.mean(list(learner_shape.values()))), "ci": cluster_mean_ci(learner_shape, boot, 11), "n_people": len(learner_shape)},
        "expert_placebo": {"mean": rnd(np.mean(list(expert_shape.values()))), "ci": cluster_mean_ci(expert_shape, boot, 12), "n_people": len(expert_shape)},
        "difference": {"value": rnd(diff), "ci": _boot_diff(learner_shape, expert_shape, boot, 13)},
        "null": {"mean": rnd(np.mean(null_diffs)), "ci": interval(null_diffs), "draws": len(null_diffs), "p_value": rnd(p_value)},
        "per_person": {"learners": {k: rnd(v) for k, v in learner_shape.items()}, "experts": {k: rnd(v) for k, v in expert_shape.items()}},
    }
    # ---- the genome's usual gap in seconds
    real, pl = co.real_gap(), co.placebo()
    nl = co.null(B=min(null_draws, 60), observed=real["gap_s"])
    seconds = {"unit": "seconds per session (a modelled quantity)", "real": {"gap_s": real["gap_s"], "ci": real["ci"], "n_people": real["n_people"]},
               "placebo": {"gap_s": pl["gap_s"], "ci": pl["ci"], "n_people": pl["n_people"]}, "null": nl}
    return {"status": "ok", "shape": shape, "seconds": seconds, "n_episodes": {"expert": len(co.experts), "learner": len(co.novices)},
            "cogs": sorted({c.id for e in eps for c in e.cogs})}
