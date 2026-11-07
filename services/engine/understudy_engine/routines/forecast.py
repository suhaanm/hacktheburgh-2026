"""Recurrence forecast (ANA-11): how many times will this routine run in the next ``h`` weeks, with an interval.

Model: runs per day follow a Poisson process whose rate depends on the day of week (weekly seasonality). Each
weekday's rate has a Gamma posterior; the prior is a Gamma centred on the routine's overall daily rate and
worth ``prior_days`` days of data, so a weekday seen only three times is pulled toward the overall rate. Week to week
the rate also wobbles: if the observed weekly totals are more dispersed than Poisson, a Gamma 'frailty' per week
(negative-binomial counts) widens the interval. The forecast is a Monte Carlo over rates and counts with a fixed
seed, so it is deterministic.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

DAY = 86400.0


@dataclass(frozen=True)
class Forecast:
    mean_runs: float
    lo: float
    hi: float
    runs_per_week: float
    dispersion: float          # NB dispersion alpha (0 = Poisson)
    draws: np.ndarray          # Monte Carlo draws of the total over the horizon (for the value model)
    horizon_days: int

    def interval(self) -> list[float]:
        return [round(self.lo, 2), round(self.hi, 2)]


def _dow(ts: float) -> int:
    return datetime.fromtimestamp(ts, timezone.utc).weekday()


def _days_in_window(start: float, end: float) -> np.ndarray:
    """Count of each weekday in [start, end), partial first and last days counted as fractions."""
    out = np.zeros(7)
    t = start
    while t < end:
        day_end = (int(t // DAY) + 1) * DAY
        seg = min(day_end, end) - t
        out[_dow(t)] += seg / DAY
        t = min(day_end, end)
    return out


def fit_forecast(times: Sequence[float], window: tuple[float, float], horizon_days: int = 28, *,
                 prior_days: float = 3.0, draws: int = 4000, seed: int = 17, workdays_only: bool | None = None) -> Forecast:
    """``times``: unix seconds of past runs. ``window``: the observation window (start, end) they came from.

    Weekdays the person never works (no activity at all in the window) are not a property of the routine; pass
    the window as the span you actually observed. ``workdays_only=None`` lets the data decide: a weekday whose
    posterior rate is low simply forecasts few runs.
    """
    start, end = window
    exposure = _days_in_window(start, end)
    counts = np.zeros(7)
    for t in times:
        if start <= t < end:
            counts[_dow(t)] += 1
    total_days = max(exposure.sum(), 1e-9)
    overall = counts.sum() / total_days
    a0, b0 = overall * prior_days + 1e-3, prior_days
    a, b = a0 + counts, b0 + exposure

    # week-level dispersion from weekly totals (needs at least three whole weeks)
    n_weeks = int((end - start) // (7 * DAY))
    alpha = 0.0
    if n_weeks >= 3:
        wk = np.zeros(n_weeks)
        for t in times:
            k = int((t - start) // (7 * DAY))
            if 0 <= k < n_weeks:
                wk[k] += 1
        m, v = wk.mean(), wk.var(ddof=1)
        if m > 0:
            alpha = float(np.clip((v - m) / (m * m), 0.0, 1.5))

    rng = np.random.default_rng(seed)
    lam = rng.gamma(a[None, :], 1.0 / b[None, :], size=(draws, 7))           # per-weekday rates, one draw each
    # horizon days: starting at the next full day after the window
    h0 = int(np.ceil(end / DAY)) * DAY
    dows = np.array([_dow(h0 + i * DAY + 1) for i in range(horizon_days)])
    week_idx = np.arange(horizon_days) // 7
    n_wk = int(week_idx.max()) + 1
    if alpha > 0:
        frail = rng.gamma(1.0 / alpha, alpha, size=(draws, n_wk))
    else:
        frail = np.ones((draws, n_wk))
    mu = lam[:, dows] * frail[:, week_idx]
    total = rng.poisson(mu).sum(axis=1).astype(float)
    lo, hi = np.quantile(total, [0.025, 0.975])
    return Forecast(float(total.mean()), float(lo), float(hi), float(total.mean() / (horizon_days / 7.0)), alpha, total, horizon_days)


def backtest_coverage(times: Sequence[float], start: float, split: float, end: float, **kw) -> dict[str, float]:
    """Fit on [start, split) and compare with what happened in [split, end). For the forecast's own calibration."""
    horizon = max(1, int(round((end - split) / DAY)))
    f = fit_forecast(times, (start, split), horizon, **kw)
    actual = float(sum(1 for t in times if split <= t < end))
    return {"predicted": f.mean_runs, "lo": f.lo, "hi": f.hi, "actual": actual, "inside": float(f.lo <= actual <= f.hi)}
