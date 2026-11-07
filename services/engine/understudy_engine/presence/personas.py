"""Presence on the synthetic personas (engine-data's ``data/synthetic/<persona>``): load, fit, evaluate, compare to truth.

The map and the return-time model are fitted from ``events.jsonl`` only. ``truth.json`` is read here, in the
evaluation, never in fitting code: it supplies ``expected_active_prob`` (pre and post schedule change) so we can
ask whether the fitted map recovers the planted schedule, not just whether it predicts held-out days.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..memory.paths import data_dir
from .evaluate import evaluate_presence
from .model import PresenceModel, PriorHours, Smoothing
from .timeline import ACTIVE, DayObs, day_states_from_events, spells_from_events

PERSONAS = ("nine-to-five", "night-owl", "shift-worker", "irregular")


def persona_dir(name: str, root: Path | None = None) -> Path:
    return (root or data_dir()) / "synthetic" / name


def have_persona(name: str, root: Path | None = None) -> bool:
    d = persona_dir(name, root)
    return (d / "events.jsonl").exists() and (d / "truth.json").exists()


def load_persona(name: str, root: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    d = persona_dir(name, root)
    events = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines() if line.strip()]
    truth = json.loads((d / "truth.json").read_text())
    return events, truth


def _truth_matrix(truth: dict[str, Any], phase: str) -> np.ndarray:
    return np.asarray(truth["expected_active_prob"][phase], dtype=float)


def recovery(days: list[DayObs], truth_p: np.ndarray, prior: PriorHours, *, tune: bool = True,
             truth_idle_h: float | None = None) -> dict[str, Any]:
    """How close is the fitted P(active) to the planted P(active), per bin, with the baselines."""
    model = PresenceModel(prior)
    model.fit(days)
    if tune and len(days) >= 7:
        model.tune(days)
    raw = PresenceModel(prior, Smoothing(0, 0, 0, 0, prior_strength=0.5)).fit(days)
    p = model.p_active()
    lo, hi = model.active_interval()
    pri = prior.prior_probs()[..., ACTIVE]

    def rmse(a: np.ndarray) -> float:
        return float(np.sqrt(np.mean((a - truth_p) ** 2)))

    idle = model.idle_capacity_interval()
    return {
        "n_days": len(days),
        "idle_capacity_h_fit": idle, "idle_capacity_h_truth": truth_idle_h,
        "rmse": round(rmse(p), 4),
        "rmse_prior_only": round(rmse(pri), 4),
        "rmse_unsmoothed": round(rmse(raw.p_active()), 4),
        "rmse_global_rate": round(rmse(np.full_like(p, float(np.mean([(d.states == ACTIVE).mean() for d in days])))), 4),
        "truth_inside_interval": round(float(np.mean((truth_p >= lo) & (truth_p <= hi))), 4),
        "interval_mean_width": round(float((hi - lo).mean()), 4),
        "active_h_per_week_fit": round(float(p.sum() * 0.25), 2),
        "active_h_per_week_truth": round(float(truth_p.sum() * 0.25), 2),
    }


def _truth_idle_h(truth: dict[str, Any], phase: str) -> float | None:
    sh = (truth.get("state_hours_per_week") or {}).get(phase)
    return round(float(sh["IDLE"] + sh["AWAY"]), 2) if sh else None


def evaluate_persona(name: str, root: Path | None = None, *, d_min: float = 30.0, cap: float = 0.10, fast: bool = False) -> dict[str, Any]:
    events, truth = load_persona(name, root)
    tz = truth.get("tz", "UTC")
    from datetime import date, timedelta

    first = date.fromisoformat(truth["start_date"])  # observation window only (metadata), not behaviour
    days = day_states_from_events(events, tz=tz, first_day=first, last_day=first + timedelta(days=int(truth["n_days"]) - 1))
    spells = spells_from_events(events, tz=tz)
    prior = PriorHours()  # the role-pack hours; the personas deliberately differ from it
    rep = evaluate_presence(days, spells, prior, origin="synthetic", d_min=d_min, cap=cap, person=truth.get("person"),
                            note="synthetic persona; schedule changes on day 15", fast=fast)
    change = int(truth.get("change_day", 15))
    pre_days = [d for i, d in enumerate(days) if i + 1 < change]
    post_days = [d for i, d in enumerate(days) if i + 1 >= change]
    rep["recovery"] = {
        "pre_change": recovery(pre_days, _truth_matrix(truth, "pre"), prior, truth_idle_h=_truth_idle_h(truth, "pre")),
        "post_change_fit_on_all_days": recovery(days, _truth_matrix(truth, "post"), prior),
        "post_change_fit_on_post_days": recovery(post_days, _truth_matrix(truth, "post"), prior),
    }
    rep["persona"] = truth.get("persona", name)
    rep["n_events"] = len(events)
    return rep


def evaluate_presence_all(root: Path | None = None, *, d_min: float = 30.0, cap: float = 0.10, fast: bool = False) -> dict[str, Any]:
    """Plain dict for the eval harness: one entry per persona that exists on disk, and a pooled summary."""
    per = {n: evaluate_persona(n, root, d_min=d_min, cap=cap, fast=fast) for n in PERSONAS if have_persona(n, root)}
    out: dict[str, Any] = {
        "name": "presence", "origin": "synthetic", "n": len(per), "n_unit": "personas", "interval_level": 0.95,
        "split": "forward and interleaved held-out days within each persona; truth only used to score recovery",
        "note": "Four synthetic personas, 21 days each, one schedule change on day 15. Not real people.",
        "personas": per,
        "meta": {"origin": "synthetic", "n": len(per), "n_unit": "personas", "interval_level": 0.95,
                 "split": "forward and interleaved held-out days within each persona; truth only used to score recovery",
                 "note": "Four synthetic personas, 21 days each, one schedule change on day 15. Not real people."},
    }
    if per:
        rows = list(per.values())

        def pick(path: list[str]) -> list[float]:
            vals = []
            for r in rows:
                x: Any = r
                for k in path:
                    x = x.get(k) if isinstance(x, dict) else None
                if isinstance(x, (int, float)):
                    vals.append(float(x))
            return vals

        def mean(v: list[float]) -> float | None:
            return round(float(np.mean(v)), 4) if v else None

        fwd = ["by_split", "forward"]
        out["summary"] = {
            "map_brier_model": mean(pick(fwd + ["map", "model", "brier"])),
            "map_brier_prior_only": mean(pick(fwd + ["map", "prior_only", "brier"])),
            "map_brier_global_rate": mean(pick(fwd + ["map", "global_rate", "brier"])),
            "window_brier_model": mean(pick(fwd + ["window", "model", "brier"])),
            "window_brier_pooled": mean(pick(fwd + ["window", "pooled", "brier"])),
            "window_brier_exponential": mean(pick(fwd + ["window", "exponential", "brier"])),
            "interruption_rate_rule": mean(pick(fwd + ["decision", "rule", "interruption_rate"])),
            "interruption_rate_fixed_overnight": mean(pick(fwd + ["decision", "fixed_overnight", "interruption_rate"])),
            "interruption_rate_idle5": mean(pick(fwd + ["decision", "run_whenever_idle_5min", "interruption_rate"])),
            "idle_used_rule": mean(pick(fwd + ["decision", "rule", "share_idle_used"])),
            "idle_used_fixed_overnight": mean(pick(fwd + ["decision", "fixed_overnight", "share_idle_used"])),
            "idle_used_idle5": mean(pick(fwd + ["decision", "run_whenever_idle_5min", "share_idle_used"])),
            "per_persona_means_over": len(rows),
        }
        out["metrics"] = out["summary"]
    out["limitations"] = limitations(out)
    return out


def report_section(result: dict[str, Any]) -> dict[str, Any]:
    """Map ``evaluate_presence_all`` onto the ``presence`` row of ``/eval/report`` (docs/API_CONTRACT.md, 7 Nov additions).

    ``reliability`` and ``brier`` are for the window forecast S(D | t, u), pooled over the personas' held-out forward
    split; the three decision numbers are pooled means with the baselines beside them.
    """
    rows, briers = [], []
    dec: dict[str, list[tuple[float, float]]] = {"rule": [], "fixed_overnight": [], "run_whenever_idle_5min": []}
    cap = None
    for p in result.get("personas", {}).values():
        part = p["by_split"].get("forward") or next(iter(p["by_split"].values()))
        rows.extend(part["window"].get("reliability", []))
        if "model" in part["window"]:
            briers.append(part["window"]["model"]["brier"])
        cap = part["decision"]["cap"]
        for k in dec:
            dec[k].append((part["decision"][k]["interruption_rate"], part["decision"][k]["share_idle_used"]))
    pooled: list[dict[str, float]] = []
    for b in range(10):
        sel = [r for r in rows if min(int(r["p_mean"] * 10), 9) == b]
        n = sum(r["n"] for r in sel)
        if n:
            pooled.append({"p_mean": round(sum(r["p_mean"] * r["n"] for r in sel) / n, 4),
                           "freq": round(sum(r["freq"] * r["n"] for r in sel) / n, 4), "n": n})

    def m(k: str, i: int) -> float:
        return round(float(np.mean([x[i] for x in dec[k]])), 4) if dec[k] else float("nan")

    return {
        "reliability": pooled,
        "brier": round(float(np.mean(briers)), 4) if briers else None,
        "baselines": {
            "fixed_overnight": {"interruption_rate": m("fixed_overnight", 0), "idle_time_used": m("fixed_overnight", 1)},
            "idle_5min": {"interruption_rate": m("run_whenever_idle_5min", 0), "idle_time_used": m("run_whenever_idle_5min", 1)},
        },
        "interruption_rate": m("rule", 0), "cap": cap, "idle_time_used": m("rule", 1),
        "calibration": pooled, "interruption_cap": cap,  # aliases the dashboard fixture uses
        "meta": {"origin": "synthetic", "n": result.get("n", 0), "n_unit": "personas",
                 "split": "forward held-out days within each persona", "interval_level": 0.95,
                 "note": "Synthetic personas, 21 days each. Pooled means of per-persona results; per-persona detail and intervals in the full dict."},
    }


def limitations(result: dict[str, Any]) -> list[dict[str, str]]:
    """Caveats computed from the numbers above, so the in-product register says what this run actually showed."""
    per = result.get("personas", {})
    out: list[dict[str, str]] = [{
        "id": "presence-synthetic",
        "text": f"Presence results come from {len(per)} synthetic personas of 21 days each, not from real people. "
                "The schedule change on day 15 is planted; the real change in a person's week will not look like it.",
        "severity": "high",
    }]
    worse = []
    for name, p in per.items():
        m = p["by_split"].get("forward", {}).get("map")
        if m and (m["model"]["brier"] > m["prior_only"]["brier"] or m["model"]["brier"] > m["global_rate"]["brier"]):
            worse.append(f"{name} (map Brier {m['model']['brier']:.3f} against prior {m['prior_only']['brier']:.3f} and "
                         f"one global rate {m['global_rate']['brier']:.3f})")
    if worse:
        out.append({"id": "presence-weekly-template", "severity": "medium",
                    "text": "The weekly map predicts held-out days worse than a simple baseline for " + "; ".join(worse)
                            + ". A weekly template does not suit rotating shifts or no routine."})
    eces = [p["by_split"]["forward"]["window"]["ece"] for p in per.values() if "window" in p["by_split"].get("forward", {})
            and "ece" in p["by_split"]["forward"]["window"]]
    if eces:
        wins = sum(1 for p in per.values() if p["by_split"]["forward"]["window"]["model"]["brier"] < p["by_split"]["forward"]["window"]["pooled"]["brier"])
        out.append({"id": "presence-window-calibration", "severity": "medium",
                    "text": f"The window forecast is only roughly calibrated: expected calibration error {min(eces):.2f} to {max(eces):.2f} "
                            f"across personas on held-out days, and it beats pooled survival (no time of week) on {wins} of {len(per)} personas."})
    cov = [p["recovery"]["pre_change"]["truth_inside_interval"] for p in per.values()]
    if cov:
        out.append({"id": "presence-interval-coverage", "severity": "medium",
                    "text": f"The 95% intervals on the presence map contain the planted active probability in only {min(cov):.0%} to "
                            f"{max(cov):.0%} of bins. Smoothing across neighbouring bins trades bias for variance, so the intervals are too narrow."})
    gaps = []
    for name, p in per.items():
        r = p["recovery"]["pre_change"]
        fit, tr = r["idle_capacity_h_fit"], r["idle_capacity_h_truth"]
        if tr is not None and fit["mean"] > tr * 1.15:
            gaps.append(f"{name} {fit['mean']:.0f} h against a planted {tr:.0f} h")
    if gaps:
        out.append({"id": "presence-idle-capacity", "severity": "medium",
                    "text": "Idle capacity per week is over-estimated: " + "; ".join(gaps) + ". With no sleep event the machine is assumed to stay on "
                            "for 60 minutes after the last event, and a locked screen still counts as idle although a desktop run cannot start on it."})
    s_ = result.get("summary", {})
    if s_.get("interruption_rate_rule") is not None:
        cap = next(iter(per.values()))["by_split"]["forward"]["decision"]["cap"] if per else 0.10
        out.append({"id": "presence-rule-conservative", "severity": "low",
                    "text": f"The start-or-wait rule is conservative: it collided with the worker's return in {s_['interruption_rate_rule']:.1%} of started runs "
                            f"against an allowed {cap:.0%}, and used {s_['idle_used_rule']:.0%} of idle time against {s_['idle_used_idle5']:.0%} for "
                            f"running whenever idle five minutes. Runs are replayed one per decision point on held-out spells; interruption and idle-use "
                            "intervals count spells as independent."})
    return out
