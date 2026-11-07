"""Semi-Markov presence simulator (CAP-9).

States ACTIVE, IDLE, AWAY, OFF. Leaving OFF is a time-inhomogeneous exponential: an hour-of-week (here:
15-minute bin) dependent start hazard, sampled by inverting the cumulative hazard exactly. Leaving the other
states picks the next state with probabilities that depend on whether the time is in a lunch band or an
end-of-window zone, after a log-normal dwell. This is deliberately a different mechanism from the models that
later fit the data (Beta posteriors per 15-minute bin, kernel survival of idle spells).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

BIN_S = 900
BINS_PER_DAY = 96
DAY_S = 86400


@dataclass(frozen=True)
class StateParams:
    active_med_s: float = 50 * 60
    active_sigma: float = 0.5
    idle_med_s: float = 4 * 60
    idle_sigma: float = 0.8
    away_med_s: float = 22 * 60
    away_lunch_med_s: float = 45 * 60
    away_sigma: float = 0.6
    start_rate_per_h: float = 6.0     # hazard inside the start band of a window
    return_rate_per_h: float = 3.0    # hazard of coming back while OFF in the body of a window
    background_rate_per_h: float = 0.005
    p_lock_when_away: float = 0.65
    p_sleep_when_off: float = 0.85


def _lognorm(rnd: random.Random, med: float, sigma: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, rnd.lognormvariate(math.log(med), sigma)))


def hazard_arrays(day_windows: list[list[tuple[float, float]]], p: StateParams):
    """Per-bin start hazard (per hour), end-zone flags, lunch-band flags, for ``len(day_windows)+2`` days."""
    n_bins = (len(day_windows) + 2) * BINS_PER_DAY
    rate = [p.background_rate_per_h] * n_bins
    end_zone = [False] * n_bins
    lunch = [False] * n_bins
    in_win = [False] * n_bins
    for d, wins in enumerate(day_windows):
        for s, e in wins:
            b0 = d * BINS_PER_DAY + int(round(s * 4))
            b1 = d * BINS_PER_DAY + int(round(e * 4))
            for b in range(max(0, b0 + 3), min(n_bins, b1 - 1)):          # window body: people come back
                rate[b] = max(rate[b], p.return_rate_per_h)
            for b in range(max(0, b0 - 1), min(n_bins, b0 + 3)):          # start band [s - 15 min, s + 45 min)
                rate[b] = max(rate[b], p.start_rate_per_h)
            for b in range(max(0, b0 - 2), min(n_bins, b1 + 2)):
                in_win[b] = True
            for b in range(max(0, b1 - 1), min(n_bins, b1 + 12)):         # end zone [e - 15 min, e + 3 h)
                end_zone[b] = True
            if e - s >= 6:
                mid = (b0 + b1) // 2
                for b in range(mid - 3, mid + 3):
                    lunch[b] = True
    return rate, end_zone, lunch, in_win


def _off_wait(t: float, rate: list[float], rnd: random.Random) -> float:
    need = rnd.expovariate(1.0)
    b = int(t // BIN_S)
    acc = 0.0
    while b < len(rate):
        bin_end = (b + 1) * BIN_S
        seg = bin_end - t
        r = rate[b]
        h = r * seg / 3600.0
        if r > 0 and acc + h >= need:
            return t + (need - acc) / r * 3600.0
        acc += h
        t = bin_end
        b += 1
    return math.inf


def _pick(rnd: random.Random, options: list[tuple[str, float]]) -> str:
    x = rnd.random() * sum(w for _, w in options)
    for name, w in options:
        x -= w
        if x <= 0:
            return name
    return options[-1][0]


def simulate_states(day_windows: list[list[tuple[float, float]]], rnd: random.Random, p: StateParams = StateParams()):
    """Return ``[(state, t0, t1)]`` in seconds from day 0 midnight, covering ``len(day_windows)`` days."""
    horizon = len(day_windows) * DAY_S
    rate, end_zone, lunch, in_win = hazard_arrays(day_windows, p)
    t = 0.0
    state = "OFF"
    out: list[tuple[str, float, float]] = []
    while t < horizon:
        b = min(int(t // BIN_S), len(rate) - 1)
        if state == "OFF":
            t1 = _off_wait(t, rate, rnd)
            nxt = "ACTIVE"
        elif state == "ACTIVE":
            t1 = t + _lognorm(rnd, p.active_med_s, p.active_sigma, 300, 4 * 3600)
            b1 = min(int(t1 // BIN_S), len(rate) - 1)
            if not in_win[b1]:
                opts = [("OFF", 0.70), ("IDLE", 0.20), ("AWAY", 0.10)]   # an off-hours blip ends soon
            elif end_zone[b1]:
                opts = [("OFF", 0.90), ("IDLE", 0.06), ("AWAY", 0.04)]
            elif lunch[b1]:
                opts = [("AWAY", 0.50), ("IDLE", 0.45), ("OFF", 0.05)]
            else:
                opts = [("IDLE", 0.62), ("AWAY", 0.35), ("OFF", 0.03)]
            nxt = _pick(rnd, opts)
        elif state == "IDLE":
            t1 = t + _lognorm(rnd, p.idle_med_s, p.idle_sigma, 45, 40 * 60)
            b1 = min(int(t1 // BIN_S), len(rate) - 1)
            opts = [("OFF", 0.60), ("AWAY", 0.15), ("ACTIVE", 0.25)] if (end_zone[b1] or not in_win[b1]) else [("ACTIVE", 0.82), ("AWAY", 0.15), ("OFF", 0.03)]
            nxt = _pick(rnd, opts)
        else:  # AWAY
            med = p.away_lunch_med_s if lunch[b] else p.away_med_s
            t1 = t + _lognorm(rnd, med, p.away_sigma, 120, 3 * 3600)
            b1 = min(int(t1 // BIN_S), len(rate) - 1)
            opts = [("OFF", 0.80), ("ACTIVE", 0.20)] if (end_zone[b1] or not in_win[b1]) else [("ACTIVE", 0.97), ("OFF", 0.03)]
            nxt = _pick(rnd, opts)
        if t1 >= horizon:
            out.append((state, t, float(horizon)))
            break
        out.append((state, t, t1))
        t, state = t1, nxt
    return out
