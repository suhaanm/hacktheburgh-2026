"""A trimmed, minified copy of a report for the dashboard's mock-mode fixture (apps/dashboard/src/fixtures/eval-report.json).

The dashboard imports the fixture into its bundle, so bulk it does not show is dropped: per-person tables, replication grids, flow lists and the sections
it does not render. Contract keys, ``evidence_map``, ``limitations`` and every stub (pending, not_run, failed, invalid_provenance) are kept. The result
always validates against report.schema.json (``trim`` raises if it would not). Written only on request: ``--fixture PATH``.
"""
from __future__ import annotations

import json
from typing import Any

from .schema import errors

DROP_SECTIONS = ("skills", "forecast", "policy_gate")
DROP_KEYS = {
    "hazard": ("per_person", "vs_planted", "secondary"), "ope": ("diagnostics", "other_targets", "replications"),
    "routing": ("held_out", "risk_control", "risk_control_naive", "calibration", "baselines", "feature_ablation", "fixed_review_budget", "random_review_at_budget", "resplits"),
    "ski_rental": ("sweep",), "presence": ("summary", "per_persona"), "agent_claims": ("model", "baselines", "operating_point"), "pooling": ("datasets",),
    "redteam": ("layer_contribution", "by_category", "defended_by"),
    "study_power": ("rows", "effects", "grid", "design", "population", "sensitivity", "analysis_fidelity"),
    "privacy": ("flows", "bucketing", "backstop", "static_guard", "ledger", "negative_controls", "coverage", "image", "layers", "scan_sensitivity", "scan_specificity", "vocabulary_problems"),
}
KEEP_KEYS = {  # newer owner sections: only what the page can show
    "git": ("meta", "owner_status", "statement", "habit_recovery", "placebo", "digest_agreement", "limitations"),
    "proactive": ("meta", "worth", "structure", "limitations"),
    "calendar": ("meta", "statement", "pattern_recovery", "suggestions", "leak_canary", "limitations"),
    "localmodel": ("meta", "owner_status", "model", "headline", "findings", "limitations"),
}
LIVE_CLAIMS_KEEP = ("label", "origin", "n", "n_unit", "n_groups", "split", "interval_level", "meta", "source", "base_failure_rate", "reliability", "brier", "base_rate")


def trim(report: dict[str, Any]) -> dict[str, Any]:
    cur = json.loads(json.dumps(report))
    secs = cur["sections"]
    for k in DROP_SECTIONS:
        secs.pop(k, None)
    for sec, keys in DROP_KEYS.items():
        s = secs.get(sec)
        if isinstance(s, dict) and "status" not in s:
            for k in keys:
                s.pop(k, None)
    for sec, keep in KEEP_KEYS.items():
        s = secs.get(sec)
        if isinstance(s, dict) and "status" not in s:
            secs[sec] = {k: v for k, v in s.items() if k in keep}
    p = secs.get("proactive")
    if isinstance(p, dict) and "status" not in p:
        p["worth"] = {k: v for k, v in (p.get("worth") or {}).items() if k in ("overall", "baselines")}
    g = secs.get("git")
    if isinstance(g, dict) and "status" not in g and isinstance(g.get("habit_recovery"), dict):
        g["habit_recovery"] = {k: v for k, v in g["habit_recovery"].items() if k in ("overall", "by_habit")}
    ac = (secs.get("agent_claims") or {}).get("live") if isinstance(secs.get("agent_claims"), dict) else None
    if isinstance(ac, dict):
        secs["agent_claims"]["live"] = {k: v for k, v in ac.items() if k in LIVE_CLAIMS_KEEP}
    errs = errors(cur)
    if errs:
        raise ValueError("the trimmed fixture does not match report.schema.json:\n  " + "\n  ".join(errs[:20]))
    return cur


def dumps_min(report: dict[str, Any]) -> str:
    return json.dumps(report, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
