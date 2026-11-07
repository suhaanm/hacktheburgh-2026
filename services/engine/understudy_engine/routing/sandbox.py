"""Routing cases grounded in agent-core's sandbox (ANA-8, A4): real households, the three calculators' own rule logic
run in-process, the sandbox oracle as the reference. Nothing is started: no servers, no browsers.

  household       understudy_agent.sandbox_sites.households.generate_households(n, seed)   (synthetic, seeded)
  site answers    oracle.site_expected("a" | "b" | "c", household)   each calculator's rules, including its planted quirks
  reference       oracle.score(household)                           an INTERNAL, SIMPLIFIED rule set, not law
  stand-in agent  the answer the agent would write into the case note after three navigators have run
                    majority_else_mean (headline): the answer at least two calculators agree on (within 1 pound);
                                                   with no such pair, the mean of the three
                    mean_of_three, median_of_three: sensitivity checks (see evaluate_routing)
  label           y = 1 when |agent answer - reference| > 1 pound
  stated confidence   derived ONLY from how much the calculators disagree (never from the label or the reference)

CIRCULARITY. The calculators' quirks (site b ignores capital tariff income, site c applies a legacy two-child limit and
treats exactly 16,000 as over the limit) and the archetypes that trigger them were planted by us. A router that does well here
has found our planted structure, which is what these cases can honestly show; they cannot show that real calculators or real
agents fail this way.
"""
from __future__ import annotations

import statistics

import numpy as np

from understudy_engine.routing.cases import Cases

TOL = 1.0   # pounds; the sandbox oracle's own tolerance (oracle.TOLERANCE_GBP)
STAND_INS = ("majority_else_mean", "mean_of_three", "median_of_three")
FLAGS = ("capital_limit_16000", "capital_tariff_band", "third_child", "housing_cap_binding", "work_allowance_edge",
         "childcare_cap_binding")

COMPLEXITY = ("n_adults", "n_children", "earnings_total", "log_savings", "log_gap_to_16k", "log_childcare", "rent_over_cap",
              "limited_capability", "scotland", "wales", "n_cliff_flags") + tuple(f"flag_{f}" for f in FLAGS)
DISAGREEMENT = ("log_spread", "pairs_disagree", "distinct_statuses", "has_majority", "log_agent_answer", "agent_confidence")


def agent_answer(answers: list[float], stand_in: str = "majority_else_mean") -> float:
    if stand_in == "median_of_three":
        return float(statistics.median(answers))
    if stand_in == "mean_of_three":
        return float(sum(answers) / 3.0)
    if stand_in == "majority_else_mean":
        for x in answers:
            if sum(abs(x - y) <= TOL for y in answers) >= 2:
                return float(x)
        return float(sum(answers) / 3.0)
    raise ValueError(f"stand_in must be one of {STAND_INS}")


def stated_confidence(answers: list[float], eligible: list[bool]) -> tuple[float, int, int]:
    """Confidence from disagreement alone. Returns (confidence, pairs differing by more than TOL, distinct statuses)."""
    pairs = sum(abs(answers[i] - answers[j]) > TOL for i in range(3) for j in range(i + 1, 3))
    spread = max(answers) - min(answers)
    distinct = len(set(eligible))
    conf = 0.98 - 0.12 * pairs - 0.10 * min(1.0, spread / 300.0) - 0.10 * (distinct - 1)
    return float(min(0.98, max(0.30, conf))), int(pairs), int(distinct)


def sandbox_cases(n: int = 900, seed: int = 2026, stand_in: str = "majority_else_mean") -> Cases:
    """Cases from the sandbox households. Raises ImportError with a plain message if the agent package is not importable."""
    try:
        from understudy_agent.sandbox_sites import oracle
        from understudy_agent.sandbox_sites.households import ARCHETYPES, generate_households
    except ImportError as exc:  # pragma: no cover - exercised only outside the workspace
        raise ImportError("routing.sandbox needs the understudy_agent package (workspace member services/agent)") from exc

    hs = generate_households(n, seed)
    rows, ys, arche = [], [], []
    for h in hs:
        ref = oracle.score(h)
        sites = [oracle.site_expected(s, h) for s in "abc"]
        answers = [float(x["uc_monthly"]) for x in sites]
        elig = [bool(x["eligible"]) for x in sites]
        ans = agent_answer(answers, stand_in)
        conf, pairs, distinct = stated_confidence(answers, elig)
        spread = max(answers) - min(answers)
        flags = set(ref["cliff_flags"])
        earnings = sum(a.earnings_monthly for a in h.adults)
        cap = oracle.housing_cap(h)
        comp = [
            len(h.adults), len(h.children_ages), earnings, np.log1p(h.savings), np.log1p(abs(h.savings - 16000.0)),
            np.log1p(h.childcare_monthly), float(h.tenure == "rent" and h.rent_monthly > cap), float(h.limited_capability),
            float(h.region == "scotland"), float(h.region == "wales"), float(len(flags)),
        ] + [float(f in flags) for f in FLAGS]
        dis = [np.log1p(spread), float(pairs), float(distinct), float(pairs < 3), np.log1p(ans), conf]
        onehot = [float(h.archetype == a) for a in ARCHETYPES]
        rows.append(comp + dis + onehot)
        ys.append(int(abs(ans - ref["uc_monthly"]) > TOL))
        arche.append(h.archetype)
    names = COMPLEXITY + DISAGREEMENT + tuple(f"archetype_{a}" for a in ARCHETYPES)
    X = np.array(rows, dtype=float)
    y = np.array(ys, dtype=int)
    col = {c: i for i, c in enumerate(names)}
    rng = np.random.default_rng(seed)
    errors_by_arch: dict[str, list[int]] = {}
    for a, yy in zip(arche, ys):
        v = errors_by_arch.setdefault(a, [0, 0])
        v[0] += yy
        v[1] += 1
    return Cases(
        X=X, y=y, p_true=None, features=names, origin="synthetic",
        groups={
            "complexity_and_archetype_only": COMPLEXITY + tuple(f"archetype_{a}" for a in ARCHETYPES),
            "calculator_disagreement_only": DISAGREEMENT,
            "all_features": names,
        },
        signals={
            "agent_confidence_only": 1.0 - X[:, col["agent_confidence"]],
            "calculator_spread_only": X[:, col["log_spread"]] + 1e-6 * rng.random(len(y)),
            "random": rng.random(len(y)),
        },
        extra={"stand_in": stand_in, "errors_by_archetype": {a: {"errors": v[0], "households": v[1]} for a, v in errors_by_arch.items()}},
    )
