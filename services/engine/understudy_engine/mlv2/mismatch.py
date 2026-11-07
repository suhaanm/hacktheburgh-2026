"""M6: generator mismatch (PLAN.md section 6.8). Fit on generator family X, test on family Y, every ordered pair, per role.

The three families come from the REALISM track (``understudy_engine.personas_v2.generate_cohort``: markov, latent_skill, process_trace); this module
only calls it. Per role and family: a training cohort of 40 people and an independent test cohort of 40 people (seeds in PLAN.md section 3). Every
variant is trained on the whole X training cohort (calibrators, personal-shift prior and alarm thresholds from grouped 5-fold out-of-fold
predictions inside X) and scores the Y test cohort, so v1 and the variants see identical bins and are compared pairwise with person-cluster
intervals (people of the test cohort).

Decision (per role): a variant must (a) pass the section 6 test on the held-out persona replicates (combined by the caller), (b) pass the POOLED
off-diagonal test (mean of the six mismatch cells' paired differences, test people resampled per family, one test per role at the family's level)
with every guard non-inferior, and (c) not be harmful in any single mismatch cell (Bonferroni, m = 6). A gain that disappears under mismatch is a null.
"""
from __future__ import annotations

import os
import pickle
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from understudy_engine.hazard.features import BinTable, build_bins
from understudy_engine.mlv2.alarms import Layout, build_layout, person_event_counts
from understudy_engine.mlv2.conformal import make_c0_rule, make_c1_rule, make_c2_rule
from understudy_engine.mlv2.family_a import GUARDS, PRIMARY_METRIC, FamilyARun, compare_family_a
from understudy_engine.mlv2.family_c import GUARD_DETECTION_MARGIN, FamilyCRun, compare_family_c
from understudy_engine.mlv2.models import (
    A7_CANDIDATES, BASELINE_SPECS, FAMILY_A, LEARNERS, Calibrator, VariantSpec, apply_personal_shift, fit_beta_prior_people,
)
from understudy_engine.mlv2.protocol import DEFAULT_BUDGET, VariantOutput, inner_assignments
from understudy_engine.mlv2.splits import HELDOUT_ENV, HeldOutLocked
from understudy_engine.mlv2.stats import (
    Clusters, EventCounts, adjusted_level, boot_multiplicities, event_draws, event_points, interval, metric_draws, metric_points, score_parts,
)

FAMILIES = ("markov", "latent_skill", "process_trace")
ROLES = ("benefits-processor", "data-analyst", "programmer")
N_PEOPLE = 40
CASES_PER_PERSON = 8              # gives 3800 to 11500 scored bins per cohort, above the plan's floor of 3000 (checked in the tests)
POOLS = ("MIS-DEV", "MIS-HELD", "MIS-RESERVE")
ORIGIN = "synthetic"


def seed_for(pool: str, family: str, split: str) -> int:
    base = {"MIS-DEV": 7100, "MIS-HELD": 8100, "MIS-RESERVE": 9100}[pool]
    return base + 10 * FAMILIES.index(family) + (0 if split == "train" else 1)


@dataclass
class TabBundle:
    family: str
    role: str
    seed: int
    tab: BinTable
    layout: Layout
    generator: dict | None = None      # params_sha256 and generator_sha256 of the REALISM generator that produced the cohort


def _cache_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_MLV2_CACHE")
    p = Path(env) if env else Path(tempfile.gettempdir()) / "understudy_mlv2_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_bundle(family: str, role: str, seed: int, *, n_people: int = N_PEOPLE, cases: int = CASES_PER_PERSON, cohort_fn=None, cache: bool = True) -> TabBundle:
    path = _cache_dir() / f"mis-{family}-{role}-{seed}-{n_people}-{cases}.pkl"
    if cache and cohort_fn is None and path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:  # noqa: BLE001
            pass
    if cohort_fn is None:
        from understudy_engine.personas_v2 import generate_cohort

        cohort_fn = generate_cohort
    coh = cohort_fn(family, role, n_people, cases, seed)
    tab = build_bins(coh.episodes())
    real = (getattr(coh, "truth", None) or {}).get("realism") or {}
    out = TabBundle(family, role, seed, tab, build_layout(tab), {k: real.get(k) for k in ("params_sha256", "generator_sha256")} if real else None)
    if cache and cohort_fn is not None and path.parent.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(out))
        os.replace(tmp, path)
    return out


def load_bundles(pool: str, role: str, *, cohort_fn=None) -> dict[tuple[str, str], TabBundle]:
    if pool in ("MIS-HELD", "MIS-RESERVE") and os.environ.get(HELDOUT_ENV, "").strip() != "1":
        raise HeldOutLocked(f"pool {pool} is held-out: set {HELDOUT_ENV}=1 and use the frozen command (PLAN.md section 5)")
    return {(f, s): make_bundle(f, role, seed_for(pool, f, s), cohort_fn=cohort_fn) for f in FAMILIES for s in ("train", "test")}


# --------------------------------------------------------------------------------------------- one row of the matrix
def _fit_base(train: BinTable, tests: dict[str, BinTable], key: str, inner_folds: int | None) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """(out-of-fold predictions on the training rows from grouped inner folds, predictions on each test table from one fit on all training rows)."""
    factory = LEARNERS[key]
    rows = np.arange(train.n)
    people = train.people
    p_in = np.full(train.n, np.nan)
    for g in inner_assignments(people, inner_folds):
        tr = train.rows_of([q for q in people if q not in g])
        te = train.rows_of(g)
        p_in[te] = factory().fit(train, tr).predict(train, te)
    model = factory().fit(train, rows)
    return p_in, {y: model.predict(t, np.arange(t.n)) for y, t in tests.items()}


def run_row(train: TabBundle, tests: dict[str, TabBundle], specs: dict[str, VariantSpec], *, rules: tuple[str, ...] = ("C0", "C1", "C2"),
            inner_folds: int | None = 5, budget: float = DEFAULT_BUDGET, n_boot_rule: int = 500) -> dict[str, dict[str, Any]]:
    """Train once on ``train`` (family X) and score every test cohort (family Y): probabilities for every spec, then the alarm rules on A0's
    probabilities. The training side (inner folds, calibrators, prior, thresholds) does not depend on the test cohort, so it is done once."""
    ttab = train.tab
    y = ttab.y.astype(float)
    keys = sorted({s.base for s in specs.values()})
    test_tabs = {yf: tb.tab for yf, tb in tests.items()}
    base = {k: _fit_base(ttab, test_tabs, k, inner_folds) for k in keys}
    eps_tr = np.arange(len(ttab.ep_person))
    eps_te_of = {yf: {q: np.array([e for e, pp in enumerate(tb.tab.ep_person) if pp == q]) for q in tb.tab.people} for yf, tb in tests.items()}

    def events_for(yf: str, p_te: np.ndarray, cfg: dict) -> EventCounts:
        etab, layout = tests[yf].tab, tests[yf].layout
        cols = {k: [] for k in ("n_events", "detected", "false_alarms", "true_alarms", "non_event_h", "total_h")}
        for q in etab.people:
            c = person_event_counts(layout, p_te, cfg["threshold"], cfg["confirm_bins"], eps_te_of[yf][q])
            for k in cols:
                cols[k].append(c[k])
        return EventCounts(**{k: np.array(v, dtype=float) for k, v in cols.items()}, thresholds=[cfg["threshold"]] * len(etab.people),
                           confirm_bins=[cfg["confirm_bins"]] * len(etab.people), budget_met_train=[bool(cfg.get("budget_met", False))] * len(etab.people))

    c0 = make_c0_rule()
    finals: dict[str, tuple[np.ndarray, dict[str, np.ndarray]]] = {}
    cfgs: dict[str, dict] = {}
    for vid, spec in specs.items():
        p_in = base[spec.base][0].copy()
        p_te = {yf: v.copy() for yf, v in base[spec.base][1].items()}
        if spec.calib:
            cal = Calibrator(spec.calib).fit(p_in, y)
            p_in = cal.transform(p_in)
            p_te = {yf: cal.transform(v) for yf, v in p_te.items()}
        if spec.shift:
            s = np.array([y[ttab.rows_of([q])].sum() for q in ttab.people])
            n = np.array([float(ttab.rows_of([q]).size) for q in ttab.people])
            prior = fit_beta_prior_people(s, n)
            for q in ttab.people:
                rq = ttab.rows_of([q])
                p_in[rq] = apply_personal_shift(ttab, p_in, rq, prior)
            for yf, tb in tests.items():
                for q in tb.tab.people:
                    rq = tb.tab.rows_of([q])
                    p_te[yf][rq] = apply_personal_shift(tb.tab, p_te[yf], rq, prior)
        finals[vid] = (p_in, p_te)
        cfgs[vid] = c0(train.layout, p_in, eps_tr, budget)
    rule_makers = {"C0": make_c0_rule, "C1": make_c1_rule, "C2": lambda: make_c2_rule(ttab, n_boot=n_boot_rule)}
    p_in0 = finals["A0"][0]
    cfg_c = {r: rule_makers[r]()(train.layout, p_in0, eps_tr, budget, None) for r in rules}
    out: dict[str, dict[str, Any]] = {}
    for yf, tb in tests.items():
        etab = tb.tab
        outputs = {vid: VariantOutput(spec, finals[vid][1][yf], events_for(yf, finals[vid][1][yf], cfgs[vid]), list(etab.people),
                                      {q: cfgs[vid] for q in etab.people}, "train once, score the other cohort") for vid, spec in specs.items()}
        c_out = {r: VariantOutput(specs["A0"], finals["A0"][1][yf], events_for(yf, finals["A0"][1][yf], cfg_c[r]), list(etab.people),
                                  {q: cfg_c[r] for q in etab.people}, "train once") for r in rules}
        out[yf] = {"outputs": outputs, "c_outputs": c_out, "train": train.family, "test": yf, "n_test_people": len(etab.people),
                   "n_test_bins": int(etab.n), "n_train_bins": int(ttab.n)}
    return out


# --------------------------------------------------------------------------------------------- pooled test
def _cell_draws(cell: dict, test: TabBundle, M: np.ndarray, budget: float) -> dict[str, dict[str, np.ndarray]]:
    tab = test.tab
    cl = Clusters.from_labels(tab.person)
    y = tab.y.astype(float)
    out: dict[str, dict[str, np.ndarray]] = {}
    for vid, o in cell["outputs"].items():
        d = dict(metric_draws(score_parts(y, o.p, cl), M))
        d.update(event_draws(o.events, M, budget))
        out[vid] = d
    out["__C__"] = {r: event_draws(o.events, M, budget) for r, o in cell["c_outputs"].items()}      # type: ignore[assignment]
    return out


def _points(cell: dict, test: TabBundle, budget: float) -> dict[str, dict[str, float]]:
    tab = test.tab
    cl = Clusters.from_labels(tab.person)
    y = tab.y.astype(float)
    res: dict[str, dict[str, float]] = {}
    for vid, o in cell["outputs"].items():
        d = dict(metric_points(score_parts(y, o.p, cl)))
        d.update(event_points(o.events, budget))
        res[vid] = d
    return res


def pooled_offdiag(cells: dict[tuple[str, str], dict], bundles: dict, *, ref: str = "A0", primary: str | None, candidates: list[str], n_boot: int, seed: int,
                   budget: float = DEFAULT_BUDGET) -> dict:
    """Mean over the mismatch cells of each variant's paired difference to ``ref``, test people resampled per family (the same resample for the
    two cells that share a test family)."""
    M_by_family = {f: boot_multiplicities(len(bundles[(f, 'test')].tab.people), n_boot, seed + 17 * i) for i, f in enumerate(FAMILIES)}
    off = [(x, y) for (x, y) in cells if x != y]
    draws = {c: _cell_draws(cells[c], bundles[(c[1], "test")], M_by_family[c[1]], budget) for c in off}
    pts = {c: _points(cells[c], bundles[(c[1], "test")], budget) for c in off}
    m = len(candidates)
    out: dict[str, Any] = {"cells": [f"{x}->{y}" for x, y in off], "n_cells": len(off), "rows": {}}
    cand_ids = [v for v in cells[off[0]]["outputs"] if v != ref and v != "TSP" and v != "BASE"]
    for vid in cells[off[0]]["outputs"]:
        lvl = 0.95 if vid in (primary, ref) else adjusted_level(m)
        deltas: dict[str, dict] = {}
        for k in ("log_loss", "brier", "ece", "auc", "detection", "false_alarms_per_hour", "overshoot"):
            dd = np.mean([draws[c][vid][k] - draws[c][ref][k] for c in off], axis=0)
            pt = float(np.mean([pts[c][vid][k] - pts[c][ref][k] for c in off]))
            lo, hi = interval(dd, lvl)
            deltas[k] = {"delta": pt, "interval": [lo, hi], "level": lvl}
        guards = {}
        for g, (side, margin) in GUARDS.items():
            lo, hi = deltas[g]["interval"]
            guards[g] = {"ok": bool((hi <= margin) if side == "upper" else (lo >= margin)), "bound": hi if side == "upper" else lo, "margin": margin}
        # single-cell harm: lower end of the Bonferroni (m = 6) interval above zero for log loss
        harmful_cells = []
        for c in off:
            d = draws[c][vid][PRIMARY_METRIC] - draws[c][ref][PRIMARY_METRIC]
            lo, hi = interval(d, adjusted_level(len(off)))
            if lo > 0:
                harmful_cells.append(f"{c[0]}->{c[1]}")
        pool_pass = bool(deltas[PRIMARY_METRIC]["interval"][1] < 0 and all(g["ok"] for g in guards.values()))
        out["rows"][vid] = {
            "paired_vs_ref": deltas, "guards": guards, "pooled_pass": pool_pass, "harmful_cells": harmful_cells,
            "no_harm": not harmful_cells,
            "per_cell_log_loss_delta": {f"{c[0]}->{c[1]}": float(pts[c][vid]["log_loss"] - pts[c][ref]["log_loss"]) for c in off},
            "mismatch_pass": bool(vid != ref and pool_pass and not harmful_cells),
        }
    # family C: overshoot and detection against C0
    crow = {}
    for r in ("C1", "C2"):
        cd = {}
        for k in ("overshoot", "detection", "false_alarms_per_hour"):
            dd = np.mean([draws[c]["__C__"][r][k] - draws[c]["__C__"]["C0"][k] for c in off], axis=0)
            pt = float(np.mean([event_points(cells[c]["c_outputs"][r].events, budget)[k] - event_points(cells[c]["c_outputs"]["C0"].events, budget)[k] for c in off]))
            lvl = 0.95 if r == "C1" else adjusted_level(2)
            lo, hi = interval(dd, lvl)
            cd[k] = {"delta": pt, "interval": [lo, hi], "level": lvl}
        pass_c = bool(cd["overshoot"]["interval"][1] < 0 and cd["detection"]["interval"][0] >= GUARD_DETECTION_MARGIN)
        crow[r] = {"paired_vs_C0": cd, "pooled_pass": pass_c}
    out["family_c"] = crow
    out["a_candidates"] = cand_ids
    return out


# --------------------------------------------------------------------------------------------- the part
def a_specs(frozen: dict | None) -> tuple[dict[str, VariantSpec], str | None]:
    specs = dict(FAMILY_A)
    primary = None
    if frozen:
        specs["A7"] = A7_CANDIDATES[frozen["a7_base"]]
        primary = frozen.get("primary_a")
    else:
        specs["A7"] = A7_CANDIDATES["A7_A4"]
    specs.update(BASELINE_SPECS)
    return specs, primary


def run_mismatch_part(pool: str, *, frozen: dict | None = None, roles: tuple[str, ...] = ROLES, n_boot: int = 4000, fast: bool = False, seed: int = 0,
                      inner_folds: int | None = 5, cohort_fn=None, variants: dict[str, VariantSpec] | None = None, log=None) -> dict[str, Any]:
    log = log or (lambda m: None)
    t0 = time.time()
    if fast:
        n_boot = min(n_boot, 300)
    specs, primary = a_specs(frozen)
    if variants is not None:
        specs = {**variants, **BASELINE_SPECS}
    cand = [v for v in specs if v.startswith("A") and v != "A0"]
    out: dict[str, Any] = {
        "pool": pool, "origin": ORIGIN + " (generator families markov, latent_skill, process_trace; REALISM track)", "n_unit": "people",
        "n_train_people_per_cell": N_PEOPLE, "n_test_people_per_cell": N_PEOPLE, "families": list(FAMILIES), "primary_a": primary,
        "split": "fit on family X (40 people), test on family Y (40 people, independent seed); every ordered pair; per role",
        "note": ("All three families are still written by us. Passing the mismatch test shows robustness to these structural changes, "
                 "not to real work."), "roles": {},
    }
    for role in roles:
        bundles = load_bundles(pool, role, cohort_fn=cohort_fn)
        cells: dict[tuple[str, str], dict] = {}
        for x in FAMILIES:
            row = run_row(bundles[(x, "train")], {yf: bundles[(yf, "test")] for yf in FAMILIES}, specs, inner_folds=inner_folds,
                          n_boot_rule=200 if fast else 500)
            for yf, cell in row.items():
                cells[(x, yf)] = cell
            log(f"role {role}: trained on {x} at {time.time() - t0:.0f}s")
        per_cell = {}
        for (x, y), cell in cells.items():
            test = bundles[(y, "test")]
            run = FamilyARun(test.tab, test.layout, cell["outputs"], {}, "fit once on X, score Y")
            cmp_a = compare_family_a(run, primary=primary, n_boot=n_boot, seed=seed, candidates=[v for v in cand if v in cell["outputs"]])
            cmp_c = compare_family_c(FamilyCRun(test.tab, cell["c_outputs"], "A0"), n_boot=n_boot, seed=seed)
            per_cell[f"{x}->{y}"] = {"kind": "in-distribution" if x == y else "mismatch", "n_test_people": cell["n_test_people"],
                                     "n_test_bins": cell["n_test_bins"], "n_train_bins": cell["n_train_bins"], "family_a": _slim(cmp_a), "family_c": _slim_c(cmp_c)}
        pooled = pooled_offdiag(cells, bundles, primary=primary, candidates=[v for v in cand if v in specs], n_boot=n_boot, seed=seed)
        diag_delta = {}
        for vid in specs:
            diag = [per_cell[f"{f}->{f}"]["family_a"]["rows"][vid]["delta_log_loss"] for f in FAMILIES if vid in per_cell[f"{f}->{f}"]["family_a"]["rows"]]
            diag_delta[vid] = float(np.mean(diag)) if diag else None
        for vid, row in pooled["rows"].items():
            row["mean_diagonal_log_loss_delta"] = diag_delta.get(vid)
            row["transfer_loss"] = None if diag_delta.get(vid) is None else float(row["paired_vs_ref"]["log_loss"]["delta"] - diag_delta[vid])
        gens = sorted({(b.generator or {}).get("generator_sha256") or "unknown" for b in bundles.values()})
        out.setdefault("generator_sha256", gens)
        out["roles"][role] = {"cells": per_cell, "pooled_off_diagonal": pooled,
                              "n_bins": {f"{f}/{s}": int(bundles[(f, s)].tab.n) for f in FAMILIES for s in ("train", "test")}}
        log(f"role {role} done at {time.time() - t0:.0f}s")
    out["seconds"] = round(time.time() - t0, 1)
    return out


def _slim(cmp_a: dict) -> dict:
    rows = {}
    for vid, r in cmp_a["rows"].items():
        rows[vid] = {"log_loss": r["metrics"]["log_loss"]["value"], "ece": r["metrics"]["ece"]["value"], "auc": r["metrics"].get("auc", {}).get("value"),
                     "delta_log_loss": r["paired_vs_ref"]["log_loss"]["delta"], "delta_interval": r["paired_vs_ref"]["log_loss"]["interval"],
                     "level": r["level"], "false_alarms_per_hour": r["events"]["false_alarms_per_hour"]["value"], "detection": r["events"]["detection"]["value"],
                     "verdict": r["verdict"]}
    return {"reference": cmp_a["reference"], "n_people": cmp_a["n_people"], "n_bins": cmp_a["n_bins"], "rows": rows}


def _slim_c(cmp_c: dict) -> dict:
    return {"rows": {r: {"false_alarms_per_hour": v["false_alarms_per_hour"], "detection": v["detection"], "budget_met": v["budget_met"],
                         "overshoot": v["overshoot"], "verdict": v["verdict"]} for r, v in cmp_c["rows"].items()}}
