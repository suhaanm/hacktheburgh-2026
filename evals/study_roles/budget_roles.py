"""The spend guard of the role studies: ``evals/study_sim/budget.Budget`` with ONE hard cap for both roles and every pilot (US$14, the lead's figure of 7 Nov 2026), carrying the spend of
earlier runs in the same results tree so the cap holds across processes. Prices come from the environment (never baked into a result) and the estimate is labelled an estimate."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from evals.study_sim.budget import Budget, BudgetExhausted, prices   # noqa: F401  (BudgetExhausted is re-exported)

CAP_USD = 14.0
PLANNER_DEFAULT_PRICES = (5.0, 30.0)      # US$ per million tokens: the lead's assumption for the planner tier; used only if STUDY_ROLES_PRICE_*_PLANNER is not set


def apply_tier_prices(tier: str) -> tuple[float, float, str]:
    """Set STUDY_SIM_PRICE_IN/OUT (the variables ``budget.prices`` reads) for the tier: fast and fast-low use STUDY_SIM_PRICE_* if set (else the conservative defaults of the guard),
    the planner uses STUDY_ROLES_PRICE_IN_PLANNER / _OUT_PLANNER if set, else PLANNER_DEFAULT_PRICES. Returns (in, out, source)."""
    if tier == "planner":
        try:
            pin, pout, src = float(os.environ["STUDY_ROLES_PRICE_IN_PLANNER"]), float(os.environ["STUDY_ROLES_PRICE_OUT_PLANNER"]), "env"
        except (KeyError, ValueError):
            (pin, pout), src = PLANNER_DEFAULT_PRICES, "default"
        os.environ["STUDY_SIM_PRICE_IN"], os.environ["STUDY_SIM_PRICE_OUT"] = str(pin), str(pout)
        return pin, pout, src
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
