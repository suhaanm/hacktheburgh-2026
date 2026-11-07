"""Expert versus learner comparison of commit habits, with bootstrap intervals and a placebo (GIT-1).

For each habit (``features.HABITS``) the learner value is ``sum(num) / sum(den)`` over the learner's commits; the expert
reference is the mean of the experts' own ratios (every expert counts once). The difference ``delta = learner - expert``
has a 95% percentile interval from a two-stage bootstrap: the learner's active **days** are resampled with replacement
(commits within a day are not independent), and on the expert side days are resampled within each expert and then the
**experts** are resampled with replacement. A habit is *flagged* when

    * the difference is in the bad direction and at least the habit's ``min_delta`` (a practical floor), and
    * the interval excludes zero in the bad direction, and
    * the learner has at least ``MIN_DEN`` commits in the denominator.

The placebo compares every expert, as if it were the learner, with the other experts: a procedure with no true gap. It
should flag next to nothing and give differences near zero. Thresholds were fixed before the evaluation seeds were drawn.
"""
from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence

import numpy as np

from .features import HABIT_IDS, HABITS, CommitTable
from .stats import interval, rate, rnd

MIN_DEN = 5
B_DEFAULT = 1000
LEVEL = 0.95


def _day_resampled_ratio(num_d: np.ndarray, den_d: np.ndarray, B: int, rng: np.random.Generator) -> np.ndarray:
    d = len(num_d)
    if d == 0:
        return np.full(B, np.nan)
    idx = rng.integers(0, d, size=(B, d))
    n, m = num_d[idx].sum(axis=1), den_d[idx].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(m > 0, n / m, np.nan)


def expert_reference(experts: Mapping[str, CommitTable], habit: str) -> float:
    vals = [t.ratio(habit) for t in experts.values() if t.den[habit].sum() > 0]
    return float(np.mean(vals)) if vals else float("nan")


def _expert_boot(experts: Sequence[CommitTable], habit: str, B: int, rng: np.random.Generator) -> np.ndarray:
    E = len(experts)
    ratios = np.empty((E, B))
    for e, tb in enumerate(experts):
        num_d, den_d = tb.day_sums(habit)
        ratios[e] = _day_resampled_ratio(num_d, den_d, B, rng)
    pick = rng.integers(0, E, size=(B, E))
    vals = ratios[pick, np.arange(B)[:, None]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(vals, axis=1)


def habit_rows(learner: CommitTable, experts: Mapping[str, CommitTable], *, B: int = B_DEFAULT, seed: int = 0) -> list[dict]:
    """One row per habit: ``{id, label, learner, expert, delta, ci, bad, min_delta, n_den, flagged, reason}``."""
    exp = list(experts.values())
    rng = np.random.default_rng(seed)
    rows = []
    for hid in HABIT_IDS:
        h = HABITS[hid]
        lv = learner.ratio(hid)
        ev = expert_reference(experts, hid)
        n_den = int(learner.den[hid].sum())
        row = {"id": hid, "label": h.label, "learner": rnd(lv), "expert": rnd(ev), "bad": h.bad, "min_delta": h.min_delta,
               "n_den": n_den, "n_num": int(learner.num[hid].sum()), "unit": h.unit}
        if n_den < MIN_DEN or not exp or np.isnan(ev):
            row.update(delta=None, ci=[None, None], flagged=False, reason="too_few_commits")
            rows.append(row)
            continue
        num_d, den_d = learner.day_sums(hid)
        lb = _day_resampled_ratio(num_d, den_d, B, rng)
        eb = _expert_boot(exp, hid, B, rng)
        delta = lv - ev
        ci = interval(lb - eb, LEVEL)
        bound = ci[0] if h.bad > 0 else ci[1]
        in_dir = h.bad * delta >= h.min_delta
        clear = bound is not None and h.bad * bound > 0
        row.update(delta=rnd(delta), ci=ci, flagged=bool(in_dir and clear),
                   reason="flagged" if (in_dir and clear) else ("below_min_delta" if not in_dir else "interval_includes_zero"))
        rows.append(row)
    return rows


def flagged_ids(rows: Sequence[dict]) -> set[str]:
    return {r["id"] for r in rows if r.get("flagged")}


def placebo(experts: Mapping[str, CommitTable], *, B: int = 300, seed: int = 11) -> dict:
    """Each expert against the other experts. Returns the false-flag rate (Wilson interval) and the mean absolute delta
    per habit. Needs at least three experts."""
    names = sorted(experts)
    if len(names) < 3:
        return {"status": "not_run", "reason": "needs at least three experts"}
    flags = 0
    pairs = 0
    deltas: dict[str, list[float]] = {h: [] for h in HABIT_IDS}
    per_habit: dict[str, int] = {h: 0 for h in HABIT_IDS}
    for k, name in enumerate(names):
        rest = {n: experts[n] for n in names if n != name}
        rows = habit_rows(experts[name], rest, B=B, seed=seed + k)
        for r in rows:
            if r["reason"] == "too_few_commits":
                continue
            pairs += 1
            deltas[r["id"]].append(abs(r["delta"]))
            if r["flagged"]:
                flags += 1
                per_habit[r["id"]] += 1
    return {
        "status": "ok", "n_experts": len(names), "pairs": pairs, "false_flags": rate(flags, pairs),
        "mean_abs_delta": {h: rnd(float(np.mean(v))) if v else None for h, v in deltas.items()},
        "false_flags_by_habit": per_habit,
    }


def score_detection(detected: Mapping[str, set[str]], planted: Mapping[str, set[str]], habits: Sequence[str] = HABIT_IDS) -> dict:
    """Planted-habit recovery over (learner, habit) pairs: precision and recall with Wilson intervals, per habit and overall."""
    tp = fp = fn = tn = 0
    by: dict[str, list[int]] = {h: [0, 0, 0, 0] for h in habits}
    for person, truth in planted.items():
        got = detected.get(person, set())
        for h in habits:
            t, g = h in truth, h in got
            i = (0 if t and g else 1 if g and not t else 2 if t and not g else 3)
            by[h][i] += 1
            tp, fp, fn, tn = tp + (i == 0), fp + (i == 1), fn + (i == 2), tn + (i == 3)

    def pr(a: int, b: int, c: int, d: int) -> dict:
        return {"tp": a, "fp": b, "fn": c, "tn": d, "precision": rate(a, a + b), "recall": rate(a, a + c),
                "specificity": rate(d, d + b)}

    return {"overall": pr(tp, fp, fn, tn), "by_habit": {h: pr(*v) for h, v in by.items()}, "pairs": tp + fp + fn + tn}
