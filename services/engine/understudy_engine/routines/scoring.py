"""Score a cluster (ANA-10): count, minutes per week, CV of duration, judgement share, and the template it matches."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core import Episode
from .finder import Cluster, collapse, edit_distance

DEFAULT_JUDGEMENT = frozenset({"SEARCH", "REFORMULATE", "COMPARE", "DECIDE"})


@dataclass(frozen=True)
class Score:
    count: int
    minutes_per_week: float
    cv: float
    judgement_share: float
    mean_duration_s: float
    n_days: int          # distinct days the routine ran on
    span_days: float     # observation window the rate is computed over


def observation_span_days(episodes: Iterable[Episode], min_days: float = 7.0) -> float:
    ts = [(e.t0, e.t1) for e in episodes]
    if not ts:
        return min_days
    return max(min_days, (max(t1 for _, t1 in ts) - min(t0 for t0, _ in ts)) / 86400.0)


def judgement_share(seq: Sequence[str], judgement: Iterable[str] = DEFAULT_JUDGEMENT) -> float:
    """Searches, compares, decides (and the pack's own judgement cogs) divided by the length of the routine."""
    j = set(judgement)
    return sum(1 for c in seq if c in j) / len(seq) if seq else 0.0


def score_cluster(cl: Cluster, span_days: float, judgement: Iterable[str] = DEFAULT_JUDGEMENT) -> Score:
    durs = np.array([e.duration for e in cl.episodes], dtype=float)
    mean = float(durs.mean()) if len(durs) else 0.0
    cv = float(durs.std(ddof=1) / mean) if len(durs) > 1 and mean > 0 else 0.0
    weeks = max(span_days, 7.0) / 7.0
    days = len({int(e.t0 // 86400) for e in cl.episodes})
    return Score(count=cl.size, minutes_per_week=float(durs.sum() / 60.0 / weeks), cv=cv,
                 judgement_share=judgement_share(cl.medoid, judgement), mean_duration_s=mean, n_days=days, span_days=span_days)


def match_template(medoid: Sequence[str], templates: Sequence[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    """Best pack template whose cog sequence is within its own ``match_distance`` of the cluster medoid."""
    best, best_d = None, 1.0
    for t in templates:
        d = edit_distance(tuple(medoid), collapse(t["cogs"]))
        if d <= float(t.get("match_distance", 0.3)) and d < best_d:
            best, best_d = t, d
    return best, best_d


def auto_id(medoid: Sequence[str]) -> str:
    return "auto-" + hashlib.sha1("|".join(medoid).encode()).hexdigest()[:6]


def auto_title(medoid: Sequence[str]) -> str:
    words = []
    for c in medoid:
        w = c.replace("_", " ").lower()
        if not words or words[-1] != w:
            words.append(w)
    head = ", then ".join(words[:4]) + ("..." if len(words) > 4 else "")
    return "Repeat: " + head


def wilson_halfwidth(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    p = k / n
    return 1.96 * math.sqrt(p * (1 - p) / n)
