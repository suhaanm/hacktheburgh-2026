"""Evaluation of the attention layer (REQ-8, NFR-11): ``evaluate_attention(fast=False, held_out=False) -> dict``.

Pre-registered in ``evals/attention/PLAN.md`` (committed before any run). SYNTHETIC end to end: simulated workers, schedules from the
synthetic personas, event streams at assumed producer rates, an assumed reaction model and an assumed attention-cost model (all in
``simulate.py``). It shows that the router behaves as designed under those assumptions. It does not show that real people find the product
natural; the live check with the four teammates (n = 4) is the real test and is not run here.

Conditions R, R-nolearn, B1 (show everything at once), B2 (one daily digest). One timeline and one event stream per worker, replayed under
every condition, so differences are paired per worker. Intervals are percentile bootstraps that resample WORKERS (a worker's days travel
together), 95%.

Dev and held-out: parameters are tuned on dev seeds only (``tune_on_dev``), one factor at a time, by the rule in the plan, and then frozen
(``freeze_config`` writes ``evals/attention/frozen_config.json`` and its hash). ``held_out=True`` refuses to run without that file and uses
exactly what it holds. A number printed from a held-out run is never fed back into a choice.

CLI::

    python -m understudy_engine.attention.evaluate --fast
    python -m understudy_engine.attention.evaluate --dev [--out evals/attention/report_dev.json]
    python -m understudy_engine.attention.evaluate --tune            # dev only; prints the selection; writes nothing frozen
    python -m understudy_engine.attention.evaluate --freeze          # writes the frozen config from the dev tuning result
    python -m understudy_engine.attention.evaluate --held-out        # needs the frozen config
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np

from . import scenarios as SC
from . import vocab as V
from .paths import repo_root
from .simulate import ARCHETYPES, COST, RATES, STEP, World, WorkerResult, build_world, population, run_condition
from .state import DEFAULT, HARD, Params, Settings

CONDITIONS = ("R", "R-nolearn", "B1", "B2")
DEV_SEEDS = (0, 1, 2, 3, 4)
HELD_SEEDS = (1000, 1001, 1002, 1003, 1004)
LEVEL = 0.95
FROZEN = "evals/attention/frozen_config.json"
ORIGIN = "synthetic"


# ------------------------------------------------------------------------------------------------ bootstrap
def _ci(draws: np.ndarray, est: float) -> dict[str, float]:
    lo, hi = np.percentile(draws, [100 * (1 - LEVEL) / 2, 100 * (1 + LEVEL) / 2])
    return {"est": round(float(est), 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4)}


def boot_diff(a: np.ndarray, b: np.ndarray, n_boot: int, seed: int) -> dict[str, float]:
    """Mean of the per-worker difference a - b with a worker-level bootstrap interval."""
    d = np.asarray(a, float) - np.asarray(b, float)
    if len(d) == 0:
        return {"est": 0.0, "lo": 0.0, "hi": 0.0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (n_boot, len(d)))
    return _ci(d[idx].mean(1), d.mean())


# metric -> (numerator, denominator) per worker; the pooled value is sum(num) / sum(den)
RATIOS: dict[str, Callable[[WorkerResult], tuple[float, float]]] = {
    "interruptions_per_flow_hour_all": lambda r: (r.flow_displays, r.flow_h),
    "interruptions_per_flow_hour_non_safety": lambda r: (r.flow_displays_nonsafety, r.flow_h),
    "interruptions_per_working_hour": lambda r: (r.displays, r.work_h),
    "hard_quiet_breaches_per_day": lambda r: (r.hq_breaches, r.days),
    "important_seen_within_window": lambda r: (r.important_seen, r.important_n),
    "duplicate_rate": lambda r: (r.dup_displays, r.displays),
    "acceptance_rate": lambda r: (r.followed, r.shown_labelled),
    "fast_dismissal_rate": lambda r: (r.dismissed_fast, r.shown_labelled),
    "attention_cost_s_per_day": lambda r: (r.cost_s, r.days),
    "screen_share_exposures_per_day": lambda r: (r.exposure, r.days),
    "reminders_per_needs_you_item": lambda r: (float(sum(r.needs_reminders)), float(len(r.needs_reminders))),
    "digest_lines_per_digest": lambda r: (float(sum(r.digest_lines)), float(len(r.digest_lines))),
    "items_folded_per_digest": lambda r: (float(sum(r.digest_folded)), float(len(r.digest_folded))),
    "safety_missed_share": lambda r: (r.safety_missed, r.safety_n),
    "time_sensitive_missed_share": lambda r: (r.time_missed, r.time_n),
}
COUNTS = {"missed_urgent_safety": lambda r: r.safety_missed, "missed_time_sensitive": lambda r: r.time_missed, "safety_items": lambda r: r.safety_n,
          "important_items": lambda r: r.important_n, "interrupting_displays": lambda r: r.displays}


def _stack(results: list[WorkerResult]) -> dict[str, np.ndarray]:
    out = {}
    for k, f in RATIOS.items():
        v = np.array([f(r) for r in results], float).reshape(-1, 2)
        out[k] = v
    return out


def _ratio(v: np.ndarray, idx: np.ndarray | None = None) -> np.ndarray | float:
    if idx is None:
        den = v[:, 1].sum()
        return float(v[:, 0].sum() / den) if den > 0 else float("nan")
    num, den = v[idx, 0].sum(-1), v[idx, 1].sum(-1)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def _median_delay(results: list[WorkerResult], idx: np.ndarray | None = None, seen_only: bool = False) -> float:
    rs = results if idx is None else [results[i] for i in idx]
    xs = [x for r in rs for x in r.delays if not (seen_only and math.isinf(x))]
    return float(np.median(xs)) if xs else float("nan")


def summarise(by_cond: dict[str, list[WorkerResult]], n_boot: int, seed: int) -> dict[str, Any]:
    """Pooled metrics with person-level intervals for every condition, and paired differences against R."""
    conds = [c for c in CONDITIONS if c in by_cond]
    n = len(by_cond[conds[0]])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, (n_boot, n))
    stacks = {c: _stack(by_cond[c]) for c in conds}
    out: dict[str, Any] = {"n_workers": n, "n_worker_days": int(sum(r.days for r in by_cond[conds[0]])), "bootstrap_draws": n_boot, "conditions": {}, "paired": {}}
    est: dict[str, dict[str, np.ndarray]] = {}
    for c in conds:
        d: dict[str, Any] = {}
        est[c] = {}
        for k, v in stacks[c].items():
            draws = _ratio(v, idx)
            est[c][k] = draws
            d[k] = _ci(draws[~np.isnan(draws)] if np.isnan(draws).any() and (~np.isnan(draws)).any() else np.nan_to_num(draws), _ratio(v))
        for k, f in COUNTS.items():
            d[k] = int(sum(f(r) for r in by_cond[c]))
        delay_draws = np.array([_median_delay(by_cond[c], i) for i in idx[: min(n_boot, 300)]])
        seen_draws = np.array([_median_delay(by_cond[c], i, True) for i in idx[: min(n_boot, 300)]])
        d["median_important_delay_s"] = _delay_ci(delay_draws, _median_delay(by_cond[c]))
        d["median_important_delay_s_seen_only"] = _delay_ci(seen_draws, _median_delay(by_cond[c], None, True))
        d["max_reminders_per_needs_you_item"] = int(max((x for r in by_cond[c] for x in r.needs_reminders), default=0))
        d["dropped_by_reason"] = _merge_counts(by_cond[c])
        out["conditions"][c] = d
    for other in conds:
        if other == "R":
            continue
        p = {}
        for k in RATIOS:
            a, b = est["R"][k], est[other][k]
            ok = ~np.isnan(a) & ~np.isnan(b)
            if ok.any():
                p[k] = _ci(a[ok] - b[ok], _ratio(stacks["R"][k]) - _ratio(stacks[other][k]))
        out["paired"][f"R_minus_{other}"] = p
    return out


def _delay_ci(draws: np.ndarray, est: float) -> dict[str, Any]:
    fin = draws[np.isfinite(draws)]
    if len(fin) == 0:
        return {"est": None, "lo": None, "hi": None, "note": "no item was seen in time"}
    lo, hi = np.percentile(fin, [2.5, 97.5])
    return {"est": None if not math.isfinite(est) else round(est, 1), "lo": round(float(lo), 1), "hi": round(float(hi), 1),
            "share_of_draws_infinite": round(float(1 - len(fin) / len(draws)), 3)}


def _merge_counts(rs: list[WorkerResult]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rs:
        for k, v in r.dropped.items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items()))


# ------------------------------------------------------------------------------------------------ running populations
def run_population(seed: int, per_archetype: int, n_work_days: int, *, conds: tuple[str, ...] = CONDITIONS, params: Params = DEFAULT, settings: Settings | None = None,
                   rate_scale: float = 1.0, gate_leak: float = 0.0, unknown_poll_rate: float = 0.0, root: Path | None = None,
                   dismiss_all: bool = False) -> tuple[dict[str, list[WorkerResult]], list[World]]:
    specs = population(seed, per_archetype, rate_scale=rate_scale, dismiss_all=dismiss_all)
    worlds = [build_world(s, n_work_days, root=root, gate_leak=gate_leak) for s in specs]
    out: dict[str, list[WorkerResult]] = {c: [] for c in conds}
    for w in worlds:
        for c in conds:
            out[c].append(run_condition(w, c, params=params, settings=settings, unknown_poll_rate=unknown_poll_rate if c.startswith("R") else 0.0))
    return out, worlds


def run_seeds(seeds: tuple[int, ...], per_archetype: int, n_work_days: int, **kw: Any) -> tuple[dict[str, list[WorkerResult]], str]:
    pooled: dict[str, list[WorkerResult]] = {}
    sources: set[str] = set()
    for s in seeds:
        res, worlds = run_population(s, per_archetype, n_work_days, **kw)
        for c, rs in res.items():
            pooled.setdefault(c, []).extend(rs)
        sources |= {w.source for w in worlds}
    return pooled, "+".join(sorted(sources))


def recost(results: list[WorkerResult], scale: float) -> float:
    """The attention cost per worker-day when every unit cost is multiplied by ``scale`` (the sensitivity run reuses the display counts)."""
    cost = sum(COST[k] * n for r in results for k, n in r.ctx_counts.items())
    days = sum(r.days for r in results)
    return round(scale * cost / days, 2) if days else float("nan")


# ------------------------------------------------------------------------------------------------ tuning (dev only)
GRID: dict[str, tuple[Any, ...]] = {"min_gap_s": (60.0, 90.0, 120.0), "budget_per_day": (6, 10, 14), "break_idle_quiet_s": (10.0, 15.0, 25.0),
                                    "max_hold_soft_s": (300.0, 600.0, 900.0), "quiet_thr1": (0.20, 0.25, 0.30), "n_min": (4.0, 6.0, 10.0)}


def configs() -> list[dict[str, Any]]:
    """The default and every one-factor change from it: 1 + 2 x 6 = 13 configurations (the plan's text says 16; the grid it lists gives 13)."""
    base = {"min_gap_s": DEFAULT.min_gap_s, "budget_per_day": DEFAULT.budget_per_day, "break_idle_quiet_s": DEFAULT.break_idle_quiet_s,
            "max_hold_soft_s": DEFAULT.max_hold_soft_s, "quiet_thr1": DEFAULT.quiet_thr1, "n_min": DEFAULT.n_min}
    out = [dict(base, name="defaults")]
    for k, vals in GRID.items():
        for v in vals:
            if v != base[k]:
                out.append(dict(base, **{k: v}, name=f"{k}={v}"))
    return out


def to_params(cfg: dict[str, Any]) -> tuple[Params, Settings]:
    p = replace(DEFAULT, min_gap_s=float(cfg["min_gap_s"]), break_idle_quiet_s=float(cfg["break_idle_quiet_s"]), max_hold_soft_s=float(cfg["max_hold_soft_s"]),
                quiet_thr1=float(cfg["quiet_thr1"]), quiet_thr2=float(cfg["quiet_thr1"]) / 2.0, n_min=float(cfg["n_min"]))
    return p, Settings(budget_per_day=int(cfg["budget_per_day"]))


def _paired_ratio_diff(a: list[list[float]], b: list[list[float]], n_boot: int = 1000, seed: int = 5) -> dict[str, float]:
    """(sum a_num / sum a_den) - (sum b_num / sum b_den) over the same workers, with a worker-level bootstrap interval."""
    A, B = np.array(a, float), np.array(b, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(A), (n_boot, len(A)))

    def ratio(M: np.ndarray, ix: np.ndarray | None) -> Any:
        num, den = (M[:, 0].sum(), M[:, 1].sum()) if ix is None else (M[ix, 0].sum(-1), M[ix, 1].sum(-1))
        return num / den

    return _ci(ratio(A, idx) - ratio(B, idx), ratio(A, None) - ratio(B, None))


def select(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The plan's rule (section 5): among configurations with important-seen at least 95%, no safety item missed and a median important delay of at
    most 120 s, the lowest non-safety flow interruptions per hour; ties (within 0.01) go to the lowest attention cost, then to the defaults. And the
    plan's last sentence: if nothing beats the defaults by more than the dev interval, the defaults stay. Read here as: the paired, worker-level
    95% interval of (chosen minus defaults) in non-safety flow interruptions per hour must lie below zero. (The first version of this function left
    that sentence out; see amendment A2 in the plan.)"""
    ok = [r for r in rows if r["important_seen"] >= 0.95 and r["missed_urgent_safety"] == 0 and (r["median_delay_s"] is not None and r["median_delay_s"] <= 120.0)]
    pool = ok or sorted(rows, key=lambda r: (-r["important_seen"], r["missed_urgent_safety"]))[:1]
    best = min(r["flow_non_safety"] for r in pool)
    tied = [r for r in pool if r["flow_non_safety"] <= best + 0.01]
    tied.sort(key=lambda r: (r["cost_per_day"], r["name"] != "defaults"))
    chosen = tied[0]
    out = {"chosen": chosen["name"], "eligible": [r["name"] for r in ok], "rule_met_by_any": bool(ok), "tied": [r["name"] for r in tied]}
    default = next((r for r in rows if r["name"] == "defaults"), None)
    if default is not None and chosen["name"] != "defaults" and chosen.get("flow_pairs") and default.get("flow_pairs"):
        iv = _paired_ratio_diff(chosen["flow_pairs"], default["flow_pairs"])
        out["interval_vs_defaults"] = iv
        out["first_choice_by_rate"] = chosen["name"]
        if iv["hi"] >= 0.0:
            out["chosen"] = "defaults"
            out["reason"] = "no gain beyond the dev interval: the defaults stay"
        else:
            out["reason"] = "beats the defaults by more than the dev interval"
    return out


def tune_on_dev(*, per_archetype: int = 2, n_work_days: int = 10, seeds: tuple[int, ...] = DEV_SEEDS, root: Path | None = None, part: tuple[int, int] | None = None) -> dict[str, Any]:
    """Run the 13 configurations on the dev population. ``part=(k, n)`` runs only the configurations at positions k, k + n, ... (so a long run can be
    cut into pieces for the short lane); the result then has ``rows`` for that part only and no selection."""
    assert not set(seeds) & set(HELD_SEEDS), "tuning never touches held-out seeds"
    rows = []
    worlds: list[World] = []
    for s in seeds:
        worlds += [build_world(sp, n_work_days, root=root) for sp in population(s, per_archetype)]
    todo = [c for i, c in enumerate(configs()) if part is None or i % part[1] == part[0]]
    for cfg in todo:
        p, st = to_params(cfg)
        rs = [run_condition(w, "R", params=p, settings=st) for w in worlds]
        st_ = _stack(rs)
        rows.append({"name": cfg["name"], "config": {k: v for k, v in cfg.items() if k != "name"},
                     "flow_non_safety": round(_ratio(st_["interruptions_per_flow_hour_non_safety"]), 4), "important_seen": round(_ratio(st_["important_seen_within_window"]), 4),
                     "missed_urgent_safety": int(sum(r.safety_missed for r in rs)), "median_delay_s": round(_median_delay(rs), 1) if math.isfinite(_median_delay(rs)) else None,
                     "cost_per_day": recost(rs, 1.0), "duplicate_rate": round(_ratio(st_["duplicate_rate"]), 4),
                     "flow_pairs": [[float(x), float(y)] for x, y in st_["interruptions_per_flow_hour_non_safety"]]})
    return {"split": "dev", "seeds": list(seeds), "n_workers": len(worlds), "n_work_days": n_work_days, "rows": rows, "selection": select(rows) if part is None else None,
            "part": None if part is None else list(part), "note": "13 configurations: the default and each one-factor change in the plan's grid (the plan's text says 16; the grid it lists gives 13)."}


def combine_parts(paths: list[Path]) -> dict[str, Any]:
    """Join the pieces of a split tuning run, in the grid's own order, and apply the plan's selection rule to the whole."""
    parts = [json.loads(p.read_text()) for p in paths]
    n = {tuple(x["part"])[1] for x in parts}
    assert len(n) == 1 and sorted(tuple(x["part"])[0] for x in parts) == list(range(n.pop())), "every piece of the tuning run is needed"
    rows = {r["name"]: r for x in parts for r in x["rows"]}
    ordered = [rows[c["name"]] for c in configs()]
    base = parts[0]
    return {**{k: base[k] for k in ("split", "seeds", "n_workers", "n_work_days", "note")}, "rows": ordered, "selection": select(ordered), "part": None}


def config_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def freeze_config(tuning: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    chosen = next(r for r in tuning["rows"] if r["name"] == tuning["selection"]["chosen"])
    cfg = {"name": chosen["name"], "config": chosen["config"], "hard_constants": {k: getattr(DEFAULT, k) for k in HARD},
           "chosen_by": "evals/attention/PLAN.md section 5, on dev seeds " + ",".join(map(str, tuning["seeds"])), "dev_row": chosen}
    cfg["hash"] = config_hash({"name": cfg["name"], "config": cfg["config"], "hard_constants": cfg["hard_constants"]})
    p = path or repo_root() / FROZEN
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=1))
    return cfg


def load_frozen(path: Path | None = None) -> dict[str, Any]:
    p = path or repo_root() / FROZEN
    if not p.exists():
        raise FileNotFoundError(f"{p} does not exist. Tune on dev seeds, freeze the choice and have the lead commit it before any held-out run.")
    return json.loads(p.read_text())


# ------------------------------------------------------------------------------------------------ acceptance
def _lower(ci: dict[str, float]) -> float:
    return ci["lo"]


def acceptance(summary: dict[str, Any], scenarios: dict[str, Any], learning_ok: bool | None = None) -> dict[str, Any]:
    c, p = summary["conditions"], summary["paired"]
    r, b1, b2 = c["R"], c["B1"], c["B2"]
    pb1, pb2 = p["R_minus_B1"], p["R_minus_B2"]

    def verdict(met: bool, not_met: bool) -> str:
        return "met" if met else ("not_met" if not_met else "inconclusive")

    imp = r["important_seen_within_window"]
    items = {
        "1_vs_B1_flow_interruptions_lower": verdict(pb1["interruptions_per_flow_hour_non_safety"]["hi"] < 0, pb1["interruptions_per_flow_hour_non_safety"]["lo"] >= 0),
        "1_vs_B1_hard_quiet_breaches_zero": verdict(r["hard_quiet_breaches_per_day"]["est"] == 0.0 and r["hard_quiet_breaches_per_day"]["hi"] == 0.0, r["hard_quiet_breaches_per_day"]["est"] > 0),
        "1_vs_B1_duplicate_rate_lower": verdict(pb1["duplicate_rate"]["hi"] < 0, pb1["duplicate_rate"]["lo"] >= 0),
        "2_important_seen_at_least_95pct": verdict(imp["lo"] >= 0.95, imp["hi"] < 0.95),
        "2_not_more_than_3_points_below_B1": verdict(pb1["important_seen_within_window"]["lo"] >= -0.03, pb1["important_seen_within_window"]["hi"] < -0.03),
        "3_missed_urgent_zero_for_R": verdict(r["missed_urgent_safety"] == 0, r["missed_urgent_safety"] > 0),
        "4_max_one_reminder_per_needs_you_item": verdict(r["max_reminders_per_needs_you_item"] <= 1, r["max_reminders_per_needs_you_item"] > 1),
        "5_vs_B2_important_seen_higher": verdict(pb2["important_seen_within_window"]["lo"] > 0, pb2["important_seen_within_window"]["hi"] < 0),
        "5_vs_B2_missed_urgent_lower": verdict(b2["missed_urgent_safety"] > r["missed_urgent_safety"], b2["missed_urgent_safety"] < r["missed_urgent_safety"]) if b2["safety_items"] else "inconclusive",
        "6_scenarios_hold": verdict(all(s["passed"] for k, s in scenarios.items() if k != "S4"), not all(s["passed"] for k, s in scenarios.items() if k != "S4")),
        "7_s4_can_wait_toasts_later_below_early_and_approvals_unchanged": _criterion_7(scenarios.get("S4")),
        "7b_s4_helpful_now_displays_fall_with_learning": _criterion_7b(scenarios.get("S4")),
    }
    return {"criteria": items, "met": sum(v == "met" for v in items.values()), "not_met": sum(v == "not_met" for v in items.values()),
            "inconclusive": sum(v == "inconclusive" for v in items.values()),
            "note": "Design targets fixed in evals/attention/PLAN.md before any run, not measured tolerances. met: the interval bound clears the target; not_met: the other bound misses it; inconclusive: the interval straddles it."}


def _approvals_unchanged(n: dict[str, Any]) -> bool:
    return bool(n.get("approval_toasts_shown", 0) > 0 and (n.get("time_sensitive_seen_share") or 0) >= 0.95 and n.get("safety_missed", 1) == 0)


def _criterion_7(s4: dict[str, Any] | None) -> str:
    """The plan's criterion 7 as written: in S4 the later-day can-wait toasts are below the early-day toasts with the interval excluding 0, and approvals
    are unchanged (still shown, still seen, nothing urgent missed). (The first version of this function tested a different thing; see amendment A3.)"""
    if not s4:
        return "inconclusive"
    n = s4["numbers"]
    d = n["wait_late_minus_early"]
    if not _approvals_unchanged(n):
        return "not_met"
    return "met" if d["hi"] < 0 else ("not_met" if d["lo"] > 0 else "inconclusive")


def _criterion_7b(s4: dict[str, Any] | None) -> str:
    """Not in the plan's list: the part of S4 that does fall. Cue's helpful-now displays are lower on the last days than on the first, and lower than
    the same worker without learning, with intervals below zero."""
    if not s4:
        return "inconclusive"
    n = s4["numbers"]
    a, b = n["helpful_late_minus_early"], n["helpful_late_router_minus_nolearn"]
    return "met" if a["hi"] < 0 and b["hi"] < 0 else ("not_met" if a["lo"] > 0 or b["lo"] > 0 else "inconclusive")


LIMITATIONS = [
    {"id": "att_sim_not_people", "severity": "high", "text": "Every number is simulated: workers, schedules, event streams, reactions and attention costs are my assumptions (simulate.py). This shows the policy behaves as designed under them. It does not show that real people find Understudy natural. The live check with four teammates (n = 4) is the real test and was not run."},
    {"id": "att_costs_assumed", "severity": "medium", "text": "The attention-cost model (seconds of focus lost per interruption by context) is an assumption. The sensitivity run halves and doubles it and reports whether the ordering of conditions changes; the magnitudes stay assumptions."},
    {"id": "att_rates_assumed", "severity": "medium", "text": "Producer rates are stated approximations of Cue, the briefing, the approval queue, the agent runtime, the calendar layer and health checks. The sensitivity run scales them by 0.5 and 2."},
    {"id": "att_labels_proxy", "severity": "medium", "text": "Implicit labels (followed within 10 s, dismissed within 4 s, ignored, never) are noisy proxies for welcome: a dismissal can mean already knew. The simulated worker's labels come from the same reaction model, so learning is validated for its direction, not for its calibration against people."},
    {"id": "att_probes_exact", "severity": "medium", "text": "Meeting, call, screen-share and quiet-hotkey states are known exactly here. In the product they come from probes that can be wrong or missing; an unknown worker is held, never interrupted, except for safety. The sensitivity run makes 10% of polls unknown to show the cost."},
    {"id": "att_b1_b2_strawmen", "severity": "low", "text": "B1 and B2 are deliberately simple baselines (everything at once, one digest a day). They show the two failure modes the layer is designed to avoid; they are not what any real notifier does."},
]


# ------------------------------------------------------------------------------------------------ the whole evaluation
def code_hashes() -> dict[str, str]:
    d = Path(__file__).parent
    return {f: hashlib.sha256((d / f).read_bytes()).hexdigest()[:12] for f in ("router.py", "service.py", "vocab.py", "state.py", "learning.py", "texts.py", "digest.py", "simulate.py", "scenarios.py", "evaluate.py")}


def _sensitivity(seeds: tuple[int, ...], per_archetype: int, n_work_days: int, params: Params, settings: Settings | None, n_boot: int, root: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base, _ = run_seeds(seeds, per_archetype, n_work_days, conds=("R", "B1", "B2"), params=params, settings=settings, root=root)
    for scale in (0.5, 1.0, 2.0):
        costs = {c: recost(base[c], scale) for c in base}
        out[f"cost_x{scale}"] = {"cost_per_day": costs, "ordering": sorted(costs, key=costs.get), "R_cheapest": min(costs, key=costs.get) == "R"}
    for name, kw in (("rates_x0.5", {"rate_scale": 0.5}), ("rates_x2", {"rate_scale": 2.0}), ("cue_gate_leak_5pct", {"gate_leak": 0.05}), ("unknown_polls_10pct", {"unknown_poll_rate": 0.10})):
        res, _ = run_seeds(seeds, per_archetype, n_work_days, conds=("R", "B1", "B2"), params=params, settings=settings, root=root, **kw)
        s = summarise(res, n_boot, 7)
        out[name] = {c: {"flow_non_safety": s["conditions"][c]["interruptions_per_flow_hour_non_safety"], "important_seen": s["conditions"][c]["important_seen_within_window"],
                         "missed_urgent_safety": s["conditions"][c]["missed_urgent_safety"], "hard_quiet_breaches_per_day": s["conditions"][c]["hard_quiet_breaches_per_day"]} for c in ("R", "B1", "B2")}
    return out


def evaluate_attention(fast: bool = False, *, held_out: bool = False, root: Path | str | None = None, params: Params | None = None, settings: Settings | None = None,
                       tune: bool | None = None, pieces_dir: Path | str | None = None) -> dict[str, Any]:
    t0 = time.time()
    root = Path(root) if root else None
    frozen = None
    if held_out:
        frozen = load_frozen()
        params, settings = to_params(frozen["config"])
        seeds, per_arch, days, n_boot, sc_seed = HELD_SEEDS, 10, 10, 1000, HELD_SEEDS[0]
    elif fast:
        seeds, per_arch, days, n_boot, sc_seed = (0,), 2, 2, 200, 0
    else:
        seeds, per_arch, days, n_boot, sc_seed = DEV_SEEDS, 10, 10, 1000, 0
    params = params or DEFAULT
    pre_sens: dict[str, Any] = {}
    if pieces_dir is not None:
        pooled, source, pre_sens = _load_pieces(Path(pieces_dir), seeds)
    else:
        pooled, source = run_seeds(seeds, per_arch, days, params=params, settings=settings, root=root)
    summary = summarise(pooled, n_boot, 11)
    scenarios = SC.run_all(sc_seed, params=params, settings=settings, fast=fast, root=root)
    out: dict[str, Any] = {
        "meta": {"origin": ORIGIN, "badge": "synthetic: simulated workers, schedules, events and reactions; not people", "split": "held_out" if held_out else "dev",
                 "seeds": list(seeds), "workers_per_archetype": per_arch, "archetypes": list(ARCHETYPES), "working_days_per_worker": days, "n_workers": summary["n_workers"],
                 "n_worker_days": summary["n_worker_days"], "schedule_source": source, "fast": fast, "interval": f"{int(LEVEL * 100)}% person-level bootstrap, {n_boot} draws",
                 "params": {k: getattr(params, k) for k in asdict(params)}, "budget_per_day": (settings.budget_per_day if settings else DEFAULT.budget_per_day),
                 "frozen_config": None if frozen is None else {"name": frozen["name"], "hash": frozen["hash"]},
                 "cost_model_s": dict(COST), "rates": dict(RATES), "step_s": STEP, "code": code_hashes(), "plan": "evals/attention/PLAN.md"},
        "conditions": summary["conditions"], "paired": summary["paired"], "scenarios": scenarios,
    }
    if not held_out:
        if tune if tune is not None else not fast:
            out["tuning"] = tune_on_dev(per_archetype=2, n_work_days=10, root=root)
        elif fast:
            out["tuning"] = {"note": "skipped in fast mode"}
        else:
            out["tuning"] = {"note": "reported separately: evals/attention/tuning_dev.json (this dev report is for the frozen configuration)"}
        out["sensitivity"] = {"note": "skipped in fast mode"} if fast else (pre_sens or _sensitivity((0, 1, 2), 2, 6, params, settings, 200, root))
    else:
        out["sensitivity"] = pre_sens or _sensitivity(HELD_SEEDS[:3], 2, 6, params, settings, 200, root)
    out["acceptance"] = acceptance(summary, scenarios)
    out["limitations"] = LIMITATIONS
    out["headline"] = _headline(out)
    out["meta"]["wall_s"] = round(time.time() - t0, 1)
    return out


# ------------------------------------------------------------------------------------------------ pieces (so a long run can use the short lane)
def run_piece(which: str, *, held_out: bool, out_dir: Path | None = None, root: Path | None = None) -> Path:
    """One piece of the full run, written as JSON: ``which`` is a population seed or ``sens`` (the sensitivity runs). The pieces together are
    exactly what ``evaluate_attention`` computes in one go; ``evaluate_attention(..., pieces_dir=...)`` joins them. Held-out pieces use the frozen config."""
    seeds = HELD_SEEDS if held_out else DEV_SEEDS
    params, settings = DEFAULT, None
    if held_out:
        params, settings = to_params(load_frozen()["config"])
    else:
        fp = repo_root() / FROZEN
        if fp.exists():
            params, settings = to_params(json.loads(fp.read_text())["config"])
    d = out_dir or repo_root() / ("evals/attention/held_out_parts" if held_out else "evals/attention/dev_parts")
    d.mkdir(parents=True, exist_ok=True)
    if which == "sens":
        payload: dict[str, Any] = {"sens": _sensitivity(seeds[:3], 2, 6, params, settings, 200, root)}
    else:
        seed = int(which)
        assert seed in seeds, "a piece is one of the split's own seeds"
        res, worlds = run_population(seed, 10, 10, params=params, settings=settings, root=root)
        payload = {"seed": seed, "source": "+".join(sorted({w.source for w in worlds})), "results": {c: [r.to_dict() for r in rs] for c, rs in res.items()}}
    p = d / f"piece_{which}.json"
    p.write_text(json.dumps(payload))
    return p


def _load_pieces(d: Path, seeds: tuple[int, ...]) -> tuple[dict[str, list[WorkerResult]], str, dict[str, Any]]:
    pooled: dict[str, list[WorkerResult]] = {}
    sources: set[str] = set()
    for s in seeds:
        j = json.loads((d / f"piece_{s}.json").read_text())
        sources |= set(j["source"].split("+"))
        for c, rs in j["results"].items():
            pooled.setdefault(c, []).extend(WorkerResult.from_dict(r) for r in rs)
    sens = json.loads((d / "piece_sens.json").read_text())["sens"] if (d / "piece_sens.json").exists() else {}
    return pooled, "+".join(sorted(sources)), sens


def _headline(o: dict[str, Any]) -> dict[str, Any]:
    c, p = o["conditions"], o["paired"]
    return {"origin": ORIGIN,
            "flow_interruptions_per_hour_non_safety": {k: c[k]["interruptions_per_flow_hour_non_safety"] for k in CONDITIONS},
            "important_seen_within_window": {k: c[k]["important_seen_within_window"] for k in CONDITIONS},
            "missed_urgent_safety": {k: c[k]["missed_urgent_safety"] for k in CONDITIONS},
            "R_minus_B1_flow_non_safety": p["R_minus_B1"]["interruptions_per_flow_hour_non_safety"], "R_minus_B1_duplicate_rate": p["R_minus_B1"]["duplicate_rate"],
            "scenarios_passed": {k: v["passed"] for k, v in o["scenarios"].items()},
            "acceptance": {k: v for k, v in o["acceptance"].items() if k in ("met", "not_met", "inconclusive")},
            "caveat": "simulated workers and an assumed reaction and cost model; shows the policy behaves as designed, not that people find it natural"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.attention.evaluate")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--held-out", action="store_true")
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--tune-part", type=str, default=None, help="K/N: run only every Nth configuration from K (a piece of the tuning run); writes evals/attention/tuning_parts/part_K_of_N.json")
    ap.add_argument("--piece", type=str, default=None, help="SEED or 'sens': run one piece of the full run (with --held-out or --dev) and write it as JSON")
    ap.add_argument("--pieces-dir", type=str, default=None, help="join pieces written by --piece instead of running the populations")
    ap.add_argument("--combine-parts", action="store_true", help="join the pieces, apply the selection rule, write tuning_dev.json; with --freeze also write the frozen config")
    a = ap.parse_args(argv)
    if a.piece:
        print(json.dumps({"piece": str(run_piece(a.piece, held_out=a.held_out))}))
        return 0
    if a.tune_part:
        k, n = (int(x) for x in a.tune_part.split("/"))
        t = tune_on_dev(part=(k, n))
        d = repo_root() / "evals/attention/tuning_parts"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"part_{k}_of_{n}.json").write_text(json.dumps(t, indent=1))
        print(json.dumps({"part": [k, n], "configs": [r["name"] for r in t["rows"]]}))
        return 0
    if a.combine_parts:
        t = combine_parts(sorted((repo_root() / "evals/attention/tuning_parts").glob("part_*_of_*.json")))
        (repo_root() / "evals/attention/tuning_dev.json").write_text(json.dumps(t, indent=1))
        print(json.dumps({"selection": t["selection"], "rows": [{k: r[k] for k in ("name", "flow_non_safety", "important_seen", "missed_urgent_safety", "median_delay_s", "cost_per_day")} for r in t["rows"]]}, indent=1))
        if a.freeze:
            f = freeze_config(t)
            print(json.dumps({"frozen": f["name"], "hash": f["hash"], "path": FROZEN}))
        return 0
    if a.tune or a.freeze:
        t = tune_on_dev()
        print(json.dumps({"selection": t["selection"], "rows": [{k: r[k] for k in ("name", "flow_non_safety", "important_seen", "missed_urgent_safety", "median_delay_s", "cost_per_day")} for r in t["rows"]]}, indent=1))
        outp = Path(a.out) if a.out else repo_root() / "evals/attention/tuning_dev.json"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(t, indent=1))
        if a.freeze:
            f = freeze_config(t)
            print(json.dumps({"frozen": f["name"], "hash": f["hash"], "path": FROZEN}))
        return 0
    kw: dict[str, Any] = {}
    if a.dev and not a.held_out:
        fp = repo_root() / FROZEN
        if fp.exists():                                   # the dev report is then shown for the chosen configuration, tuning reported separately
            kw["params"], kw["settings"] = to_params(json.loads(fp.read_text())["config"])
            kw["tune"] = False
    if a.pieces_dir:
        kw["pieces_dir"] = (repo_root() / a.pieces_dir) if not Path(a.pieces_dir).is_absolute() else Path(a.pieces_dir)
    rep = evaluate_attention(fast=a.fast, held_out=a.held_out, **kw)
    out = a.out or ("evals/attention/report_held_out.json" if a.held_out else ("evals/attention/report_fast.json" if a.fast else "evals/attention/report_dev.json"))
    p = Path(out) if Path(out).is_absolute() else repo_root() / out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep["headline"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
