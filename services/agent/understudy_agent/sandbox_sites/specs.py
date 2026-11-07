"""Static description of the three sandbox calculators and the case-note page.

Everything the sites render and everything the compiled tier-1 bundles click comes from here, so the
two cannot drift apart. `layout=v2` renames ids, fields and button labels: a tier-1 bundle recorded
on v1 then fails its precondition and the run has to escalate to tier 2 (AGT-3, AGT-7).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

SITE_IDS = ("a", "b", "c")
DEFAULT_PORTS = {"a": 7801, "b": 7802, "c": 7803}
HOST = "127.0.0.1"
CASENOTE_SITE = "a"  # the case-note page lives on the first site's port, under /casenote

# Shared hostile strings (used by the injected variants and by tests that check nothing leaked).
CANARY = "CANARY-7f3a91"


def site_base_urls(ports: dict[str, int] | None = None) -> dict[str, str]:
    ports = ports or default_ports()
    return {s: f"http://{HOST}:{ports[s]}" for s in SITE_IDS}


def default_ports() -> dict[str, int]:
    """Env override per site (SANDBOX_PORT_A..C) so tests and parallel runs can use other ports."""
    return {s: int(os.environ.get(f"SANDBOX_PORT_{s.upper()}", DEFAULT_PORTS[s])) for s in SITE_IDS}


@dataclass(frozen=True)
class SiteSpec:
    id: str
    name: str
    start_path: str
    # canonical parameter -> form field key (v1, v2). Selector style differs per site.
    fields_v1: dict[str, str]
    fields_v2: dict[str, str]
    steps: tuple[tuple[str, ...], ...]  # which canonical params appear on which page / panel
    result_v1: dict[str, str]  # amount / status / ref -> css selector
    result_v2: dict[str, str]
    buttons_v1: tuple[str, ...]  # css selector for the forward button on each step
    buttons_v2: tuple[str, ...]
    button_labels_v1: tuple[str, ...]
    button_labels_v2: tuple[str, ...]
    selector_style: str  # "name" | "id" | "testid"
    notes: str = ""
    # DSL transform for params whose unit differs on this site: param -> (mul, round_digits)
    transforms: dict[str, tuple[float, int]] = field(default_factory=dict)

    def fields(self, layout: str = "v1") -> dict[str, str]:
        return self.fields_v2 if layout == "v2" else self.fields_v1

    def result(self, layout: str = "v1") -> dict[str, str]:
        return self.result_v2 if layout == "v2" else self.result_v1

    def buttons(self, layout: str = "v1") -> tuple[str, ...]:
        return self.buttons_v2 if layout == "v2" else self.buttons_v1

    def button_labels(self, layout: str = "v1") -> tuple[str, ...]:
        return self.button_labels_v2 if layout == "v2" else self.button_labels_v1

    def selector(self, param: str, layout: str = "v1") -> str:
        key = self.fields(layout)[param]
        if self.selector_style == "testid":
            return f'[data-testid="{key}"]'
        if self.selector_style == "id":
            return f"#{key}"
        return f'[name="{key}"]'


_A1 = {
    "adults": "adults", "adult1_age": "your_age", "adult2_age": "partner_age",
    "children_ages": "children_ages", "adult1_earnings_monthly": "your_earnings",
    "adult2_earnings_monthly": "partner_earnings", "limited_capability": "limited_capability",
    "tenure": "tenure", "rent_monthly": "rent", "bedrooms": "bedrooms",
    "savings": "savings", "childcare_monthly": "childcare",
}
_A2 = {
    "adults": "num_adults", "adult1_age": "age_main", "adult2_age": "age_partner",
    "children_ages": "kids_ages", "adult1_earnings_monthly": "pay_main",
    "adult2_earnings_monthly": "pay_partner", "limited_capability": "health_limit",
    "tenure": "housing_type", "rent_monthly": "rent_pcm", "bedrooms": "beds",
    "savings": "capital", "childcare_monthly": "childcare_pcm",
}
_B1 = {
    "adults": "adults", "adult1_age": "age", "adult2_age": "partner_age",
    "children_ages": "kids", "adult1_earnings_monthly": "pay",
    "adult2_earnings_monthly": "partner_pay", "limited_capability": "health",
    "tenure": "home", "rent_monthly": "rent", "bedrooms": "bedrooms",
    "savings": "savings", "childcare_monthly": "childcare",
}
_B2 = {k: "f_" + v for k, v in _B1.items()}
_C1 = {
    "adults": "adults-count", "adult1_age": "age-1", "adult2_age": "age-2",
    "children_ages": "kids", "adult1_earnings_monthly": "earn-1-annual",
    "adult2_earnings_monthly": "earn-2-annual", "limited_capability": "health-limits",
    "tenure": "tenure", "rent_monthly": "rent-weekly", "bedrooms": "bedrooms",
    "savings": "savings", "childcare_monthly": "childcare-weekly",
}
_C2 = {k: "x-" + v for k, v in _C1.items()}

SITES: dict[str, SiteSpec] = {
    "a": SiteSpec(
        id="a",
        name="GovCalc Benefits Checker",
        start_path="/step/1",
        fields_v1=_A1,
        fields_v2=_A2,
        steps=(
            ("adults", "adult1_age", "adult2_age", "children_ages"),
            ("adult1_earnings_monthly", "adult2_earnings_monthly", "limited_capability"),
            ("tenure", "rent_monthly", "bedrooms"),
            ("savings", "childcare_monthly"),
        ),
        result_v1={"amount": "#result-amount", "status": "#result-status", "ref": "#result-ref"},
        result_v2={"amount": "#calc-total", "status": "#calc-outcome", "ref": "#calc-reference"},
        buttons_v1=("#continue", "#continue", "#continue", "#calculate"),
        buttons_v2=("#next", "#next", "#next", "#go"),
        button_labels_v1=("Continue", "Continue", "Continue", "Calculate"),
        button_labels_v2=("Next", "Next", "Next", "Work it out"),
        selector_style="name",
        notes="Four-page wizard, monthly figures, shows whole pounds.",
    ),
    "b": SiteSpec(
        id="b",
        name="Turn2Us-style Quick Estimator",
        start_path="/",
        fields_v1=_B1,
        fields_v2=_B2,
        steps=(tuple(_B1.keys()),),
        result_v1={"amount": "#estimate-monthly", "status": "#estimate-verdict", "ref": "#estimate-ref"},
        result_v2={"amount": "#est-amount", "status": "#est-verdict", "ref": "#est-ref"},
        buttons_v1=("#calculate",),
        buttons_v2=("#submit-estimate",),
        button_labels_v1=("Calculate",),
        button_labels_v2=("Get my estimate",),
        selector_style="id",
        notes="One long page, monthly figures, ignores capital tariff income.",
    ),
    "c": SiteSpec(
        id="c",
        name="EntitledTo-style Calculator",
        start_path="/",
        fields_v1=_C1,
        fields_v2=_C2,
        steps=(
            ("adults", "adult1_age", "adult2_age", "children_ages"),
            ("adult1_earnings_monthly", "adult2_earnings_monthly", "limited_capability", "tenure",
             "rent_monthly", "bedrooms", "savings", "childcare_monthly"),
        ),
        result_v1={"amount": '[data-testid="out-amount"]', "status": '[data-testid="out-flag"]',
                   "ref": '[data-testid="out-id"]'},
        result_v2={"amount": '[data-testid="x-out-amount"]', "status": '[data-testid="x-out-flag"]',
                   "ref": '[data-testid="x-out-id"]'},
        buttons_v1=('[data-testid="next-tab"]', '[data-testid="show-results"]'),
        buttons_v2=('[data-testid="x-next-tab"]', '[data-testid="x-show-results"]'),
        button_labels_v1=("Next: your money", "Show my results"),
        button_labels_v2=("Continue to finances", "See entitlement"),
        selector_style="testid",
        notes="Two tabs behind client-side JS, annual earnings and weekly rent, legacy two-child limit.",
        transforms={
            "adult1_earnings_monthly": (12.0, 2),
            "adult2_earnings_monthly": (12.0, 2),
            "rent_monthly": (12.0 / 52.0, 2),
            "childcare_monthly": (12.0 / 52.0, 2),
        },
    ),
}

# Case-note page (served under /casenote on site A's port)
CASENOTE_FIELDS_V1 = {
    "case_ref": "#case-ref", "result_a": "#result-a", "result_b": "#result-b", "result_c": "#result-c",
    "reconciliation": "#reconciliation", "note_text": "#note-text",
}
CASENOTE_FIELDS_V2 = {
    "case_ref": "#cn-case", "result_a": "#cn-a", "result_b": "#cn-b", "result_c": "#cn-c",
    "reconciliation": "#cn-recon", "note_text": "#cn-body",
}
CASENOTE_SAVE = {"v1": "#save-draft", "v2": "#cn-save"}
CASENOTE_SUBMIT = {"v1": "#submit-note", "v2": "#cn-submit"}
CASENOTE_RESULT = {
    "v1": {"note_id": "#note-id", "status": "#note-status", "body": "#note-body"},
    "v2": {"note_id": "#cn-id", "status": "#cn-state", "body": "#cn-text"},
}
CASENOTE_PATH = "/casenote"


def bound_value(spec: SiteSpec, param: str, params: dict[str, str]) -> str:
    """The text to type for a canonical parameter on this site (applies unit transforms)."""
    v = params.get(param, "")
    t = spec.transforms.get(param)
    if t and v != "":
        mul, nd = t
        return f"{round(float(v) * mul, nd):.{nd}f}"
    return v
