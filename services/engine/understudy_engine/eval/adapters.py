"""One adapter per report section: call the owning track's code, reshape to docs/API_CONTRACT.md, never invent a number.

Every adapter takes a ``Ctx`` and returns the section dict (with ``meta``). Anything the owner cannot give us yet is
reported as ``pending`` by ``assemble`` (``NotLanded`` is raised when the owner's module or entry point is missing).
Contract keys are always present; extra keys are additive (the dashboard tolerates them) and a few aliases carry the
names the dashboard's fixture uses until it follows the contract.
"""
from __future__ import annotations

import importlib
import json
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
    allow_live: bool = False
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


def _injected(robust: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """What was injected, per pattern, from agent-core's own plan (``benefits_eval.robust_switches``) and what happened to those households."""
    try:
        plan_fn = owner_attr("agent-core", "understudy_agent.benefits_eval", "robust_switches")
    except NotLanded as e:
        return [], f"the injection plan is not available ({e})"
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
            live = _run_block(live_raw)
            cost = live_raw.get("cost_usd_est", _g(live_raw, "meta", "cost_usd_est", default=_g(live_raw, "cost", "usd_est")))
            live.update({"cost_usd_est": cost, "label": "real model",
                         "note": "Real model, small n: these runs show the pipeline works with a live model, not a pass rate. " + str(_g(live_raw, "meta", "note", default=""))})
        except (KeyError, TypeError, ValueError) as e:
            live, live_error = None, f"{AGENT_LIVE} is present but could not be read: {type(e).__name__}: {e}"
    runs = c["n"] + (rb["n"] if rb else 0) + (live["n"] if live else 0)
    false_claims = sum(x["false_claims"] or 0 for x in (c, rb, live) if x)
    out = {
        "meta": make_meta(
            "synthetic", runs, "runs",
            f"{c['n']} sandbox households run on the clean path" + (", and again with failures injected (layout changes, one-off 503s)" if rb else "")
            + ("; plus a small real-model block" if live else "") + "; local sandbox calculators, deterministic mock model, simplified oracle",
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


def redteam_live(ctx: Ctx) -> dict[str, Any]:
    fn = owner_attr("agent-safety", "understudy_agent.security.redteam_runner", "evaluate_redteam_live")
    if not ctx.allow_live:
        raise Skipped("the live red team calls a real model, so `make eval` stays offline and leaves it out "
                      "(set UNDERSTUDY_EVAL_LIVE=1, with a model key and without UNDERSTUDY_MOCK, to include it)")
    r = fn()
    rows = [dict(x, label=_ablation_label(str(x.get("ablation")))) for x in (r.get("rows") or [])]
    return {"meta": normalise_meta(r.get("meta")), "rows": rows, "false_pause_rate": r.get("false_pause_rate"),
            "false_pause_ci": r.get("false_pause_ci"), "limitations": _limits(r)}


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
        return json.loads(summary.read_text())
    return None


def study(ctx: Ctx) -> dict[str, Any]:
    """Live study (n = 4), exactly as ANALYSIS_PLAN.md pre-registered it. The headline is the UNASSISTED skill score on a later
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
    SectionSpec("study", "platform", study, needs_synthetic=False),
)
SECTION_NAMES = tuple(s.name for s in SECTIONS)
