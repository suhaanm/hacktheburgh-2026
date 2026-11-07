"""One adapter per report section: call the owning track's code, reshape to docs/API_CONTRACT.md, never invent a number.

Every adapter takes a ``Ctx`` and returns the section dict (with ``meta``). Anything the owner cannot give us yet is
reported as ``pending`` by ``assemble`` (``NotLanded`` is raised when the owner's module or entry point is missing).
Contract keys are always present; extra keys are additive (the dashboard tolerates them) and a few aliases carry the
names the dashboard's fixture uses until it follows the contract.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import deficit as deficit_mod
from .data import evals_out_dir, resolve_root
from .meta import make_meta, normalise_meta
from .stats import rnd, wilson


class NotLanded(Exception):
    """The owner's module or entry point does not exist (yet)."""

    def __init__(self, owner: str, detail: str):
        super().__init__(f"{owner} not landed ({detail})")
        self.owner, self.detail = owner, detail


class Skipped(Exception):
    """The owner's code exists but this run chose not to call it (for example it needs a real model); shown as ``pending``."""


@dataclass
class Ctx:
    fast: bool = False
    root: Path | None = None
    seed: int = 0
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def n_boot(self) -> int:
        return 60 if self.fast else 300


def owner_attr(owner: str, module: str, attr: str) -> Callable[..., Any]:
    """Import ``module.attr`` or raise ``NotLanded``. Errors inside a module that exists are real errors and propagate."""
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        missing = e.name or ""
        if module == missing or module.startswith(missing + "."):
            raise NotLanded(owner, f"module {module} missing") from e
        raise
    fn = getattr(mod, attr, None)
    if fn is None:
        raise NotLanded(owner, f"{module}.{attr} missing")
    return fn


def _g(d: Any, *path: str, default: Any = None) -> Any:
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def _scores(d: dict[str, Any] | None, keys: tuple[str, ...] = ("log_loss", "brier", "ece", "ci_log_loss")) -> dict[str, Any]:
    return {k: d[k] for k in keys if d and k in d}


def _caveats(r: dict[str, Any]) -> list[str]:
    return [str(c) for c in (r.get("caveats") or [])]


def _limits(r: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(x) for x in (r.get("limitations") or []) if isinstance(x, dict) and "id" in x and "text" in x]


# --------------------------------------------------------------------------------------------- deficits and controls
def _deficit_pair(ctx: Ctx) -> deficit_mod.Result:
    if "deficit" not in ctx.cache:
        ctx.cache["deficit"] = deficit_mod.compute(ctx.root, fast=ctx.fast)
    return ctx.cache["deficit"]


def deficit_recovery(ctx: Ctx) -> dict[str, Any]:
    return _deficit_pair(ctx).deficit_recovery


def null_placebo(ctx: Ctx) -> dict[str, Any]:
    return _deficit_pair(ctx).null_placebo


# ------------------------------------------------------------------------------------------------------------ hazard
def hazard(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.hazard", "evaluate_hazard_data")
    r = fn(ctx.root, n_boot=ctx.n_boot, seed=ctx.seed, include_series=False, include_secondary=True, fast=ctx.fast)
    ev = _g(r, "model", "events", default={})
    per = {}
    for p, v in (r.get("per_person") or {}).items():
        per[p] = {"n_bins": v.get("n_bins"), "stuck_rate": rnd(v.get("stuck_rate")),
                  "model_log_loss": rnd(_g(v, "model", "log_loss")), "time_since_progress_log_loss": rnd(_g(v, "time_since_progress", "log_loss")),
                  "base_rate_log_loss": rnd(_g(v, "base_rate", "log_loss")), "false_alarms_per_hour": rnd(_g(v, "events", "false_alarms_per_hour")),
                  "detection_rate": rnd(_g(v, "events", "detection_rate"))}
    out = {
        "meta": normalise_meta(r.get("meta")),
        "model": {**_scores(r.get("model"), ("log_loss", "brier", "ece", "ci_log_loss", "ci_brier", "ci_ece"))},
        "baselines": {k: _scores(v, ("log_loss", "brier", "ece", "ci_log_loss")) for k, v in (r.get("baselines") or {}).items()},
        "calibration": [{k: b[k] for k in ("p_mean", "freq", "n", "lo", "hi") if k in b} for b in (r.get("calibration") or [])],
        "false_alarms_per_hour": r.get("false_alarms_per_hour"),
        "split": r.get("split", "leave-one-person-out"),
        # additive
        "false_alarms_per_hour_ci": ev.get("false_alarms_per_hour_ci"),
        "detection_rate": ev.get("detection_rate"), "detection_rate_ci": ev.get("detection_rate_ci"),
        "budget_false_alarms_per_hour": r.get("budget_fa_per_hour"),
        "false_alarms_within_budget": r.get("false_alarms_within_budget"),
        "model_minus_tsp_log_loss": r.get("model_minus_tsp_log_loss"), "model_minus_tsp_log_loss_ci": r.get("model_minus_tsp_log_loss_ci"),
        "model_minus_base_log_loss": r.get("model_minus_base_log_loss"), "model_minus_base_log_loss_ci": r.get("model_minus_base_log_loss_ci"),
        "per_person": per,
        "vs_planted": r.get("vs_planted"),
        "interval_note": r.get("interval_note"),
        "data_source": r.get("data_source"),
        "caveats": _caveats(r), "limitations": _limits(r),
    }
    sec = r.get("secondary")
    if sec:
        sev = _g(sec, "model", "events", default={})
        out["secondary"] = {
            "meta": normalise_meta(sec.get("meta")), "data_source": sec.get("data_source"),
            "model": _scores(sec.get("model"), ("log_loss", "brier", "ece", "ci_log_loss")),
            "baselines": {k: _scores(v, ("log_loss", "brier", "ece")) for k, v in (sec.get("baselines") or {}).items()},
            "false_alarms_per_hour": sec.get("false_alarms_per_hour"), "detection_rate": sev.get("detection_rate"),
            "split": sec.get("split"), "caveats": _caveats(sec),
        }
    return out


def policy_gate(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.policy.evaluate", "evaluate_gate")
    load = owner_attr("engine-data", "understudy_engine.hazard.data", "load_persona_episodes")
    eps, _planted, _info = load(ctx.root)
    r = fn(eps, seed=ctx.seed, fast=ctx.fast)
    r = dict(r)
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin", "synthetic"), "n": r.get("n", 0), "n_unit": r.get("n_unit", "people"),
                                               "split": r.get("split"), "note": r.get("note")})
    r["limitations"] = _limits(r)
    return r


def skills(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.skills.evaluate", "evaluate_skills")
    r = dict(fn(ctx.root, fast=ctx.fast) if ctx.root else fn(fast=ctx.fast))
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
    r["limitations"] = _limits(r)
    r["caveats"] = _caveats(r)
    return r


# --------------------------------------------------------------------------------------------------------------- ope
OPE_LABEL = {"naive": "Naive on-policy average", "ips": "Inverse propensity (IPS)", "snips": "Self-normalised IPS", "dr": "Doubly robust"}


def ope(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.policy", "evaluate_ope")
    r = fn(seed=ctx.seed, fast=ctx.fast)
    head = r.get("headline_target", "rule_baseline")
    t = _g(r, "targets", head, default={})
    est = []
    for e in r.get("estimators") or []:
        est.append({"name": e["name"], "value": e["value"], "ci": e["ci"], "label": OPE_LABEL.get(e["name"], e["name"])})
    out = {
        "meta": normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")}),
        "true_value": r.get("true_value"),
        "estimators": est,
        "headline_target": head,
        "optimal_value": r.get("optimal_value"),
        "diagnostics": t.get("diagnostics"),
        "other_targets": {k: {"true_value": v.get("true_value"),
                              "estimators": {n: {"estimate": x.get("estimate"), "ci": x.get("ci"), "ci_covers_truth": x.get("ci_covers_truth")}
                                             for n, x in (v.get("estimators") or {}).items()}}
                          for k, v in (r.get("targets") or {}).items() if k != head},
        "replications": r.get("replications"),
        "caveats": _caveats(r), "limitations": _limits(r),
    }
    return out


# ----------------------------------------------------------------------------------------------------------- routing
def routing(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.routing", "evaluate_routing")
    r = fn(seed=ctx.seed, fast=ctx.fast)
    keep = ("alpha", "curve", "chosen_coverage", "held_out_error", "held_out_ci", "bound_held", "expert_minutes_per_case", "delta",
            "bound_held_definition", "held_out_within_alpha", "held_out", "risk_control", "risk_control_naive", "base_error_rate",
            "expert_minutes_review_all", "review_minutes_assumed_per_case", "calibration", "baselines", "feature_ablation",
            "fixed_review_budget", "random_review_at_budget", "resplits", "aurc_model")
    out: dict[str, Any] = {"meta": normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})}
    out.update({k: r[k] for k in keep if k in r})
    out["caveats"] = _caveats(r)
    out["limitations"] = _limits(r)
    return out


# ------------------------------------------------------------------------------------------------------------ ski rental
def ski_rental(ctx: Ctx) -> dict[str, Any]:
    rep = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "ski_rental_report")
    full = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "evaluate_ski_rental")
    r = dict(rep())
    r["meta"] = normalise_meta(r.get("meta"))
    r["limitations"] = _limits(full())
    return r


# ------------------------------------------------------------------------------------------------------------ presence
def presence(ctx: Ctx) -> dict[str, Any]:
    ev = owner_attr("engine-handoff", "understudy_engine.presence.personas", "evaluate_presence_all")
    sec = owner_attr("engine-handoff", "understudy_engine.presence.personas", "report_section")
    pres = ev(ctx.root)
    if not pres.get("personas"):
        raise FileNotFoundError("no synthetic personas under data/synthetic; run `understudy synth --all`")
    r = dict(sec(pres))
    r["meta"] = normalise_meta(r.get("meta"))
    r["summary"] = pres.get("summary")
    per = {}
    for n, p in (pres.get("personas") or {}).items():
        fwd = _g(p, "by_split", "forward", default={}) or {}
        rule = _g(fwd, "decision", "rule", default={}) or {}
        per[n] = {"map_brier": _g(fwd, "map", "model", "brier"), "window_brier": _g(fwd, "window", "model", "brier"),
                  "window_brier_ci": _g(fwd, "window", "model", "brier_ci"), "interruption_rate": rule.get("interruption_rate"),
                  "interruption_ci": rule.get("interruption_ci"), "idle_time_used": rule.get("share_idle_used"),
                  "idle_time_used_ci": rule.get("share_idle_used_ci")}
    r["per_persona"] = per
    r["limitations"] = _limits(pres)
    return r


def routines(ctx: Ctx) -> dict[str, Any]:
    """Routine finder. The contract's headline precision is over PROPOSALS after the value gate; the raw finder's precision over all
    clusters it returns is put beside it in every row and in ``overall`` so 100% cannot be read as the finder's accuracy."""
    fin = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "evaluate_finder")
    rep = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "routines_report")
    f = fin(ctx.root)
    r = dict(rep(f))
    by_persona = {p.get("persona"): p for p in (f.get("personas") or []) if isinstance(p, dict)}

    def raw_of(p: dict[str, Any]) -> dict[str, Any]:
        x = p.get("finder") or {}
        return {"clusters": x.get("clusters"), "correct": x.get("true_clusters"), "precision": x.get("precision"), "precision_ci": x.get("precision_ci")}

    def gate_of(p: dict[str, Any]) -> dict[str, Any]:
        x = p.get("proposals") or {}
        return {"proposals": x.get("clusters"), "correct": x.get("true_clusters"), "precision": x.get("precision"), "precision_ci": x.get("precision_ci")}

    rows = [{**row, "raw_finder": raw_of(by_persona.get(row["persona"], {})), "after_value_gate": gate_of(by_persona.get(row["persona"], {}))} for row in r["rows"]]
    m = f.get("metrics") or {}

    def total(key: str, sub: str) -> int | None:
        vals = [row[key][sub] for row in rows if isinstance(row[key].get(sub), int)]
        return sum(vals) if vals else None

    raw = {"clusters": total("raw_finder", "clusters"), "correct": total("raw_finder", "correct"),
           "precision": m.get("finder_precision"), "precision_ci": m.get("finder_precision_ci")}
    gate = {"proposals": total("after_value_gate", "proposals"), "correct": total("after_value_gate", "correct"),
            "precision": m.get("precision"), "precision_ci": m.get("precision_ci")}
    r["rows"] = rows
    r["overall"] = {**r["overall"], "recall_ci": m.get("recall_ci"), "raw_finder": raw, "after_value_gate": gate,
                    "precision_basis": "after the value gate (proposals shown to the worker); the raw finder's precision is in raw_finder"}
    meta = normalise_meta(r.get("meta"))
    if raw["clusters"] and raw["precision"] is not None:
        meta["note"] = ((meta.get("note") or "") + f" The raw finder returns {raw['clusters']} clusters, {raw['correct']} of them planted routines "
                        f"({100 * raw['precision']:.0f}%); the value gate keeps {gate['proposals']} proposals, {gate['correct']} planted "
                        f"({100 * gate['precision']:.0f}%). Read the headline precision as the proposals' precision, not the finder's.").strip()
    r["meta"] = meta
    r["metrics"] = m
    r["limitations"] = _limits(f)
    return r


def forecast(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "evaluate_forecast")
    r = dict(fn(ctx.root))
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
    r["limitations"] = _limits(r)
    return r


# ---------------------------------------------------------------------------------------------------------- agent claims
def agent_claims(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("engine-analytics", "understudy_engine.trust.claims", "evaluate_claims")
    r = fn(seed=ctx.seed, n_boot=ctx.n_boot, fast=ctx.fast)
    n = int(r["n"])
    op = r.get("operating_point") or {}
    false_n = int(op.get("false_claims_total", round(float(r["base_rate"]) * n)))
    out = {
        "meta": normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": n, "n_unit": r.get("n_unit"), "split": r.get("split")}),
        "reliability": [{k: b[k] for k in ("p_mean", "freq", "n", "lo", "hi") if k in b} for b in r.get("reliability") or []],
        "brier": r.get("brier"), "base_rate": r.get("base_rate"),
        "model": r.get("model"), "baselines": r.get("baselines"), "operating_point": op,
        "base_failure_rate": r.get("base_failure_rate"),
        # names the dashboard fixture reads. A false claim is a claimed success that the code check rejected, so the code check
        # catches every one by construction; what is measured is whether it can be predicted before the check runs.
        "live": r.get("live"),     # slot: engine-analytics adds the claim-calibration result on the real-model runs here
        "claims": n, "false_claims": false_n, "false_claim_rate": rnd(false_n / n if n else float("nan")),
        "false_claim_ci": wilson(false_n, n), "caught_by_code_check": false_n,
        "caveats": _caveats(r), "limitations": _limits(r),
    }
    return out


# ------------------------------------------------------------------------------------------------------------ agent runs
AGENT_CLEAN = "agent_benefits_20.json"
AGENT_ROBUST = "agent_benefits_20_robust.json"
AGENT_LIVE = "agent_live_runs.json"


def _read_eval_file(root: Path | None, name: str) -> dict[str, Any] | None:
    p = resolve_root(root) / "eval" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _tier_households(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        for t in set(r.get("tiers") or []):
            out[str(t)] = out.get(str(t), 0) + 1
    return dict(sorted(out.items()))


def _run_block(d: dict[str, Any]) -> dict[str, Any]:
    pr = d["pass_rate"]
    n = int(pr["n"])
    checks = d.get("check_pass_counts") or {}
    no_false = checks.get("no_false_claims")
    return {
        "n": n, "pass": int(pr["passed"]), "wilson": pr.get("wilson_95") or wilson(int(pr["passed"]), n), "mean_s": d.get("mean_elapsed_s"),
        "tiers": sorted(set(d.get("tiers_seen") or [])), "tier_households": _tier_households(d.get("rows") or []),
        "false_claims": (n - int(no_false)) if isinstance(no_false, int) else None, "checks": checks,
        "flagged_discrepancies": _g(d, "flagged_discrepancies", "count"), "seed": _g(d, "meta", "seed"), "label": _g(d, "meta", "label"),
    }


def _robust_plan_fn() -> Callable[..., Any]:
    """agent-core's own failure-injection plan, ``benefits_eval.robust_switches(n, seed)``."""
    return owner_attr("agent-core", "understudy_agent.benefits_eval", "robust_switches")


def _injected(robust: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """What was injected, per pattern, from agent-core's own plan (``benefits_eval.robust_switches``) and what happened to those households."""
    try:
        plan_fn = _robust_plan_fn()
    except NotLanded as e:
        return [], f"the injection plan is not available ({e})"
    except Exception as e:     # an import-time bug elsewhere in agent-core must not take the results down with it
        return [], f"the injection plan could not be loaded ({type(e).__name__}: {e})"
    seed = _g(robust, "meta", "seed", default=2026)
    rows = robust.get("rows") or []
    plan = plan_fn(len(rows), seed)

    def kind(q: str) -> str:
        return "layout change" if "layout" in q else "one-off 503" if "503" in q else q

    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        sw = plan.get(r.get("household_id"))
        if not sw:
            continue
        label = " and ".join(f"{kind(q)} on site {site}" for site, q in sorted(sw.items()))
        groups.setdefault(label, []).append(r)
    out = []
    for label, rs in groups.items():
        out.append({"injection": label, "n": len(rs), "pass": sum(1 for r in rs if r.get("pass")),
                    "used_tier2": sum(1 for r in rs if any(t >= 2 for t in (r.get("tiers") or [])))})
    return out, None


LIVE_CONDITION_LABEL = {"clean": "Clean", "layout_v2": "Layout change (layout v2)", "glitch": "One-off error page (glitch)", "injected": "Injected page (prompt injection)"}
FIX_DESCRIPTION = ("a page-state label from the quarantined reader fed to the planner, retries, and the cliff check moved after the verifier; made AFTER the glitch "
                   "result was seen")


def _live_condition(c: dict[str, Any]) -> dict[str, Any]:
    inj = c.get("injection") or {}
    return {
        "n": int(c["n"]), "pass": int(c["code_check_ok"]), "wilson": c.get("wilson_95") or wilson(int(c["code_check_ok"]), int(c["n"])), "success_rate": c.get("success_rate"),
        "claimed_success": c.get("claimed_success"), "false_claims": c.get("false_claims"), "paused": c.get("paused"),
        "injected_runs": inj.get("runs_with_injected_site"), "injection_detected": inj.get("detected"), "attack_success": inj.get("attack_success"),
        "tiers": sorted(set(c.get("tiers_seen") or [])), "mean_steps": c.get("mean_steps"), "mean_latency_s": c.get("mean_latency_s"),
        "failure_reasons": c.get("failure_reasons") or [], "cost_usd_est": c.get("cost_usd_est"),
    }


def _live_block(raw: dict[str, Any]) -> dict[str, Any]:
    """The real-model run (agent-core C4): four conditions on the first variant, the in-sample fix on the second, tier 3 and cost, from the file."""
    by_variant = raw.get("summary_by_variant") or {}
    first = next(iter(by_variant.values()), None) if by_variant else raw["summary"]
    v1 = {k: _live_condition(v) for k, v in first.items()}
    fix_raw = next((v for name, v in by_variant.items() if name != next(iter(by_variant))), {}) if by_variant else {}
    fixes = {k: _live_condition(v) for k, v in (fix_raw or {}).items()}
    meta = raw.get("meta") or {}
    cost = raw.get("cost") or {}
    cum = cost.get("cumulative_in_this_file") or cost.get("cumulative_rows_in_this_file") or {}
    usd_estimates = {k: v for k, v in cum.items() if k.startswith("usd_") and isinstance(v, (int, float))}
    primary_usd = next((v for k, v in usd_estimates.items() if "placeholder" in k or "assumed" in k), None)
    if primary_usd is None and usd_estimates:
        primary_usd = next(iter(usd_estimates.values()))
    runs = raw.get("runs") or []
    t3 = raw.get("tier3_simulated") or {}
    t3_runs = t3.get("runs") or []
    dropped = meta.get("dropped_after_budget_stop")
    if dropped is None:
        m = re.search(r"(\w+) v2 rows dropped after the budget stop", str(cum.get("note") or ""))
        dropped = m.group(1) if m else None
    elif isinstance(dropped, (list, tuple)):
        dropped = len(dropped)
    all_false = sum(int(c.get("false_claims") or 0) for c in list(v1.values()) + list(fixes.values()))
    glitch_fix = None
    if fixes.get("glitch"):
        glitch_fix = {**fixes["glitch"], "variant": next((n for n in by_variant if n != next(iter(by_variant))), None), "in_sample": True,
                      "description": FIX_DESCRIPTION, "same_condition_before": {k: v1["glitch"][k] for k in ("n", "pass", "wilson", "false_claims")} if v1.get("glitch") else None,
                      "dropped_after_budget_stop": dropped,
                      "dropped_note": meta.get("dropped_note") or "the file lists rows dropped when the run budget stopped (meta.dropped_after_budget_stop in data/eval/agent_live_runs.json)"}
    hc = "clean" if "clean" in v1 else next(iter(v1))
    head = v1[hc]
    return {
        "label": "real model", "condition": hc, "headline_condition": hc,
        # the contract keys below describe ONE condition (headline_condition): never read them as totals; every condition is in the *_by_condition maps
        "n": head["n"], "pass": head["pass"], "wilson": head["wilson"], "tiers": head["tiers"], "false_claims": head["false_claims"],
        "pass_by_condition": {k: {"pass": c["pass"], "n": c["n"], "wilson": c["wilson"]} for k, c in v1.items()},
        "false_claims_by_condition": {k: c["false_claims"] for k, c in v1.items()},
        "tiers_by_condition": {k: c["tiers"] for k, c in v1.items()},
        "false_claims_all_conditions": all_false, "cost_usd_est": primary_usd,
        "note": (f"Real model, small n. The headline figures (n, pass, wilson, tiers, false_claims) are for the '{hc}' condition only; the other conditions are in "
                 "conditions and the *_by_condition maps. 20 households per condition shows the pipeline and its failure modes with a live model, not a pass rate. "
                 + str(meta.get("note") or "")).strip(),
        "households": meta.get("households"), "runs_total": meta.get("n"), "models": meta.get("models"),
        "conditions": v1, "glitch_fix": glitch_fix,
        "tier3": {"simulated_actuator": True, "runs": len(t3_runs), "pointer_actions": t3.get("pointer_actions"), "landed_on_interactive": t3.get("landed_on_interactive"),
                  "outcomes": sorted({r.get("outcome") for r in t3_runs if r.get("outcome")}), "note": t3.get("note")},
        "cost": {"estimated_usd_this_run": cost.get("estimated_usd"), "cumulative_usd_at_assumed_rates": primary_usd, "usd_estimates": usd_estimates,
                 "tokens_in": cum.get("tokens_in"), "tokens_out": cum.get("tokens_out"), "price_assumption_usd_per_million": meta.get("price_assumption_usd_per_million"),
                 "live_calls_in_rows": sum(int(r.get("live_calls") or 0) for r in runs), "cache_hits_in_rows": sum(int(r.get("cache_hits") or 0) for r in runs),
                 "unique_prompts_cached": cost.get("unique_prompts_cached"),
                 "note": cum.get("note") or cost.get("not_in_the_rows_above") or None},
    }


def agent_runs(ctx: Ctx) -> dict[str, Any]:
    clean = _read_eval_file(ctx.root, AGENT_CLEAN)
    if clean is None:
        raise FileNotFoundError(f"data/eval/{AGENT_CLEAN} (agent-core writes it: `python -m understudy_agent.benefits_eval`)")
    robust = _read_eval_file(ctx.root, AGENT_ROBUST)
    c = _run_block(clean)
    rb = None
    if robust is not None:
        rb = _run_block(robust)
        rb["injected"], note = _injected(robust)
        if note:
            rb["injected_note"] = note
    live, live_error = None, None
    live_raw = _read_eval_file(ctx.root, AGENT_LIVE)
    if live_raw is not None:
        try:
            live = _live_block(live_raw)
        except (KeyError, TypeError, ValueError, StopIteration) as e:
            live, live_error = None, f"{AGENT_LIVE} is present but could not be read: {type(e).__name__}: {e}"
    runs = c["n"] + (rb["n"] if rb else 0) + ((live.get("runs_total") or live["n"]) if live else 0)
    false_claims = sum(x["false_claims"] or 0 for x in (c, rb) if x)                      # mock-model runs only; the real-model block has its own by-condition map
    false_claims_all = false_claims + ((live or {}).get("false_claims_all_conditions") or 0)
    out = {
        "meta": make_meta(
            "synthetic", runs, "runs",
            f"{c['n']} sandbox households run on the clean path" + (", and again with failures injected (layout changes, one-off 503s)" if rb else "")
            + (f"; plus a real-model block ({live.get('households')} households x {len(live['conditions'])} conditions: "
               + ", ".join(LIVE_CONDITION_LABEL.get(k, k).split(" (")[0].lower() for k in live["conditions"]) + ")" if live else "")
            + "; local sandbox calculators, mock model except the real-model block, simplified oracle",
            note=("The clean path is the compiled path on the sandbox it was written against, so a full pass is expected and says little. The "
                  "discriminating evidence is the robust and injected runs. Households whose calculators disagree are planted discrepancies; "
                  "passing them means the discrepancy was flagged. Scored against a simplified internal oracle, not the law.")),
        "clean": c, "robust": rb,
        "discrepancies_flagged": {"n": c["flagged_discrepancies"], "of": c["n"]},
        "false_claims": false_claims,
        "false_claims_scope": "the mock-model clean and robust runs only; the real-model false claims are by condition in live.false_claims_by_condition",
        "false_claims_all_runs": false_claims_all,
        "live": live,
    }
    if live_error:
        out["live_error"] = live_error
    if live_raw is not None and live is not None:
        lims = live_raw.get("limitations") or []
        out["caveats"] = [x for x in lims if isinstance(x, str)]                       # agent-core writes its own limits as plain sentences
        out["limitations"] = [dict(x) for x in lims if isinstance(x, dict) and "id" in x and "text" in x]
    return out


# -------------------------------------------------------------------------------------------------------------- red team
LAYER_LABEL = {
    "sanitize": "input sanitising", "reader": "the quarantined reader", "actions": "typed actions", "gates": "the action-class gate",
    "dataflow": "data-flow rules", "detector": "the injection detector", "drift": "the goal-drift check", "settings": "protected settings",
}


def _ablation_label(a: str) -> str:
    if a == "all_on":
        return "All layers on"
    if a == "all_off":
        return "All layers off"
    if a.startswith("no_"):
        return f"Without {LAYER_LABEL.get(a[3:], a[3:])}"
    return a


def redteam(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("agent-safety", "understudy_agent.security.redteam_runner", "evaluate_redteam")
    r = fn(fast=ctx.fast)
    rows = []
    for x in r.get("rows") or []:
        row = dict(x)
        row["label"] = _ablation_label(str(x.get("ablation")))
        rows.append(row)
    fp = r.get("false_pause") or {}
    n_attack = rows[0].get("n") if rows else None
    split = (f"{n_attack} attack runs per configuration, {len(rows)} configurations (every layer on, each layer off in turn, all off); "
             f"{fp.get('n')} clean pages for the false-pause rate; scripted planner on sandbox pages") if n_attack and fp.get("n") is not None else None
    out = {
        "meta": normalise_meta(r.get("meta"), {"split": r.get("meta", {}).get("split") or split}),
        "rows": rows,
        "false_pause_rate": r.get("false_pause_rate"), "false_pause_ci": r.get("false_pause_ci"),
        "false_pause": r.get("false_pause"),
        "layer_contribution": _g(r, "detail", "layer_contribution"),
        "by_category": _g(r, "detail", "by_category"),
        "defended_by": _g(r, "detail", "defended_by"),
        "limitations": _limits(r),
    }
    return out


REDTEAM_LIVE_FILE = "redteam_live.json"


def _ci_overlap(a: list[float | None], b: list[float | None]) -> bool | None:
    if not a or not b or None in a or None in b:
        return None
    return a[0] <= b[1] and b[0] <= a[1]


def redteam_live(ctx: Ctx) -> dict[str, Any]:
    """The real-model red-team run, read from agent-safety's cached report (``data/redteam_live.json``). This evaluation never calls a model:
    with no cached file the section is a stub. The cached report holds the model's recorded answers; nothing is re-run here."""
    p = resolve_root(ctx.root) / REDTEAM_LIVE_FILE
    if not p.is_file():
        raise Skipped(f"no cached live red-team run: data/{REDTEAM_LIVE_FILE} is absent. agent-safety writes it (`python -m understudy_agent.security.redteam_runner --live`); "
                      "`make eval` itself never calls a model")
    r = json.loads(p.read_text(encoding="utf-8"))
    m = r.get("meta") or {}
    rows = []
    for x in r.get("rows") or []:
        d = x.get("detail") or {}
        atk, tsk = d.get("attack_success") or {}, d.get("task_success_under_attack") or {}
        rows.append({
            "ablation": x.get("ablation"), "label": _ablation_label(str(x.get("ablation"))),
            "attack_success": x.get("attack_success"), "attack_ci": x.get("attack_ci"), "task_success": x.get("task_success"), "task_ci": x.get("task_ci"),
            "n": x.get("n"), "n_runs": x.get("n_runs"), "attack_successes": atk.get("k"), "attack_runs": atk.get("n"), "task_successes": tsk.get("k"),
            "paused_rate": x.get("paused_rate"), "false_pause_rate": x.get("false_pause_rate"), "false_pause_ci": x.get("false_pause_ci"),
            "n_clean": x.get("n_clean"), "n_clean_runs": x.get("n_clean_runs"),
            "false_pause_hard_negatives": x.get("false_pause_hn"), "task_success_clean": x.get("task_success_clean"),
        })
    on = next((x for x in rows if x["ablation"] == "all_on"), None)
    off = next((x for x in rows if x["ablation"] == "all_off"), None)
    overlap = _ci_overlap(on["attack_ci"], off["attack_ci"]) if on and off else None
    n_cases, repeats = m.get("n"), m.get("repeats")
    label = f"real model, n = {n_cases} cases ({repeats} repeats each)"
    reading = None
    if on and off:
        tail = (f"task success under attack was {100 * on['task_success']:.0f}% with every layer on against {100 * off['task_success']:.0f}% with all off, "
                f"and {on['attack_successes']} of {on['attack_runs']} runs with every layer on let an attack through")
        reading = (f"Intervals overlap: this shows what the layers cost ({tail}), not that the layers prevent attacks."
                   if overlap else
                   f"The attack-success intervals do not overlap ({tail}); with attacks written by the same team that wrote the defences this is still one model on one day.")
    hn_clusters = ((on or {}).get("false_pause_hard_negatives") or {}).get("clusters")
    split = (f"{n_cases} attack cases x {repeats} repeats x {len(rows)} configurations (every layer on, all layers off); {m.get('n_clean')} clean pages"
             + (f" ({hn_clusters} hard negatives)" if hn_clusters is not None else "") + f" x {repeats} repeats; real planner, reader and drift check; nothing executed; "
             "intervals treat the repeats of a case as one observation")
    meta = normalise_meta(m, {"origin": "synthetic", "n": n_cases, "n_unit": "cases", "split": split})
    meta["n"], meta["n_unit"], meta["split"] = int(n_cases or 0), "cases", split
    meta["note"] = f"{label}. " + (str(m.get("note") or "").strip() + " " if m.get("note") else "") + "Cached model answers: this evaluation called no model."
    return {
        "meta": meta, "label": label, "reading": reading, "intervals_overlap": overlap, "rows": rows,
        "false_pause_rate": r.get("false_pause_rate"), "false_pause_ci": r.get("false_pause_ci"), "false_pause": r.get("false_pause"),
        "n_runs": m.get("n_runs"), "repeats": repeats, "n_clean": m.get("n_clean"), "models": m.get("models"), "calls": m.get("calls"),
        "cost_estimate_usd": m.get("cost_estimate_usd"), "source": f"data/{REDTEAM_LIVE_FILE} (cached; agent-safety)",
        "limitations": _limits(r),
    }


# ------------------------------------------------------------------------------------------------------------ privacy
def _static_guard_violations(o: Any, path: str = "") -> list[str]:
    """Every entry of any ``violations`` list found under a ``static_guard`` block, at any depth, as text (``file:line`` when the owner gives them)."""
    found: list[str] = []
    if isinstance(o, dict):
        for k, v in o.items():
            here = f"{path}/{k}"
            if k == "violations" and "static_guard" in path and isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        loc = x.get("file") or x.get("path") or x.get("module") or "?"
                        line = x.get("line") or x.get("lineno")
                        found.append(f"{loc}:{line}" if line is not None else str(loc) + (f" ({x['rule']})" if x.get("rule") else ""))
                    else:
                        found.append(str(x))
            else:
                found += _static_guard_violations(v, here)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            found += _static_guard_violations(v, f"{path}[{i}]")
    return found


def privacy(ctx: Ctx) -> dict[str, Any]:
    """The privacy layer's own offline evaluation (canary leaks, ledger completeness, negative controls, bucketing). Needs no model.
    ``record=False``: the harness writes only its report files, never the layer's summary file. A static-guard violation anywhere makes the whole
    section ``failed`` (with the file:line list): an evaluation that found its own rule broken is not shown as passing."""
    fn = owner_attr("privacy-layer", "understudy_engine.privacy.evaluate", "evaluate_privacy")
    r = dict(fn(record=False, seeds=tuple(range(3 if ctx.fast else 8))))          # fewer seeds per flow in --fast; the structure is the same
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin", "synthetic"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
    viol = _static_guard_violations(r)
    n_head = (r.get("headline") or {}).get("static_guard_violations") or 0
    if viol or n_head:
        shown = ", ".join(viol[:8]) + (f" and {len(viol) - 8} more" if len(viol) > 8 else "")
        count = len(viol) or n_head
        return {"status": "failed", "reason": f"the privacy layer's static guard found {count} violation(s)" + (f": {shown}" if viol else " (the owner's headline counts them but lists none)"),
                "meta": r["meta"], "violations": viol, "headline": r.get("headline")}
    r["meta"]["note"] = ((r["meta"].get("note") or "") + " The static-guard file counts and lists follow the code tree at run time, so they change when files are added.").strip()
    r.pop("purposes", None)                       # the purpose schemas are code documentation, not a result
    r["limitations"] = _limits(r)
    return r


# ------------------------------------------------------------------------------------------------------------- pooling
POOLING_CANDIDATES = (
    ("understudy_engine.skills.pooling", "evaluate_pooling"),
    ("understudy_engine.hazard.pooling", "evaluate_pooling"),
    ("understudy_engine.policy.pooling", "evaluate_pooling"),
    ("understudy_engine.pooling", "evaluate_pooling"),
    ("understudy_engine.trust.pooling", "evaluate_pooling"),
)


def pooling(ctx: Ctx) -> dict[str, Any]:
    for mod, attr in POOLING_CANDIDATES:
        try:
            fn = owner_attr("engine-analytics", mod, attr)
        except NotLanded:
            continue
        try:
            r = dict(fn(seed=ctx.seed, fast=ctx.fast))
        except TypeError:
            r = dict(fn())
        r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
        r["limitations"] = _limits(r)
        return r
    raise NotLanded("engine-analytics", "no evaluate_pooling found (ANA-9)")


# --------------------------------------------------------------------------------------------------------------- study
STUDY_N = 4


MANIFEST = "MANIFEST.json"
MANIFEST_FIELDS = ("origin", "consent_ref", "collected_by", "n_participants", "date")
SIM_ID = re.compile(r"(^p_?sim)|(^sim[_-]?\d)|silicon|(^llm)|(^gpt)|synthetic", re.IGNORECASE)
SIM_COLUMNS = {"arm", "persona", "model", "model_id", "effort_unit", "provider", "temperature"}


def _symlink_in(path: Path, stop: Path) -> Path | None:
    """The first symlink on the way from ``path`` up to ``stop`` (inclusive), if any."""
    p = path
    while True:
        if p.is_symlink():
            return p
        if p == stop or p.parent == p:
            return None
        p = p.parent


def _sim_signs(columns: list[str], ids: list[str]) -> list[str]:
    bad = []
    cols = [c for c in columns if c.strip().lower() in SIM_COLUMNS or "sim" in c.lower() or "llm" in c.lower()]
    if cols:
        bad.append("columns " + ", ".join(sorted(cols)))
    ids_bad = sorted({i for i in ids if SIM_ID.search(str(i))})
    if ids_bad:
        bad.append("participant ids " + ", ".join(ids_bad[:5]))
    return bad


def _read_manifest(results: Path) -> tuple[dict[str, Any] | None, str | None]:
    """(manifest, problem). The manifest is hand-written by the person who ran the study; origin must be "human" and every field present."""
    p = results / MANIFEST
    if not p.is_file():
        return None, None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"{MANIFEST} is not valid JSON ({type(e).__name__})"
    if not isinstance(m, dict):
        return None, f"{MANIFEST} is not a JSON object"
    missing = [k for k in MANIFEST_FIELDS if m.get(k) in (None, "", [])]
    if missing:
        return None, f"{MANIFEST} is missing {', '.join(missing)}"
    if m["origin"] != "human":
        return None, f"{MANIFEST} says origin {m['origin']!r}, not 'human'"
    if not isinstance(m["n_participants"], int) or isinstance(m["n_participants"], bool) or m["n_participants"] < 1:
        return None, f"{MANIFEST} n_participants must be a positive integer"
    return m, None


def _provenance_stub(reason: str, kind: str = "invalid_provenance") -> dict[str, Any]:
    meta = make_meta("unknown", STUDY_N, "people", "within-subject, counterbalanced, teammates only",
                     note="n = 4. Treat every number here as a case study, not a result. No data is shown without a human-study manifest.")
    return {"status": kind, "reason": reason, "n": STUDY_N, "rows": [], "meta": meta}


def _load_analyzer(study_dir: Path):
    """Import the platform's pre-registered analysis script (evals/study/analyze.py) by path, without running its CLI."""
    import importlib.util

    path = study_dir / "analyze.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("understudy_study_analyze", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _study_analysis(study_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(analysis, stub). A stub means: show this instead and never the data. Provenance is checked BEFORE any analysis runs:
    no symlinks, a hand-written manifest saying human, no sign of a simulation in the columns or ids, and the manifest's n matching the file."""
    results = study_dir / "results"
    if not results.exists() and not results.is_symlink():
        return None, None
    csv_path, summary = results / "participants.csv", results / "summary.json"
    for p in (results, csv_path, summary, results / MANIFEST, study_dir / "analyze.py", study_dir / "assignments.json"):
        bad = _symlink_in(p, study_dir) if p.exists() or p.is_symlink() else None
        if bad is not None:
            return None, _provenance_stub(f"{bad.parent.name}/{bad.name} is a symlink; the live study's data and analysis must be real files written in place, "
                                          "not links to results from elsewhere")
    if study_dir.is_symlink():
        return None, _provenance_stub("evals/study is a symlink; the live study's data must live in place")
    for p in (results, csv_path, summary):
        if p.exists() and study_dir.resolve() not in p.resolve().parents:
            return None, _provenance_stub(f"{p.name} resolves outside evals/study")
    if not csv_path.is_file() and not summary.is_file():
        return None, None
    manifest, problem = _read_manifest(results)
    if problem:
        return None, _provenance_stub(problem)
    if manifest is None:
        return None, _provenance_stub("no human-study manifest: data is present in evals/study/results/ but there is no hand-written MANIFEST.json "
                                      "{origin: \"human\", consent_ref, collected_by, n_participants, date}, so it is not shown", kind="not_run")
    if csv_path.is_file():
        import csv

        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            columns, ids = list(reader.fieldnames or []), [r.get("participant", "") for r in reader]
        signs = _sim_signs(columns, ids)
        if signs:
            return None, _provenance_stub("the results look simulated (" + "; ".join(signs) + "), so they are not the live study even though a manifest says human")
        mod = _load_analyzer(study_dir)
        if mod is None:
            raise NotLanded("platform", "evals/study/analyze.py missing, cannot analyse participants.csv")
        rows = mod.load(csv_path)
        if not rows:
            return None, None
        asg = study_dir / "assignments.json"
        analysis = mod.analyse(rows, json.loads(asg.read_text()) if asg.is_file() else None)
        n_file = len({r["participant"] for r in rows})
    else:
        analysis = json.loads(summary.read_text())
        origin = _g(analysis, "meta", "origin")
        blocks = _g(analysis, "headline_unassisted", "blocks", default=[]) or []
        signs = _sim_signs([], [b.get("participant", "") for b in blocks])
        if origin not in (None, "real") or signs:
            return None, _provenance_stub(f"summary.json is not marked as people's data (origin {origin!r}" + (f"; {'; '.join(signs)}" if signs else "") + ")")
        n_file = len({b.get("participant") for b in blocks})
    if n_file != manifest["n_participants"]:
        return None, _provenance_stub(f"the manifest says {manifest['n_participants']} participants but the results file has {n_file}")
    analysis["_provenance"] = {k: manifest[k] for k in MANIFEST_FIELDS}
    return analysis, None


def study(ctx: Ctx) -> dict[str, Any]:
    """Live study (n = 4), exactly as ANALYSIS_PLAN.md pre-registered it. PEOPLE ONLY, and only with provenance: it needs a hand-written
    ``results/MANIFEST.json`` saying origin human, refuses symlinks and anything that looks simulated, and its origin is "real" only after that.
    Without a manifest the section is ``not_run``; with a bad one it is ``invalid_provenance``; the meta origin is "unknown" until validated.

    The headline is the UNASSISTED skill score on a later matched case (coached skill minus uncoached skill, per participant); assisted speed is
    reported beside it, never combined. Contract keys the dashboard reads are filled honestly from the secondary unassisted-time measure:
    ``unassisted_before_s`` is the post-test time after the UNCOACHED skill block, ``unassisted_after_s`` after the COACHED block, ``mean_change_s`` their mean difference."""
    study_dir = evals_out_dir() / "study"
    a, stub = _study_analysis(study_dir)
    if stub is not None:
        return stub
    default = make_meta("unknown", STUDY_N, "people", "within-subject, counterbalanced, teammates only",
                        note="n = 4. Treat every number here as a case study, not a result.")
    if not a or not a.get("headline_unassisted", {}).get("blocks"):
        return {"status": "not_run", "reason": "the live study has not been run: no data in evals/study/results/", "n": STUDY_N, "rows": [], "meta": default}
    meta = normalise_meta(a.get("meta"), default)
    meta["origin"] = "real"                      # only reachable after the manifest and the content checks above
    head = a["headline_unassisted"]
    by_p: dict[str, dict[str, dict[str, Any]]] = {}
    for b in head["blocks"]:
        by_p.setdefault(b["participant"], {})[b["condition"]] = b
    rows = []
    for p in sorted(by_p):
        c, u = by_p[p].get("coached"), by_p[p].get("uncoached")
        if not (c and u):
            continue
        rows.append({
            "participant": p, "skill_coached": c["skill"], "skill_uncoached": u["skill"],
            "score_coached": c["post_score"], "score_uncoached": u["post_score"], "score_difference": rnd(c["post_score"] - u["post_score"], 3),
            "unassisted_s_coached": c["post_seconds"], "unassisted_s_uncoached": u["post_seconds"],
            "assisted_s_coached": c["practice_seconds"], "assisted_s_uncoached": u["practice_seconds"],
            "capped": bool(c["post_capped"] or u["post_capped"] or c["practice_capped"] or u["practice_capped"]),
            "unassisted_before_s": u["post_seconds"], "unassisted_after_s": c["post_seconds"],
        })
    us = a.get("unassisted_speed") or {}
    n = len(rows)
    lim: list[dict[str, str]] = []
    ci = head.get("ci95") or [None, None]
    if ci[0] is not None and ci[0] <= 0 <= ci[1]:
        lim.append({"id": "study-interval-includes-zero", "severity": "high",
                    "text": (f"The headline interval ({ci[0]:.2f} to {ci[1]:.2f} on a 0 to 1 skill score) includes zero: consistent with no effect and with a large "
                             f"effect; {n} people cannot tell. The smallest possible exact p with n = {n} is {head.get('smallest_possible_p')}, so no significance is claimed.")})
    neg = [r["participant"] for r in rows if r["score_difference"] is not None and r["score_difference"] < 0]
    if neg:
        lim.append({"id": "study-negative-differences", "severity": "high",
                    "text": f"For {', '.join(neg)} the coached skill was shown less often unassisted than the uncoached skill (negative difference). It is shown, not averaged away."})
    if a.get("design_problems"):
        lim.append({"id": "study-design-problems", "severity": "medium", "text": "Design problems found before analysis: " + "; ".join(a["design_problems"][:6])})
    if a.get("excluded_participants"):
        lim.append({"id": "study-exclusions", "severity": "medium",
                    "text": "Excluded participants (decided before looking at scores): " + ", ".join(a["excluded_participants"]) + ". Excluded people reduce n."})
    return {
        "meta": meta, "n": n, "rows": rows,
        "headline": {k: v for k, v in head.items() if k != "blocks"},
        "assisted_speed": a.get("assisted_speed"), "unassisted_speed": us, "coach_use": a.get("coach_use"),
        "design_problems": a.get("design_problems", []), "excluded_participants": a.get("excluded_participants", []),
        "not_claimed": a.get("not_claimed", []),
        "mean_change_s": us.get("mean_difference_s"), "mean_change_ci": us.get("ci95") or [None, None],
        "provenance": a.get("_provenance"),
        "alias_note": ("Dashboard keys: unassisted_before_s / unassisted_after_s are the post-test seconds after the uncoached / coached skill block; "
                       "mean_change_s is their mean difference. The headline is `headline` (skill score), reported separately from assisted speed."),
        "limitations": lim,
    }


# --------------------------------------------------------------------------------------------------- simulated study and power
STUDY_SIM_LABEL = "simulated participants (language model), not people"


def _repo_import_root() -> Path:
    return evals_out_dir().parent


@contextlib.contextmanager
def _repo_on_path():
    """An owner's own absolute imports (`from evals.study_sim import ...`) resolve against the repo root, for the duration of a load or a call."""
    import sys

    root = str(_repo_import_root())
    sys.path.insert(0, root)
    try:
        yield
    finally:
        if root in sys.path:
            sys.path.remove(root)


def _find_in_dir(owner: str, d: Path, attr: str) -> Callable[..., Any]:
    """Find ``attr`` in a package directory that is not on sys.path (evals/study_sim): the package itself, then its modules."""
    import importlib.util
    import sys

    if not d.is_dir():
        raise NotLanded(owner, f"{d.parent.name}/{d.name} does not exist yet")
    base = f"_understudy_{d.name}_{abs(hash(str(d))) % 10**8}"
    candidates = [d / "__init__.py"] + sorted(p for p in d.glob("*.py") if p.name not in ("__init__.py", "__main__.py") and not p.name.startswith("test_"))
    with _repo_on_path():
        for path in candidates:
            if not path.is_file():
                continue
            name = base if path.name == "__init__.py" else f"{base}.{path.stem}"
            if name in sys.modules:
                mod = sys.modules[name]
            else:
                spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[str(d)] if path.name == "__init__.py" else None)
                assert spec is not None and spec.loader is not None
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                try:
                    spec.loader.exec_module(mod)
                except BaseException:
                    sys.modules.pop(name, None)
                    raise
            fn = getattr(mod, attr, None)
            if callable(fn):
                return fn
    raise NotLanded(owner, f"{d.parent.name}/{d.name} has no {attr}()")


def study_sim(ctx: Ctx) -> dict[str, Any]:
    """Language-model simulated participants (study-simulation agent). NEVER the live study and never fed into it.

    Forced to origin ``synthetic`` and labelled "simulated participants (language model), not people" wherever it appears. The owner's own ``status``
    (for example "complete") is kept as ``owner_status``; only pending, not_run and failed make a stub. A recorded run 5 pilot decision is attached."""
    d = evals_out_dir() / "study_sim"
    fn = _find_in_dir("study-sim", d, "study_sim_section")
    try:
        with _repo_on_path():
            r = dict(fn())
    except ModuleNotFoundError as e:
        if (e.name or "").startswith("_understudy_study_sim_"):         # the package's own lazy import of a module that is not written yet
            raise NotLanded("study-sim", f"evals/study_sim/{(e.name or '').rsplit('.', 1)[-1]}.py does not exist yet") from e
        raise
    status = r.pop("status", None)
    if status is not None and status not in OWNER_STUB_STATUSES:
        r["owner_status"] = status
        status = None
    meta = normalise_meta(r.get("meta"), {"origin": "synthetic", "n": r.get("n"), "n_unit": "runs"})
    owner_origin = (r.get("meta") or {}).get("origin")
    if owner_origin not in (None, "synthetic"):
        meta["origin_detail"] = owner_origin
    meta["origin"] = "synthetic"
    if r.get("n_aa"):
        meta["n"] = int(r.get("n") or 0) + int(r["n_aa"])                      # coached-arm plus A/A participants
        meta["split"] = f"{meta.get('split') or 'within-participant, counterbalanced'}; n = {r.get('n')} coached-arm plus {r['n_aa']} A/A participants"
    note = (meta.get("note") or "").strip()
    if STUDY_SIM_LABEL not in note.lower():
        note = f"{STUDY_SIM_LABEL[0].upper() + STUDY_SIM_LABEL[1:]}. " + note
    meta["note"] = note.strip()
    if r.get("label") and r["label"] != STUDY_SIM_LABEL:
        r["owner_label"] = r["label"]
    r["label"] = STUDY_SIM_LABEL
    r["meta"] = meta
    cap = STUDY_SIM_LABEL[0].upper() + STUDY_SIM_LABEL[1:]
    r["limitations"] = [dict(x, text=x["text"] if STUDY_SIM_LABEL in x["text"].lower() else f"{cap}: {x['text']}") for x in _limits(r)]     # the phrase travels with every text
    pilot = _recorded(d / "results_run5" / "pilot" / "PILOT_DECISION.json")
    if pilot is not None:
        r["run5_pilot"] = {k: pilot.get(k) for k in ("pass", "post_tests", "post_tests_above_zero", "needed_above_zero", "pilot_scores", "reasons_for_stopping", "criterion",
                                                     "pilot_spend_usd", "affordable_participants", "budget_usd")}
        r["run5_pilot"]["source"] = "evals/study_sim/results_run5/pilot/PILOT_DECISION.json"
    if status in OWNER_STUB_STATUSES and not r.get("reason"):
        r["reason"] = (meta.get("note") or "the simulated study has not been run").strip()      # a stub needs a reason; the owner's note says why
    if status in OWNER_STUB_STATUSES:
        r["status"] = status
    return r


def _power_headline(r: dict[str, Any]) -> dict[str, Any]:
    """The n = 4 and n = 16 rows plainly, read off the owner's grid (no spill-over, no order effect), plus what spill-over does to them."""
    rows = r.get("rows") or []
    min_p = r.get("min_p_by_n") or {}

    def cell(n: int, effect: str, carry: float, order: float) -> dict[str, Any] | None:
        return next((x for x in rows if x.get("n") == n and x.get("effect_label") == effect and x.get("carryover") == carry and x.get("order_effect") == order), None)

    out: dict[str, Any] = {}
    for n in (4, 16):
        cells = {e: cell(n, e, 0.0, 0.0) for e in ("none", "small", "medium", "large")}
        if not any(cells.values()):
            continue
        spill = {}
        full = cell(n, "medium", 1.0, 0.0)
        if cells["medium"] and full:
            spill = {"effect": "medium", "carryover": 1.0, "power_ci_without": cells["medium"]["power_ci"], "power_ci_with": full["power_ci"],
                     "bias_pp_with": full.get("bias_pp"), "bias_pp_without": cells["medium"].get("bias_pp")}
        out[str(n)] = {
            "min_sign_flip_p": min_p.get(str(n)),
            "p05_impossible": all((x.get("power_p05") == 0) for x in rows if x.get("n") == n),
            "power_ci": {e: (c or {}).get("power_ci") for e, c in cells.items()},
            "true_effect_pp": {e: (c or {}).get("true_effect_pp") for e, c in cells.items()},
            "spillover": spill,
        }
    return out


def study_power(ctx: Ctx) -> dict[str, Any]:
    """What the n = 4 design could detect under our assumptions (engine-analytics). A property of the design, not a result about people."""
    fn = owner_attr("engine-analytics", "understudy_engine.study_power", "evaluate_study_power")
    r = dict(fn(fast=ctx.fast))
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin", "synthetic"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
    r["meta"]["origin"] = "synthetic"             # a Monte Carlo of the design: never a claim about people, whatever the owner's dict says
    r["limitations"] = _limits(r)
    r["caveats"] = _caveats(r)
    r["headline_power"] = _power_headline(r)
    return r


# ------------------------------------------------------------------------------------------------- newer owner sections
OWNER_STUB_STATUSES = ("pending", "not_run", "failed", "invalid_provenance")
TIMING_KEYS = ("elapsed_s", "wall_s")          # how long the owner's own evaluation took: not a result, and not deterministic
COMPACT_BYTES = 60_000                         # a top-level key bigger than this is replaced and listed under `trimmed`


OFFLINE_UNSET = ("UNDERSTUDY_EVIDENCE_LIVE", "UNDERSTUDY_X_LOCALMODEL", "UNDERSTUDY_X", "UNDERSTUDY_X_EVIDENCE", "OPENAI_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY")


@contextlib.contextmanager
def _offline():
    """The harness never calls a model. Owner code that can reach one honours UNDERSTUDY_MOCK (the project-wide offline switch, NFR-2) and the feature
    flags that turn a model on, so for every newer owner section MOCK is forced on and those flags and the provider keys are removed for the duration of
    the call, whatever the caller's environment says (the report's own ``mock`` flag is read before this). Restored afterwards."""
    import os

    saved = {k: os.environ.get(k) for k in ("UNDERSTUDY_MOCK", *OFFLINE_UNSET)}
    os.environ["UNDERSTUDY_MOCK"] = "1"
    for k in OFFLINE_UNSET:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _text_limits(name: str, items: Any) -> list[dict[str, Any]]:
    """Owner limitations as register entries; accepts dicts ({id, text, severity}) and plain sentences."""
    out = []
    for k, x in enumerate(items or []):
        if isinstance(x, dict) and "id" in x and "text" in x:
            out.append(dict(x))
        elif isinstance(x, str):
            out.append({"id": f"{name}-limit-{k + 1}", "text": x, "severity": "medium"})
    return out


def _shape_generic(name: str, r: dict[str, Any], *, fallback_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """A newer owner's dict as a report section: ``status`` moved out of the way unless it says the section has no numbers, meta complete,
    limitations as entries, timing dropped, oversized keys listed instead of copied."""
    r = dict(r)
    status = r.pop("status", None)
    reason = r.get("reason")
    for k in TIMING_KEYS:
        r.pop(k, None)
    meta = normalise_meta(r.get("meta"), {"origin": r.get("origin"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split"), **(fallback_meta or {})})
    raw_origin = str(meta.get("origin") or "")
    if raw_origin not in ("real", "synthetic", "mixed", "unknown"):
        # an owner's own word for where its data comes from (simulated_llm, simulated_participants ...) is kept as origin_detail; the badge is synthetic
        meta["origin_detail"] = raw_origin
        meta["origin"] = "synthetic" if ("sim" in raw_origin.lower() or "synth" in raw_origin.lower()) else "unknown"
    r["meta"] = meta
    r["limitations"] = _text_limits(name, r.get("limitations"))
    if status in OWNER_STUB_STATUSES:
        reason = reason or meta.get("note") or f"{name} reports status {status}"
        return {"status": status, "reason": str(reason), "meta": meta, **{k: v for k, v in r.items() if k in ("limitations", "caveats", "label")}}
    if status is not None:
        r["owner_status"] = status
    trimmed = []
    for k, v in list(r.items()):
        if k not in ("meta", "limitations") and len(json.dumps(v, default=str)) > COMPACT_BYTES:
            trimmed.append({"key": k, "bytes": len(json.dumps(v, default=str))})
            r[k] = None
    if trimmed:
        r["trimmed"] = trimmed
    return r


def _call_isolated(module: str, attr: str, kwargs: dict[str, Any], timeout_s: int = 1800) -> dict[str, Any]:
    """Run ``module.attr(**kwargs)`` in a fresh Python process and return its JSON result. For an owner that forks a worker pool: forking after this process
    has loaded numpy, scipy and the other tracks' code can kill the workers (BrokenProcessPool) on macOS, so such an evaluation gets a clean process."""
    import os
    import subprocess
    import sys

    from ..store.paths import repo_root

    code = ("import json, sys\nfrom importlib import import_module\n"
            f"r = getattr(import_module({module!r}), {attr!r})(**{kwargs!r})\n"
            "sys.stdout.write('\\n@@JSON@@' + json.dumps(r, default=str))\n")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ), cwd=str(repo_root()), timeout=timeout_s)
    if proc.returncode != 0 or "@@JSON@@" not in proc.stdout:
        raise RuntimeError(f"{module}.{attr} failed in its own process (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-500:].strip()}")
    return json.loads(proc.stdout.split("@@JSON@@", 1)[1])


def _call_owner(ctx: Ctx, name: str, owner: str, module: str, attr: str, *, fallback_meta: Any = None, isolated: bool = False, **extra: Any) -> dict[str, Any]:
    """Call an owner's evaluator offline. ``fast`` is passed when it takes it; ``extra`` are keyword arguments (which win over ``fast``). ``fallback_meta`` is a
    dict, or a function of the owner's result, that fills any AnalyticMeta field the owner left out (never one it set). ``isolated`` runs it in a fresh process."""
    import inspect

    fn = owner_attr(owner, module, attr)
    params = inspect.signature(fn).parameters
    kw = ({"fast": ctx.fast} if "fast" in params else {}) | extra
    with _offline():
        r = _call_isolated(module, attr, kw) if isolated else fn(**kw)
    fb = fallback_meta(r) if callable(fallback_meta) else fallback_meta
    return _shape_generic(name, r, fallback_meta=fb)


def git(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "git", "git-analysis", "understudy_engine.gitanalysis.evaluate", "evaluate_git")


def proactive(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "proactive", "proactive", "understudy_engine.proactive.evaluate", "evaluate_proactive")


def calendar(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "calendar", "calendar", "understudy_engine.calendar.evaluate", "evaluate_calendar")


def localmodel(ctx: Ctx) -> dict[str, Any]:
    # force_live stays False and the call runs offline (mock on), so the local model is read from its recorded answers and never started here
    return _call_owner(ctx, "localmodel", "local-model", "understudy_engine.localmodel.evaluate", "evaluate_localmodel", force_live=False)


def _recorded(path: Path) -> dict[str, Any] | None:
    """A recorded result file (a frozen command's output, read here and never re-run). Symlinks and unreadable files are ignored."""
    try:
        if not path.is_file() or path.is_symlink():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _mlv2_recorded() -> dict[str, Any]:
    """Held-out and transfer results the mlv2 track wrote under evals/mlv2/results, read through the track's own loaders and slimmers; whatever has not
    been produced yet is simply absent (``heldout_log.jsonl`` says which frozen parts have run)."""
    import importlib

    mod = importlib.import_module("understudy_engine.mlv2.evaluate")
    out: dict[str, Any] = {"files": {}}
    held: dict[str, Any] = {}
    for part, fname, slim in (("hazard", "heldout_hazard.json", "slim_hazard"), ("genome", "heldout_genome.json", "slim_genome"), ("mismatch", "heldout_mismatch.json", "slim_mismatch")):
        res = mod._load(fname)
        out["files"][fname] = res is not None
        if res is not None:
            held[part] = {"fingerprint": mod._fingerprint_note(res, part), "result": getattr(mod, slim)(res)}
    if held:
        out["heldout"] = held
        out["verdicts"] = mod.verdict_table(*(mod._load(f) for f in ("heldout_hazard.json", "heldout_genome.json", "heldout_mismatch.json")))
    tr = mod._load("transfer_sim.json")
    out["files"]["transfer_sim.json"] = tr is not None
    if tr is not None:
        out["transfer_simulated_participants"] = tr
    try:
        from understudy_engine.mlv2 import freeze

        out["frozen"] = {k: v for k, v in (freeze.read_frozen() or {}).items() if not k.startswith("hazard_code")}
    except Exception:
        pass
    return out


def mlv2(ctx: Ctx) -> dict[str, Any]:
    """ML v2 (REQ-6). The owner's evaluator in the harness's own mode: ``fast`` only when the caller asked for ``--fast`` (the owner's fast mode is the dev
    numbers with a not_run scorecard); a normal run uses the full mode, which loads the frozen result files the track recorded under evals/mlv2/results
    (held-out hazard, genome and mismatch, the transfer result, and the pre-registered decision) and recomputes only the dev numbers. This adapter is
    read-only on those files: it never calls the held-out runner (``understudy_engine.mlv2.run``), which the track runs once, itself."""
    s = _call_owner(ctx, "mlv2", "mlv2", "understudy_engine.mlv2.evaluate", "evaluate_mlv2")
    if "status" in s:
        return s
    try:
        rec = _mlv2_recorded()
    except Exception as e:                          # the recorded results are an addition: their failure must not hide the dev numbers
        s["recorded_error"] = f"{type(e).__name__}: {e}"
        return s
    s["recorded"] = {k: v for k, v in rec.items() if k not in ("heldout", "verdicts", "transfer_simulated_participants", "frozen")}
    for k in ("heldout", "verdicts", "transfer_simulated_participants", "frozen"):
        if k in rec and k not in s:                  # the owner's full mode already carries these; fast mode does not
            s[k] = rec[k]
    return s


EVIDENCE_LIVE_COPY = ("evidence", "live_recorded.json")


def evidence(ctx: Ctx) -> dict[str, Any]:
    """Evidence quality (the explainer and its number-provenance check). ``with_live=False``: the harness never calls a model; the live results recorded
    on 7 Nov (real models, small n, synthetic packets) are read from the committed copy evals/evidence/live_recorded.json (the original,
    data/eval/evidence_live.json, is gitignored)."""
    s = _call_owner(ctx, "evidence", "evidence", "understudy_engine.evidence.evaluate", "evaluate_evidence", with_live=False)
    if "status" in s:
        return s
    rec = _recorded(evals_out_dir().joinpath(*EVIDENCE_LIVE_COPY))
    live = dict(s.get("live") or {})
    if rec is not None:
        live["recorded"] = rec
        live["recorded_source"] = "evals/evidence/live_recorded.json (copied from data/eval/evidence_live.json, which is gitignored)"
        live["label"] = "live, real models, small n; packets are synthetic; recorded 7 Nov, not re-run by make eval"
    else:
        live.pop("recorded", None)
        live["recorded_missing"] = "evals/evidence/live_recorded.json is absent, so no live result is shown"
    s["live"] = live
    return s


def cue(ctx: Ctx) -> dict[str, Any]:
    """Cue (the worker-facing hint). The owner's fast or dev path (never its held-out run) plus the held-out result its frozen command recorded in
    evals/cue/held_out.json, read here and never re-run."""
    s = _call_owner(ctx, "cue", "cue", "understudy_engine.cue.evaluate", "evaluate_cue", held_out=False)
    if "status" in s:
        return s
    rec = _recorded(evals_out_dir() / "cue" / "held_out.json")
    if rec is not None:
        s["held_out"] = {"source": "evals/cue/held_out.json (the frozen held-out command, run once; read here, never run by the harness)",
                         **{k: rec[k] for k in ("cue", "score_validation", "params", "meta") if k in rec}}
    return s


def attention(ctx: Ctx) -> dict[str, Any]:
    """Attention routing. The owner's dev or fast path (never ``held_out=True``) plus its recorded held-out report if the frozen command has produced one."""
    def fb(r: dict[str, Any]) -> dict[str, Any]:
        m = r.get("meta") or {}
        return {"n": m.get("n_workers"), "n_unit": "simulated workers", "split": f"{m.get('split', 'dev')} seeds {m.get('seeds')}; held-out is the owner's separate frozen command",
                "note": m.get("badge")}

    s = _call_owner(ctx, "attention", "attention", "understudy_engine.attention.evaluate", "evaluate_attention", fallback_meta=fb, held_out=False)
    if "status" in s:
        return s
    rec = _recorded(evals_out_dir() / "attention" / "report_held_out.json")
    if rec is not None:
        s["held_out"] = {"source": "evals/attention/report_held_out.json (the frozen held-out command; read here, never run by the harness)", **rec}
    return s


def insights(ctx: Ctx) -> dict[str, Any]:
    """Insights (pointers for workers and admins). The owner's dev-seed path only (``heldout=False``, always); a recorded held-out result is attached
    if one of the known files exists. The harness never runs the held-out seeds."""
    def fb(r: dict[str, Any]) -> dict[str, Any]:
        m = r.get("meta") or {}
        seeds = m.get("seed_list") or []
        return {"n": len(seeds) * int(m.get("people_per_firm") or 0), "n_unit": "synthetic people",
                "split": f"{m.get('seeds', 'dev')} seeds {seeds} ({len(seeds)} synthetic firms of {m.get('people_per_firm')} people); held-out seeds are run once by the owner (evals/insights/PLAN.md)",
                "note": m.get("badge")}

    s = _call_owner(ctx, "insights", "insights", "understudy_engine.insights.evaluate", "evaluate_insights", fallback_meta=fb, heldout=False)
    if "status" in s:
        return s
    for rel in ("heldout.json", "held_out.json", "results/heldout.json", "results/held_out.json"):
        rec = _recorded(evals_out_dir() / "insights" / rel)
        if rec is not None:
            s["held_out"] = {"source": f"evals/insights/{rel} (the held-out seeds, run once; read here, never run by the harness)", **rec}
            break
    return s


def hitlist(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "hitlist", "hitlist", "understudy_engine.hitlist.evaluate", "evaluate_hitlist")


REALISM_FAMILIES = ("v1", "markov", "latent_skill", "process_trace")
REALISM_BLOCK_KINDS = ("hazard", "routines", "genome")


def _est(e: Any) -> dict[str, Any]:
    e = e or {}
    return {"est": e.get("est"), "ci": e.get("ci") or [None, None]}


def _hazard_block_summary(d: dict[str, Any]) -> dict[str, Any]:
    """One recorded realism hazard block (fit family -> test family cells) as the numbers the findings and the page need, classified by the kind of cell."""
    cells = (d.get("result") or {}).get("cells") or {}
    v2 = [f for f in REALISM_FAMILIES if f != "v1"]
    table = {k: {"h1": _est((c.get("metrics") or {}).get("h1")), "fa_per_h": _est((c.get("metrics") or {}).get("fa_per_h")), "detection": _est((c.get("metrics") or {}).get("detection")),
                 "fa_over_budget": bool(c.get("fa_over_budget")), "no_skill": bool(c.get("no_skill")), "n_people": c.get("n_people"),
                 "verdict_vs_diagonal": ((c.get("delta_vs_diagonal") or {}).get("h1") or {}).get("verdict")} for k, c in cells.items()}

    def count(keys: list[str]) -> dict[str, int]:
        keys = [k for k in keys if k in table]
        return {"n": len(keys), "over": sum(1 for k in keys if table[k]["fa_over_budget"])}

    off = [f"{x}->{y}" for x in v2 for y in v2 if x != y]
    return {
        "v1_own": table.get("v1->v1") or {"h1": {"est": None, "ci": [None, None]}},
        "v2_diagonals": {f: table[f"{f}->{f}"]["h1"] for f in v2 if f"{f}->{f}" in table},
        "v1_trained_on_v2": {f: table[f"v1->{f}"]["h1"] for f in v2 if f"v1->{f}" in table},
        "false_alarm_over_budget": {"v2_off_diagonal": count(off), "v2_diagonal": count([f"{f}->{f}" for f in v2]), "v1_to_v2": count([f"v1->{f}" for f in v2]),
                                    "v2_to_v1": count([f"{f}->v1" for f in v2]), "budget_per_hour": 1.0},
        "no_skill_cells": sorted(k for k, c in table.items() if c["no_skill"]),
        "n_people_v1_cell": (table.get("v1->v1") or {}).get("n_people"), "n_people_v2_cell": (table.get(f"{v2[0]}->{v2[0]}") or {}).get("n_people"),
        "partial": d.get("partial"), "cells": table,
    }


def _generic_block_summary(d: dict[str, Any]) -> dict[str, Any]:
    cells = (d.get("result") or {}).get("cells") or {}
    return {"partial": d.get("partial"), "cells": {k: {m: _est(v) for m, v in ((c.get("metrics") or {}).items()) if isinstance(v, dict) and "est" in v} | {"verdicts": {m: (x or {}).get("verdict") for m, x in (c.get("delta_vs_diagonal") or {}).items()}}
                                                    for k, c in cells.items()}}


def _genome_block_summary(d: dict[str, Any]) -> dict[str, Any]:
    """One recorded realism genome block (deficit detection; fit family -> test family): precision, recall, the gap estimate and the false attribution to deficits
    that are absent, classified by the kind of cell. The per-deficit columns stay in the recorded file."""
    cells = (d.get("result") or {}).get("cells") or {}
    v2 = [f for f in REALISM_FAMILIES if f != "v1"]
    keys = ("precision", "recall", "gap_s", "false_attr_s")
    table = {k: {m: _est((c.get("metrics") or {}).get(m)) for m in keys} | {"n_people": c.get("n_people"), "verdicts": {m: ((c.get("delta_vs_diagonal") or {}).get(m) or {}).get("verdict") for m in ("precision", "recall")}}
             for k, c in cells.items()}
    pick = lambda fmt: {f: table[fmt(f)] for f in v2 if fmt(f) in table}  # noqa: E731
    return {
        "v1_own": table.get("v1->v1"), "v2_diagonals": pick(lambda f: f"{f}->{f}"), "v1_trained_on_v2": pick(lambda f: f"v1->{f}"), "v2_trained_on_v1": pick(lambda f: f"{f}->v1"),
        "n_people_v1_cell": (table.get("v1->v1") or {}).get("n_people"), "n_people_v2_cell": (table.get(f"{v2[0]}->{v2[0]}") or {}).get("n_people"),
        "partial": d.get("partial"), "cells": table,
    }


def _routines_block_summary(d: dict[str, Any]) -> dict[str, Any]:
    """One recorded realism routines block: raw cluster precision (R1), recall (R2) and proposal precision after the gate (R3), for thresholds fitted per family
    ('fitted') and for the thresholds the product ships ('shipped', which cannot depend on the fit family)."""
    res = d.get("result") or {}
    cells = res.get("cells") or {}
    keys = ("r1_precision", "r2_recall", "r3_proposal_precision", "clusters_per_person", "proposals_per_person")
    out: dict[str, Any] = {"fitted": {}, "shipped": {}}
    for k, c in cells.items():
        mode, _, pair = k.partition(":")
        if mode not in out or "->" not in pair:
            continue
        out[mode][pair] = {m: _est((c.get("metrics") or {}).get(m)) for m in keys} | {"n_people": c.get("n_people")}
    shipped = out["shipped"]
    tests = sorted({p.split("->")[1] for p in shipped})
    same = all(len({json.dumps({m: shipped[p][m] for m in keys[:3]}, sort_keys=True) for p in shipped if p.endswith(f"->{t}")}) == 1 for t in tests) if shipped else None
    out["shipped_identical_across_fit_family"] = same
    out["shipped_by_test_family"] = {t: shipped[next(p for p in sorted(shipped) if p.endswith(f"->{t}"))] for t in tests}
    out["tuned_threshold"] = res.get("tuned_threshold")
    out["partial"] = d.get("partial")
    return out


def _realism_blocks(root: Path) -> dict[str, Any]:
    """The finished blocks the realism track recorded under data/eval/realism_blocks (``<kind>_<role>.json``; fast_* files are its own smoke runs and are skipped)."""
    out: dict[str, dict[str, Any]] = {k: {} for k in REALISM_BLOCK_KINDS}
    d = root / "eval" / "realism_blocks"
    if not d.is_dir():
        return {}
    for f in sorted(d.glob("*.json")):
        kind, _, role = f.stem.partition("_")
        if kind not in REALISM_BLOCK_KINDS or not role:
            continue
        rec = _recorded(f)
        if rec is None:
            continue
        summarise = {"hazard": _hazard_block_summary, "genome": _genome_block_summary, "routines": _routines_block_summary}.get(kind, _generic_block_summary)
        out[kind][role] = summarise(rec)
    return {k: v for k, v in out.items() if v}


def realism(ctx: Ctx) -> dict[str, Any]:
    """Persona realism (personas v2). The owner's fast path always (the full evaluation is the track's own multi-minute command), plus the finished blocks and
    the leave-one-person-out result it recorded under data/eval, read and never recomputed."""
    try:     # its worker pool forks, so it runs in its own process; it also shares an on-disk cache with the track's long runs, so one transient failure is retried once
        s = _call_owner(ctx, "realism", "personas-v2", "understudy_engine.personas_v2.evaluate", "evaluate_realism", isolated=True, fast=True)
    except NotLanded:
        raise
    except Exception:
        s = _call_owner(ctx, "realism", "personas-v2", "understudy_engine.personas_v2.evaluate", "evaluate_realism", isolated=True, fast=True)
    if "status" in s:
        return s
    root = resolve_root(ctx.root)
    blocks = _realism_blocks(root)
    if blocks:
        s["blocks"] = blocks
        s["blocks_source"] = "data/eval/realism_blocks/<kind>_<role>.json (the track's own full-size blocks; read here, never run by the harness)"
    rep = evals_out_dir() / "realism" / "REPORT.md"
    if rep.is_file() and not rep.is_symlink():              # the track's assembled write-up: linked by path and hash, never copied into this report
        s["report_file"] = {"path": "evals/realism/REPORT.md", "sha256": hashlib.sha256(rep.read_bytes()).hexdigest(), "bytes": rep.stat().st_size,
                            "note": "assembled by the realism track from the same recorded blocks; this report reads the blocks directly"}
    rec = _recorded(root / "eval" / "realism_lopo.json")
    if rec is not None:
        s["lopo_recorded"] = {"source": "data/eval/realism_lopo.json (the track's own leave-one-person-out run; read here, never run by the harness)", **rec}
    return s


def _read_json_file(owner: str, path: Path, how: str, shown: str) -> dict[str, Any]:
    if not path.is_file():
        raise Skipped(f"{owner} not landed: {shown} is absent ({how}); `make eval` reads results and never runs models")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return data


def runtime(ctx: Ctx) -> dict[str, Any]:
    """The agent runtime evaluation, read from the file the agent track writes (``python -m understudy_agent.runtime.evaluate``)."""
    r = _read_json_file("agent-runtime", resolve_root(ctx.root) / "eval" / "runtime_eval.json", "the agent track writes it with `python -m understudy_agent.runtime.evaluate`", "data/eval/runtime_eval.json")
    return _real_claim_needs_manifest("runtime", resolve_root(ctx.root) / "eval", r) or _shape_generic("runtime", r, fallback_meta={"n_unit": "runs"})


def modelbench(ctx: Ctx) -> dict[str, Any]:
    r = _read_json_file("modelbench", resolve_root(ctx.root) / "eval" / "modelbench.json", "the model-benchmark track writes it", "data/eval/modelbench.json")
    return _real_claim_needs_manifest("modelbench", resolve_root(ctx.root) / "eval", r) or _shape_generic("modelbench", r)


def _dir_section(owner: str, d: Path, attrs: tuple[str, ...], files: tuple[str, ...]) -> dict[str, Any]:
    """A section an owner publishes from a directory under evals/: a function in the package, else a results file."""
    if not d.is_dir():
        raise NotLanded(owner, f"evals/{d.name} does not exist yet")
    fn = None
    for attr in attrs:
        try:
            fn = _find_in_dir(owner, d, attr)
            break
        except NotLanded:
            continue
    if fn is not None:
        try:
            with _repo_on_path(), _offline():
                return dict(fn())
        except ModuleNotFoundError as e:
            if (e.name or "").startswith(f"_understudy_{d.name}_"):
                raise NotLanded(owner, f"evals/{d.name}/{(e.name or '').rsplit('.', 1)[-1]}.py does not exist yet") from e
            raise
    for f in files:
        p = d / f
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise NotLanded(owner, f"evals/{d.name} has none of {', '.join(attrs)}() or {', '.join(files)} yet")


def _real_claim_needs_manifest(name: str, d: Path, r: dict[str, Any]) -> dict[str, Any] | None:
    """A section may call its data 'real' or 'mixed' (people) only with a hand-written manifest saying human, no symlinks, and no sign of a simulation.
    Returns a stub when the claim is not backed, else None."""
    origin = _g(r, "meta", "origin", default=r.get("origin"))
    if origin not in ("real", "mixed"):
        return None
    meta = normalise_meta(r.get("meta"), {"origin": "unknown", "n": r.get("n"), "n_unit": r.get("n_unit")})
    meta["origin"] = "unknown"

    def stub(reason: str) -> dict[str, Any]:
        return {"status": "invalid_provenance", "reason": reason, "meta": meta}

    bad = _symlink_in(d, d.parent) if d.exists() or d.is_symlink() else None
    if bad is not None:
        return stub(f"{bad.parent.name}/{bad.name} is a symlink, so its results cannot be shown as people's data")
    if (d / MANIFEST).is_symlink():
        return stub(f"{d.name}/{MANIFEST} is a symlink")
    m, problem = _read_manifest(d)
    if problem:
        return stub(f"{name} claims origin {origin!r} but {problem}")
    if m is None:
        return stub(f"{name} claims origin {origin!r} but there is no hand-written {d.name}/{MANIFEST} (origin human, consent_ref, collected_by, n_participants, date)")
    ids = [str(x.get("participant", "")) for x in (r.get("rows") or []) if isinstance(x, dict)]
    cols = sorted({c for x in (r.get("rows") or []) if isinstance(x, dict) for c in x})
    signs = _sim_signs(cols, ids)
    if signs:
        return stub(f"{name} claims origin {origin!r} but looks simulated ({'; '.join(signs)})")
    return None


def study_roles(ctx: Ctx) -> dict[str, Any]:
    """Role-pack study results (study-roles track). Never the live `study`: that section is people only and does not read this. An origin of real or
    mixed is accepted only with a hand-written manifest (see ``_real_claim_needs_manifest``). With no study results the section is not_run and shows the
    feasibility pilots the owner recorded (``results/<role>/PILOT_*.json``), saying plainly that the study itself has not been run."""
    from . import agentic as ag

    d = evals_out_dir() / "study_roles"
    r = _dir_section("study-roles", d, ("study_roles_section", "section"), ("section.json", "summary.json", "results/summary.json"))
    guard = _real_claim_needs_manifest("study_roles", d, r)
    if guard:
        return guard
    pilots = r.get("pilots") if isinstance(r.get("pilots"), dict) else {}
    s = _shape_generic("study_roles", r)
    if not pilots:
        return s
    extras = ag.study_roles_extras(pilots, (d / "PLAN.md").read_text(encoding="utf-8") if (d / "PLAN.md").is_file() else "")
    s.update(pilots=extras["pilots"], study_run=extras["study_run"] if s.get("status") == "not_run" else s.get("study_run", True), go_ahead=extras["go_ahead"])
    if s.get("status") == "not_run":
        s["reason"] = f"{extras['pilot_text']} Go-ahead: {extras['go_ahead']['where']}; needs {extras['go_ahead']['needs']}."
    s["limitations"] = [*(s.get("limitations") or []), {"id": "study-roles-pilots-only", "severity": "high", "source": "study_roles",
                                                        "text": f"{extras['pilot_text']} The go-ahead is described in {extras['go_ahead']['where']}."}]
    return s


def agentic(ctx: Ctx) -> dict[str, Any]:
    """The agent evaluation, read from the recorded files under evals/agentic/results only (offline long-horizon suites, the held-out confirmation, the spend
    ledger); a held-out part with no file yet says 'not run yet'. See ``agentic.py`` for the claim wording."""
    from . import agentic as ag

    root = evals_out_dir() / "agentic"
    if not root.is_dir():
        raise NotLanded("agentic", "evals/agentic does not exist yet")
    r = ag.build(root)
    if r is None:
        raise NotLanded("agentic", "evals/agentic/results has none of lh_offline.json, heldout_*.json, spend_ledger.json yet")
    s = _shape_generic("agentic", r)
    s["meta"]["origin_detail"] = ag.ORIGIN_TEXT
    return s


# ---------------------------------------------------------------------------------------------------------------- table
@dataclass(frozen=True)
class SectionSpec:
    name: str
    owner: str
    fn: Callable[[Ctx], dict[str, Any]]
    needs_synthetic: bool = True


SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("deficit_recovery", "engine-eval (engine-data genome)", deficit_recovery),
    SectionSpec("null_placebo", "engine-eval (engine-data genome)", null_placebo),
    SectionSpec("hazard", "engine-analytics", hazard),
    SectionSpec("policy_gate", "engine-analytics", policy_gate),
    SectionSpec("skills", "engine-analytics", skills),
    SectionSpec("ope", "engine-analytics", ope),
    SectionSpec("routing", "engine-analytics", routing),
    SectionSpec("ski_rental", "engine-handoff", ski_rental),
    SectionSpec("presence", "engine-handoff", presence),
    SectionSpec("routines", "engine-handoff", routines),
    SectionSpec("forecast", "engine-handoff", forecast),
    SectionSpec("agent_claims", "engine-analytics", agent_claims),
    SectionSpec("agent_runs", "agent-core", agent_runs, needs_synthetic=False),
    SectionSpec("pooling", "engine-analytics", pooling),
    SectionSpec("redteam", "agent-safety", redteam, needs_synthetic=False),
    SectionSpec("redteam_live", "agent-safety", redteam_live, needs_synthetic=False),
    SectionSpec("privacy", "privacy-layer", privacy, needs_synthetic=False),
    SectionSpec("git", "git-analysis", git, needs_synthetic=False),
    SectionSpec("proactive", "proactive", proactive, needs_synthetic=False),
    SectionSpec("calendar", "calendar", calendar, needs_synthetic=False),
    SectionSpec("localmodel", "local-model", localmodel, needs_synthetic=False),
    SectionSpec("runtime", "agent-runtime", runtime, needs_synthetic=False),
    SectionSpec("mlv2", "mlv2", mlv2, needs_synthetic=False),
    SectionSpec("evidence", "evidence", evidence, needs_synthetic=False),
    SectionSpec("cue", "cue", cue, needs_synthetic=False),
    SectionSpec("realism", "personas-v2", realism, needs_synthetic=False),
    SectionSpec("attention", "attention", attention, needs_synthetic=False),
    SectionSpec("insights", "insights", insights, needs_synthetic=False),
    SectionSpec("hitlist", "hitlist", hitlist, needs_synthetic=False),
    SectionSpec("modelbench", "modelbench", modelbench, needs_synthetic=False),
    SectionSpec("study_roles", "study-roles", study_roles, needs_synthetic=False),
    SectionSpec("agentic", "agentic", agentic, needs_synthetic=False),
    SectionSpec("study", "platform", study, needs_synthetic=False),
    SectionSpec("study_sim", "study-sim", study_sim, needs_synthetic=False),
    SectionSpec("study_power", "engine-analytics", study_power, needs_synthetic=False),
)
SECTION_NAMES = tuple(s.name for s in SECTIONS)
