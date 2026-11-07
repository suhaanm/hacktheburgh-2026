"""The spend guard of the role studies: ``evals/study_sim/budget.Budget`` with ONE hard cap for both roles and every pilot (US$8; pilots at most US$2 of it), carrying the spend of
earlier runs in the same results tree so the cap holds across processes. Prices come from the environment (never baked into a result) and the estimate is labelled an estimate."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from evals.study_sim.budget import Budget, BudgetExhausted, prices   # noqa: F401  (BudgetExhausted is re-exported)

CAP_USD = 8.0                  # the whole study, both roles, pilots included (the lead's figure of 7 Nov 2026, evening: the owner's US$60 is shared and about US$20 is used)
PILOT_CAP_USD = 2.0            # all pilots together


def apply_tier_prices(tier: str) -> tuple[float, float, str]:
    """The prices ``budget.prices`` reads (STUDY_SIM_PRICE_IN / _OUT, US$ per million tokens) for the fast model, with the source: env if set, else the guard's conservative defaults."""
    pin, pout, from_env = prices()
    return pin, pout, "env" if from_env else "default"


def carried_usd(results_root: Path) -> float:
    """Spend of every earlier run under the results tree (each run writes cost.json with ``usd_this_run``)."""
    total = 0.0
    for f in Path(results_root).rglob("cost.json"):
        try:
            total += float(json.loads(f.read_text()).get("usd_this_run", 0.0))
        except (OSError, ValueError):
            continue
    return total


def pilot_spent_usd(results_root: Path) -> float:
    """Spend of the pilots so far (cost.json files of the pilot_* folders)."""
    total = 0.0
    for f in Path(results_root).rglob("pilot_*/cost.json"):
        try:
            total += float(json.loads(f.read_text()).get("usd_this_run", 0.0))
        except (OSError, ValueError):
            continue
    return total


@dataclass
class RolesBudget(Budget):
    cap_usd: float = CAP_USD
    carried: float = 0.0

    @property
    def usd_this_run(self) -> float:
        pin, pout, _ = prices()
        return (self.tokens_in * pin + self.tokens_out * pout) / 1e6

    @property
    def usd(self) -> float:                                  # type: ignore[override]
        return self.carried + self.usd_this_run

    def summary(self) -> dict:
        s = super().summary()
        s.update({"usd_this_run": round(self.usd_this_run, 4), "carried_usd_from_earlier_runs": round(self.carried, 4), "cap_usd": self.cap_usd})
        return s
