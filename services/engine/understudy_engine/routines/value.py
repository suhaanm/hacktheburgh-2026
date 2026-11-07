"""Value model (ANA-11): hours saved and net value of automating a routine, with intervals.

    hours_saved = forecast_runs * time_per_run * (1 - judgement_share)
    net         = hours_saved * wage - build_cost - maintenance_risk - error_cost

The worker still does the judgement part, so only the non-judgement share of a run is saved. ``wage`` is a
parameter (default 15 pounds an hour: an illustration only, see docs/DECISIONS.md concern 8). Build cost is in units of
one manual run (``build_cost_runs``, the same ``b`` ski rental uses). Everything is a draw, so intervals carry the
uncertainty of the forecast and of the per-run time; ``confidence`` is P(net > 0).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ValueParams:
    wage_gbp_h: float = 15.0
    build_cost_runs: float = 6.0         # b: effort to set up and check the automation, in manual runs
    maintenance_risk_gbp: float = 5.0    # expected upkeep over the horizon
    error_rate: float = 0.02             # chance an automated run goes wrong
    error_cost_gbp: float = 5.0          # cost of one wrong run
    horizon_weeks: int = 4


def hours_per_run_draws(durations_s: Sequence[float], n: int, seed: int = 23) -> np.ndarray:
    """Bootstrap draws of the mean time per run, in hours."""
    d = np.asarray(durations_s, dtype=float)
    if d.size == 0:
        return np.zeros(n)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(n, d.size))
    return d[idx].mean(axis=1) / 3600.0


def value_model(run_draws: np.ndarray, durations_s: Sequence[float], judgement_share: float, p: ValueParams,
                seed: int = 23) -> dict:
    n = len(run_draws)
    t_run = hours_per_run_draws(durations_s, n, seed)          # hours per manual run
    saved = run_draws * t_run * max(0.0, 1.0 - judgement_share)
    build = p.build_cost_runs * t_run * p.wage_gbp_h
    errors = run_draws * p.error_rate * p.error_cost_gbp
    net = saved * p.wage_gbp_h - build - p.maintenance_risk_gbp - errors
    q = lambda a: [round(float(x), 2) for x in np.quantile(a, [0.025, 0.975])]  # noqa: E731
    return {
        "hours_saved": q(saved), "hours_saved_mean": round(float(saved.mean()), 2),
        "net_gbp": [round(float(x), 1) for x in np.quantile(net, [0.025, 0.975])], "net_gbp_mean": round(float(net.mean()), 1),
        "confidence": round(float((net > 0).mean()), 3), "horizon_weeks": p.horizon_weeks,
        "assumptions": {"wage_gbp_h": p.wage_gbp_h, "build_cost_runs": p.build_cost_runs, "error_rate": p.error_rate,
                        "error_cost_gbp": p.error_cost_gbp, "maintenance_risk_gbp": p.maintenance_risk_gbp},
    }
