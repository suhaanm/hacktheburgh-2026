"""Routine finder under mismatch, from the routines module's public functions (``find_routines``, ``detect_routines``).

A cluster is *true* when at least half its members are instances of one planted routine; a planted routine is *detectable*
with at least 3 instances and *found* when a true cluster has it as its majority. Fit on X = the finder's cut height, chosen
from a grid to maximise F1 of (cluster precision, recall) pooled over X's people; the fixed shipped value 0.35 is reported
beside it (no fitting). Proposals (after the value gate) are scored at the shipped config only.
"""
from __future__ import annotations

from collections import Counter

from ..core import Episode
from ..routines.detect import DetectConfig, detect_routines
from ..routines.finder import FinderConfig, find_routines

GRID = (0.20, 0.25, 0.30, 0.35, 0.40, 0.50)
DEFAULT_T = 0.35
MIN_SUPPORT = 3


def score_person(eps: list[Episode], labels: dict[str, str], threshold: float) -> dict:
    """Cluster-level tallies for one person. ``labels``: task_id -> routine name (anything else is ad hoc)."""
    counts = Counter(labels.get(e.task_id, "adhoc") for e in eps)
    counts.pop("adhoc", None)
    detectable = {k for k, n in counts.items() if n >= MIN_SUPPORT}
    clusters = find_routines(eps, FinderConfig(threshold=threshold, min_support=MIN_SUPPORT))
    true_n, found = 0, set()
    for c in clusters:
        cnt = Counter(labels.get(e.task_id, "adhoc") for e in c.episodes)
        top, n = cnt.most_common(1)[0]
        if top != "adhoc" and n / len(c.episodes) >= 0.5:
            true_n += 1
            found.add(top)
    return {"clusters": len(clusters), "true": true_n, "detectable": len(detectable), "found": len(found & detectable),
            "planted": len(counts), "episodes": len(eps)}


def score_proposals(eps: list[Episode], labels: dict[str, str], pack, person: str, draws: int = 1000) -> dict:
    """Proposals after the value and skill gates at the shipped finder config."""
    det = detect_routines(eps, pack, person=person, cfg=DetectConfig(finder=FinderConfig(threshold=DEFAULT_T), forecast_draws=draws))
    shown = [d for d in det if d["proposable"] or d["value"]["confidence"] >= 0.5]
    true_n = 0
    for d in shown:
        cnt = Counter(labels.get(t, "adhoc") for t in d["member_task_ids"])
        top, n = cnt.most_common(1)[0]
        if top != "adhoc" and n / len(d["member_task_ids"]) >= 0.5:
            true_n += 1
    return {"proposals": len(shown), "proposals_true": true_n, "reported": len(det)}


def choose_threshold(per_person_by_t: dict[float, list[dict]]) -> tuple[float, dict[float, float]]:
    """The grid value with the best pooled F1 over the training people (ties go to the shipped value, then the smaller)."""
    f1s: dict[float, float] = {}
    for t, rows in per_person_by_t.items():
        c = sum(r["clusters"] for r in rows)
        p = sum(r["true"] for r in rows) / c if c else 0.0
        d = sum(r["detectable"] for r in rows)
        r_ = sum(r["found"] for r in rows) / d if d else 0.0
        f1s[t] = 2 * p * r_ / (p + r_) if p + r_ > 0 else 0.0
    best = max(f1s.values())
    cands = [t for t, f in f1s.items() if abs(f - best) < 1e-9]
    pick = DEFAULT_T if DEFAULT_T in cands else min(cands)
    return pick, f1s
