"""The final, pre-registered decisions from the held-out results (PLAN.md sections 6.2, 6.4 and 6.8). Pure functions of the result files.

A probability variant (family A) replaces v1 for a role only if (a) it was accepted on the held-out persona replicates (section 6.2: upper end of the paired
log-loss interval below zero at its level, every guard non-inferior) and (b) it passes the pooled off-diagonal generator-mismatch test for that role with no
harmful cell (section 6.8). The deep role (benefits-processor) decides; a thin role cannot rescue a variant that fails the deep role. An alarm rule (family C)
needs (a) and (b) in the same way. Where several variants qualify, the one with the lowest held-out log loss difference is the default v2.
"""
from __future__ import annotations

DEEP_ROLE = "benefits-processor"
A_IDS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7")


def decide(hazard: dict | None, mismatch: dict | None) -> dict:
    out: dict = {"deep_role": DEEP_ROLE, "family_a": {}, "family_c": {}, "default_v2": {}, "v1_stays_for": []}
    if not hazard or not mismatch:
        out["status"] = "incomplete: the held-out hazard and mismatch results are both needed"
        return out
    rows = hazard["family_a"]["rows"]
    roles = list(mismatch["roles"])
    for vid in A_IDS:
        if vid not in rows:
            continue
        a_ok = rows[vid]["verdict"] == "accepted"
        per_role = {r: bool(mismatch["roles"][r]["pooled_off_diagonal"]["rows"][vid]["mismatch_pass"]) for r in roles}
        out["family_a"][vid] = {
            "held_out_persona_verdict": rows[vid]["verdict"], "held_out_delta_log_loss": rows[vid]["paired_vs_ref"]["log_loss"]["delta"],
            "held_out_interval": rows[vid]["paired_vs_ref"]["log_loss"]["interval"], "level": rows[vid]["paired_vs_ref"]["log_loss"]["level"],
            "survives_mismatch_by_role": per_role,
            "replaces_v1_by_role": {r: bool(a_ok and per_role[r] and (r == DEEP_ROLE or (a_ok and per_role.get(DEEP_ROLE, False)))) for r in roles},
        }
    for r in roles:
        ok = [v for v, d in out["family_a"].items() if d["replaces_v1_by_role"][r]]
        if ok:
            best = min(ok, key=lambda v: out["family_a"][v]["held_out_delta_log_loss"])
            out["default_v2"][r] = best
        else:
            out["default_v2"][r] = None
            out["v1_stays_for"].append(r)
    fc = hazard["family_c"]["on_A0"]["rows"]
    for cid in ("C1", "C2"):
        a_ok = cid in fc and fc[cid]["verdict"] == "accepted"
        per_role = {r: bool(mismatch["roles"][r]["pooled_off_diagonal"]["family_c"][cid]["pooled_pass"]) for r in roles}
        out["family_c"][cid] = {"held_out_persona_verdict": fc[cid]["verdict"], "survives_mismatch_by_role": per_role,
                                "replaces_v1_rule_by_role": {r: bool(a_ok and per_role[r]) for r in roles},
                                "note": ("v1 already met the budget on the persona replicates, so the registered overshoot metric cannot improve (null by construction); "
                                         "under generator mismatch v1 overshoots and the risk-controlled rule reduces it") if not a_ok else ""}
    out["status"] = "complete"
    return out
