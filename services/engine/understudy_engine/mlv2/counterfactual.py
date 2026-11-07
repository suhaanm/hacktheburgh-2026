"""M4: counterfactual seconds (PLAN.md section 6.6): how many seconds would be recovered if one habit were fixed.

SEQUENCE-LEVEL REPLAY. Take the aligned columns of a novice case against an expert, group them by habit (v1's labels), and replace the novice's
segment of each habit with the expert's segment:

  extra step the expert does not take     removed; the novice's dwell on it is recovered                      (+ dwell)
  step the expert takes and the novice skipped  re-inserted at the expert's dwell scaled by the case's pace ratio     (- rho x expert dwell)
  step substituted for another            replaced by the expert's step at the scaled dwell                    (novice dwell - rho x expert dwell)
  step both take                          (the "pace" habit) recovered if the novice were as fast as the expert (novice dwell - expert dwell)

``rho`` is the novice's pace on this case: total novice dwell over total expert dwell on the columns both traverse (matches and substitutions).
Q1 uses it; Q1b prices the re-inserted and substituted steps at the unscaled expert dwell, which is exactly v1's pricing.

ASSUMES the rest of the path would be unchanged when the habit is fixed. FAILS when habits interact (a skipped check causes the rework that later
steps depend on; fixing one changes what the other costs) or when two habits share steps (the seconds can move between them). The replay's time
is a sum over disjoint column sets, so on this additive accounting the Shapley interaction is zero by construction; ``stress_test_interaction`` shows what
happens to a single-habit replay, and to a Shapley allocation, when the world has an interaction we planted.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from understudy_engine.core import Episode
from understudy_engine.genome.align import Alignment
from understudy_engine.genome.labels import LABEL_ORDER, label_columns


def pace_ratio(al: Alignment, ref: Episode, ep: Episode, *, lo: float = 0.5, hi: float = 3.0) -> float:
    """Novice dwell over expert dwell on the shared columns (matches and substitutions), clipped to a sane range; 1.0 when nothing is shared."""
    num = den = 0.0
    for c in al.columns:
        if c.i is not None and c.j is not None:
            num += ep.cogs[c.j].dwell
            den += ref.cogs[c.i].dwell
    if den <= 0:
        return 1.0
    return float(np.clip(num / den, lo, hi))


def splice_seconds(al: Alignment, ref: Episode, ep: Episode, *, scaled: bool = True) -> np.ndarray:
    """Seconds recovered per waterfall label if that label's columns were spliced to the expert's segment. Order is LABEL_ORDER."""
    rho = pace_ratio(al, ref, ep) if scaled else 1.0
    labels = label_columns(al)
    out = {l: 0.0 for l in LABEL_ORDER}
    for lab, c in zip(labels, al.columns):
        if c.op == "gap_expert":                       # the novice's extra step is removed
            out[lab] += ep.cogs[c.j].dwell
        elif c.op == "gap_novice":                     # the expert's step is inserted where the novice skipped it
            out[lab] -= rho * ref.cogs[c.i].dwell
        elif c.op == "mismatch":
            out[lab] += ep.cogs[c.j].dwell - rho * ref.cogs[c.i].dwell
        else:                                          # match: only "pace" gets an expert-speed counterfactual (unscaled by definition)
            out[lab] += ep.cogs[c.j].dwell - ref.cogs[c.i].dwell
    return np.array([out[l] for l in LABEL_ORDER])


def q1_functional(al: Alignment, ref: Episode, ep: Episode) -> np.ndarray:
    return splice_seconds(al, ref, ep, scaled=True)


def q1b_functional(al: Alignment, ref: Episode, ep: Episode) -> np.ndarray:
    return splice_seconds(al, ref, ep, scaled=False)


# ------------------------------------------------------------------------------------------------ Shapley
def shapley_values(habits: list[str], value) -> dict[str, float]:
    """Exact Shapley values by enumerating all subsets (at most about 10 habits). ``value`` maps a frozenset of habits to a number; the
    empty set must be 0 (or is used as the baseline)."""
    n = len(habits)
    if n > 10:
        raise ValueError("exact enumeration is for small habit sets (at most 10)")
    cache: dict[frozenset, float] = {}

    def v(S: frozenset) -> float:
        if S not in cache:
            cache[S] = float(value(S))
        return cache[S]

    phi = {h: 0.0 for h in habits}
    fact = math.factorial
    for h in habits:
        rest = [x for x in habits if x != h]
        for k in range(len(rest) + 1):
            w = fact(k) * fact(n - k - 1) / fact(n)
            for comb in itertools.combinations(rest, k):
                S = frozenset(comb)
                phi[h] += w * (v(S | {h}) - v(S))
    return phi


def splice_value_function(sec_by_habit: dict[str, float]):
    """Value of a habit subset under the replay accounting: the seconds recovered by splicing all of them in one replay, a sum over disjoint
    column sets, hence additive (the interaction is zero by construction)."""
    return lambda S: sum(sec_by_habit.get(h, 0.0) for h in S)


@dataclass
class InteractionStress:
    habits: list[str]
    true_shapley: dict[str, float]
    single_replay: dict[str, float]          # naive: time with the habit minus time with it fixed, others left as they are
    fitted_shapley: dict[str, float]         # Shapley of an OLS-with-pairwise-interactions model fitted to noisy cases
    total_true: float
    single_replay_sum: float
    note: str


def stress_test_interaction(n_cases: int = 400, seed: int = 0, noise_s: float = 6.0) -> InteractionStress:
    """A labelled stress test with an interaction WE planted (invented, not data about work): three habits with additive prices plus a
    multiplicative interaction (rework is 1.5 times slower when the person also rereads). The truth is known, so the three estimators can be
    compared with it: the single-habit replay does not sum to the total when habits interact; the Shapley allocation does, if its value function
    can represent the interaction (here a regression with pairwise terms fitted on the cases)."""
    rng = np.random.default_rng(seed)
    hab = ["repeated_reads", "missed_check", "search_loops"]
    a = {"repeated_reads": 30.0, "missed_check": 60.0, "search_loops": 70.0}
    b = {("repeated_reads", "missed_check"): 45.0}          # extra seconds when both are present (the planted interaction)

    def true_time(z: dict[str, int]) -> float:
        t = 300.0 + sum(a[h] * z[h] for h in hab)
        for (h1, h2), c in b.items():
            t += c * z[h1] * z[h2]
        return t

    def v_true(S: frozenset) -> float:                       # seconds recovered from the full-habit case when the habits in S are fixed
        full = {h: 1 for h in hab}
        fixed = {h: (0 if h in S else 1) for h in hab}
        return true_time(full) - true_time(fixed)

    true_phi = shapley_values(hab, v_true)
    single = {h: v_true(frozenset({h})) for h in hab}
    # fit time ~ habit indicators + pairwise products on noisy cases drawn with random habit sets
    Z = rng.integers(0, 2, size=(n_cases, len(hab)))
    T = np.array([true_time({h: int(z[i]) for i, h in enumerate(hab)}) for z in Z]) + rng.normal(0, noise_s, n_cases)
    cols = [np.ones(n_cases)] + [Z[:, i] for i in range(len(hab))] + [Z[:, i] * Z[:, j] for i in range(len(hab)) for j in range(i + 1, len(hab))]
    beta, *_ = np.linalg.lstsq(np.column_stack(cols), T, rcond=None)
    pairs = [(i, j) for i in range(len(hab)) for j in range(i + 1, len(hab))]

    def f(z: np.ndarray) -> float:
        out = beta[0] + sum(beta[1 + i] * z[i] for i in range(len(hab)))
        for k, (i, j) in enumerate(pairs):
            out += beta[1 + len(hab) + k] * z[i] * z[j]
        return float(out)

    def v_fit(S: frozenset) -> float:
        full = np.ones(len(hab))
        fixed = np.array([0.0 if h in S else 1.0 for h in hab])
        return f(full) - f(fixed)

    fit_phi = shapley_values(hab, v_fit)
    return InteractionStress(
        hab, true_phi, single, fit_phi, v_true(frozenset(hab)), sum(single.values()),
        "Invented stress test: the true prices are additive plus one planted interaction. The single-habit replays double-count the interaction "
        "(each habit's replay includes all of it), so they sum to more than the total; the Shapley allocation shares it and sums to the total.")
