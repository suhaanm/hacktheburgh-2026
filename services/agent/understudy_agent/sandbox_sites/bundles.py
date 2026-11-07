"""Hand-authored tier-1 bundles for the sandbox sites (what a compiled recording of the expert looks like).

`calculator_bundle(site, layout)` and `casenote_bundle(layout)` return plain JSON-able dicts for the
step DSL in tiers/dsl.py. Layout v1 is what they were "recorded" on; v2 selectors differ, so a v1
bundle replayed on v2 fails its first precondition and the run escalates to tier 2.
"""
from __future__ import annotations

from typing import Any

from .specs import (
    CASENOTE_FIELDS_V1, CASENOTE_FIELDS_V2, CASENOTE_PATH, CASENOTE_RESULT, CASENOTE_SAVE, SITES,
)

SELECT_PARAMS = {"adults", "limited_capability", "tenure", "bedrooms"}
CANONICAL_PARAMS = [
    "adults", "adult1_age", "adult2_age", "children_ages", "adult1_earnings_monthly",
    "adult2_earnings_monthly", "limited_capability", "tenure", "rent_monthly", "bedrooms", "savings",
    "childcare_monthly",
]


CLIFF_BUTTON = "#cliff-btn"
CLIFF_PANEL = "#cliff-panel"  # data-understudy-zone="cliff_panel", the same in both layouts


def cliff_steps() -> list[dict[str, Any]]:
    """CHECK_CLIFF: open the inline panel and read it. Works on every site and layout (stable ids)."""
    return [
        {"id": "cliff_open", "op": "click", "selector": CLIFF_BUTTON, "pre": [{"visible": CLIFF_BUTTON}],
         "post": [{"visible": CLIFF_PANEL}]},
        {"id": "cliff_read", "op": "extract", "name": "cliff", "selector": CLIFF_PANEL},
    ]


def cliff_bundle(site: str) -> dict[str, Any]:
    """Run after the result is read by ANY tier, if the panel was not opened yet."""
    return {"id": f"cliff-{site}", "version": 1, "site": site, "layout": "any", "params": [],
            "outputs": ["cliff"], "steps": cliff_steps()}


def calculator_bundle(site: str, layout: str = "v1") -> dict[str, Any]:
    spec = SITES[site]
    steps: list[dict[str, Any]] = [{"id": "open", "op": "goto", "url": "{base}" + spec.start_path,
                                    "post": [{"visible": spec.selector(spec.steps[0][0], layout)}]}]
    n_pages = len(spec.steps)
    for i, params in enumerate(spec.steps):
        for p in params:
            sel = spec.selector(p, layout)
            value: dict[str, Any] = {"param": p}
            if p in spec.transforms:
                mul, nd = spec.transforms[p]
                value.update({"mul": mul, "round": nd})
            steps.append({"id": f"p{i + 1}_{p}", "op": "select" if p in SELECT_PARAMS else "fill",
                          "selector": sel, "value": value, "pre": [{"visible": sel}]})
        btn = spec.buttons(layout)[i]
        post = ([{"visible": spec.selector(spec.steps[i + 1][0], layout)}] if i + 1 < n_pages
                else [{"visible": spec.result(layout)["amount"]}])
        steps.append({"id": f"p{i + 1}_go", "op": "click", "selector": btn, "pre": [{"visible": btn}], "post": post})
    steps.append({"id": "result_visible", "op": "wait_for", "selector": spec.result(layout)["amount"]})
    for name, sel in spec.result(layout).items():
        steps.append({"id": f"read_{name}", "op": "extract", "name": name, "selector": sel})
    steps += cliff_steps()
    steps.append({"id": "done", "op": "checkpoint", "name": f"calculator_{site}_result_read"})
    return {"id": f"calc-{site}-{layout}", "version": 1, "site": site, "layout": layout,
            "params": list(CANONICAL_PARAMS), "outputs": ["amount", "status", "ref", "cliff"], "steps": steps}


def casenote_bundle(layout: str = "v1") -> dict[str, Any]:
    f = CASENOTE_FIELDS_V2 if layout == "v2" else CASENOTE_FIELDS_V1
    res = CASENOTE_RESULT[layout]
    steps: list[dict[str, Any]] = [{"id": "open", "op": "goto", "url": "{base}" + CASENOTE_PATH,
                                    "post": [{"visible": f["case_ref"]}]}]
    for p in ("case_ref", "result_a", "result_b", "result_c", "note_text"):
        steps.append({"id": f"fill_{p}", "op": "fill", "selector": f[p], "value": {"param": p},
                      "pre": [{"visible": f[p]}]})
    steps.append({"id": "fill_reconciliation", "op": "select", "selector": f["reconciliation"],
                  "value": {"param": "reconciliation"}, "pre": [{"visible": f["reconciliation"]}]})
    save = CASENOTE_SAVE[layout]
    steps.append({"id": "save", "op": "click", "selector": save, "pre": [{"visible": save}],
                  "post": [{"visible": res["note_id"]}]})
    steps.append({"id": "read_note_id", "op": "extract", "name": "note_id", "selector": res["note_id"]})
    steps.append({"id": "read_status", "op": "extract", "name": "status", "selector": res["status"]})
    steps.append({"id": "read_body", "op": "extract", "name": "body", "selector": res["body"]})
    steps.append({"id": "done", "op": "checkpoint", "name": "case_note_saved"})
    return {"id": f"casenote-{layout}", "version": 1, "site": "casenote", "layout": layout,
            "params": ["case_ref", "result_a", "result_b", "result_c", "reconciliation", "note_text"],
            "outputs": ["note_id", "status", "body"], "steps": steps}
