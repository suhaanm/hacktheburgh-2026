"""One adapter per report section: call the owning track's code, reshape to docs/API_CONTRACT.md, never invent a number.

Every adapter takes a ``Ctx`` and returns the section dict (with ``meta``). Anything the owner cannot give us yet is
reported as ``pending`` by ``assemble`` (``NotLanded`` is raised when the owner's module or entry point is missing).
Contract keys are always present; extra keys are additive (the dashboard tolerates them) and a few aliases carry the
names the dashboard's fixture uses until it follows the contract.
"""
from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import deficit as deficit_mod
from .data import evals_out_dir, resolve_root
from .meta import make_meta, normalise_meta
from .stats import rnd, t_interval, wilson


class NotLanded(Exception):
    """The owner's module or entry point does not exist (yet)."""

    def __init__(self, owner: str, detail: str):
        super().__init__(f"{owner} not landed ({detail})")
        self.owner, self.detail = owner, detail


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
    r["per_persona"] = {n: {"map_brier": _g(p, "by_split", "forward", "map", "model", "brier"),
                            "window_brier": _g(p, "by_split", "forward", "window", "model", "brier"),
                            "interruption_rate": _g(p, "by_split", "forward", "decision", "rule", "interruption_rate"),
                            "idle_time_used": _g(p, "by_split", "forward", "decision", "rule", "share_idle_used")}
                        for n, p in (pres.get("personas") or {}).items()}
    r["limitations"] = _limits(pres)
    return r


def routines(ctx: Ctx) -> dict[str, Any]:
    fin = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "evaluate_finder")
    rep = owner_attr("engine-handoff", "understudy_engine.routines.evaluate", "routines_report")
    f = fin(ctx.root)
    r = dict(rep(f))
    r["meta"] = normalise_meta(r.get("meta"))
    r["metrics"] = f.get("metrics")
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
    out = {
        "meta": normalise_meta(r.get("meta")),
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
        raise NotLanded("agent-safety", "evaluate_redteam_live exists but calls a real model; `make eval` stays offline "
                                        "(set UNDERSTUDY_EVAL_LIVE=1 and a model key to include it)")
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


def _study_files(results: Path) -> list[Path]:
    return sorted(p for p in results.glob("*") if p.is_file() and p.suffix in (".json", ".csv") and not p.name.startswith("."))


def _read_rows(p: Path) -> list[dict[str, Any]]:
    if p.suffix == ".json":
        d = json.loads(p.read_text())
        if isinstance(d, dict):
            d = d.get("rows") or d.get("participants") or []
        return [x for x in d if isinstance(x, dict)]
    import csv

    with p.open() as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def study(ctx: Ctx) -> dict[str, Any]:
    """Live study (n = 4). Reads ``evals/study/results/*.json|csv`` with rows
    ``{participant, unassisted_before_s, unassisted_after_s}``. Absent results are a plain ``not_run``."""
    results = evals_out_dir() / "study" / "results"
    files = _study_files(results) if results.is_dir() else []
    meta = make_meta("real", STUDY_N, "people", "within-subject, counterbalanced, teammates only",
                     note="n = 4. Treat every number here as a case study, not a result.")
    rows: list[dict[str, Any]] = []
    for p in files:
        for x in _read_rows(p):
            try:
                rows.append({"participant": str(x["participant"]), "unassisted_before_s": float(x["unassisted_before_s"]),
                             "unassisted_after_s": float(x["unassisted_after_s"])})
            except (KeyError, TypeError, ValueError):
                continue
    if not rows:
        return {"status": "not_run", "reason": "the live study has not been run: no rows in evals/study/results/", "n": STUDY_N, "rows": [], "meta": meta}
    changes = [r["unassisted_after_s"] - r["unassisted_before_s"] for r in rows]
    n = len(rows)
    meta["n"] = n
    meta["note"] = (f"n = {n}. Treat every number here as a case study, not a result. Mean change in unassisted time on a later matched task "
                    "(after minus before; negative is faster); interval is a Student-t interval on the paired differences (df = n - 1), "
                    "wider than a bootstrap at this size. Assisted speed is reported separately.")
    return {"meta": meta, "rows": rows, "mean_change_s": rnd(sum(changes) / n, 2), "mean_change_ci": t_interval(changes, nd=2), "n": n}


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
    SectionSpec("pooling", "engine-analytics", pooling),
    SectionSpec("redteam", "agent-safety", redteam, needs_synthetic=False),
    SectionSpec("redteam_live", "agent-safety", redteam_live, needs_synthetic=False),
    SectionSpec("study", "platform", study, needs_synthetic=False),
)
SECTION_NAMES = tuple(s.name for s in SECTIONS)
