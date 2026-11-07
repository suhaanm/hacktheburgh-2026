"""A generative model of the live study, for a power check of the PRE-REGISTERED analysis (evals/study/ANALYSIS_PLAN.md).

The analysis is imported from `evals/study/analyze.py` (read-only): `t_interval`, `sign_flip_p`, `skill_score`'s scoring rule.
The generator is deliberately a different mechanism from the analysis (a hierarchical logit model, not a t test):

  person i, skill s in {cliff, reconcile}, block j in {1, 2}, practice condition c in {coached, uncoached}
    eta = mu_s + u_i + v_is                       baseline propensity: skill difficulty + person + person-by-skill, all logit scale
        + gamma * [c = coached]                    the training gain from coached practice (the effect being sought)
        + [j = 2] * ( omega + kappa * G1 )         block-2 nuisance: omega = order/fatigue shift; kappa * G1 = carry-over,
                                                   where G1 = g_u + gamma * [block 1 was coached] is the training block 1 gave
    P(check) = sigmoid(eta)
  measurement (the REAL discrete score in [0, 1]):
    cliff      two independent binary checks (one per calculator) -> score = (X1 + X2) / 2, in {0, 1/2, 1}
    reconcile  one binary check                                    -> score = X, in {0, 1}
  participant difference d = score(coached skill block) - score(uncoached skill block)

The estimand is the DIRECT coaching effect: the mean over people and both skills of sigmoid(b + gamma) - sigmoid(b), in
probability points. Nuisances (omega, kappa) are not part of it, so any change they cause in the estimate shows up as bias.

With g_u > 0 and no coaching effect (gamma = 0), carry-over is the same shift in block 2 for everyone; the balanced design
should cancel it. When gamma > 0, carry-over spills the coached gain onto the other skill, which dilutes the contrast: the
design cannot cancel that, and the bias column shows how much.
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import stats

SKILLS = ("cliff", "reconcile")
POSSIBLE = {"cliff": 2, "reconcile": 1}
G_UNCOACHED = 0.4          # logit gain that uncoached practice itself gives (part of the baseline; transfers under carry-over)
FALLBACK_SEQUENCES = {
    "S1": [("cliff", "coached"), ("reconcile", "uncoached")],
    "S2": [("reconcile", "coached"), ("cliff", "uncoached")],
    "S3": [("cliff", "uncoached"), ("reconcile", "coached")],
    "S4": [("reconcile", "uncoached"), ("cliff", "coached")],
}


@dataclass(frozen=True)
class Population:
    """Heterogeneity of the people (logit scale). Defaults are assumptions, not estimates."""
    mu_cliff: float = -0.8        # per-check baseline about 0.31: the Check cliff edges button is visible but not obvious
    mu_reconcile: float = -0.4    # about 0.40 baseline: the form defaults to 'agree', the right answer is 'discrepancy'
    sd_person: float = 0.8        # person-level propensity shared across skills
    sd_skill: float = 0.5         # person-by-skill propensity


DEFAULT_POP = Population()


def _repo_study_dir() -> Path:
    from understudy_engine.store.paths import repo_root
    return repo_root() / "evals" / "study"


@lru_cache(maxsize=1)
def load_analysis():
    """The pre-registered analysis module, imported by path (it is a script, not a package). Never edited."""
    path = _repo_study_dir() / "analyze.py"
    if not path.is_file():
        raise FileNotFoundError(f"pre-registered analysis not found: {path}")
    spec = importlib.util.spec_from_file_location("preregistered_analyze", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def sequences() -> dict[str, list[tuple[str, str]]]:
    """The counterbalanced sequences S1 to S4, from the design file when it is there."""
    path = _repo_study_dir() / "make_assignments.py"
    if path.is_file():
        spec = importlib.util.spec_from_file_location("preregistered_assignments", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        seq = getattr(mod, "SEQUENCES", None)
        if seq:
            return {k: [tuple(x) for x in v] for k, v in seq.items()}
    return FALLBACK_SEQUENCES


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def true_effect(gamma: float, pop: Population = DEFAULT_POP, n_mc: int = 400_000, seed: int = 20261107) -> float:
    """The direct coaching effect in score units (probability points / 100), by Monte Carlo over the population."""
    rng = np.random.default_rng(seed)
    u = rng.normal(0, pop.sd_person, n_mc)
    out = 0.0
    for mu in (pop.mu_cliff, pop.mu_reconcile):
        b = mu + u + rng.normal(0, pop.sd_skill, n_mc)
        out += float(np.mean(_sigmoid(b + gamma) - _sigmoid(b)))
    return out / 2.0


def simulate_differences(n: int, reps: int, gamma: float, kappa: float, omega: float, *, pop: Population = DEFAULT_POP,
                         seed: int = 0) -> np.ndarray:
    """(reps, n) participant differences d on the exactly counterbalanced design; n must be a multiple of 4 and each
    sequence gets n / 4 people (n = 4 is the real study: one person per sequence)."""
    if n % 4:
        raise ValueError("n must be a multiple of 4 (balanced across the four sequences)")
    seqs = sequences()
    names = sorted(seqs)
    ss = np.random.SeedSequence([seed, n, int(round(gamma * 1000)), int(round(kappa * 1000)), int(round(omega * 1000)) + 10_000])
    rng = np.random.default_rng(ss)
    per_seq = n // 4
    u = rng.normal(0, pop.sd_person, (reps, n))
    v = {s: rng.normal(0, pop.sd_skill, (reps, n)) for s in SKILLS}
    mu = {"cliff": pop.mu_cliff, "reconcile": pop.mu_reconcile}
    unif = {s: rng.random((reps, n, POSSIBLE[s])) for s in SKILLS}
    d = np.zeros((reps, n))
    col = 0
    for name in names:
        (s1, c1), (s2, c2) = seqs[name]
        for _ in range(per_seq):
            scores = {}
            for block, (skill, cond) in enumerate(((s1, c1), (s2, c2)), start=1):
                eta = mu[skill] + u[:, col] + v[skill][:, col] + (gamma if cond == "coached" else 0.0)
                if block == 2:
                    g1 = G_UNCOACHED + (gamma if c1 == "coached" else 0.0)
                    eta = eta + omega + kappa * g1
                p = _sigmoid(eta)
                checks = (unif[skill][:, col, :] < p[:, None]).sum(axis=1)
                scores[cond] = checks / POSSIBLE[skill]           # the analysis' skill_score: done / possible
            d[:, col] = scores["coached"] - scores["uncoached"]
            col += 1
    return d


# ---- the pre-registered analysis, vectorised over replications and checked against the real functions
def t_interval_vec(D: np.ndarray, level: float = 0.95) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = D.shape[1]
    mean = D.mean(axis=1)
    sd = D.std(axis=1, ddof=1)
    half = stats.t.ppf(1 - (1 - level) / 2, n - 1) * sd / math.sqrt(n)
    return mean, mean - half, mean + half


@lru_cache(maxsize=None)
def _tail_table(n1: int, n2: int) -> np.ndarray:
    """P(|S| >= m) for m = 0..M where S is the sum of n1 terms of size 1 and n2 of size 2, each with a random sign."""
    m = n1 + 2 * n2
    dist = np.zeros(2 * m + 1)
    dist[m] = 1.0
    for size, count in ((1, n1), (2, n2)):
        for _ in range(count):
            new = np.zeros_like(dist)
            new[size:] += 0.5 * dist[:-size]
            new[:-size] += 0.5 * dist[size:]
            dist = new
    absdist = dist[m:].copy()
    absdist[1:] += dist[:m][::-1]                    # fold the negative side onto the positive
    return np.cumsum(absdist[::-1])[::-1]             # tail[m] = P(|S| >= m)


def sign_flip_p_vec(D: np.ndarray) -> np.ndarray:
    """Exact two-sided sign-flip p of the mean difference for each row, in O(1) per row after a small table.
    Valid when differences are multiples of 0.5, which they are for these scores; equal to the plan's `sign_flip_p`."""
    A = np.rint(2.0 * D).astype(int)
    mag = np.abs(A)
    if mag.max(initial=0) > 2 or not np.allclose(A / 2.0, D):
        raise ValueError("differences must be multiples of 0.5 within [-1, 1]")
    n1 = (mag == 1).sum(axis=1)
    n2 = (mag == 2).sum(axis=1)
    obs = np.abs(A.sum(axis=1))
    p = np.ones(D.shape[0])
    key = n1 * 100 + n2
    for k in np.unique(key):
        sel = key == k
        tab = _tail_table(int(k // 100), int(k % 100))
        p[sel] = tab[np.minimum(obs[sel], len(tab) - 1)]
    return p


def check_against_real(D: np.ndarray, n_check: int = 20, max_n_flip: int = 8) -> dict:
    """Run the plan's own `t_interval` (and `sign_flip_p` for small n) on the first rows and compare."""
    an = load_analysis()
    D = np.asarray(D)
    k = min(n_check, D.shape[0])
    mean, lo, hi = t_interval_vec(D[:k])
    p = sign_flip_p_vec(D[:k]) if D.shape[1] <= max_n_flip else None
    worst_ci = worst_p = 0.0
    for i in range(k):
        m, l, h = an.t_interval([float(x) for x in D[i]])
        worst_ci = max(worst_ci, abs(m - mean[i]), abs(l - lo[i]), abs(h - hi[i]))
        if p is not None:
            worst_p = max(worst_p, abs(an.sign_flip_p([float(x) for x in D[i]]) - p[i]))
    return {"replications_checked": k, "max_abs_diff_ci": worst_ci,
            "max_abs_diff_p": None if p is None else worst_p, "sign_flip_checked_against_plan": p is not None}
