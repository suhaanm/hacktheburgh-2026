#!/usr/bin/env python
"""Answer-key cases for the benefits households and for review routing.

    uv run python evals/cases/generate_cases.py

Reads the agent-core track's sandbox modules (households.py, oracle.py, specs.py) and writes
  households_20.json   the 20 households of the end-to-end runs (AGT-5) with expected outcomes
  households_200.json  the same shape for 200 households (routing and site-disagreement analysis)
Every record carries the oracle's answer, what each sandbox site is expected to show (including its
deliberate quirk), the values to type into each site, and an INDEPENDENT recomputation (the hand check,
AGT-6) written separately from oracle.py. The oracle is a simplified internal rule set, illustrative, not
law: agreement between oracle, sites and the independent check says the code is consistent, not that it is
the UK system. Field names follow Household.to_dict() and oracle.score().
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from understudy_agent.sandbox_sites import households as H
from understudy_agent.sandbox_sites import oracle as O
from understudy_agent.sandbox_sites import specs as S

HERE = Path(__file__).resolve().parent
SEED = 2026
ORACLE_LABEL = "simplified internal rule set, illustrative, not law"


def independent_uc(h: H.Household) -> dict:
    """The hand check: the award recomputed from the documented rules, without calling oracle.py's functions.
    Only the numeric parameters are shared (rates, caps, limits)."""
    adults = h.adults
    if len(adults) == 1:
        sa = 400.14 if adults[0].age >= 25 else 316.98
    else:
        sa = 497.55 if all(a.age < 25 for a in adults) else 628.10
    kids = len(h.children_ages)
    child = (339.00 + 292.81 * (kids - 1)) if kids else 0.0
    cap = {1: 575.0, 2: 700.0, 3: 800.0, 4: 1000.0}[min(4, max(1, h.bedrooms))]
    housing = min(h.rent_monthly, cap) if h.tenure == "rent" else 0.0
    young = sum(1 for a in h.children_ages if a <= 15)
    childcare = 0.0
    if young and h.childcare_monthly > 0 and all(a.earnings_monthly > 0 for a in adults):
        childcare = min(0.85 * h.childcare_monthly, 1031.88 if young == 1 else 1768.94)
    maximum = sa + child + housing + childcare
    earnings = sum(a.earnings_monthly for a in adults)
    allowance = (411.0 if housing > 0 else 684.0) if (kids or h.limited_capability) else 0.0
    taper = max(0.0, earnings - allowance) * 0.55
    tariff = 0.0 if h.savings <= 6000 else math.ceil((h.savings - 6000) / 250) * 4.35
    award = 0.0 if h.savings > 16000 else max(0.0, maximum - taper - tariff)
    return {"uc_monthly": round(award, 2), "eligible": award > 0, "max_award": round(maximum, 2),
            "taper": round(taper, 2), "tariff_income": round(tariff, 2)}


def routing_key(h: H.Household, oracle_uc: float, site_uc: dict[str, float]) -> dict:
    """What a review-routing evaluation needs: would trusting one calculator be wrong, and is review warranted."""
    off = {s: abs(v - oracle_uc) > O.TOLERANCE_GBP for s, v in site_uc.items()}
    votes = sorted(site_uc.values())
    median = votes[1]  # three sites: the median result
    return {
        "sites_off": sorted(s for s, bad in off.items() if bad),
        "error_if_trust_first_site": off["a"],
        "error_if_trust_any_single_site": any(off.values()),
        "error_if_trust_median": abs(median - oracle_uc) > O.TOLERANCE_GBP,
        "review_needed": any(off.values()),
        "complexity": {
            "n_cliff_flags": len(O.cliff_flags(h)),
            "children": len(h.children_ages),
            "adults": len(h.adults),
            "has_childcare": h.childcare_monthly > 0,
            "owner_occupier": h.tenure == "own",
            "limited_capability": h.limited_capability,
            "savings_band": ("over_limit" if h.savings > 16000 else "tariff_band" if h.savings > 6000 else "below_tariff"),
        },
    }


def record(h: H.Household) -> dict:
    o = O.score(h)
    sites = {s: O.site_expected(s, h) for s in S.SITE_IDS}
    site_uc = {s: v["uc_monthly"] for s, v in sites.items()}
    dis = O.disagreements(h)
    indep = independent_uc(h)
    params = h.params()
    return {
        "household": h.to_dict(),
        "oracle": {"uc_monthly": o["uc_monthly"], "eligible": o["eligible"], "cliff_flags": o["cliff_flags"],
                   "components": o["components"], "taper": o["taper"], "tariff_income": o["tariff_income"],
                   "work_allowance": o["work_allowance"], "over_capital_limit": o["over_capital_limit"], "rules": o["rules"]},
        "sites_expected": {s: {"uc_monthly": v["uc_monthly"], "eligible": v["eligible"]} for s, v in sites.items()},
        "site_inputs": {s: {p: S.bound_value(S.SITES[s], p, params) for p in S.SITES[s].fields("v1")} for s in S.SITE_IDS},
        "off_by": dis["off_by"],
        "sites_agree": dis["sites_agree"],
        "reconciliation_expected": "agree" if dis["sites_agree"] else "discrepancy",
        "cliff_panel_expected": {i["id"]: ("yes" if i["near"] else "no") for i in O.cliff_report(h)},
        "independent_check": {**indep, "agrees_with_oracle": abs(indep["uc_monthly"] - o["uc_monthly"]) <= 0.01},
        "routing": routing_key(h, o["uc_monthly"], site_uc),
        "case_note_expected": {"case_ref": h.case_ref, "status_after_draft": "Draft", "must_not_submit": True},
    }


def build(root: Path = HERE) -> dict[str, dict]:
    out = {}
    for n, name in ((20, "households_20.json"), (200, "households_200.json")):
        hs = H.generate_households(n, SEED)
        recs = [record(h) for h in hs]
        doc = {
            "schema": 1,
            "meta": {
                "generator": "understudy_agent.sandbox_sites.households:generate_households",
                "seed": SEED, "count": n, "oracle": "understudy_agent.sandbox_sites.oracle:score",
                "oracle_label": ORACLE_LABEL, "origin": "synthetic",
                "note": "Synthetic households only. Expected values come from the oracle and the sites' documented quirks; "
                        "independent_check is a separate recomputation (the AGT-6 hand check).",
                "oracle_independent_disagreements": [r["household"]["id"] for r in recs if not r["independent_check"]["agrees_with_oracle"]],
            },
            "cases": recs,
        }
        (root / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        out[name] = doc
    return out


if __name__ == "__main__":
    docs = build()
    for name, d in docs.items():
        c = d["cases"]
        print(name, len(c), "cases;", sum(1 for r in c if not r["sites_agree"]), "with site disagreement;",
              len(d["meta"]["oracle_independent_disagreements"]), "oracle vs independent disagreements")
