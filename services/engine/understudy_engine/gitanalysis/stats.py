"""Tiny statistics helpers (numpy only, fixed seeds). Local copies so this package does not import the eval harness."""
from __future__ import annotations

import math

import numpy as np

Z95 = 1.959963984540054


def rnd(x, nd: int = 4):
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    return None if math.isnan(xf) or math.isinf(xf) else round(xf, nd)


def interval(samples, level: float = 0.95, nd: int = 4) -> list:
    a = np.asarray(samples, dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return [None, None]
    lo, hi = np.percentile(a, [100 * (1 - level) / 2, 100 * (1 + level) / 2])
    return [rnd(lo, nd), rnd(hi, nd)]


def wilson(k: int, n: int, z: float = Z95) -> list:
    if n <= 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [rnd(max(0.0, c - h)), rnd(min(1.0, c + h))]


def rate(k: int, n: int) -> dict:
    return {"k": int(k), "n": int(n), "value": rnd(k / n) if n else None, "ci": wilson(k, n)}
