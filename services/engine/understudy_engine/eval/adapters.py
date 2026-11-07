"""One adapter per report section: call the owning track's code, reshape to docs/API_CONTRACT.md, never invent a number.

Every adapter takes a ``Ctx`` and returns the section dict (with ``meta``). Anything the owner cannot give us yet is
reported as ``pending`` by ``assemble`` (``NotLanded`` is raised when the owner's module or entry point is missing).
Contract keys are always present; extra keys are additive (the dashboard tolerates them) and a few aliases carry the
names the dashboard's fixture uses until it follows the contract.
"""
from __future__ import annotations

import contextlib
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
    cum = cost.get("cumulative_in_this_file") or {}
    runs = raw.get("runs") or []
    t3 = raw.get("tier3_simulated") or {}
    t3_runs = t3.get("runs") or []
    clean = v1["clean"]
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
    return {
        "label": "real model", "headline_condition": "clean",
        "n": clean["n"], "pass": clean["pass"], "wilson": clean["wilson"], "tiers": sorted({t for c in v1.values() for t in c["tiers"]}),
        "false_claims": all_false, "cost_usd_est": cum.get("usd_at_assumed_rates", cost.get("estimated_usd")),
        "note": ("Real model, small n: 20 households per condition shows the pipeline and its failure modes with a live model, not a pass rate. "
                 + str(meta.get("note") or "")).strip(),
        "households": meta.get("households"), "runs_total": meta.get("n"), "models": meta.get("models"),
        "conditions": v1, "glitch_fix": glitch_fix,
        "tier3": {"simulated_actuator": True, "runs": len(t3_runs), "pointer_actions": t3.get("pointer_actions"), "landed_on_interactive": t3.get("landed_on_interactive"),
                  "outcomes": sorted({r.get("outcome") for r in t3_runs if r.get("outcome")}), "note": t3.get("note")},
        "cost": {"estimated_usd_this_run": cost.get("estimated_usd"), "cumulative_usd_at_assumed_rates": cum.get("usd_at_assumed_rates"),
                 "tokens_in": cum.get("tokens_in"), "tokens_out": cum.get("tokens_out"), "price_assumption_usd_per_million": meta.get("price_assumption_usd_per_million"),
                 "live_calls_in_rows": sum(int(r.get("live_calls") or 0) for r in runs), "cache_hits_in_rows": sum(int(r.get("cache_hits") or 0) for r in runs),
                 "unique_prompts_cached": cost.get("unique_prompts_cached"), "note": cum.get("note")},
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
    false_claims = sum(x["false_claims"] or 0 for x in (c, rb, live) if x)
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
def privacy(ctx: Ctx) -> dict[str, Any]:
    """The privacy layer's own offline evaluation (canary leaks, ledger completeness, negative controls, bucketing). Needs no model.
    ``record=False``: the harness writes only its two report files, never the layer's summary file."""
    fn = owner_attr("privacy-layer", "understudy_engine.privacy.evaluate", "evaluate_privacy")
    r = dict(fn(record=False, seeds=tuple(range(3 if ctx.fast else 8))))          # fewer seeds per flow in --fast; the structure is the same
    r["meta"] = normalise_meta(r.get("meta"), {"origin": r.get("origin", "synthetic"), "n": r.get("n"), "n_unit": r.get("n_unit"), "split": r.get("split")})
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


def _study_analysis(study_dir: Path) -> dict[str, Any] | None:
    """The analysis dict: computed fresh from participants.csv with the pre-registered script, else the summary.json it wrote."""
    csv_path = study_dir / "results" / "participants.csv"
    if csv_path.is_file():
        mod = _load_analyzer(study_dir)
        if mod is None:
            raise NotLanded("platform", "evals/study/analyze.py missing, cannot analyse participants.csv")
        rows = mod.load(csv_path)
        if not rows:
            return None
        asg = study_dir / "assignments.json"
        return mod.analyse(rows, json.loads(asg.read_text()) if asg.is_file() else None)
    summary = study_dir / "results" / "summary.json"
    if summary.is_file():
        data = json.loads(summary.read_text())
        if _g(data, "meta", "origin") not in (None, "real"):
            return None        # anything not marked real is never shown as the live study (simulated participants live in `study_sim`)
        return data
    return None


def study(ctx: Ctx) -> dict[str, Any]:
    """Live study (n = 4), exactly as ANALYSIS_PLAN.md pre-registered it. LIVE HUMANS ONLY: this never reads `study_sim`. The headline is the UNASSISTED skill score on a later
    matched case (coached skill minus uncoached skill, per participant); assisted speed is reported beside it, never combined.

    Contract keys the dashboard reads are filled honestly from the secondary unassisted-time measure: ``unassisted_before_s`` is the post-test
    time after the UNCOACHED skill block, ``unassisted_after_s`` after the COACHED block, ``mean_change_s`` their mean difference."""
    study_dir = evals_out_dir() / "study"
    a = _study_analysis(study_dir)
    default = make_meta("real", STUDY_N, "people", "within-subject, counterbalanced, teammates only",
                        note="n = 4. Treat every number here as a case study, not a result.")
    if not a or not a.get("headline_unassisted", {}).get("blocks"):
        return {"status": "not_run", "reason": "the live study has not been run: no data in evals/study/results/", "n": STUDY_N, "rows": [], "meta": default}
    meta = normalise_meta(a.get("meta"), default)
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

    Forced to origin ``synthetic`` and labelled "simulated participants (language model), not people" wherever it appears."""
    d = evals_out_dir() / "study_sim"
    fn = _find_in_dir("study-sim", d, "study_sim_section")
    try:
        with _repo_on_path():
            r = dict(fn())
    except ModuleNotFoundError as e:
        if (e.name or "").startswith("_understudy_study_sim_"):         # the package's own lazy import of a module that is not written yet
            raise NotLanded("study-sim", f"evals/study_sim/{(e.name or '').rsplit('.', 1)[-1]}.py does not exist yet") from e
        raise
    meta = normalise_meta(r.get("meta"), {"origin": "synthetic", "n": r.get("n"), "n_unit": "runs"})
    meta["origin"] = "synthetic"
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
    if r.get("status") in ("pending", "not_run", "failed") and not r.get("reason"):
        r["reason"] = (meta.get("note") or "the simulated study has not been run").strip()      # a stub needs a reason; the owner's note says why
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
    r["limitations"] = _limits(r)
    r["caveats"] = _caveats(r)
    r["headline_power"] = _power_headline(r)
    return r


# ------------------------------------------------------------------------------------------------- newer owner sections
OWNER_STUB_STATUSES = ("pending", "not_run", "failed")
TIMING_KEYS = ("elapsed_s", "wall_s")          # how long the owner's own evaluation took: not a result, and not deterministic
COMPACT_BYTES = 60_000                         # a top-level key bigger than this is replaced and listed under `trimmed`


@contextlib.contextmanager
def _offline():
    """Owner code that can reach a model honours UNDERSTUDY_MOCK (the project-wide offline switch, NFR-2). The harness never calls a model, so every
    newer owner section runs with it on, whatever the caller's environment says (the report's own ``mock`` flag is read before this)."""
    import os

    old = os.environ.get("UNDERSTUDY_MOCK")
    os.environ["UNDERSTUDY_MOCK"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("UNDERSTUDY_MOCK", None)
        else:
            os.environ["UNDERSTUDY_MOCK"] = old


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


def _call_owner(ctx: Ctx, name: str, owner: str, module: str, attr: str, **extra: Any) -> dict[str, Any]:
    import inspect

    fn = owner_attr(owner, module, attr)
    params = inspect.signature(fn).parameters
    kw = ({"fast": ctx.fast} if "fast" in params else {}) | extra
    with _offline():
        r = fn(**kw)
    return _shape_generic(name, r)


def git(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "git", "git-analysis", "understudy_engine.gitanalysis.evaluate", "evaluate_git")


def proactive(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "proactive", "proactive", "understudy_engine.proactive.evaluate", "evaluate_proactive")


def calendar(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "calendar", "calendar", "understudy_engine.calendar.evaluate", "evaluate_calendar")


def localmodel(ctx: Ctx) -> dict[str, Any]:
    # force_live stays False and the call runs offline (mock on), so the local model is read from its recorded answers and never started here
    return _call_owner(ctx, "localmodel", "local-model", "understudy_engine.localmodel.evaluate", "evaluate_localmodel", force_live=False)


def mlv2(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "mlv2", "mlv2", "understudy_engine.mlv2.evaluate", "evaluate_mlv2")


def evidence(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "evidence", "evidence", "understudy_engine.evidence.evaluate", "evaluate_evidence")


def cue(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "cue", "cue", "understudy_engine.cue.evaluate", "evaluate_cue")


def realism(ctx: Ctx) -> dict[str, Any]:
    return _call_owner(ctx, "realism", "personas-v2", "understudy_engine.personas_v2.evaluate", "evaluate_realism")


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
    return _shape_generic("runtime", r, fallback_meta={"n_unit": "runs"})


def modelbench(ctx: Ctx) -> dict[str, Any]:
    r = _read_json_file("modelbench", resolve_root(ctx.root) / "eval" / "modelbench.json", "the model-benchmark track writes it", "data/eval/modelbench.json")
    return _shape_generic("modelbench", r)


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


def study_roles(ctx: Ctx) -> dict[str, Any]:
    """Role-pack study results (study-roles track). Never the live `study`: that section is people only and does not read this."""
    r = _dir_section("study-roles", evals_out_dir() / "study_roles", ("study_roles_section", "section"), ("section.json", "summary.json", "results/summary.json"))
    return _shape_generic("study_roles", r)


def agentic(ctx: Ctx) -> dict[str, Any]:
    r = _dir_section("agentic", evals_out_dir() / "agentic", ("agentic_section", "section"), ("section.json", "summary.json", "results/summary.json", "report.json"))
    return _shape_generic("agentic", r)


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
    SectionSpec("modelbench", "modelbench", modelbench, needs_synthetic=False),
    SectionSpec("study_roles", "study-roles", study_roles, needs_synthetic=False),
    SectionSpec("agentic", "agentic", agentic, needs_synthetic=False),
    SectionSpec("study", "platform", study, needs_synthetic=False),
    SectionSpec("study_sim", "study-sim", study_sim, needs_synthetic=False),
    SectionSpec("study_power", "engine-analytics", study_power, needs_synthetic=False),
)
SECTION_NAMES = tuple(s.name for s in SECTIONS)
