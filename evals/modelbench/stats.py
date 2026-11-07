"""Interval and summary helpers for the bake-off. Pure and deterministic (every resample has an explicit seed)."""
from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

Z95 = 1.96


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials; (0, 1) when n == 0."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got {k}/{n}")
    if n == 0:
        return 0.0, 1.0
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    return (0.0 if k == 0 else lo), (1.0 if k == n else hi)


def rate(k: int, n: int) -> dict[str, float | int | None]:
    """{k, n, p, lo, hi}: a proportion with its Wilson 95% interval (p is None when n == 0)."""
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "p": (k / n if n else None), "lo": round(lo, 4), "hi": round(hi, 4)}


def percentile(vals: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100); the same rule the router's meter uses."""
    s = sorted(vals)
    if not s:
        return None
    return s[max(0, min(len(s) - 1, math.ceil(q / 100.0 * len(s)) - 1))]


def bootstrap_ci(vals: Sequence[float], stat: Callable[[Sequence[float]], float | None], *, B: int = 2000, seed: int = 20261107,
                 alpha: float = 0.05) -> tuple[float, float] | None:
    """Percentile bootstrap interval of `stat` over `vals` (seeded). None when there are fewer than 2 values."""
    vals = list(vals)
    if len(vals) < 2:
        return None
    rng = random.Random(seed)
    n = len(vals)
    out = []
    for _ in range(B):
        r = stat([vals[rng.randrange(n)] for _ in range(n)])
        if r is not None:
            out.append(r)
    out.sort()
    if not out:
        return None
    return out[int(alpha / 2 * len(out))], out[min(len(out) - 1, int((1 - alpha / 2) * len(out)))]


def summarize(vals: Sequence[float], *, seed: int = 20261107) -> dict[str, object]:
    """n, mean, p50, p95 and a bootstrap 95% interval for each of p50 and p95."""
    vals = [float(v) for v in vals]
    p50, p95 = percentile(vals, 50), percentile(vals, 95)
    ci50 = bootstrap_ci(vals, lambda v: percentile(v, 50), seed=seed)
    ci95 = bootstrap_ci(vals, lambda v: percentile(v, 95), seed=seed + 1)
    return {"n": len(vals), "mean": (sum(vals) / len(vals) if vals else None), "p50": p50, "p50_ci": ci50, "p95": p95, "p95_ci": ci95}


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two (x0, y0, x1, y1) boxes."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def point_in_box(x: float, y: float, box: Sequence[float]) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def paired_diff(a: Sequence[int], b: Sequence[int], *, B: int = 2000, seed: int = 20261107) -> dict[str, object]:
    """Paired comparison of two 0/1 outcome vectors over the SAME cases: difference in rate (a - b), discordant counts, a paired
    bootstrap 95% interval of the difference, and an exact two-sided McNemar p-value."""
    if len(a) != len(b):
        raise ValueError("paired vectors must have the same length")
    n = len(a)
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    diff = (sum(a) - sum(b)) / n if n else None
    ci = bootstrap_ci([x - y for x, y in zip(a, b)], lambda v: sum(v) / len(v), B=B, seed=seed)
    m = only_a + only_b
    if m == 0:
        p = 1.0
    else:
        k = min(only_a, only_b)
        p = min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m)
    return {"n": n, "diff": diff, "ci": ci, "only_a": only_a, "only_b": only_b, "mcnemar_p": round(p, 4)}
