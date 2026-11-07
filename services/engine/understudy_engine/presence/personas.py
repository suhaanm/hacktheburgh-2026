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
from .timeline import ACTIVE, SLOTS, DayObs, day_states_from_events, spells_from_events

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


def recovery(days: list[DayObs], truth_p: np.ndarray, prior: PriorHours, *, tune: bool = True) -> dict[str, Any]:
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

    return {
        "n_days": len(days),
        "rmse": round(rmse(p), 4),
        "rmse_prior_only": round(rmse(pri), 4),
        "rmse_unsmoothed": round(rmse(raw.p_active()), 4),
        "rmse_global_rate": round(rmse(np.full_like(p, float(np.mean([(d.states == ACTIVE).mean() for d in days])))), 4),
        "truth_inside_interval": round(float(np.mean((truth_p >= lo) & (truth_p <= hi))), 4),
        "interval_mean_width": round(float((hi - lo).mean()), 4),
        "active_h_per_week_fit": round(float(p.sum() * 0.25), 2),
        "active_h_per_week_truth": round(float(truth_p.sum() * 0.25), 2),
    }


def evaluate_persona(name: str, root: Path | None = None, *, d_min: float = 30.0, cap: float = 0.10) -> dict[str, Any]:
    events, truth = load_persona(name, root)
    tz = truth.get("tz", "UTC")
    days = day_states_from_events(events, tz=tz)
    spells = spells_from_events(events, tz=tz)
    prior = PriorHours()  # the role-pack hours; the personas deliberately differ from it
    rep = evaluate_presence(days, spells, prior, origin="synthetic", d_min=d_min, cap=cap, person=truth.get("person"),
                            note="synthetic persona; schedule changes on day 15")
    change = int(truth.get("change_day", 15))
    pre_days = [d for i, d in enumerate(days) if i + 1 < change]
    post_days = [d for i, d in enumerate(days) if i + 1 >= change]
    rep["recovery"] = {
        "pre_change": recovery(pre_days, _truth_matrix(truth, "pre"), prior),
        "post_change_fit_on_all_days": recovery(days, _truth_matrix(truth, "post"), prior),
        "post_change_fit_on_post_days": recovery(post_days, _truth_matrix(truth, "post"), prior),
    }
    rep["persona"] = truth.get("persona", name)
    rep["n_events"] = len(events)
    return rep


def evaluate_presence_all(root: Path | None = None, *, d_min: float = 30.0, cap: float = 0.10) -> dict[str, Any]:
    """Plain dict for the eval harness: one entry per persona that exists on disk, and a pooled summary."""
    per = {n: evaluate_persona(n, root, d_min=d_min, cap=cap) for n in PERSONAS if have_persona(n, root)}
    out: dict[str, Any] = {
        "name": "presence", "origin": "synthetic", "n": len(per), "n_unit": "personas", "interval_level": 0.95,
        "split": "forward and interleaved held-out days within each persona; truth only used to score recovery",
        "note": "Four synthetic personas, 21 days each, one schedule change on day 15. Not real people.",
        "personas": per,
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
    return out
