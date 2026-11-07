#!/usr/bin/env python
"""Fixes the study design before any data: the four counterbalanced sequences and the matched household pairs.

    uv run python evals/study/make_assignments.py     # writes evals/study/assignments.json

Deterministic: it reads evals/cases/households_200.json and picks, by rule, two matched pairs of households.
Each study case is run on two calculators only (GovCalc a and Quick Estimator b) to fit the time budget, so a
case counts only if a and b show different amounts (the correct reconciliation is then "discrepancy", which is
never the form's default) and its cliff panel has at least one item marked near.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE.parent / "cases" / "households_200.json"

# Four sequences: each skill is coached for two participants and uncoached for two, and each
# order (coached block first or second) occurs twice. n = 4, one participant per sequence.
SEQUENCES = {
    "S1": [("cliff", "coached"), ("reconcile", "uncoached")],
    "S2": [("reconcile", "coached"), ("cliff", "uncoached")],
    "S3": [("cliff", "uncoached"), ("reconcile", "coached")],
    "S4": [("reconcile", "uncoached"), ("cliff", "coached")],
}
SKILL_ID = {"cliff": "check-the-cliff", "reconcile": "reconcile-before-noting"}


def usable(c: dict) -> bool:
    a, b = c["sites_expected"]["a"]["uc_monthly"], c["sites_expected"]["b"]["uc_monthly"]
    near = any(v == "yes" for v in c["cliff_panel_expected"].values())
    return abs(a - b) > 1.0 and near and c["household"]["archetype"] != "high_income"


def gap(c: dict) -> float:
    return abs(c["sites_expected"]["a"]["uc_monthly"] - c["sites_expected"]["b"]["uc_monthly"])


def flags(c: dict) -> frozenset:
    return frozenset(c["oracle"]["cliff_flags"])


def pick_pairs(cases: list[dict]) -> dict[str, list[str]]:
    pool = [c for c in cases if usable(c)]
    by_arch: dict[str, list[dict]] = {}
    for c in pool:
        by_arch.setdefault(c["household"]["archetype"], []).append(c)
    # most populated archetypes first; within one, the closest pair on (flags, savings, gap, children)
    ranked = sorted(by_arch.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    chosen: list[list[dict]] = []
    used: set[str] = set()
    for arch, group in ranked:
        best = None
        for i, x in enumerate(group):
            for y in group[i + 1:]:
                if x["household"]["id"] in used or y["household"]["id"] in used or flags(x) != flags(y):
                    continue
                score = (abs(x["household"]["savings"] - y["household"]["savings"]) / 1000 + abs(gap(x) - gap(y)) / 50
                         + abs(len(x["household"]["children_ages"]) - len(y["household"]["children_ages"])))
                if best is None or score < best[0]:
                    best = (score, x, y)
        if best:
            chosen.append([best[1], best[2]])
            used |= {best[1]["household"]["id"], best[2]["household"]["id"]}
        if len(chosen) == 2:
            break
    if len(chosen) < 2:
        raise SystemExit("not enough usable matched pairs in households_200.json")
    return {"cliff": [c["household"]["id"] for c in chosen[0]], "reconcile": [c["household"]["id"] for c in chosen[1]]}


def build() -> dict:
    doc = json.loads(CASES.read_text())
    cases = doc["cases"]
    by_id = {c["household"]["id"]: c for c in cases}
    pairs = pick_pairs(cases)
    participants = {}
    for k, (seq, blocks) in enumerate(SEQUENCES.items()):
        swap = k % 2 == 1  # alternate which member of a pair is the practice case, so case version is not confounded
        plan = []
        for n, (skill, cond) in enumerate(blocks, 1):
            p = list(pairs[skill])
            if swap:
                p.reverse()
            plan.append({"block": n, "skill": skill, "skill_id": SKILL_ID[skill], "condition": cond,
                         "practice_case": p[0], "post_case": p[1], "calculators": ["a", "b"]})
        participants[f"P{k + 1}"] = {"sequence": seq, "blocks": plan}
    return {
        "schema": 1,
        "note": "Fixed before data. n = 4 teammates, one per sequence. Households are synthetic; the oracle is a simplified internal rule set, illustrative, not law.",
        "pairs": {skill: [{"id": i, "archetype": by_id[i]["household"]["archetype"], "savings": by_id[i]["household"]["savings"],
                           "cliff_flags": by_id[i]["oracle"]["cliff_flags"], "a": by_id[i]["sites_expected"]["a"]["uc_monthly"],
                           "b": by_id[i]["sites_expected"]["b"]["uc_monthly"], "case_ref": by_id[i]["household"]["case_ref"]}
                          for i in ids] for skill, ids in pairs.items()},
        "sequences": {k: [{"skill": s, "condition": c} for s, c in v] for k, v in SEQUENCES.items()},
        "participants": participants,
    }


if __name__ == "__main__":
    out = build()
    (HERE / "assignments.json").write_text(json.dumps(out, indent=2) + "\n")
    for skill, rows in out["pairs"].items():
        print(skill, [(r["id"], r["archetype"], r["savings"], r["a"], r["b"]) for r in rows])
