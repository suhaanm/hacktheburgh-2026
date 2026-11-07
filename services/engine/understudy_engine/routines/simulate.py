"""Simulated workdays for ski rental: regret against the hindsight best and against break-even (ANA-11)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import skirental as sk


@dataclass(frozen=True)
class SimConfig:
    n_routines: int = 4000
    horizon_workdays: int = 60          # the planning horizon the build decision is made over
    history_workdays: int = 10          # days of history the forecast sees
    median_rate: float = 1.0            # runs per workday
    rate_sigma: float = 0.7
    p_retire: float = 0.45              # chance the routine ends within the horizon (the project stops)
    mean_life_workdays: float = 8.0     # mean remaining life of a routine that ends
    b_values: tuple[float, ...] = (4.0, 8.0, 16.0, 32.0)
    lambdas: tuple[float, ...] = (0.2, 0.5, 0.8)
    seed: int = 101


def simulate_routines(cfg: SimConfig):
    """Per routine: x (true runs in the horizon after the history window) and y (forecast from history alone).

    Mechanism: a daily Poisson process with a lognormal rate; with probability ``p_retire`` the routine ends after an
    exponential life. The forecast sees only the history window and assumes the rate continues for the whole horizon,
    so it is wrong exactly when the routine retires, and noisy through the sampling of a short history.
    """
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_routines
    rate = np.exp(rng.normal(np.log(cfg.median_rate), cfg.rate_sigma, n))
    retire = rng.random(n) < cfg.p_retire
    life = np.where(retire, rng.exponential(cfg.mean_life_workdays, n), np.inf)
    hist = rng.poisson(rate * cfg.history_workdays)
    fut_days = cfg.horizon_workdays - cfg.history_workdays
    active = np.minimum(life, fut_days)
    x = rng.poisson(rate * active)
    # the forecaster's posterior-mean rate: (history + prior) / (days + prior days), prior a weak 1 run per day
    r_hat = (hist + 1.0 * 3) / (cfg.history_workdays + 3.0)
    y = r_hat * fut_days
    return x.astype(float), y.astype(float)


def _boot(vals: np.ndarray, n_boot: int = 400, seed: int = 5) -> list[float]:
    rng = np.random.default_rng(seed)
    means = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(n_boot)]
    return [round(float(np.quantile(means, 0.025)), 3), round(float(np.quantile(means, 0.975)), 3)]


def regret_table(cfg: SimConfig | None = None) -> dict:
    cfg = cfg or SimConfig()
    x, y = simulate_routines(cfg)
    rows = []
    paired: dict[tuple, np.ndarray] = {}
    for b in cfg.b_values:
        opt = np.minimum(x, b)
        be = np.array([sk.cost(xi, sk.break_even_run(b), b) for xi in x]) - opt
        rows.append({"rule": "break-even", "b": b, "regret": round(float(be.mean()), 3), "ci": _boot(be),
                     "worst_ratio": round(float(np.max((be + opt) / np.maximum(opt, 1e-9))), 3)})
        rent = x - opt
        buy = b - opt
        rows.append({"rule": "always-rent", "b": b, "regret": round(float(rent.mean()), 3), "ci": _boot(rent)})
        rows.append({"rule": "buy-now", "b": b, "regret": round(float(buy.mean()), 3), "ci": _boot(buy)})
        for lam in cfg.lambdas:
            c = np.array([sk.cost(xi, sk.buy_run(yi, b, lam), b) for xi, yi in zip(x, y)]) - opt
            d = c - be
            rows.append({"rule": "predictions", "lambda": lam, "b": b, "regret": round(float(c.mean()), 3), "ci": _boot(c),
                         "vs_break_even": round(float(d.mean()), 3), "vs_break_even_ci": _boot(d),
                         "worst_ratio": round(float(np.max((c + opt) / np.maximum(opt, 1e-9))), 3),
                         "bound_ratio": round(sk.robustness(lam), 3)})
            paired[(b, lam)] = c
        # lambda learned online from the forecast errors of the routines seen so far
        errs: list[float] = []
        learned = np.zeros(len(x))
        lams = np.zeros(len(x))
        for i, (xi, yi) in enumerate(zip(x, y)):
            lam = sk.choose_lambda(errs[-200:])
            lams[i] = lam
            learned[i] = sk.cost(xi, sk.buy_run(yi, b, lam), b) - opt[i]
            errs.append(float(np.log((yi + 1.0) / (xi + 1.0))))
        rows.append({"rule": "predictions", "lambda": "learned", "b": b, "regret": round(float(learned.mean()), 3), "ci": _boot(learned),
                     "vs_break_even": round(float((learned - be).mean()), 3), "vs_break_even_ci": _boot(learned - be),
                     "mean_lambda": round(float(lams.mean()), 3)})
    return {"rows": rows, "cfg": cfg, "x": x, "y": y}
