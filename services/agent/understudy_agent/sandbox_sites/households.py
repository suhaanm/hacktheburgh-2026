"""Synthetic UK-style households for the benefits workflow (AGT-5). No real people.

Every household is generated from a seeded RNG and named only `Household NNNN`. Some archetypes are
planted on purpose so the sandbox calculators' cliff edges show up in a 20-household run.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

ARCHETYPES = (
    "single_worker",
    "couple_two_kids",
    "lone_parent_childcare",
    "savings_cliff_16k",
    "savings_tariff_band",
    "third_child",
    "childless_earner",
    "owner_no_housing",
    "high_rent_cap",
    "high_income",
    "carer_limited_capability",
    "young_couple",
)


@dataclass(frozen=True)
class Adult:
    age: int
    earnings_monthly: float = 0.0  # net monthly earnings, pounds


@dataclass(frozen=True)
class Household:
    id: str
    case_ref: str
    region: str  # england | scotland | wales
    adults: tuple[Adult, ...]
    children_ages: tuple[int, ...] = ()
    tenure: str = "rent"  # rent | own
    rent_monthly: float = 0.0
    bedrooms: int = 1
    savings: float = 0.0
    childcare_monthly: float = 0.0
    limited_capability: bool = False
    archetype: str = ""
    synthetic: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"Household {self.id.split('_')[-1]}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["adults"] = [asdict(a) for a in self.adults]
        d["children_ages"] = list(self.children_ages)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Household":
        adults = tuple(
            a if isinstance(a, Adult) else Adult(int(a["age"]), float(a.get("earnings_monthly", 0)))
            for a in d["adults"]
        )
        return cls(
            id=str(d["id"]),
            case_ref=str(d.get("case_ref", "CASE-0000")),
            region=str(d.get("region", "england")),
            adults=adults,
            children_ages=tuple(int(x) for x in d.get("children_ages", ())),
            tenure=str(d.get("tenure", "rent")),
            rent_monthly=float(d.get("rent_monthly", 0)),
            bedrooms=int(d.get("bedrooms", 1)),
            savings=float(d.get("savings", 0)),
            childcare_monthly=float(d.get("childcare_monthly", 0)),
            limited_capability=bool(d.get("limited_capability", False)),
            archetype=str(d.get("archetype", "")),
            synthetic=bool(d.get("synthetic", True)),
            notes=list(d.get("notes", [])),
        )

    # ----- canonical form-parameter view used by every site mapping -----
    def params(self) -> dict[str, str]:
        a1 = self.adults[0]
        a2 = self.adults[1] if len(self.adults) > 1 else None
        return {
            "adults": str(len(self.adults)),
            "adult1_age": str(a1.age),
            "adult2_age": str(a2.age) if a2 else "",
            "children_count": str(len(self.children_ages)),
            "children_ages": ", ".join(str(x) for x in self.children_ages),
            "adult1_earnings_monthly": _num(a1.earnings_monthly),
            "adult2_earnings_monthly": _num(a2.earnings_monthly) if a2 else "0",
            "tenure": self.tenure,
            "rent_monthly": _num(self.rent_monthly),
            "bedrooms": str(self.bedrooms),
            "savings": _num(self.savings),
            "childcare_monthly": _num(self.childcare_monthly),
            "limited_capability": "yes" if self.limited_capability else "no",
            "case_ref": self.case_ref,
            "household_label": self.label,
        }


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}"


def as_household(h: "Household | Mapping[str, Any]") -> Household:
    return h if isinstance(h, Household) else Household.from_dict(h)


def _build(idx: int, archetype: str, rng: random.Random) -> Household:
    hid = f"hh_{idx:04d}"
    case = f"CASE-{1000 + idx}"
    region = rng.choice(["england", "england", "england", "scotland", "wales"])
    r = rng
    adults: tuple[Adult, ...]
    children: tuple[int, ...] = ()
    tenure, rent, beds, savings, childcare, lcw = "rent", 0.0, 1, 0.0, 0.0, False
    notes: list[str] = []

    def earn(lo: int, hi: int) -> float:
        return float(r.randrange(lo, hi, 10))

    if archetype == "single_worker":
        adults = (Adult(r.randint(25, 58), earn(500, 1600)),)
        rent, savings = float(r.randrange(380, 640, 5)), float(r.randrange(0, 4000, 50))
    elif archetype == "couple_two_kids":
        adults = (Adult(r.randint(27, 45), earn(300, 1500)), Adult(r.randint(27, 45), earn(0, 900)))
        children = tuple(sorted(r.sample(range(1, 14), 2)))
        rent, beds, savings = float(r.randrange(600, 790, 5)), 3, float(r.randrange(0, 5000, 50))
    elif archetype == "lone_parent_childcare":
        adults = (Adult(r.randint(24, 40), earn(900, 1900)),)
        children = tuple(sorted(r.sample(range(0, 8), r.choice([1, 2]))))
        rent, beds = float(r.randrange(550, 690, 5)), 2
        childcare, savings = float(r.randrange(300, 1700, 10)), float(r.randrange(0, 3000, 50))
    elif archetype == "savings_cliff_16k":
        adults = (Adult(r.randint(30, 60), earn(0, 300)),)
        rent = float(r.randrange(400, 600, 5))
        savings = float([16000, 15900, 16000, 16001][(idx // len(ARCHETYPES)) % 4])
        notes.append("savings at the 16,000 capital limit")
    elif archetype == "savings_tariff_band":
        adults = (Adult(r.randint(30, 60), earn(0, 600)),)
        rent = float(r.randrange(400, 600, 5))
        savings = float(r.randrange(6500, 15500, 250))
        notes.append("savings in the tariff band")
    elif archetype == "third_child":
        adults = (Adult(r.randint(28, 44), earn(300, 1100)), Adult(r.randint(28, 44), earn(0, 700)))
        children = tuple(sorted(r.sample(range(0, 14), r.choice([3, 3, 4]))))
        rent, beds, savings = float(r.randrange(700, 990, 5)), 4, float(r.randrange(0, 3000, 50))
        notes.append("three or more children")
    elif archetype == "childless_earner":
        adults = (Adult(r.randint(26, 50), earn(700, 1200)),)
        rent, savings = float(r.randrange(400, 560, 5)), float(r.randrange(0, 2000, 50))
        notes.append("no children, no limited capability: no work allowance")
    elif archetype == "owner_no_housing":
        adults = (Adult(r.randint(35, 62), earn(200, 900)),)
        tenure, rent, beds = "own", 0.0, 2
        savings = float(r.randrange(0, 5000, 50))
        children = tuple(sorted(r.sample(range(0, 14), r.choice([0, 1]))))
    elif archetype == "high_rent_cap":
        adults = (Adult(r.randint(26, 55), earn(200, 800)),)
        beds = 1
        rent = float(r.randrange(640, 900, 5))
        savings = float(r.randrange(0, 3000, 50))
        notes.append("rent above the local housing cap")
    elif archetype == "high_income":
        adults = (Adult(r.randint(30, 55), earn(2600, 4200)), Adult(r.randint(30, 55), earn(1500, 2800)))
        children = tuple(sorted(r.sample(range(0, 14), 1)))
        rent, beds, savings = float(r.randrange(650, 800, 5)), 3, float(r.randrange(2000, 9000, 50))
    elif archetype == "carer_limited_capability":
        adults = (Adult(r.randint(30, 62), earn(0, 500)),)
        lcw = True
        rent, beds, savings = float(r.randrange(400, 620, 5)), 1, float(r.randrange(0, 2500, 50))
    elif archetype == "young_couple":
        adults = (Adult(r.randint(19, 24), earn(300, 1100)), Adult(r.randint(19, 24), earn(200, 800)))
        rent, beds, savings = float(r.randrange(420, 570, 5)), 1, float(r.randrange(0, 1500, 50))
    else:  # pragma: no cover
        raise ValueError(archetype)

    return Household(
        id=hid, case_ref=case, region=region, adults=adults, children_ages=children,
        tenure=tenure, rent_monthly=rent, bedrooms=beds, savings=savings,
        childcare_monthly=childcare, limited_capability=lcw, archetype=archetype, notes=notes,
    )


def generate_households(n: int = 20, seed: int = 2026) -> list[Household]:
    """Seeded, reproducible. Archetypes are cycled so every cliff edge appears in a 20-household run."""
    rng = random.Random(seed)
    out: list[Household] = []
    for i in range(n):
        out.append(_build(i + 1, ARCHETYPES[i % len(ARCHETYPES)], rng))
    return out


def get_household(household_id: str, n: int = 20, seed: int = 2026) -> Household:
    for h in generate_households(max(n, 40), seed):
        if h.id == household_id:
            return h
    raise KeyError(household_id)
