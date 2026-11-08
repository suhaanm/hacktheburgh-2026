"""Role-level priors with partial pooling for a NEW person (ANA-9, ROL-6).

Question: a new worker has done k episodes. How well can we guess their rates (the stuck base rate, how often each
planted deficit shows up) for later episodes, using (a) only their own k episodes, (b) only what other people in
the same role look like, or (c) a blend that leans on their own data more as it accumulates?

  no pooling        theta = (s + 0.5) / (n + 1)                      own data only, flat Jeffreys prior (0.5 at k = 0)
  complete pooling  theta = role rate from OTHER people              ignores the person
  partial pooling   theta = (s + a) / (n + a + b)                    empirical-Bayes beta-binomial: (a, b) fitted
                                                                     by maximum likelihood across the other people's
                                                                     totals; own weight n / (n + a + b) grows with n

Hand-rolled: the beta-binomial marginal likelihood is maximised over (mean, concentration) with L-BFGS in
log space; nothing from a stats package beyond `gammaln` and the optimiser.

Protocol (leave one person out, `evaluate_pooling`): the held-out person's role prior comes from everyone else's full
data; reveal their first k episodes; score each estimate by predictive log loss on that person's LATER episodes
(episodes from index max(k) on, the same for every k so the rows are comparable). Intervals resample the scored
episodes (clusters), holding each person's estimates fixed.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta

EPS = 1e-9
KAPPA_MIN, KAPPA_MAX = 1.0, 1e5
METHODS = ("no_pooling", "partial_pooling", "complete_pooling")


# ---------------------------------------------------------------- estimators
def _betabinom_ll(s: np.ndarray, n: np.ndarray, a: float, b: float) -> float:
    """Sum of log beta-binomial pmf up to the binomial coefficient (constant in a, b)."""
    return float(np.sum(gammaln(a + s) + gammaln(b + n - s) - gammaln(a + b + n) - gammaln(a) - gammaln(b) + gammaln(a + b)))


def fit_beta_prior(s: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    """ML beta prior (a, b) from per-person successes s out of n. People with n = 0 are ignored. If the people look no more
    different than binomial noise allows, the concentration runs to its cap, which means complete pooling."""
    s = np.asarray(s, float)
    n = np.asarray(n, float)
    keep = n > 0
    s, n = s[keep], n[keep]
    if s.size == 0:
        return 1.0, 1.0
    mu0 = float(np.clip(s.sum() / n.sum(), 1e-4, 1 - 1e-4))
    if s.size == 1:                           # one person: no information about spread; stay near flat
        return mu0 * 2.0, (1 - mu0) * 2.0

    def nll(theta: np.ndarray) -> float:
        mu = 1.0 / (1.0 + np.exp(-theta[0]))
        kappa = float(np.exp(theta[1]))
        return -_betabinom_ll(s, n, mu * kappa, (1 - mu) * kappa)

    best = None
    for k0 in (2.0, 20.0, 400.0):
        res = minimize(nll, x0=np.array([np.log(mu0 / (1 - mu0)), np.log(k0)]), method="L-BFGS-B",
                       bounds=[(-12.0, 12.0), (np.log(KAPPA_MIN), np.log(KAPPA_MAX))])
        if best is None or res.fun < best.fun:
            best = res
    mu = 1.0 / (1.0 + np.exp(-best.x[0]))
    kappa = float(np.exp(best.x[1]))
    return mu * kappa, (1 - mu) * kappa


def estimate(method: str, s: float, n: float, prior_ab: tuple[float, float], role_rate: float) -> float:
    if method == "no_pooling":
        th = (s + 0.5) / (n + 1.0)
    elif method == "complete_pooling":
        th = role_rate
    elif method == "partial_pooling":
        a, b = prior_ab
        th = (s + a) / (n + a + b)
    else:
        raise ValueError(method)
    return float(np.clip(th, EPS, 1 - EPS))


# ---------------------------------------------------------------- units and loss
@dataclass
class Unit:
    """One episode's outcomes for Q quantities: s[q] successes out of n[q] trials."""
    s: np.ndarray
    n: np.ndarray


def _loss(unit: Unit, theta: np.ndarray) -> float:
    """Sum of binomial log losses (nats) of this episode under rates theta (length Q)."""
    return float(-np.sum(unit.s * np.log(theta) + (unit.n - unit.s) * np.log(1 - theta)))


def _pooling_rows(people: dict[str, list[Unit]], ks: Sequence[int], *, n_boot: int, seed: int,
                  quantity_names: Sequence[str] | None = None) -> dict:
    ks = sorted(ks)
    kmax = max(ks)
    pids = sorted(people)
    q = len(next(iter(people.values()))[0].s)
    # per scored episode: owner person, trials, and loss for each (k, method)
    rec_n: list[float] = []
    rec_person: list[str] = []
    rec_loss: dict[tuple[int, str], list[float]] = {(k, m): [] for k in ks for m in METHODS}
    kappas: dict[str, list[float]] = {}
    weights: dict[int, list[float]] = {k: [] for k in ks}
    for held in pids:
        if len(people[held]) <= kmax:
            continue
        others = [p for p in pids if p != held and people[p]]
        S = np.array([np.sum([u.s for u in people[p]], axis=0) for p in others])        # (people, Q)
        N = np.array([np.sum([u.n for u in people[p]], axis=0) for p in others])
        priors = [fit_beta_prior(S[:, j], N[:, j]) for j in range(q)]
        role_rate = np.clip(S.sum(0) / np.maximum(N.sum(0), 1.0), EPS, 1 - EPS)
        kappas[held] = [a + b for a, b in priors]
        test = people[held][kmax:]
        for k in ks:
            own = people[held][:k]
            s_own = np.sum([u.s for u in own], axis=0) if own else np.zeros(q)
            n_own = np.sum([u.n for u in own], axis=0) if own else np.zeros(q)
            for m in METHODS:
                theta = np.array([estimate(m, s_own[j], n_own[j], priors[j], role_rate[j]) for j in range(q)])
                for u in test:
                    rec_loss[(k, m)].append(_loss(u, theta))
            weights[k].append(float(np.mean([n_own[j] / (n_own[j] + a + b) for j, (a, b) in enumerate(priors)])))
        for u in test:
            rec_n.append(float(np.sum(u.n)))
            rec_person.append(held)
    if not rec_n:
        raise ValueError("no person has more than max(k) episodes")
    n_arr = np.array(rec_n)
    persons = np.array(rec_person)
    L = {key: np.array(v) for key, v in rec_loss.items()}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_arr.size, size=(n_boot, n_arr.size))
    rows = []
    for k in ks:
        row: dict = {"n_episodes": k}
        draws = {}
        for m in METHODS:
            row[m] = float(L[(k, m)].sum() / n_arr.sum())
            draws[m] = L[(k, m)][idx].sum(1) / n_arr[idx].sum(1)
            row[f"ci_{m}"] = [float(np.quantile(draws[m], 0.025)), float(np.quantile(draws[m], 0.975))]
        row["ci"] = row["ci_partial_pooling"]
        for other in ("no_pooling", "complete_pooling"):
            d = draws[other] - draws["partial_pooling"]
            row[f"{other}_minus_partial"] = {"value": row[other] - row["partial_pooling"],
                                            "ci": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))]}
        row["own_weight_partial"] = float(np.mean(weights[k])) if weights[k] else None
        row["best"] = min(METHODS, key=lambda m: row[m])
        rows.append(row)
    per_person = {}
    for p in sorted(set(persons.tolist())):
        sel = persons == p
        per_person[p] = {f"k{k}": {m: float(L[(k, m)][sel].sum() / n_arr[sel].sum()) for m in METHODS} for k in ks}
    return {"rows": rows, "n_people": len(set(persons.tolist())), "n_scored_episodes": int(n_arr.size),
            "scored_from_episode_index": kmax, "mean_prior_concentration": float(np.mean([np.mean(v) for v in kappas.values()])),
            "per_person": per_person, "quantities": list(quantity_names) if quantity_names else None}


# ---------------------------------------------------------------- datasets
def _stuck_units(episodes) -> dict[str, list[Unit]]:
    from understudy_engine.hazard.features import build_bins
    tab = build_bins(episodes)
    per: dict[str, list[tuple[float, Unit]]] = {}
    for e in range(len(tab.ep_person)):
        a, b = int(tab.ep_offsets[e]), int(tab.ep_offsets[e + 1])
        per.setdefault(tab.ep_person[e], []).append(
            (float(tab.t[a]), Unit(np.array([float(tab.y[a:b].sum())]), np.array([float(b - a)]))))
    return {p: [u for _, u in sorted(v, key=lambda x: x[0])] for p, v in per.items()}


def _deficit_units(truth_path: Path, types: Sequence[str]) -> dict[str, list[Unit]]:
    truth = json.loads(Path(truth_path).read_text())
    per: dict[str, list[tuple[int, Unit]]] = {}
    for tr in truth["traces"]:
        present = {d["type"] for d in tr["deficits"]}
        x = np.array([1.0 if t in present else 0.0 for t in types])
        per.setdefault(tr["person"], []).append((int(tr["case"]), Unit(x, np.ones(len(types)))))
    return {p: [u for _, u in sorted(v, key=lambda z: z[0])] for p, v in per.items()}


DEFICIT_TYPES = ("skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter")


def evaluate_pooling(root=None, *, n_boot: int = 300, seed: int = 0, ks: Sequence[int] = (0, 1, 3, 10),
                     fast: bool = False) -> dict:
    """Cold-start error after 0, 1, 3, 10 episodes: no pooling vs partial pooling vs complete pooling.

    `rows` (primary) = the stuck base rate on the four personas. `datasets` holds the others. Every row's methods are scored
    by predictive log loss (nats per trial) on later episodes; `ci` is the interval of the partial-pooling value and
    `*_minus_partial` gives each competitor's excess loss with its own interval (positive = partial pooling better).
    """
    from understudy_engine.hazard.data import load_apprentice_episodes, load_persona_episodes
    from understudy_engine.store import data_dir

    if fast:
        n_boot = min(n_boot, 60)
    base = Path(root) if root else data_dir()
    datasets: dict[str, dict] = {}
    ks = tuple(ks)

    eps_p, _, _ = load_persona_episodes(root)
    datasets["stuck_rate_personas"] = {
        "quantity": "stuck base rate (share of 30 s bins with no progress in the next 60 s)",
        "unit": "bins", "role_prior_from": "the other three personas",
        **_pooling_rows(_stuck_units(eps_p), ks, n_boot=n_boot, seed=seed)}

    try:
        eps_a, _, _ = load_apprentice_episodes(root)
        datasets["stuck_rate_apprentices"] = {
            "quantity": "stuck base rate (share of bins with no progress in the next 60 s)", "unit": "bins",
            "role_prior_from": "the other 23 apprentices",
            **_pooling_rows(_stuck_units(eps_a), [k for k in ks if k <= 1], n_boot=n_boot, seed=seed)}
        datasets["deficit_rates_apprentices"] = {
            "quantity": "probability an episode shows each planted deficit (5 types); experts have none", "unit": "episodes x deficit types",
            "role_prior_from": "the other 23 apprentices (experts included)",
            **_pooling_rows(_deficit_units(base / "synthetic" / "apprentices" / "truth.json", DEFICIT_TYPES),
                            [k for k in ks if k <= 1], n_boot=n_boot, seed=seed, quantity_names=DEFICIT_TYPES)}
    except FileNotFoundError:
        pass
    lt = base / "synthetic" / "learners" / "truth.json"
    if lt.exists():
        datasets["deficit_rates_learners"] = {
            "quantity": "probability a case shows each planted deficit (5 types); true rates FALL with practice",
            "unit": "cases x deficit types", "role_prior_from": "the other two learners",
            **_pooling_rows(_deficit_units(lt, DEFICIT_TYPES), ks, n_boot=n_boot, seed=seed, quantity_names=DEFICIT_TYPES)}

    primary = datasets["stuck_rate_personas"]
    best_at_0 = primary["rows"][0]
    return {
        "rows": primary["rows"],
        "note": ("Cold-start error is predictive log loss (nats per trial, lower is better) on the person's later episodes, leave one "
                 "person out. Partial pooling shrinks a new person toward the role's rate and trusts their own data more as it "
                 "accumulates. `ci` is the interval for the partial-pooling value; `*_minus_partial` shows how much worse each "
                 "alternative is, with its own interval."),
        "datasets": datasets,
        "origin": "synthetic", "n": primary["n_people"], "n_unit": "personas",
        "split": "leave-one-person-out; scored on episodes after the first max(k)", "interval_level": 0.95,
        "meta": analytic_meta("synthetic", primary["n_people"], "personas", "leave-one-person-out",
                              note="Cold start for a new worker: error after 0, 1, 3 and 10 of their own episodes. Four generated personas."),
        "headline": {"quantity": primary["quantity"], "k0_partial": best_at_0["partial_pooling"], "k0_no_pooling": best_at_0["no_pooling"]},
        "limitations": limitations_for("pooling"),
        "caveats": [
            "The primary result has four personas, so 'the role' is three other people; between-persona spread is small, which pushes partial "
            "pooling toward complete pooling. The apprentice rows have 24 people but only two episodes each.",
            "Deficit rows read the planted deficits from truth.json, as if the genome module had detected them perfectly.",
            "Learners' true deficit rates fall with practice, so every static estimate, pooled or not, is biased for later cases; pooling does not fix drift.",
            "Intervals resample scored episodes with each person's estimate held fixed; they do not capture person-to-person variation beyond what those episodes show.",
            "Bins within an episode are correlated, so bin-level counts overstate the information in a person's data; the empirical-Bayes prior fitted on them is "
            "therefore a little too tight about each person's own rate.",
        ],
    }
