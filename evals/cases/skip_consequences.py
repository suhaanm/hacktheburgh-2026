#!/usr/bin/env python
"""What skipping a step costs, from the answer-key cases.

    uv run python evals/cases/skip_consequences.py     # writes evals/cases/skip_consequences.json

The genome prices a skipped step in seconds, which makes skipping look like a time saving. This file prices it
in answers. Definitions:
- RECONCILE skipped: the worker does not compare the calculators and writes ONE calculator's figure into the
  note. They cannot know which one is faithful, so the main number is the expectation over which calculator
  they happen to trust (each of the three equally likely); the per-calculator numbers are reported beside it.
  A household is "wrong" when that figure differs from the oracle by more than TOLERANCE_GBP.
  (First version of this file used GovCalc as the main policy. GovCalc is the oracle-faithful site by
  construction, so that policy is trivially right and made skipping look harmless; it is kept as one row.)
- CHECK_CLIFF skipped: the cliff panel does not change today's figure (reconciling by the median figure is
  right on every case here), it warns that a small change would move the award. So the cost is a missed
  warning: on households near an edge, how much a small documented nudge would change the award
  (NUDGES below, scored by the oracle), and on how many that is material (more than MATERIAL_GBP a month).
The oracle is a simplified internal rule set, illustrative, not law. Households cycle through 12 archetypes, so
shares describe this synthetic mix, not any real caseload.
"""
from __future__ import annotations

import dataclasses
import json
import math
import random
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOLERANCE = 1.0
MATERIAL_GBP = 50.0
SETS = {"households_20": "households_20.json", "households_200": "households_200.json"}
# the small change a cliff check would have probed, per oracle cliff flag: (what changes, by how much)
NUDGES = {
    "capital_limit_16000": ("savings", 500.0),
    "capital_tariff_band": ("savings", 1000.0),
    "childcare_cap_binding": ("childcare_monthly", 100.0),
    "housing_cap_binding": ("rent_monthly", 100.0),
    "work_allowance_edge": ("adult1_earnings_monthly", 100.0),
    "third_child": ("site_gap_c", 0.0),      # no household change: the legacy two-child limit shows as site c's gap
}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def summarise(errors: dict[str, float]) -> dict:
    n = len(errors)
    wrong = {i: e for i, e in errors.items() if e > TOLERANCE}
    vals = list(errors.values())
    wv = list(wrong.values())
    return {
        "n": n, "wrong_n": len(wrong), "wrong_share": round(len(wrong) / n, 3), "wrong_share_ci95": wilson(len(wrong), n),
        "sentence": f"gives a wrong answer on {len(wrong)} of {n} households",
        "error_gbp": {
            "mean_all": round(statistics.fmean(vals), 2), "median_all": round(statistics.median(vals), 2),
            "mean_when_wrong": round(statistics.fmean(wv), 2) if wv else 0.0,
            "median_when_wrong": round(statistics.median(wv), 2) if wv else 0.0,
            "max": round(max(vals), 2),
        },
        "wrong_cases": sorted(wrong),
    }


def _nudged(hh: dict, field: str, delta: float):
    from understudy_agent.sandbox_sites.households import Household
    h = Household.from_dict(hh)
    if field == "adult1_earnings_monthly":
        first = dataclasses.replace(h.adults[0], earnings_monthly=h.adults[0].earnings_monthly + delta)
        return dataclasses.replace(h, adults=(first,) + h.adults[1:])
    return dataclasses.replace(h, **{field: getattr(h, field) + delta})


def _award(h) -> float:
    from understudy_agent.sandbox_sites.oracle import score
    return score(h)["uc_monthly"]


def nudge_impact(c: dict) -> float:
    """Largest change in the oracle's award from the small nudge for each cliff flag the household has."""
    from understudy_agent.sandbox_sites.households import Household
    base = c["oracle"]["uc_monthly"]
    best = 0.0
    for flag in c["oracle"]["cliff_flags"]:
        field, delta = NUDGES[flag]
        if field == "site_gap_c":
            best = max(best, abs(c["sites_expected"]["c"]["uc_monthly"] - base))
        else:
            best = max(best, abs(_award(_nudged(c["household"], field, delta)) - base))
    return round(best, 2)


def _boot_ci(p: list[float], seed: int = 2026, draws: int = 1000) -> list[float]:
    rng = random.Random(seed)
    n = len(p)
    means = sorted(sum(rng.choice(p) for _ in range(n)) / n for _ in range(draws))
    return [round(means[int(0.025 * draws)], 3), round(means[int(0.975 * draws) - 1], 3)]


def analyse(cases: list[dict]) -> dict:
    err = {s: {} for s in ("a", "b", "c", "median")}
    p_wrong: list[float] = []
    pooled: list[float] = []
    for c in cases:
        hid = c["household"]["id"]
        ref = c["oracle"]["uc_monthly"]
        fig = {s: v["uc_monthly"] for s, v in c["sites_expected"].items()}
        for s in "abc":
            err[s][hid] = abs(fig[s] - ref)
            pooled.append(err[s][hid])
        err["median"][hid] = abs(sorted(fig.values())[1] - ref)
        p_wrong.append(sum(err[s][hid] > TOLERANCE for s in "abc") / 3)
    n = len(cases)
    wrong_pooled = [e for e in pooled if e > TOLERANCE]
    near = [c for c in cases if any(v == "yes" for v in c["cliff_panel_expected"].values())]
    impacts = {c["household"]["id"]: nudge_impact(c) for c in near}
    iv = list(impacts.values())
    material = sorted(i for i, v in impacts.items() if v > MATERIAL_GBP)
    by_arch: dict[str, dict] = {}
    for c in cases:
        d = by_arch.setdefault(c["household"]["archetype"], {"n": 0, "reconcile_skipped_expected_wrong": 0.0, "near_cliff": 0, "cliff_skipped_material": 0})
        hid = c["household"]["id"]
        d["n"] += 1
        d["reconcile_skipped_expected_wrong"] += sum(err[s][hid] > TOLERANCE for s in "abc") / 3
        d["near_cliff"] += hid in impacts
        d["cliff_skipped_material"] += hid in material
    for d in by_arch.values():
        d["reconcile_skipped_expected_wrong"] = round(d["reconcile_skipped_expected_wrong"], 2)
    exp_wrong = sum(p_wrong)
    return {
        "RECONCILE": {
            "skipped_means": "the worker writes one calculator's figure into the note without comparing; which one is down to habit, so each of the three is equally likely",
            "main_policy": "uniform_single_site",
            "n": n, "expected_wrong_n": round(exp_wrong, 1), "expected_wrong_share": round(exp_wrong / n, 3),
            "expected_wrong_share_ci95_bootstrap_by_household": _boot_ci(p_wrong),
            "sentence": f"gives a wrong answer on about {exp_wrong:.1f} of {n} households (expected over which calculator is trusted)",
            "error_gbp_pooled_over_the_three_choices": {
                "mean_all": round(statistics.fmean(pooled), 2), "median_all": round(statistics.median(pooled), 2),
                "mean_when_wrong": round(statistics.fmean(wrong_pooled), 2) if wrong_pooled else 0.0,
                "median_when_wrong": round(statistics.median(wrong_pooled), 2) if wrong_pooled else 0.0,
                "max": round(max(pooled), 2),
            },
            "by_calculator": {f"site_{s}": summarise(err[s]) for s in "abc"},
        },
        "CHECK_CLIFF": {
            "skipped_means": "no warning that a small change would move the award; today's figure is unaffected",
            "main_policy": "missed_warning_with_documented_nudges",
            "nudges": {k: {"field": f, "delta": d} for k, (f, d) in NUDGES.items()},
            "households_near_an_edge": len(near), "of": n, "share_near": round(len(near) / n, 3),
            "share_near_ci95_wilson": wilson(len(near), n),
            "of_those_sites_disagree": sum(1 for c in near if not c["sites_agree"]),
            "material_threshold_gbp_per_month": MATERIAL_GBP,
            "material_n": len(material), "material_share_of_near": round(len(material) / len(near), 3) if near else 0.0,
            "sentence": f"leaves a nearby cliff edge unwarned on {len(near)} of {n} households; a small change moves the award by more than {MATERIAL_GBP:.0f} pounds a month on {len(material)} of them",
            "impact_gbp_per_month_among_near": {
                "mean": round(statistics.fmean(iv), 2) if iv else 0.0, "median": round(statistics.median(iv), 2) if iv else 0.0, "max": round(max(iv), 2) if iv else 0.0,
            },
            "material_cases": material,
            "reconcile_by_median_is_wrong_on": {"n": sum(1 for e in err["median"].values() if e > TOLERANCE), "of": n,
                                                 "note": "with these three calculators the middle figure is always right, so the panel's value is the warning and the explanation, not today's number"},
        },
        "by_archetype": by_arch,
    }


def build(root: Path = HERE) -> dict:
    sets = {}
    for name, fname in SETS.items():
        doc = json.loads((root / fname).read_text())
        sets[name] = {"n": len(doc["cases"]), "n_unit": "households", **analyse(doc["cases"])}
    out = {
        "schema": 1,
        "meta": {
            "origin": "synthetic", "n_unit": "households", "tolerance_gbp": TOLERANCE, "interval_level": 0.95,
            "interval_method": "Wilson score interval on the share of households; households cycle through 12 archetypes, so it describes this mix only",
            "oracle": "understudy_agent.sandbox_sites.oracle:score", "oracle_label": "simplified internal rule set, illustrative, not law",
            "source": [f"evals/cases/{f}" for f in SETS.values()],
            "note": "Prices a skipped step in answers, not seconds: the genome's seconds make skipping look free.",
        },
        "sets": sets,
    }
    (root / "skip_consequences.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    o = build()
    for name, s in o["sets"].items():
        print(name, "| RECONCILE skipped:", s["RECONCILE"]["sentence"], "| CHECK_CLIFF skipped:", s["CHECK_CLIFF"]["sentence"])
