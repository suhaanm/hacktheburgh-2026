"""The decisions scoreboard (``evals/hrt/PLAN.md`` section 5): realised cost or value of each decision rule we ship, against naive policies and an
oracle, on fresh simulated worlds, with paired bootstrap intervals over replicate worlds and a stated multiple-comparison correction.

A row's unit is the replicate world (a draw of routines, of cases, of a persona's weeks, of a simulator run). A policy's number in a replicate is its
realised cost (lower is better) or value (higher is better) in that world; a contrast is the shipped rule minus a naive policy on the same worlds.
The four primary contrasts of the plan are reported at the Bonferroni-adjusted level beside the nominal 95%; everything else is exploratory.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import worlds as wd

B_BOOT = 4000
LEVEL = 0.95
N_PRIMARY = 4
LEVEL_ADJ = 1.0 - 0.05 / N_PRIMARY                      # 98.75%
REVIEW_MIN = 10.0                                      # assumed expert minutes per reviewed case (routing.evaluate.REVIEW_MIN_PER_CASE)


# ----------------------------------------------------------------------------------------------------------- stats
def _interval(d: np.ndarray, level: float) -> list[float]:
    tail = (1.0 - level) / 2.0
    return [float(np.quantile(d, tail)), float(np.quantile(d, 1.0 - tail))]


def boot_idx(K: int, B: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, K, size=(B, K))


def mean_ci(v: np.ndarray, idx: np.ndarray) -> dict[str, Any]:
    return {"est": float(np.mean(v)), "ci": _interval(v[idx].mean(axis=1), LEVEL)}


def contrast(shipped: np.ndarray, other: np.ndarray, idx: np.ndarray, *, good: str, primary: bool, label: str, n_exploratory: int | None = None) -> dict[str, Any]:
    """Shipped minus other over the replicates (paired: the same resamples). ``good`` is 'lower' or 'higher'. A win needs the interval to exclude 0 in the
    good direction at the level that applies: the adjusted level for a primary contrast, the nominal level for an exploratory one (and exploratory
    cells are never used to say a rule works)."""
    d = shipped - other
    dd = d[idx].mean(axis=1)
    ci95, ci_adj = _interval(dd, LEVEL), _interval(dd, LEVEL_ADJ)
    use = ci_adj if primary else ci95
    wins = (use[1] < 0) if good == "lower" else (use[0] > 0)
    loses = (use[0] > 0) if good == "lower" else (use[1] < 0)
    out = {"label": label, "est": float(d.mean()), "ci95": ci95, "primary": primary, "good_direction": good,
           "verdict": "win" if wins else "loss" if loses else "no clear difference"}
    if primary:
        out["ci_adjusted"] = ci_adj
        out["adjusted_level"] = LEVEL_ADJ
        out["family_size"] = N_PRIMARY
    else:
        out["exploratory_cells_in_row"] = n_exploratory
    return out


def gap_closed(shipped: np.ndarray, naive: np.ndarray, oracle: np.ndarray, idx: np.ndarray, *, good: str) -> dict[str, Any]:
    """Share of the naive-to-oracle gap the shipped rule closes: (naive - shipped) / (naive - oracle) for costs, the mirror for values. Reported with an
    interval only where the gap itself is clearly non-zero; otherwise the share is not defined."""
    sign = 1.0 if good == "lower" else -1.0
    gap = sign * (naive - oracle)
    gap_b = gap[idx].mean(axis=1)
    lo, hi = _interval(gap_b, LEVEL)
    if not (lo > 0 or hi < 0):
        return {"share": None, "reason": "the naive-to-oracle gap is not clearly different from zero, so a share of it is not defined"}
    num_b = (sign * (naive - shipped))[idx].mean(axis=1)
    sh = num_b / gap_b
    return {"share": float(np.mean(sign * (naive - shipped)) / np.mean(gap)), "ci": _interval(sh, LEVEL)}


def policy_table(values: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, Any]:
    return {k: mean_ci(v, idx) for k, v in values.items()}


# ------------------------------------------------------------------------------------------------ D1 build timing
def ski_replicate(seed: int, bs: tuple[float, ...], n_routines: int = 500) -> dict[float, dict[str, float]]:
    """Per build cost b, mean cost per routine (manual-run equivalents) of each policy in one simulated world."""
    from understudy_engine.routines import skirental as sk
    from understudy_engine.routines.simulate import SimConfig, simulate_routines

    x, y = simulate_routines(SimConfig(n_routines=n_routines, seed=seed))
    out: dict[float, dict[str, float]] = {}
    for b in bs:
        errs: list[float] = []
        learned = np.empty(len(x))
        for i, (xi, yi) in enumerate(zip(x, y)):
            lam = sk.choose_lambda(errs[-200:])
            learned[i] = sk.cost(xi, sk.buy_run(yi, b, lam), b)
            errs.append(float(np.log((yi + 1.0) / (xi + 1.0))))
        be = np.array([sk.cost(xi, sk.break_even_run(b), b) for xi in x])
        now = np.array([sk.cost(xi, 1, b) for xi in x])
        out[b] = {"shipped_learned_lambda": float(learned.mean()), "break_even": float(be.mean()), "build_now": float(now.mean()), "never_build": float(x.mean()),
                  "fixed_lambda_0.2": float(np.mean([sk.cost(xi, sk.buy_run(yi, b, 0.2), b) for xi, yi in zip(x, y)])),
                  "fixed_lambda_0.5": float(np.mean([sk.cost(xi, sk.buy_run(yi, b, 0.5), b) for xi, yi in zip(x, y)])),
                  "oracle_hindsight": float(np.minimum(x, b).mean())}
    return out


def build_timing_row(ks: tuple[int, ...], *, bs: tuple[float, ...] = (4.0, 8.0, 16.0, 32.0), b_primary: float = 8.0, n_routines: int = 500, seed: int = 41, log=None) -> dict[str, Any]:
    reps = []
    for k in ks:
        reps.append(ski_replicate(wd.decide_seed("ski", k), bs, n_routines))
        if log and len(reps) % 10 == 0:
            log(f"  ski: {len(reps)} of {len(ks)} worlds")
    idx = boot_idx(len(ks), B_BOOT, seed)
    naive = ("break_even", "build_now", "never_build")
    n_expl = len(bs) * len(naive) - 1
    cells: dict[str, Any] = {}
    for b in bs:
        vals = {p: np.array([r[b][p] for r in reps]) for p in reps[0][b]}
        cell: dict[str, Any] = {"policies": policy_table(vals, idx), "contrasts": {}, "gap_closed_vs_break_even": gap_closed(vals["shipped_learned_lambda"], vals["break_even"], vals["oracle_hindsight"], idx, good="lower")}
        for nv in naive:
            prim = bool(b == b_primary and nv == "break_even")
            cell["contrasts"][f"shipped_minus_{nv}"] = contrast(vals["shipped_learned_lambda"], vals[nv], idx, good="lower", primary=prim, label=f"shipped rule minus {nv.replace('_', ' ')} at b = {b:g}", n_exploratory=n_expl)
        cells[f"{b:g}"] = cell
    return {"id": "D1", "decision": "when to build an automation (ski rental with predictions)", "unit": "manual-run equivalents per routine (lower is better)", "direction": "lower",
            "replicates": len(ks), "replicate_unit": f"simulated worlds of {n_routines} routines", "primary_cell": f"b = {b_primary:g}, shipped rule minus break-even",
            "shipped": "ski rental with trust lambda learned online (routines.skirental.choose_lambda)", "naive": list(naive), "oracle": "hindsight: min(runs, b)",
            "cells": cells, "primary": cells[f"{b_primary:g}"]["contrasts"]["shipped_minus_break_even"],
            "note": "Past forecast errors for the learned lambda come from routines in the same simulated world, taken as finished; in use a routine's outcome arrives after its whole horizon."}


# ------------------------------------------------------------------------------------------- D2 review routing
def routing_replicate(seed: int, budgets: tuple[float, ...], n: int = 3000) -> dict[float, dict[str, float]]:
    from understudy_engine.routing.cases import simulate_cases, split_indices
    from understudy_engine.routing.model import RoutingModel

    c = simulate_cases(n, seed)
    tr, ca, te = split_indices(c.n, seed)
    m = RoutingModel().fit(c.X[tr], c.y[tr])
    m.calibrate(c.X[ca], c.y[ca])
    y = c.y[te].astype(float)
    nte = y.size
    rng = np.random.default_rng(seed + 7)
    conf = c.col("agent_confidence")[te]
    dis = c.col("disagree")[te] + 1e-6 * rng.random(nte)
    scores = {"model": m.predict(c.X[te]), "agent_confidence_only": 1.0 - conf, "disagreement_only": dis, "prior_only_reference": c.p_true[te]}
    out: dict[float, dict[str, float]] = {}
    for bud in budgets:
        k = int(round(bud * nte))
        rec: dict[str, float] = {}
        for name, sc_ in scores.items():
            order = np.argsort(-sc_, kind="mergesort")
            reviewed = np.zeros(nte, bool)
            reviewed[order[:k]] = True
            rec[name] = float(y[~reviewed].sum() / nte * 100.0)
        rec["random"] = float(y.sum() * (1.0 - k / nte) / nte * 100.0)          # exact expectation of reviewing a random k
        rec["hindsight_oracle"] = float(max(0.0, y.sum() - k) / nte * 100.0)
        rec["error_rate_per_100"] = float(y.mean() * 100.0)
        out[bud] = rec
    return out


def routing_row(ks: tuple[int, ...], *, budgets: tuple[float, ...] = (0.1, 0.2, 0.3, 0.5), b_primary: float = 0.3, n: int = 3000, seed: int = 42, log=None) -> dict[str, Any]:
    reps = []
    for k in ks:
        reps.append(routing_replicate(wd.decide_seed("routing", k), budgets, n))
        if log and len(reps) % 10 == 0:
            log(f"  routing: {len(reps)} of {len(ks)} worlds")
    idx = boot_idx(len(ks), B_BOOT, seed)
    naive = ("random", "agent_confidence_only", "disagreement_only")
    cells: dict[str, Any] = {}
    n_expl = len(budgets) * len(naive) - 1
    for bud in budgets:
        vals = {p: np.array([r[bud][p] for r in reps]) for p in reps[0][bud]}
        cell: dict[str, Any] = {"policies": policy_table(vals, idx), "contrasts": {}, "gap_closed_vs_random": gap_closed(vals["model"], vals["random"], vals["hindsight_oracle"], idx, good="lower")}
        for nv in naive:
            prim = bool(bud == b_primary and nv == "random")
            cell["contrasts"][f"model_minus_{nv}"] = contrast(vals["model"], vals[nv], idx, good="lower", primary=prim, label=f"model minus {nv.replace('_', ' ')} at a {bud:.0%} review budget", n_exploratory=n_expl)
        cells[f"{bud:g}"] = cell
    # the cost ratio at which routing pays: an escaped error costs c expert-minutes; reviewing a case costs REVIEW_MIN
    mid = cells[f"{b_primary:g}"]["policies"]
    esc = mid["model"]["est"] / 100.0
    base = float(np.mean([r[b_primary]["error_rate_per_100"] for r in reps])) / 100.0
    review_cost = REVIEW_MIN * b_primary
    lo = review_cost / (base - esc) if base > esc else None                  # below this an escaped error is too cheap to be worth reviewing 30%
    hi = REVIEW_MIN * (1.0 - b_primary) / esc if esc > 0 else None            # above this reviewing everything is cheaper than routing
    return {"id": "D2", "decision": "which cases an expert reviews under a review budget (review routing)", "unit": "escaped errors per 100 cases at the same expert cost (lower is better)", "direction": "lower",
            "replicates": len(ks), "replicate_unit": f"simulated worlds of {n} cases (train / calibration / held-out 50/25/25)", "primary_cell": f"{b_primary:.0%} budget, model minus random review",
            "shipped": "the routing model's calibrated risk, top share reviewed", "naive": list(naive), "oracle": "review exactly the wrong cases, up to the budget (hindsight)",
            "reference": "prior_only_reference: rank by the generator's true error probability given the household's own features. It is a reference, not a ceiling: the model also sees the worker's check and the agent's stated confidence, which the generator draws from the realised error.",
            "cells": cells, "primary": cells[f"{b_primary:g}"]["contrasts"]["model_minus_random"],
            "cost_ratio": {"review_minutes_per_case_assumed": REVIEW_MIN, "budget": b_primary, "mean_error_rate": base, "mean_escaped_rate_model": esc,
                           "routing_beats_reviewing_nothing_when_an_escaped_error_costs_more_than_minutes": lo,
                           "routing_beats_reviewing_everything_when_an_escaped_error_costs_less_than_minutes": hi,
                           "note": "An escaped error's cost is an assumption; between these two numbers the budgeted routing is the cheapest of the three plans."},
            "note": "The routing model is scored on the non-circular generator (routing/cases.py), not on the sandbox households, whose error is a near-deterministic function of calculator disagreement. In that generator the worker's check (disagreement), the agent's stated confidence and the worker's trace are drawn from the realised error, as they partly would be in use, so part of the model's edge is signal that our generator hands it."}


# ----------------------------------------------------------------------------------------- D3 background starts
def presence_replicate(seed: int, slug: str, loss_ratios: tuple[float, ...], d_min: float = 30.0, cap: float = 0.10) -> dict[str, Any]:
    """One persona stream (a new seed): the forward split, the shipped start rule and the two naive start policies from ``presence.evaluate``, and an oracle
    that starts a run exactly when the idle spell will last long enough. Counts per policy; values at each loss ratio L/G."""
    import dataclasses
    from datetime import date, timedelta

    from understudy_engine.personas import PERSONA_BY_SLUG, simulate_persona
    from understudy_engine.presence.evaluate import evaluate_decisions, replay_policy, split_days
    from understudy_engine.presence.timeline import day_states_from_events, spells_from_events

    spec = dataclasses.replace(PERSONA_BY_SLUG[slug], slug=f"{slug}-dec", person=f"{PERSONA_BY_SLUG[slug].person}dec", seed=seed)
    run = simulate_persona(spec, 21, with_mc=False)
    tz = run.truth.get("tz", "UTC")
    first = date.fromisoformat(run.truth["start_date"])
    days = day_states_from_events(run.rows, tz=tz, first_day=first, last_day=first + timedelta(days=int(run.truth["n_days"]) - 1))
    spells = spells_from_events(run.rows, tz=tz)
    train, test = split_days(days, "forward")
    tr_days, te_days = {d.day for d in train}, {d.day for d in test}

    def day_of(s) -> date:
        return date.fromordinal(date(1970, 1, 1).toordinal() + int(s.start // 86400))

    tr_sp = [s for s in spells if day_of(s) in tr_days]
    te_sp = [s for s in spells if day_of(s) in te_days]
    dec = evaluate_decisions(tr_sp, te_sp, d_min=d_min, cap=cap, day_of=day_of, n_boot=20)
    usable = [s for s in te_sp if s.duration_min >= 5.0]
    orc = replay_policy(usable, lambda s, u: (s.duration_min - u) >= d_min, d_min=d_min, u0=5.0)
    counts = {"shipped_rule": (dec["rule"]["completed_runs"], dec["rule"]["collisions"]), "run_whenever_idle_5min": (dec["run_whenever_idle_5min"]["completed_runs"], dec["run_whenever_idle_5min"]["collisions"]),
              "fixed_overnight": (dec["fixed_overnight"]["completed_runs"], dec["fixed_overnight"]["collisions"]), "oracle_knows_spell_length": (orc.completed_runs, orc.collisions)}
    n_days = max(1, len(test))
    return {"n_test_days": n_days, "counts": counts,
            "value_per_day": {lr: {p: (c - lr * x) / n_days for p, (c, x) in counts.items()} for lr in loss_ratios},
            "interruption_rate": {"shipped_rule": dec["rule"]["interruption_rate"], "run_whenever_idle_5min": dec["run_whenever_idle_5min"]["interruption_rate"],
                                  "fixed_overnight": dec["fixed_overnight"]["interruption_rate"]},
            "share_idle_used": {"shipped_rule": dec["rule"]["share_idle_used"], "run_whenever_idle_5min": dec["run_whenever_idle_5min"]["share_idle_used"],
                                "fixed_overnight": dec["fixed_overnight"]["share_idle_used"]}}


def start_rule_row(ks: tuple[int, ...], *, loss_ratios: tuple[float, ...] = (1.0, 3.0, 9.0, 27.0), lr_primary: float = 9.0, seed: int = 43, log=None) -> dict[str, Any]:
    from .worlds import BASES

    reps = []
    for k in ks:
        for t_i, slug in enumerate(BASES):
            reps.append(presence_replicate(wd.decide_seed("presence", k) + 13 * t_i, slug, loss_ratios))
        if log:
            log(f"  presence: replicate {k} done")
    idx = boot_idx(len(reps), B_BOOT, seed)
    naive = ("run_whenever_idle_5min", "fixed_overnight")
    cells: dict[str, Any] = {}
    n_expl = len(loss_ratios) * len(naive) - 1
    for lr in loss_ratios:
        vals = {p: np.array([r["value_per_day"][lr][p] for r in reps]) for p in reps[0]["value_per_day"][lr]}
        cell: dict[str, Any] = {"policies": policy_table(vals, idx), "contrasts": {}, "gap_closed_vs_run_whenever_idle_5min": gap_closed(vals["shipped_rule"], vals["run_whenever_idle_5min"], vals["oracle_knows_spell_length"], idx, good="higher")}
        for nv in naive:
            prim = bool(lr == lr_primary and nv == "run_whenever_idle_5min")
            cell["contrasts"][f"shipped_minus_{nv}"] = contrast(vals["shipped_rule"], vals[nv], idx, good="higher", primary=prim, label=f"shipped rule minus {nv.replace('_', ' ')} at L/G = {lr:g}", n_exploratory=n_expl)
        cells[f"{lr:g}"] = cell
    axes = {m: {p: mean_ci(np.array([r[m][p] for r in reps]), idx) for p in reps[0][m]} for m in ("interruption_rate", "share_idle_used")}
    return {"id": "D3", "decision": "when to start a background run (the presence window rule)", "unit": "value per held-out day: completed runs minus (L/G) x collisions (higher is better)", "direction": "higher",
            "replicates": len(reps), "replicate_unit": f"persona streams ({len(ks)} draws x 4 personas), 21 days, forward split", "primary_cell": f"L/G = {lr_primary:g}, shipped rule minus run-whenever-idle",
            "shipped": "start only if the forecast chance the idle spell lasts long enough exceeds L/(G+L), L/G = 9 implied by the 10% interruption cap", "naive": list(naive),
            "oracle": "start a run exactly when the idle spell will last long enough (knows each spell's length)", "cells": cells, "primary": cells[f"{lr_primary:g}"]["contrasts"]["shipped_minus_run_whenever_idle_5min"],
            "axes": axes, "note": "L/G, the cost of a collision against the value of a finished run, is an assumption; every other ratio is in the cells. The shipped rule is fixed at the 10% cap; only the valuation changes."}


# --------------------------------------------------------------------------------------------- D4 nudge or silence
def nudge_replicate(seed: int, n: int = 3000) -> dict[str, float]:
    from understudy_engine.policy import rules, sim
    from understudy_engine.policy.context import K, NUDGE, SILENT

    X, a, r, p, g, bandit, snap = sim.simulate_log(n, seed=seed)

    def const(act: int):
        return lambda X_: np.tile(np.eye(K)[act], (X_.shape[0], 1))

    return {"shipped_bandit_snapshot": sim.true_value(snap.policy_probs), "rule_baseline": sim.true_value(lambda X_: rules.rule_probs(X_)), "always_nudge": sim.true_value(const(NUDGE)),
            "never_speak": sim.true_value(const(SILENT)), "oracle_optimum": sim.optimal_value()}


def nudge_row(ks: tuple[int, ...], *, n: int = 3000, seed: int = 44, log=None) -> dict[str, Any]:
    reps = []
    for k in ks:
        reps.append(nudge_replicate(wd.decide_seed("nudge", k), n))
        if log and len(reps) % 10 == 0:
            log(f"  nudge: {len(reps)} of {len(ks)} runs")
    idx = boot_idx(len(ks), B_BOOT, seed)
    vals = {p: np.array([r[p] for r in reps]) for p in reps[0]}
    naive = ("rule_baseline", "always_nudge", "never_speak")
    n_expl = len(naive) - 1
    cell: dict[str, Any] = {"policies": policy_table(vals, idx), "contrasts": {}, "gap_closed_vs_rule_baseline": gap_closed(vals["shipped_bandit_snapshot"], vals["rule_baseline"], vals["oracle_optimum"], idx, good="higher")}
    for nv in naive:
        cell["contrasts"][f"shipped_minus_{nv}"] = contrast(vals["shipped_bandit_snapshot"], vals[nv], idx, good="higher", primary=(nv == "rule_baseline"), label=f"bandit snapshot minus {nv.replace('_', ' ')}", n_exploratory=n_expl)
    return {"id": "D4", "decision": "speak, annotate, take over or stay silent (the intervention policy)", "unit": "simulator reward per decision, exact in expectation (higher is better)", "direction": "higher",
            "replicates": len(ks), "replicate_unit": f"simulator runs of {n:,} logged decisions; the bandit snapshot is taken at the halfway point", "primary_cell": "bandit snapshot minus the rule baseline",
            "shipped": "the contextual bandit's greedy snapshot (policy.bandit)", "naive": list(naive), "oracle": "the exact optimum of the simulator's reward", "cells": {"all": cell},
            "primary": cell["contrasts"]["shipped_minus_rule_baseline"],
            "note": "The reward weights, the gain from a nudge and the interruption costs are ours. The true value of every policy is computed exactly from the simulator, so the spread across replicates is the bandit learning from a different log each time."}


# -------------------------------------------------------------------------------------------- recorded and unscored
def cue_row(root=None) -> dict[str, Any]:
    """The Cue track's own held-out result, read from its recorded file and never re-run here."""
    import json

    from understudy_engine.store.paths import evals_dir

    path = evals_dir() / "cue" / "held_out.json"
    base = {"id": "D5", "decision": "Cue: speak at a stuck moment", "recorded": True, "source": "evals/cue/held_out.json (the Cue track's frozen held-out command; read here, not re-run)"}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        m = d["cue"]["metrics"]
        acc = d["cue"]["acceptance"]
    except (OSError, ValueError, KeyError):
        return {**base, "status": "pending", "reason": "evals/cue/held_out.json is not present"}
    net = m.get("net_seconds_saved_per_hour", {})
    return {**base, "status": "ok", "unit": "net seconds saved per hour of work (stall seconds saved minus seconds lost to interruptions; higher is better)", "direction": "higher",
            "shipped": {"est": net.get("value"), "ci": net.get("ci")}, "naive": {"never speak": net.get("baseline_no_cue", 0.0)}, "oracle": None,
            "n": {"workers": net.get("n_workers"), "hours": m.get("hours")}, "acceptance": {"false_nudges_target": acc.get("P1_false_nudges"), "faster_to_resume_target": acc.get("P2_faster_to_resume")},
            "false_nudges_per_hour": m.get("p1_false_nudges_per_hour", {}).get("primary_975"),
            "note": "Origin: simulated workers. Cue met one of its two pre-registered targets; the net seconds saved is a secondary number, not a target. Not part of the multiple-comparison family."}


def ladder_row() -> dict[str, Any]:
    return {"id": "D6", "decision": "the help-level ladder (L1 to L4)", "status": "not_scored",
            "reason": "The ladder is deterministic code cross-checked against a written spec (COA-3). It has no outcome to score until the live study; a simulated outcome would score our own reward model."}


# ----------------------------------------------------------------------------------------------------------- top
def evaluate_scoreboard(ks: dict[str, tuple[int, ...]], *, log=None) -> dict[str, Any]:
    """All rows. ``ks`` gives the replicate indices per row (``ski``, ``routing``, ``presence``, ``nudge``): DEV or HELD."""
    rows = [build_timing_row(ks["ski"], log=log), routing_row(ks["routing"], log=log), start_rule_row(ks["presence"], log=log), nudge_row(ks["nudge"], log=log)]
    out: dict[str, Any] = {"rows": rows, "recorded": [cue_row()], "not_scored": [ladder_row()]}
    prim = [r["primary"] for r in rows]
    out["primary_family"] = {"size": N_PRIMARY, "adjusted_level": LEVEL_ADJ, "method": "Bonferroni: each primary contrast is also shown at 98.75%; a win needs the adjusted interval to exclude 0",
                             "contrasts": [{"row": r["id"], "label": r["primary"]["label"], "est": r["primary"]["est"], "ci95": r["primary"]["ci95"], "ci_adjusted": r["primary"]["ci_adjusted"], "verdict": r["primary"]["verdict"]} for r in rows]}
    out["wins"] = sum(p["verdict"] == "win" for p in prim)
    return out
