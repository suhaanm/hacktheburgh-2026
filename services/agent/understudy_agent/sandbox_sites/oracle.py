"""Reference scoring for the sandbox calculators (AGT-6).

This is an INTERNAL, SIMPLIFIED, ILLUSTRATIVE rule set loosely shaped like a Universal Credit
monthly award. It is not law and not a benefits calculator anyone should rely on; it exists so the
three sandbox sites have a reference answer and so planted "cliff edges" can be measured.
Spike S4 (PolicyEngine UK) is recorded in the agent-core final report; PolicyEngine is AGPL-family
and is never vendored here.

`score(household)` is the entry point the benefits pack points at
(`understudy_agent.sandbox_sites.oracle:score`).

Each sandbox site then deviates from these rules on purpose (see `site_expected`):
  site a: faithful, but rounds the displayed monthly figure to whole pounds
  site b: ignores capital tariff income (savings 6,000 to 16,000) and applies the one-child
          childcare cap to every household
  site c: still applies a legacy two-child limit and treats savings of exactly 16,000 as over the limit
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from .households import Household, as_household

RULES_ID = "internal-simplified-v1"
TOLERANCE_GBP = 1.0  # sites "agree" if they are within one pound

STANDARD_ALLOWANCE = {
    "single_under_25": 316.98,
    "single_25_plus": 400.14,
    "couple_under_25": 497.55,
    "couple_25_plus": 628.10,
}
CHILD_ELEMENT_FIRST = 339.00
CHILD_ELEMENT_OTHER = 292.81
HOUSING_CAP_BY_BEDROOMS = {1: 575.0, 2: 700.0, 3: 800.0, 4: 1000.0}
WORK_ALLOWANCE_WITH_HOUSING = 411.0
WORK_ALLOWANCE_NO_HOUSING = 684.0
TAPER_RATE = 0.55
CAPITAL_LOWER = 6000.0
CAPITAL_UPPER = 16000.0
TARIFF_PER_BAND = 4.35
TARIFF_BAND = 250.0
CHILDCARE_RATE = 0.85
CHILDCARE_CAP_ONE = 1031.88
CHILDCARE_CAP_TWO_PLUS = 1768.94
CHILD_MAX_AGE_CHILDCARE = 15


def standard_allowance(h: Household) -> float:
    if len(h.adults) == 1:
        return STANDARD_ALLOWANCE["single_25_plus" if h.adults[0].age >= 25 else "single_under_25"]
    both_under_25 = all(a.age < 25 for a in h.adults)
    return STANDARD_ALLOWANCE["couple_under_25" if both_under_25 else "couple_25_plus"]


def child_element(h: Household, two_child_limit: bool = False) -> float:
    total = 0.0
    for i, _age in enumerate(h.children_ages):
        if two_child_limit and i >= 2:
            continue
        total += CHILD_ELEMENT_FIRST if i == 0 else CHILD_ELEMENT_OTHER
    return total


def housing_cap(h: Household) -> float:
    return HOUSING_CAP_BY_BEDROOMS[max(1, min(4, h.bedrooms))]


def housing_element(h: Household) -> float:
    if h.tenure != "rent":
        return 0.0
    return min(h.rent_monthly, housing_cap(h))


def childcare_element(h: Household, *, single_cap: bool = False) -> float:
    """85% of costs up to a cap, only if every adult is in paid work and there is a child under 16."""
    young = sum(1 for a in h.children_ages if a <= CHILD_MAX_AGE_CHILDCARE)
    if young == 0 or h.childcare_monthly <= 0:
        return 0.0
    if not all(a.earnings_monthly > 0 for a in h.adults):
        return 0.0
    cap = CHILDCARE_CAP_ONE if (young == 1 or single_cap) else CHILDCARE_CAP_TWO_PLUS
    return min(h.childcare_monthly * CHILDCARE_RATE, cap)


def work_allowance(h: Household) -> float:
    eligible = bool(h.children_ages) or h.limited_capability
    if not eligible:
        return 0.0
    return WORK_ALLOWANCE_WITH_HOUSING if housing_element(h) > 0 else WORK_ALLOWANCE_NO_HOUSING


def tariff_income(savings: float) -> float:
    if savings <= CAPITAL_LOWER:
        return 0.0
    return math.ceil((savings - CAPITAL_LOWER) / TARIFF_BAND) * TARIFF_PER_BAND


def _award(
    h: Household,
    *,
    two_child_limit: bool,
    use_tariff: bool,
    childcare_single_cap: bool,
    over_limit_inclusive: bool,
) -> dict[str, Any]:
    over = h.savings >= CAPITAL_UPPER if over_limit_inclusive else h.savings > CAPITAL_UPPER
    components = {
        "standard": standard_allowance(h),
        "children": child_element(h, two_child_limit),
        "housing": housing_element(h),
        "childcare": childcare_element(h, single_cap=childcare_single_cap),
    }
    max_award = sum(components.values())
    earnings = sum(a.earnings_monthly for a in h.adults)
    wa = work_allowance(h)
    taper = max(0.0, earnings - wa) * TAPER_RATE
    tariff = tariff_income(h.savings) if use_tariff else 0.0
    if over:
        award = 0.0
    else:
        award = max(0.0, max_award - taper - tariff)
    return {
        "uc_monthly": round(award, 2),
        "eligible": award > 0.0,
        "components": {k: round(v, 2) for k, v in components.items()},
        "taper": round(taper, 2),
        "tariff_income": round(tariff, 2),
        "work_allowance": wa,
        "over_capital_limit": over,
    }


def cliff_flags(h: Household) -> list[str]:
    """Inputs near a rule boundary where calculators are likely to disagree. Used by the critic."""
    flags: list[str] = []
    if CAPITAL_UPPER - 600 <= h.savings <= CAPITAL_UPPER + 600:
        flags.append("capital_limit_16000")
    if CAPITAL_LOWER < h.savings < CAPITAL_UPPER and h.savings >= CAPITAL_LOWER + 1:
        flags.append("capital_tariff_band")
    if len(h.children_ages) >= 3:
        flags.append("third_child")
    if h.tenure == "rent" and h.rent_monthly > housing_cap(h):
        flags.append("housing_cap_binding")
    earnings = sum(a.earnings_monthly for a in h.adults)
    wa = work_allowance(h)
    if wa > 0 and abs(earnings - wa) <= 150:
        flags.append("work_allowance_edge")
    young = sum(1 for a in h.children_ages if a <= CHILD_MAX_AGE_CHILDCARE)
    if young >= 2 and h.childcare_monthly * CHILDCARE_RATE > CHILDCARE_CAP_ONE:
        flags.append("childcare_cap_binding")
    return flags


def score(household: Household | Mapping[str, Any]) -> dict[str, Any]:
    """Reference entitlement for one household. Accepts a `Household` or its dict form."""
    h = as_household(household)
    base = _award(h, two_child_limit=False, use_tariff=True, childcare_single_cap=False,
                  over_limit_inclusive=False)
    return {
        "household_id": h.id,
        "rules": RULES_ID,
        **base,
        "cliff_flags": cliff_flags(h),
    }


# What each sandbox site is supposed to display (including its deliberate quirks).
def site_expected(site: str, household: Household | Mapping[str, Any]) -> dict[str, Any]:
    h = as_household(household)
    if site == "a":
        r = _award(h, two_child_limit=False, use_tariff=True, childcare_single_cap=False,
                   over_limit_inclusive=False)
        r["uc_monthly"] = float(round(r["uc_monthly"]))  # displays whole pounds
        r["eligible"] = r["uc_monthly"] > 0
        return r
    if site == "b":
        return _award(h, two_child_limit=False, use_tariff=False, childcare_single_cap=True,
                      over_limit_inclusive=False)
    if site == "c":
        return _award(h, two_child_limit=True, use_tariff=True, childcare_single_cap=False,
                      over_limit_inclusive=True)
    raise ValueError(f"unknown site {site!r}")


def disagreements(household: Household | Mapping[str, Any]) -> dict[str, Any]:
    """Which sites differ from the oracle by more than the tolerance for this household."""
    h = as_household(household)
    ref = score(h)["uc_monthly"]
    out: dict[str, float] = {}
    for s in ("a", "b", "c"):
        got = site_expected(s, h)["uc_monthly"]
        if abs(got - ref) > TOLERANCE_GBP:
            out[s] = round(got - ref, 2)
    return {"household_id": h.id, "oracle": ref, "off_by": out, "sites_agree": not out}


def cliff_report(household: Household | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Plain-text 'check cliff edges' items for one household, from the same rules as `score`.

    Each item: {id, text, near}. `near` is True exactly when `score(...)['cliff_flags']` has the matching flag,
    so the sites' cliff panel and the oracle cannot disagree about what counts as close to an edge.
    """
    h = as_household(household)
    flags = set(cliff_flags(h))
    items: list[dict[str, Any]] = []
    s = h.savings
    gap = CAPITAL_UPPER - s
    if gap > 0:
        txt = f"Savings are {gap:,.0f} below the 16,000 limit. " + (
            "Close: a small rise would stop the award." if "capital_limit_16000" in flags else "No change at this level.")
    elif gap == 0:
        txt = "Savings are exactly at the 16,000 limit. Under these rules the award continues; one pound more would end it."
    else:
        txt = f"Savings are {-gap:,.0f} above the 16,000 limit. No award at this level."
    items.append({"id": "capital_limit", "text": txt, "near": "capital_limit_16000" in flags})
    if s > CAPITAL_LOWER and s <= CAPITAL_UPPER:
        txt = (f"Savings above 6,000 reduce the award by {tariff_income(s):.2f} a month "
               f"({TARIFF_PER_BAND:.2f} for each {TARIFF_BAND:.0f}).")
    else:
        txt = f"Savings are {max(CAPITAL_LOWER - s, 0):,.0f} below the 6,000 tariff band. No change at this level."
    items.append({"id": "capital_tariff", "text": txt, "near": "capital_tariff_band" in flags})
    n = len(h.children_ages)
    txt = (f"This household has {n} children. The child element is paid for every child under these rules; "
           "a calculator that still applies a two-child limit will show less." if n >= 3 else
           f"This household has {n} children. The two-child limit does not matter at this size.")
    items.append({"id": "children", "text": txt, "near": "third_child" in flags})
    if h.childcare_monthly > 0:
        young = sum(1 for a in h.children_ages if a <= CHILD_MAX_AGE_CHILDCARE)
        cap = CHILDCARE_CAP_ONE if young <= 1 else CHILDCARE_CAP_TWO_PLUS
        want = h.childcare_monthly * CHILDCARE_RATE
        txt = (f"Childcare: 85% of costs is {want:,.2f} a month and the cap is {cap:,.2f}. " +
               ("The cap applies." if want > cap else "Under the cap."))
    else:
        txt = "No childcare costs entered. The childcare cap does not matter."
    items.append({"id": "childcare", "text": txt, "near": "childcare_cap_binding" in flags})
    earnings = sum(a.earnings_monthly for a in h.adults)
    wa = work_allowance(h)
    if wa > 0:
        side = "above" if earnings >= wa else "below"
        txt = (f"Earnings are {abs(earnings - wa):,.0f} {side} the work allowance of {wa:,.0f}. "
               "Each extra pound above it reduces the award by 55 pence.")
    else:
        txt = "This household has no work allowance. Each extra pound earned reduces the award by 55 pence."
    items.append({"id": "earnings", "text": txt, "near": "work_allowance_edge" in flags})
    if h.tenure == "rent":
        cap = housing_cap(h)
        txt = (f"Rent is {h.rent_monthly - cap:,.0f} above the local cap of {cap:,.0f}; only the cap counts."
               if h.rent_monthly > cap else f"Rent is under the local cap of {cap:,.0f}.")
        items.append({"id": "housing", "text": txt, "near": "housing_cap_binding" in flags})
    return items
