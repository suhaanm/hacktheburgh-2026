"""Realism evaluation: marginal checks, the analytics on v1 and on each v2 family, and the generator-mismatch matrix.

    python -m understudy_engine.personas_v2.evaluate --full     # writes evals/realism/REPORT.md and data/eval/realism.json
    python -m understudy_engine.personas_v2.evaluate --fast     # the same shape, small n
    from understudy_engine.personas_v2.evaluate import evaluate_realism; evaluate_realism(fast=True)

Everything follows ``evals/realism/PLAN.md`` (frozen before the first analytic ran on v2 data). The analytics are called
through their public functions; their code is not copied. Every number carries a person-cluster bootstrap interval, the
badge is "synthetic, realism-calibrated", and nothing says the data are human data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import eval_genome as EG
from . import eval_hazard as EH
from . import eval_routines as ER
from . import marginals as MG
from .cohort import generate_cohort
from .evalkit import B_FAST, B_FULL, boot_idx, est, interval, mean_draws, point_mean, point_ratio, ratio_draws, rnd, sd_across, verdict
from .families import FAMILY_ORDER
from .params import params_sha256
from .roles import ROLES
from .version import generator_sha256
from .workweeks import generate_workweeks

BADGE = "generated, realism-calibrated"
SEED0 = 20261107
ROLE_ORDER = ("benefits-processor", "data-analyst", "programmer")
FAMS = tuple(FAMILY_ORDER)
ALL = ("v1",) + FAMS
KINDS = {"cohort": 0, "workweeks": 1}
MARGIN = {"h1": 0.01, "g1": 0.10, "r": 0.10}


def seed_for(family: str, role: str, k: int, kind: str) -> int:
    return SEED0 + 1000 * FAMS.index(family) + 100 * ROLE_ORDER.index(role) + 10 * k + KINDS[kind]


@dataclass
class Config:
    fast: bool
    roles: tuple[str, ...]
    K: int
    n_ww: int
    days: int
    n_coh: int
    cases: int
    genome_cases: int
    B: int
    grid: tuple[float, ...]
    with_v1: bool
    proposals: bool
    lopo_diag: bool
    workers: int

    @classmethod
    def make(cls, fast: bool, workers: int | None = None) -> "Config":
        env = os.environ.get("UNDERSTUDY_REALISM_WORKERS")
        # fast mode is serial by default (safe in any process, deterministic); the full run defaults to a small pool
        w = workers or (int(env) if env else (1 if fast else max(1, min(6, (os.cpu_count() or 4) - 2))))
        if fast:
            return cls(True, ("benefits-processor",), 2, 14, 7, 14, 4, 2, B_FAST, (0.25, 0.35, 0.45), False, False, False, w)
        return cls(False, ROLE_ORDER, 3, 40, 14, 48, 8, 2, B_FULL, ER.GRID, True, True, True, w)


# ------------------------------------------------------------------------------------------ dataset construction (workers)
@dataclass
class WW:
    family: str
    role: str
    rep: int
    seed: int
    persons: dict[str, list]
    labels: dict[str, str]
    label_checks: list[dict]
    hyper: dict
    counts: dict


@dataclass
class Coh:
    family: str
    role: str
    rep: int
    seed: int
    episodes: list
    levels: dict[str, str]
    truth: dict
    checks: list[dict]
    hyper: dict


def _cache_dir() -> Path:
    from ..store.paths import data_dir

    d = data_dir() / "eval" / "realism_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cached(name: str, build):
    """Datasets are deterministic: cache them on disk keyed by the generator hash, so a crashed or resumed run does not rebuild them."""
    import pickle

    path = _cache_dir() / f"{name}_{generator_sha256()[:10]}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:      # a partial file from an interrupted write
            path.unlink(missing_ok=True)
    obj = build()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(path)
    return obj


def _make_ww(args) -> WW:
    family, role, k, n, days = args

    def build() -> WW:
        seed = seed_for(family, role, k, "workweeks")
        w = generate_workweeks(family, role, n_people=n, n_days=days, seed=seed)
        eps = w.episodes()
        by: dict[str, list] = {}
        for e in eps:
            by.setdefault(e.person, []).append(e)
        chk = MG.label_checks(w, eps)
        return WW(family, role, k, seed, by, dict(w.labels), chk, w.hyper, dict(w.truth["counts"]))

    return _cached(f"ww_{role}_{family}_{k}_{n}_{days}", build)


def _make_coh(args) -> Coh:
    family, role, k, n, cases = args

    def build() -> Coh:
        seed = seed_for(family, role, k, "cohort")
        c = generate_cohort(family, role, n_people=n, cases_per_person=cases, seed=seed)
        eps = c.episodes()
        checks = MG.cohort_checks(c) + MG.structure_checks(c) + MG.label_checks(c, eps)
        t = c.truth
        slim = {"traces": [{k_: v for k_, v in tr.items() if k_ not in ("cogs", "strategy")} for tr in t["traces"]], "deficit_types": t["deficit_types"], "role": t["role"],
                "counts": t["counts"], "n_experts": t["n_experts"], "n_novices": t["n_novices"]}
        return Coh(family, role, k, seed, eps, dict(c.levels), slim, checks, c.hyper)

    return _cached(f"coh_{role}_{family}_{k}_{n}_{cases}", build)


def _pmap(fn, items, workers: int, log=None, label: str = ""):
    """Ordered parallel map in forked processes; logs progress (completed / total) when ``log`` is given."""
    if workers <= 1 or len(items) <= 1:
        out = []
        for i, it in enumerate(items):
            out.append(fn(it))
            if log and (i + 1) % max(1, len(items) // 10) == 0:
                log(f"realism: {label} {i + 1}/{len(items)}")
        return out
    import multiprocessing as mp
    from concurrent.futures import as_completed

    results: list = [None] * len(items)
    # "spawn" is safe from inside a process that has already used BLAS (a forked child segfaults in the matrix multiply on macOS);
    # the long CLI run sets UNDERSTUDY_REALISM_FORK=1 from a clean parent for speed.
    method = "fork" if os.environ.get("UNDERSTUDY_REALISM_FORK") == "1" else "spawn"
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context(method)) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        done = 0
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()
            done += 1
            if log and (done % max(1, len(items) // 10) == 0 or done == len(items)):
                log(f"realism: {label} {done}/{len(items)}")
    return results


# ------------------------------------------------------------------------------------------ aggregation
def _people_arrays(rows: dict[str, dict], keys: list[str]) -> tuple[list[str], dict[str, np.ndarray]]:
    people = sorted(rows)
    return people, {k: np.array([rows[p][k] for p in people], dtype=float) for k in keys}


def _avg(lst: list[dict]) -> dict:
    out = {}
    for k in lst[0]:
        v = [d[k] for d in lst]
        out[k] = np.mean(v, axis=0) if isinstance(v[0], np.ndarray) else float(np.mean(v))
    return out


def _collapse(rows_by_person: dict[str, list[dict]]) -> dict[str, dict]:
    return {p: _avg(v) for p, v in rows_by_person.items()}


HZ_KEYS = ["n_bins", "y_rate", "ll_full", "ll_tsp", "ll_base", "brier_full", "fa", "non_h", "n_ev", "det", "hours", "alarms"]


def hz_metrics(a: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, tuple[float, np.ndarray]]:
    h1 = a["ll_tsp"] - a["ll_full"]
    return {
        "h1": (point_mean(h1), mean_draws(h1, idx)),
        "ll_full": (point_mean(a["ll_full"]), mean_draws(a["ll_full"], idx)),
        "ll_tsp": (point_mean(a["ll_tsp"]), mean_draws(a["ll_tsp"], idx)),
        "ll_base": (point_mean(a["ll_base"]), mean_draws(a["ll_base"], idx)),
        "brier": (point_mean(a["brier_full"]), mean_draws(a["brier_full"], idx)),
        "fa_per_h": (point_ratio(a["fa"], a["non_h"]), ratio_draws(a["fa"], a["non_h"], idx)),
        "detection": (point_ratio(a["det"], a["n_ev"]), ratio_draws(a["det"], a["n_ev"], idx)),
        "label_rate": (point_mean(a["y_rate"]), mean_draws(a["y_rate"], idx)),
    }


GN_KEYS = ["tp", "fp", "fn", "tn", "n_present", "rec_present", "inj_present", "n_absent", "attr_absent", "n_indet", "gap_s", "cases"]


def gn_metrics(a: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, tuple[float, np.ndarray]]:
    tp, fp, fn = a["tp"].sum(axis=1), a["fp"].sum(axis=1), a["fn"].sum(axis=1)
    out = {
        "precision": (point_ratio(tp, tp + fp), ratio_draws(tp, tp + fp, idx)),
        "recall": (point_ratio(tp, tp + fn), ratio_draws(tp, tp + fn, idx)),
        "gap_s": (point_ratio(a["gap_s"], a["cases"]), ratio_draws(a["gap_s"], a["cases"], idx)),
        "false_attr_s": (point_ratio(a["attr_absent"].sum(axis=1), a["n_absent"].sum(axis=1)), ratio_draws(a["attr_absent"].sum(axis=1), a["n_absent"].sum(axis=1), idx)),
    }
    for i, d in enumerate(EG.DEFICITS):
        out[f"precision:{d}"] = (point_ratio(a["tp"][:, i], a["tp"][:, i] + a["fp"][:, i]), ratio_draws(a["tp"][:, i], a["tp"][:, i] + a["fp"][:, i], idx))
        out[f"recall:{d}"] = (point_ratio(a["tp"][:, i], a["tp"][:, i] + a["fn"][:, i]), ratio_draws(a["tp"][:, i], a["tp"][:, i] + a["fn"][:, i], idx))
        out[f"bias_s:{d}"] = (point_ratio(a["rec_present"][:, i] - a["inj_present"][:, i], a["n_present"][:, i]),
                              ratio_draws(a["rec_present"][:, i] - a["inj_present"][:, i], a["n_present"][:, i], idx))
        out[f"n_present:{d}"] = (float(a["n_present"][:, i].sum()), np.array([np.nan]))
    out["n_present"] = (float(a["n_present"].sum()), np.array([np.nan]))
    out["n_absent"] = (float(a["n_absent"].sum()), np.array([np.nan]))
    out["n_indeterminate"] = (float(a["n_indet"].sum()), np.array([np.nan]))
    return out


RT_KEYS = ["clusters", "true", "detectable", "found", "planted", "episodes", "proposals", "proposals_true"]


def rt_metrics(a: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, tuple[float, np.ndarray]]:
    return {
        "r1_precision": (point_ratio(a["true"], a["clusters"]), ratio_draws(a["true"], a["clusters"], idx)),
        "r2_recall": (point_ratio(a["found"], a["detectable"]), ratio_draws(a["found"], a["detectable"], idx)),
        "r3_proposal_precision": (point_ratio(a["proposals_true"], a["proposals"]), ratio_draws(a["proposals_true"], a["proposals"], idx)),
        "clusters_per_person": (point_mean(a["clusters"]), mean_draws(a["clusters"], idx)),
        "proposals_per_person": (point_mean(a["proposals"]), mean_draws(a["proposals"], idx)),
    }


def cell_stats(rows: dict[str, dict], diag: dict[str, dict] | None, keys: list[str], fn, B: int, seed: int, deltas: dict[str, tuple[float, bool]],
               rep_of: dict[str, int] | None = None) -> dict[str, Any]:
    """Estimates with person-cluster intervals; paired deltas against the diagonal on the same people; replicate SD."""
    people, arr = _people_arrays(rows, keys)
    idx = boot_idx(len(people), B, seed)
    m = fn(arr, idx)
    out: dict[str, Any] = {"n_people": len(people), "metrics": {k: est(v[0], v[1]) for k, v in m.items()}}
    if diag is not None:
        assert sorted(diag) == people, "paired cells need the same test people"
        _, arr0 = _people_arrays(diag, keys)
        m0 = fn(arr0, idx)
        dl: dict[str, Any] = {}
        for name, (margin, hib) in deltas.items():
            d = m[name][0] - m0[name][0]
            dd = m[name][1] - m0[name][1]
            ci = interval(dd)
            dl[name] = {"est": rnd(d), "ci": ci, "verdict": verdict(d, ci, margin, hib)}
        out["delta_vs_diagonal"] = dl
    if rep_of:
        reps = sorted(set(rep_of.values()))
        per: dict[str, list[float]] = {}
        for r in reps:
            sub = {p: rows[p] for p in people if rep_of.get(p) == r}
            if len(sub) < 2:
                continue
            _, a = _people_arrays(sub, keys)
            mm = fn(a, np.arange(len(sub))[None, :])
            for name in deltas:
                per.setdefault(name, []).append(float(mm[name][0]))
        out["replicate_sd"] = {n: sd_across(v) for n, v in per.items()}
        out["replicate_values"] = {n: [rnd(x) for x in v] for n, v in per.items()}
    return out


# ------------------------------------------------------------------------------------------ the three matrices
def _fit_apply_hazard(args):
    X, k, eps_train, tests = args
    rule = EH.fit_rule(eps_train)
    return X, k, {Y: EH.apply_rule(rule, eps) for Y, eps in tests.items()}, rule.cfg


def hazard_matrix(role: str, ww: dict[tuple[str, int], WW], v1, cfg: Config, log) -> dict:
    K = cfg.K
    fams = FAMS
    has_v1 = v1 is not None and role == "benefits-processor"
    v1_all = [e for es in v1.persona_eps.values() for e in es] if has_v1 else None
    rep_of: dict[str, dict[str, int]] = {Y: {p: r for r in range(K) for p in ww[(Y, r)].persons} for Y in fams}
    jobs = []
    for X in fams:
        for k in range(K):
            tests = {Y: [e for es in ww[(Y, (k + 1) % K)].persons.values() for e in es] for Y in fams}
            if has_v1:
                tests["v1"] = v1_all
            jobs.append((X, k, [e for es in ww[(X, k)].persons.values() for e in es], tests))
    if has_v1:      # the v1-trained rule does not depend on k: it is tested on every replicate of each family
        jobs.append(("v1", 0, v1_all, {Y: [e for r in range(K) for es in ww[(Y, r)].persons.values() for e in es] for Y in fams}))
    results = _pmap(_fit_apply_hazard, jobs, cfg.workers, log, f"hazard {role} fits")
    cells: dict[tuple[str, str], dict[str, list[dict]]] = {}
    alarm_cfg: dict[tuple[str, str], list[dict]] = {}
    for X, k, per_y, acfg in results:
        for Y, per in per_y.items():
            for person, d in per.items():
                cells.setdefault((X, Y), {}).setdefault(person, []).append(d)
            alarm_cfg.setdefault((X, Y), []).append({"threshold": rnd(acfg["threshold"]), "confirm_bins": acfg["confirm_bins"], "budget_met": acfg["budget_met"]})
    if has_v1:      # v1 diagonal: leave one persona out
        cells[("v1", "v1")] = {p: [d] for p, d in EH.lopo_cells(v1.persona_eps).items()}
    out: dict[str, Any] = {"cells": {}, "alarm_rules": {f"{X}->{Y}": v for (X, Y), v in alarm_cfg.items()}}
    ys = fams + (("v1",) if has_v1 else ())
    for Y in ys:
        diag = _collapse(cells[(Y, Y)])
        for X in ys:
            rows = _collapse(cells[(X, Y)])
            st = cell_stats(rows, None if X == Y else diag, HZ_KEYS, hz_metrics, cfg.B, 1000 + 7 * ALL.index(Y),
                            {"h1": (MARGIN["h1"], True), "detection": (0.1, True), "fa_per_h": (0.25, False)}, rep_of.get(Y))
            st["n_bins"] = int(sum(r["n_bins"] for r in rows.values()))
            st["origin"] = f"generated ({X} fit, {Y} test)"
            h1 = st["metrics"]["h1"]
            st["no_skill"] = bool(h1["ci"][0] is None or h1["ci"][0] <= 0)
            st["fa_over_budget"] = bool(st["metrics"]["fa_per_h"]["ci"][0] is not None and st["metrics"]["fa_per_h"]["ci"][0] > EH.BUDGET)
            out["cells"][f"{X}->{Y}"] = st
    return out


def _genome_task(args):
    key, ex_eps, ex_levels, X_thr, nov_eps, nov_levels, truth_Y = args
    from ..genome import Cohort

    co_x = Cohort(ex_eps, ex_levels)
    co_y = Cohort(nov_eps, nov_levels)
    return key, EG.score_cell(co_x, X_thr, co_y, truth_Y)


def _placebo_task(args):
    key, eps, levels, truth = args
    from ..genome import Cohort

    co = Cohort(eps, levels)
    X, mx = EG.placebo_thresholds(co)
    return key, X, mx, EG.expert_contamination(co, truth)


def genome_matrix(coh: dict[tuple[str, int], Coh], v1, cfg: Config, log) -> dict:
    K = cfg.K
    keep = cfg.genome_cases

    def split(c: Coh):
        case_of = {t["task_id"]: t["case"] for t in c.truth["traces"]}
        eps = [e for e in c.episodes if case_of.get(e.task_id, 10 ** 9) <= keep]
        ex = [e for e in eps if c.levels[e.person] == "expert"]
        nv = [e for e in eps if c.levels[e.person] == "novice"]
        return ex, nv

    spl = {key: split(c) for key, c in coh.items()}
    pjobs, gjobs = [], []
    for (X, k), c in coh.items():
        ex, nv = spl[(X, k)]
        lv = {e.person: c.levels[e.person] for e in ex + nv}
        pjobs.append(((X, k), ex + nv, lv, c.truth))
    v1_ex = v1_nv = v1_lv = None
    if v1 is not None:
        co = v1.cohort
        v1_ex, v1_nv = list(co.experts), list(co.novices)
        v1_lv = dict(co.levels)
        pjobs.append((("v1", 0), v1_ex + v1_nv, {e.person: v1_lv[e.person] for e in v1_ex + v1_nv}, v1.truth))
    placebo = {key: (X, mx, cont) for key, X, mx, cont in _pmap(_placebo_task, pjobs, cfg.workers, log, "genome placebo")}

    def ex_pack(X, k):
        if X == "v1":
            return v1_ex, {e.person: "expert" for e in v1_ex}, placebo[("v1", 0)][0]
        ex, _ = spl[(X, k)]
        return ex, {e.person: "expert" for e in ex}, placebo[(X, k)][0]

    def nv_pack(Y, k):
        if Y == "v1":
            return v1_nv, {e.person: "novice" for e in v1_nv}, v1.truth
        _, nv = spl[(Y, k % K)]
        c = coh[(Y, k % K)]
        return nv, {e.person: "novice" for e in nv}, c.truth

    for X in ALL if v1 is not None else FAMS:
        for Y in ALL if v1 is not None else FAMS:
            ks = [0] if (X == "v1" and Y == "v1") else range(K)
            for k in ks:
                ex, exl, thr = ex_pack(X, k)
                # train replicate k of X is scored on the NEXT replicate of Y (an independent draw even on the diagonal);
                # v1 as the training family has one fit and is scored on every replicate of Y
                kk = k if X == "v1" else (k + 1) % K
                nv, nvl, tr = nv_pack(Y, kk)
                gjobs.append(((X, Y, kk), ex, exl, thr, nv, nvl, tr))
    res = _pmap(_genome_task, gjobs, cfg.workers, log, "genome cells")
    cells: dict[tuple[str, str], dict[str, list[dict]]] = {}
    rep_of: dict[str, dict[str, int]] = {}
    for (X, Y, kk), per in res:
        for person, d in per.items():
            cells.setdefault((X, Y), {}).setdefault(person, []).append(d)
            if Y != "v1":
                rep_of.setdefault(Y, {})[person] = kk
    out: dict[str, Any] = {"cells": {}, "placebo": {}, "thresholds_s": {}}
    for (name, k), (X, mx, cont) in placebo.items():
        out["placebo"][f"{name}:{k}"] = {"max_attribution_s": {d: rnd(v, 2) for d, v in mx.items()}, "expert_contamination": rnd(cont)}
        out["thresholds_s"][f"{name}:{k}"] = {d: rnd(v, 2) for d, v in X.items()}
    ys = ALL if v1 is not None else FAMS
    for Y in ys:
        diag = _collapse(cells[(Y, Y)])
        for X in ys:
            rows = _collapse(cells[(X, Y)])
            st = cell_stats(rows, None if X == Y else diag, GN_KEYS, gn_metrics, cfg.B, 2000 + 7 * ALL.index(Y),
                            {"precision": (MARGIN["g1"], True), "recall": (MARGIN["g1"], True)}, rep_of.get(Y))
            st["origin"] = f"generated ({X} references and thresholds, {Y} test)"
            out["cells"][f"{X}->{Y}"] = st
    return out


def _route_task(args):
    key, eps, labels, thresholds = args
    return key, {t: ER.score_person(eps, labels, t) for t in thresholds}


def _prop_task(args):
    key, eps, labels, role, person, draws = args
    from ..memory.packinfo import load_pack

    return key, ER.score_proposals(eps, labels, load_pack(role), person, draws)


def routines_matrix(role: str, ww: dict[tuple[str, int], WW], v1, cfg: Config, log) -> dict:
    K = cfg.K
    persons: dict[tuple[str, int], dict[str, list]] = {k: w.persons for k, w in ww.items()}
    labels: dict[tuple[str, int], dict[str, str]] = {k: w.labels for k, w in ww.items()}
    if v1 is not None and role == "benefits-processor":
        persons[("v1", 0)] = v1.persona_eps
    def labs(key, person, eps):
        lab = labels.get(key)
        full = lab if lab is not None else v1.persona_labels[person]
        return {e.task_id: full[e.task_id] for e in eps if e.task_id in full}

    jobs = [((key, person), eps, labs(key, person, eps), cfg.grid) for key, pp in persons.items() for person, eps in pp.items()]
    sc: dict[tuple, dict] = {}
    for (key, person), per_t in _pmap(_route_task, jobs, cfg.workers, log, f"routines {role} finder"):
        for t, v in per_t.items():
            sc[(key, person, t)] = v
    prop = {}
    if cfg.proposals:
        pj = [((key, person), eps, labs(key, person, eps), role, person, 600 if cfg.fast else 1000) for key, pp in persons.items() for person, eps in pp.items()]
        prop = dict(_pmap(_prop_task, pj, cfg.workers, log, f"routines {role} proposals"))

    def person_row(key, person, t) -> dict:
        r = dict(sc[(key, person, t)])
        p = prop.get((key, person), {"proposals": 0, "proposals_true": 0})
        r.update({"proposals": p["proposals"], "proposals_true": p["proposals_true"]})
        return r

    tuned: dict[tuple[str, int], tuple[float, dict]] = {}
    for key, pp in persons.items():
        tuned[key] = ER.choose_threshold({t: [sc[(key, person, t)] for person in pp] for t in cfg.grid})
    fams = FAMS + (("v1",) if "v1" in {k[0] for k in persons} else ())
    out: dict[str, Any] = {"cells": {}, "tuned_threshold": {f"{k[0]}:{k[1]}": rnd(v[0], 2) for k, v in tuned.items()},
                           "f1_by_threshold": {f"{k[0]}:{k[1]}": {str(t): rnd(f) for t, f in v[1].items()} for k, v in tuned.items()}}
    for fit_mode in ("fitted", "shipped"):
        cells: dict[tuple[str, str], dict[str, list[dict]]] = {}
        rep_of: dict[str, dict[str, int]] = {}
        for X in fams:
            for Y in fams:
                ks = [0] if X == "v1" and Y == "v1" else range(K)
                for k in ks:
                    xk = ("v1", 0) if X == "v1" else (X, k)
                    yk = ("v1", 0) if Y == "v1" else (Y, (k + 1) % K)
                    if X == "v1" and Y == "v1":
                        # v1 diagonal: tune on three personas, test on the fourth
                        ps = sorted(persons[yk])
                        for q in ps:
                            rest = {t: [sc[(yk, p, t)] for p in ps if p != q] for t in cfg.grid}
                            thr = ER.choose_threshold(rest)[0] if fit_mode == "fitted" else ER.DEFAULT_T
                            cells.setdefault((X, Y), {}).setdefault(q, []).append(person_row(yk, q, thr))
                        continue
                    thr = tuned[xk][0] if fit_mode == "fitted" else ER.DEFAULT_T
                    for q in persons[yk]:
                        cells.setdefault((X, Y), {}).setdefault(q, []).append(person_row(yk, q, thr))
                        if Y != "v1":
                            rep_of.setdefault(Y, {})[q] = yk[1]
        for Y in fams:
            diag = _collapse(cells[(Y, Y)])
            for X in fams:
                rows = _collapse(cells[(X, Y)])
                st = cell_stats(rows, None if X == Y else diag, RT_KEYS, rt_metrics, cfg.B, 3000 + 7 * ALL.index(Y),
                                {"r1_precision": (MARGIN["r"], True), "r2_recall": (MARGIN["r"], True)}, rep_of.get(Y))
                st["origin"] = f"generated ({X} fit, {Y} test)"
                out["cells"][f"{fit_mode}:{X}->{Y}"] = st
    return out


# ------------------------------------------------------------------------------------------ run
def _blocks_dir() -> Path:
    from ..store.paths import data_dir

    d = data_dir() / "eval" / "realism_blocks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _block(name: str, role: str, fn, cfg: Config, resume: bool, log):
    """Run one block of the matrix (or load it when resuming) and write it to disk as soon as it is done."""
    path = _blocks_dir() / f"{'fast_' if cfg.fast else ''}{name}_{role}.json"
    if resume and path.exists():
        log(f"realism: {name} {role} loaded from {path.name}")
        return json.loads(path.read_text())
    t = time.time()
    res = fn()
    path.write_text(json.dumps({"origin": "synthetic", "badge": BADGE, "block": name, "role": role, "generator_sha256": generator_sha256(),
                                "params_sha256": params_sha256(), "partial": False, "result": res}, indent=1,
                               default=lambda o: None if o != o else str(o)))
    log(f"realism: BLOCK {name} {role} done in {time.time() - t:.0f}s -> {path}")
    return json.loads(path.read_text())


def run(cfg: Config, log=print, resume: bool = False) -> dict[str, Any]:
    t0 = time.time()
    log(f"realism: building datasets (workers {cfg.workers}, roles {len(cfg.roles)}, K {cfg.K})")
    ww_jobs = [(f, r, k, cfg.n_ww, cfg.days) for r in cfg.roles for f in FAMS for k in range(cfg.K)]
    coh_jobs = [(f, r, k, cfg.n_coh, cfg.cases) for r in cfg.roles for f in FAMS for k in range(cfg.K)]
    ww_all = _pmap(_make_ww, ww_jobs, cfg.workers, log, "workweek datasets")
    coh_all = _pmap(_make_coh, coh_jobs, cfg.workers, log, "cohort datasets")
    WWs = {(w.role, w.family, w.rep): w for w in ww_all}
    COHs = {(c.role, c.family, c.rep): c for c in coh_all}
    log(f"realism: datasets built in {time.time() - t0:.0f}s")
    v1 = None
    if cfg.with_v1:
        from .v1data import load_v1

        v1 = load_v1()
        log(f"realism: v1 data ready at {time.time() - t0:.0f}s")

    result: dict[str, Any] = {"hazard": {}, "genome": {}, "routines": {}}
    wr = lambda role: {(f, k): WWs[(role, f, k)] for f in FAMS for k in range(cfg.K)}      # noqa: E731
    for role in cfg.roles:
        result["hazard"][role] = _block("hazard", role, lambda role=role: hazard_matrix(role, wr(role), v1, cfg, log), cfg, resume, log)["result"]
    for role in cfg.roles:
        result["routines"][role] = _block("routines", role, lambda role=role: routines_matrix(role, wr(role), v1, cfg, log), cfg, resume, log)["result"]
    for role in cfg.roles:
        if role == "benefits-processor":
            cr = {(f, k): COHs[(role, f, k)] for f in FAMS for k in range(cfg.K)}
            result["genome"][role] = _block("genome", role, lambda cr=cr: genome_matrix(cr, v1, cfg, log), cfg, resume, log)["result"]
    result["marginals"] = {
        "cohort": MG.summarise({f"{c.role}|{c.family}|{c.rep}": c.checks for c in coh_all}),
        "by_family": {f: MG.summarise({f"{c.role}|{c.family}|{c.rep}": c.checks for c in coh_all if c.family == f}) for f in FAMS},
        "workweeks_label": MG.summarise({f"{w.role}|{w.family}|{w.rep}": w.label_checks for w in ww_all}),
    }
    result["datasets"] = {
        "workweeks": [{"role": w.role, "family": w.family, "replicate": w.rep, "seed": w.seed, "people": len(w.persons), "episodes": sum(len(v) for v in w.persons.values()),
                       "routine_tasks": w.counts.get("routine_tasks"), "tasks": w.counts.get("tasks")} for w in ww_all],
        "cohort": [{"role": c.role, "family": c.family, "replicate": c.rep, "seed": c.seed, "people": len(c.levels), "episodes": len(c.episodes),
                    "experts": c.truth["n_experts"], "novices": c.truth["n_novices"]} for c in coh_all],
    }
    result["elapsed_s"] = round(time.time() - t0, 1)
    return result


def _meta(cfg: Config, n_people: int) -> dict[str, Any]:
    return {"origin": "synthetic", "badge": BADGE, "n": n_people, "n_unit": "people",
            "split": ("fit on a replicate of family X, test on an independent replicate of family Y, every ordered pair; diagonal = independent draw of the same family; "
                      "person-cluster bootstrap"),
            "interval_level": 0.95,
            "note": ("Generated, realism-calibrated. Marginals sit inside cited ranges where a constant was found; this does not show the data match real users, "
                     "and the generators are written by the same team." + (" FAST MODE: small n, one role, v1 omitted." if cfg.fast else ""))}


LIMITATIONS = [
    {"id": "realism-synthetic", "severity": "high",
     "text": "Every number here comes from generators we wrote. The v2 families have marginals inside cited ranges, but nothing shows they match real people; the live study (n = 4) and an optional labelled pilot are the only evidence about real people."},
    {"id": "realism-shared-parts", "severity": "medium",
     "text": "The three v2 families share the person hierarchy, the interruption process, the event emitter and noise model, the role vocabulary and the task grammar's valid paths. A family with less shared code would be a stronger test."},
    {"id": "realism-label-circularity", "severity": "medium",
     "text": "The hazard label is a point process driven by hidden stuck episodes, not an emission table, but both behaviour and label come from the same hidden state: the circularity is reduced, not removed."},
    {"id": "realism-citations", "severity": "medium",
     "text": "Published ranges were read from search-result summaries; primary papers were not opened. Hick-Hyman slope, circadian amplitude and warm-up are unverified wide assumptions."},
    {"id": "realism-calibration", "severity": "low",
     "text": "Deficit prevalence and stuck-episode rates were calibrated once to structural plausibility targets (S1 to S6) before any analytic was run; the families still differ a lot in prevalence."},
]


def assemble(cfg: Config, res: dict[str, Any]) -> dict[str, Any]:
    from .cited import CITED, status_counts

    n_people = cfg.n_ww * cfg.K * len(FAMS) * len(cfg.roles)
    out = {
        "name": "realism", "meta": _meta(cfg, n_people), "origin": "synthetic", "badge": BADGE,
        "generator": {"params_sha256": params_sha256(), "generator_sha256": generator_sha256(), "families": list(FAMS), "roles": list(cfg.roles),
                      "plan": "evals/realism/PLAN.md", "cited_status_counts": status_counts()},
        "config": {"fast": cfg.fast, "K": cfg.K, "n_workweek_people": cfg.n_ww, "workweek_days": cfg.days, "n_cohort_people": cfg.n_coh, "cases_per_person": cfg.cases,
                   "genome_cases_per_person": cfg.genome_cases, "bootstrap_B": cfg.B, "routine_grid": list(cfg.grid), "with_v1": cfg.with_v1,
                   "proposals": cfg.proposals, "margins": MARGIN},
        "results": res,
        "cited_constants": {k: {"status": v["status"], "range": list(v["range"]) if v.get("range") else None, "source": v["source"], "note": v.get("note", "")} for k, v in CITED.items()},
    }
    out["limitations"] = LIMITATIONS
    out["deviations"] = DEVIATIONS
    return out


DEVIATIONS = [
    "Hazard leave-one-person-out diagnostics (the public `evaluate_hazard`) were run for the benefits role only, on the first 16 people of replicate 0 of each family and on v1's four personas, because the nested leave-one-out costs people squared fits per variant; the plan said each family and role. The matrix itself (train on replicate k, test on replicate k + 1) covers every role.",
    "The genome uses the first 2 cases per person (as planned) and runs for the benefits role only (as planned: the named-deficit labels are benefits-specific).",
    "Routine proposals after the value gate (R3) are scored at the shipped finder config only; the finder cut height is fitted for R1 and R2.",
    "v1 as the training family has a single fit; it is tested on every replicate of each v2 family. v1 as the test family has four personas (hazard, routines) or 16 novices and 8 experts (genome); its diagonal is leave-one-persona-out (hazard, routines) or the apprentices' own expert-novice split (genome), because no independent v1 draw exists.",
    "Interpretation rule additions: when a delta interval lies entirely on the beneficial side but outside the margin, the pre-registered rule says inconclusive; the tables add '(better than the diagonal)' beside it for readability without changing the verdict.",
    "Fast mode (`evaluate_realism(fast=True)`) uses K = 2 replicates of 14 people (the plan said one replicate, which cannot give an independent test replicate), benefits role only, no v1, serial by default; it is a smoke-level section with the same metrics, not the matrix.",
    "The first full run was stopped after about 35 minutes (it had computed no analytic) so that the matrix could be rerun with a dataset cache and blocks written to disk as they finish, as the lead asked; generators and analyses were unchanged. The rerun saved every block and then stopped at the final assembly step because of a bug of mine (an accidentally deleted function); the report was assembled with `--resume` from the saved blocks and cached datasets.",
    "The thin role packs (data analyst, programmer) were extended by another track after the generators were frozen; v2 emits the original seven pack cogs per thin role, so it does not exercise the new cogs.",
    "The `markov` family draws hesitation pauses only through freezes and quiet stalls, so its pause-tail check (M3) is outside the cited range in 3 of the 5 datasets where it can be measured; the family was not changed after the freeze.",
    "No generator parameter, range or code was changed after PLAN.md was frozen (the report prints the two hashes and flags a mismatch).",
]


def lopo_diagnostics(cfg: Config) -> dict[str, Any]:
    """The public `evaluate_hazard` (leave one person out, nested threshold choice) on 16 people per family, and on v1's four personas."""
    from ..hazard import evaluate_hazard

    out: dict[str, Any] = {}
    role = "benefits-processor"
    for fam in FAMS:
        w = _make_ww((fam, role, 0, cfg.n_ww, cfg.days))
        people = sorted(w.persons)[:16]
        eps = [e for p in people for e in w.persons[p]]
        out[fam] = _lopo_row(evaluate_hazard(eps, n_boot=200, include_series=False), len(people))
    if cfg.with_v1:
        from .v1data import load_v1

        v1 = load_v1()
        eps = [e for es in v1.persona_eps.values() for e in es]
        out["v1"] = _lopo_row(evaluate_hazard(eps, n_boot=200, include_series=False, planted=v1.planted), len(v1.persona_eps))
    return out


def _lopo_row(r: dict, n: int) -> dict:
    ev = r["model"]["events"]
    return {"n_people": n, "n_bins": r["n_bins"], "n_stuck_bins": r["n_stuck_bins"], "label_rate": rnd(r["n_stuck_bins"] / max(1, r["n_bins"])),
            "ll_full": est(r["model"]["log_loss"], np.array(r["model"]["ci_log_loss"])), "ll_tsp": est(r["baselines"]["time_since_progress"]["log_loss"], np.array(r["baselines"]["time_since_progress"]["ci_log_loss"])),
            "ll_base": est(r["baselines"]["base_rate"]["log_loss"], np.array(r["baselines"]["base_rate"]["ci_log_loss"])),
            "gain_over_tsp": {"est": rnd(-r["model_minus_tsp_log_loss"]), "ci": [rnd(-r["model_minus_tsp_log_loss_ci"][1]), rnd(-r["model_minus_tsp_log_loss_ci"][0])]},
            "fa_per_h": {"est": rnd(ev.get("false_alarms_per_hour")), "ci": [rnd(x) for x in (ev.get("false_alarms_per_hour_ci") or [None, None])]},
            "detection": {"est": rnd(ev.get("detection_rate")), "ci": [rnd(x) for x in (ev.get("detection_rate_ci") or [None, None])]},
            "within_budget": r["false_alarms_within_budget"], "note": "episode-cluster intervals from the public function (they do not capture person-to-person variation)"}


def evaluate_realism(fast: bool = True) -> dict[str, Any]:
    """Eval-harness section: the generator-mismatch matrix over v2 families (fast mode: small n, one role, no v1, under 60 s)."""
    cfg = Config.make(fast=fast)
    res = run(cfg, log=lambda *_: None)
    sec = assemble(cfg, res)
    sec["rows"] = headline_rows(res)
    sec["caveats"] = [l["text"] for l in LIMITATIONS]
    return sec


def headline_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for role, hz in res["hazard"].items():
        for key, st in hz["cells"].items():
            X, Y = key.split("->")
            rows.append({"analytic": "hazard", "role": role, "fit": X, "test": Y, "h1": st["metrics"]["h1"], "fa_per_h": st["metrics"]["fa_per_h"],
                         "verdict": (st.get("delta_vs_diagonal") or {}).get("h1", {}).get("verdict")})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--full", action="store_true")
    g.add_argument("--fast", action="store_true")
    g.add_argument("--lopo", action="store_true", help="only the leave-one-person-out diagnostics; writes data/eval/realism_lopo.json")
    g.add_argument("--render", action="store_true", help="re-render REPORT.md from data/eval/realism.json (and realism_lopo.json)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--resume", action="store_true", help="reuse blocks already written to data/eval/realism_blocks")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args(argv)
    from ..store.paths import data_dir, repo_root
    from .report import write_report

    root = repo_root()
    if a.lopo or a.render:
        jp = data_dir() / "eval" / "realism.json"
        lp = data_dir() / "eval" / "realism_lopo.json"
        if a.lopo:
            cfg = Config.make(fast=False, workers=a.workers)
            lp.write_text(json.dumps(lopo_diagnostics(cfg), indent=1))
            print(f"wrote {lp}", file=sys.stderr)
            return 0
        sec = json.loads(jp.read_text())
        if lp.exists():
            sec["results"]["lopo"] = json.loads(lp.read_text())
        sec["deviations"] = DEVIATIONS
        mp = Path(a.out_md) if a.out_md else root / "evals" / "realism" / "REPORT.md"
        mp.write_text(write_report(sec))
        jp.write_text(json.dumps(sec, indent=1, default=lambda o: None if o != o else str(o)))
        print(f"re-rendered {mp}", file=sys.stderr)
        return 0
    cfg = Config.make(fast=a.fast, workers=a.workers)
    res = run(cfg, log=lambda m: print(m, file=sys.stderr, flush=True), resume=a.resume)
    sec = assemble(cfg, res)
    jp = Path(a.out_json) if a.out_json else data_dir() / "eval" / ("realism_fast.json" if cfg.fast else "realism.json")
    mp = Path(a.out_md) if a.out_md else root / "evals" / "realism" / ("REPORT_fast.md" if cfg.fast else "REPORT.md")
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(sec, indent=1, default=lambda o: None if o != o else str(o)))
    mp.write_text(write_report(sec))
    print(f"wrote {jp} and {mp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
