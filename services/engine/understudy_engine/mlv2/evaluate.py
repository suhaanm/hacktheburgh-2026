"""``evaluate_mlv2``: the report section for ML v2 (REQ-6), in the eval harness's section envelope (meta, tables, caveats, limitations).

``fast=True`` runs in well under a minute: dev-labelled hazard numbers on D0 and genome numbers on the original apprentice cohort, never touching any
held-out pool or the simulated-participant traces. ``fast=False`` also recomputes D0 at full bootstrap size and loads the frozen results files written
by ``python -m understudy_engine.mlv2.run`` (DEV, held-out, mismatch, transfer), checking each file's code fingerprint against the current code.

Everything is labelled: dev results are never acceptance evidence; held-out replicates share our generator; the simulated participants are language
models, not people; the live study stays not_run.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from understudy_engine.mlv2 import freeze
from understudy_engine.mlv2.variants import count_tested

LABEL = "Models v2 (REQ-6): pre-registered improvements to detection, comparison and analysis, with honest nulls"
PLAN = "evals/mlv2/PLAN.md"

LIMITATIONS = [
    {"id": "mlv2-synthetic", "severity": "high",
     "text": "Every number in this section comes from synthetic people or simulated participants (language model), not people. A gain on synthetic data can be the model learning the generator; held-out replicates share the generator and cannot rule that out."},
    {"id": "mlv2-heldout-same-generator", "severity": "high",
     "text": "The held-out persona and apprentice replicates are fresh seeds of the same generators: they catch overfitting to one noise draw, not learning the generator. Only the cross-family matrix (three differently built generators, still written by us) and the simulated-participant traces go beyond it."},
    {"id": "mlv2-awareness-planted", "severity": "medium",
     "text": "The awareness features come from a generator that plants a cursor-to-stuck link by assumption; an ablation lift shows the pipeline can use a planted signal, not that real cursors predict being stuck."},
    {"id": "mlv2-alarm-guarantee", "severity": "medium",
     "text": "The risk-controlled alarm threshold is guaranteed only for exchangeable episodes and independent false alarms; it fails for a new person who differs from the training people, for drift and for clustered alarms."},
    {"id": "mlv2-counterfactual-additive", "severity": "medium",
     "text": "The seconds-if-fixed estimate assumes the rest of the path would be unchanged. It fails when habits interact; the generator's prices are additive by construction, so the stress test with a planted interaction is invented by us."},
    {"id": "mlv2-labelling", "severity": "medium",
     "text": "The deficit rows that stay mis-priced (copy error, repeated reads) are mis-priced by the rule that names alignment columns after the alignment, not by the substitution costs; a better labelling rule written from our own planted structure would be fitting the generator, so none was added."},
    {"id": "mlv2-sim-sparse", "severity": "medium",
     "text": "The simulated-participant traces have few progress events and short cases, so the transfer numbers rest on little and the label is nearly constant; the test is reported whatever it shows."},
]


def _slim_a(cmp_a: dict) -> list[dict]:
    rows = []
    for vid, r in cmp_a["rows"].items():
        d = r["paired_vs_ref"]["log_loss"]
        rows.append({"id": vid, "label": r["label"], "log_loss": r["metrics"]["log_loss"]["value"], "ece": r["metrics"]["ece"]["value"],
                     "delta_log_loss": d["delta"], "interval": d["interval"], "level": d["level"],
                     "false_alarms_per_hour": r["events"]["false_alarms_per_hour"]["value"], "detection": r["events"]["detection"]["value"],
                     "guards_ok": r["guards_ok"], "verdict": r["verdict"]})
    return rows


def _slim_c(cmp_c: dict) -> list[dict]:
    return [{"id": r, "false_alarms_per_hour": v["false_alarms_per_hour"], "detection": v["detection"], "budget_met": v["budget_met"],
             "budget_demonstrated": v["budget_demonstrated"], "overshoot_delta": v["paired_vs_ref"]["overshoot"], "verdict": v["verdict"]}
            for r, v in cmp_c["rows"].items()]


def _slim_genome(cmp_g: dict) -> list[dict]:
    out = []
    for vid, r in cmp_g["rows"].items():
        p = r["paired_primary_abs_error"]
        out.append({"id": vid, "target_abs_error_delta": p.get("delta"), "interval": p.get("interval"), "level": r["level"], "recall": r["recall"],
                    "precision": r["precision"], "placebo_gap_s": r["placebo"]["gap_s"], "guards_ok": r["guards_ok"], "verdict": r["verdict"]})
    return out


def slim_hazard(h: dict) -> dict:
    out = {"pool": h.get("pool"), "n_people": h.get("n_people"), "n_bins": h.get("n_bins"), "inner": h.get("inner"), "primary_a": h.get("primary_a"),
           "family_a": _slim_a(h["family_a"]), "family_c_on_A0": _slim_c(h["family_c"]["on_A0"])}
    if "on_primary_a" in h["family_c"]:
        out["family_c_on_primary_a"] = _slim_c(h["family_c"]["on_primary_a"])
    if "tte" in h:
        t = h["tte"]
        out["tte"] = {"paired_s60_log_loss": t["s60"]["paired"], "c_index": t.get("c_index"), "mean_expected_min": t.get("mean_expected_min")}
    if "controls" in h:
        out["controls"] = {k: {"all_pass": v["all_pass"], "role": v["role"]} for k, v in h["controls"].items()}
    if "ablation" in h:
        ab = h["ablation"]
        out["ablation"] = {k: {g: {"delta_log_loss": r["paired_vs_without"]["log_loss"]["delta"], "interval": r["paired_vs_without"]["log_loss"]["interval"],
                                   "improves": r["improves_log_loss"]} for g, r in v["rows"].items()} | {"controls_ok": v["controls_ok"]}
                           for k, v in ab.items() if isinstance(v, dict) and "rows" in v}
    return out


def slim_genome(g: dict) -> dict:
    return {"pool": g.get("pool"), "n_cohorts": g.get("n_cohorts"), "n_novices": g.get("n_novices"), "family_e": _slim_genome(g["family_e"]),
            "family_q": _slim_genome(g["family_q"]), "primary_e": g.get("primary_e"), "primary_q": g.get("primary_q"),
            "shapley_max_interaction_on_replay": g["shapley"]["max_abs_interaction_on_replay"],
            "nulls": {k: {"gap_s": v["gap_s"], "interval": v["interval"]} for k, v in g.get("nulls", {}).items()}}


def slim_mismatch(m: dict) -> dict:
    roles = {}
    for role, r in m["roles"].items():
        p = r["pooled_off_diagonal"]
        roles[role] = {"pooled_off_diagonal": {v: {"delta_log_loss": row["paired_vs_ref"]["log_loss"]["delta"], "interval": row["paired_vs_ref"]["log_loss"]["interval"],
                                                   "transfer_loss": row.get("transfer_loss"), "mismatch_pass": row["mismatch_pass"], "harmful_cells": row["harmful_cells"]}
                                               for v, row in p["rows"].items()},
                       "family_c": {k: {"pooled_pass": v["pooled_pass"], "overshoot_delta": v["paired_vs_C0"]["overshoot"]} for k, v in p["family_c"].items()}}
    return {"pool": m.get("pool"), "primary_a": m.get("primary_a"), "roles": roles, "generator_sha256": m.get("generator_sha256")}


def _load(name: str) -> dict | None:
    p = freeze.out_dir() / "results" / name
    return freeze.read_json(p) if p.exists() else None


def _fingerprint_note(res: dict | None, part: str) -> dict | None:
    if res is None:
        return None
    now = freeze.code_fingerprint(freeze.code_hashes(part))
    return {"file": res.get("split_label"), "code_fingerprint_at_run": res.get("code_fingerprint"), "code_fingerprint_now": now,
            "code_unchanged_since_run": res.get("code_fingerprint") == now}


def verdict_table(hazard: dict | None, genome: dict | None, mismatch: dict | None, transfer: dict | None = None) -> list[dict]:
    """Every variant tried, with its pre-registered verdict from the held-out run (or 'not run')."""
    rows: list[dict] = []
    if hazard:
        for vid, r in hazard["family_a"]["rows"].items():
            if vid in ("A0", "TSP", "BASE"):
                continue
            rows.append({"family": "A", "id": vid, "verdict": r["verdict"], "delta": r["paired_vs_ref"]["log_loss"]["delta"],
                         "interval": r["paired_vs_ref"]["log_loss"]["interval"], "level": r["level"], "primary": r["is_primary"]})
        for vid, r in hazard["family_c"]["on_A0"]["rows"].items():
            if vid != "C0":
                rows.append({"family": "C", "id": vid, "verdict": r["verdict"], "delta": r["paired_vs_ref"]["overshoot"]["delta"],
                             "interval": r["paired_vs_ref"]["overshoot"]["interval"], "level": r["level"], "primary": r["is_primary"]})
    if genome:
        for fam, key in (("E", "family_e"), ("Q", "family_q")):
            for vid, r in genome[key]["rows"].items():
                if r["verdict"] != "reference":
                    p = r["paired_primary_abs_error"]
                    rows.append({"family": fam, "id": vid, "verdict": r["verdict"], "delta": p.get("delta"), "interval": p.get("interval"),
                                 "level": r["level"], "primary": r["is_primary"]})
    if mismatch:
        for role, r in mismatch["roles"].items():
            for vid, row in r["pooled_off_diagonal"]["rows"].items():
                if vid not in ("A0", "TSP", "BASE"):
                    rows.append({"family": "A under mismatch", "role": role, "id": vid, "verdict": "survives mismatch" if row["mismatch_pass"] else "does not survive",
                                 "delta": row["paired_vs_ref"]["log_loss"]["delta"], "interval": row["paired_vs_ref"]["log_loss"]["interval"]})
    return rows


def reproduction_check() -> dict:
    """PLAN.md section 4: the mlv2 protocol must reproduce v1's published D0 numbers exactly, or nothing is reported."""
    from understudy_engine.hazard.evaluate import evaluate_hazard
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.mlv2 import splits
    from understudy_engine.mlv2.alarms import build_layout
    from understudy_engine.mlv2.models import FAMILY_A, LEARNERS
    from understudy_engine.mlv2.protocol import apply_variant, fit_base_oof, make_folds, reproduces_v1

    eps = splits.load_pool("D0")
    tab = build_bins(eps)
    v1 = evaluate_hazard(eps, n_boot=10, include_series=False)
    folds = make_folds(tab)
    base = fit_base_oof(tab, LEARNERS["L"], folds=folds)
    out = apply_variant(tab, base, FAMILY_A["A0"], layout=build_layout(tab), folds=folds)
    return reproduces_v1(tab, v1, out)


def _est(value, interval) -> dict:
    return {"value": value, "ci": list(interval) if interval else None}


def _row_block(row: dict) -> dict:
    m, e = row["metrics"], row["events"]
    return {"log_loss": _est(m["log_loss"]["value"], m["log_loss"]["interval"]), "brier": _est(m["brier"]["value"], m["brier"]["interval"]),
            "ece": _est(m["ece"]["value"], m["ece"]["interval"]),
            "false_alarms_per_hour": _est(e["false_alarms_per_hour"]["value"], e["false_alarms_per_hour"]["interval"]),
            "detection_rate": _est(e["detection"]["value"], e["detection"]["interval"])}


def _calibration_d0(spec_id: str | None) -> tuple[list[dict], str]:
    """Reliability bins on D0 (leave one person out, dev) of v1 or of the frozen primary, with a Wilson interval on each observed frequency
    (it treats bins as independent, so it is narrower than the person-level uncertainty; said in the caveats)."""
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.mlv2 import splits
    from understudy_engine.mlv2.deployed import spec_by_id
    from understudy_engine.mlv2.family_a import run_family_a
    from understudy_engine.mlv2.models import FAMILY_A
    from understudy_engine.trust.calibration import reliability_bins
    from understudy_engine.trust.stats import wilson_interval

    tab = build_bins(splits.load_pool("D0"))
    spec = spec_by_id(spec_id) if spec_id else FAMILY_A["A0"]
    run = run_family_a(tab, variants={"X": spec}, include_baselines=False, inner_folds=5)
    bins = reliability_bins(tab.y.astype(float), run.outputs["X"].p)
    out = []
    for b in bins:
        lo, hi = wilson_interval(int(round(b["freq"] * b["n"])), int(b["n"]))
        out.append({"p_mean": b["p_mean"], "freq": b["freq"], "n": b["n"], "lo": lo, "hi": hi})
    return out, "D0: the four v1 personas, leave one person out (dev)"


def scorecard(held: dict | None, dev_d0: dict, *, fast: bool, frozen: dict | None, tte_dev: dict | None = None, decision: dict | None = None) -> dict:
    """ONE stable block for the dashboard's Predictions scorecard: the frozen v2 candidate against v1 and the baselines, with the pre-registered
    verdict. ``accepted`` is true only when the single held-out run accepted the candidate; otherwise v1 stays the default (shown as ``v1``)."""
    src = held if held else dev_d0
    rows = src["family_a"]["rows"]
    from understudy_engine.mlv2.decision import DEEP_ROLE
    from understudy_engine.mlv2.deployed import spec_by_id

    chosen = (decision or {}).get("default_v2", {}).get(DEEP_ROLE) if (decision or {}).get("status") == "complete" else None
    if chosen:
        # the variant that passed BOTH pre-registered tests (held-out persona replicates and generator mismatch) for the deep role
        prim, prim_id, accepted = chosen, chosen, chosen in rows
        label = spec_by_id(chosen).label
    else:
        prim = (frozen or {}).get("primary_a") or src.get("primary_a")
        prim_id = prim if prim in rows else ((frozen or {}).get("a7_base") if prim == "A7" and (frozen or {}).get("a7_base") in rows else None)
        accepted = False
        label = None
        if frozen and frozen.get("a7_base") and prim:
            label = spec_by_id(frozen["a7_base"]).label if prim == "A7" else spec_by_id(prim).label
    baselines = {"base_rate": _row_block(rows["BASE"]), "time_since_progress": _row_block(rows["TSP"]), "v1": _row_block(rows["A0"])}
    model = _row_block(rows[prim_id]) if prim_id else baselines["v1"]
    budget = 1.0
    t = src.get("tte") or tte_dev
    tte = None
    if t:
        ci = t.get("c_index") or {}
        tte = {"c_index": _est((ci.get("head") or {}).get("value"), (ci.get("head") or {}).get("interval")),
               "calibration": [{"n": c["n"], "predicted_min": c["predicted_min"], "observed_km_min": c["observed_km_min"]} for c in t["calibration_expected_minutes"]],
               "mean_expected_min": t["mean_expected_min"], "km_restricted_mean_min": t["km_restricted_mean_min"]}
    cal, cal_src = ([], "not computed in fast mode")
    if not fast:
        cal, cal_src = _calibration_d0((frozen or {}).get("a7_base") if prim == "A7" else prim)
    return {
        "meta": {"origin": "synthetic", "n": src["n_people"], "n_unit": "people", "split": src.get("split_label") or src.get("split"),
                 "pool": "held-out replicates (single frozen run)" if held else "D0 (dev), not held-out", "interval_level": 0.95},
        "accepted": accepted, "verdict": ("accepted_by_both_tests" if accepted else (rows[prim_id]["verdict"] if (held and prim_id) else ("not_run" if not held else "no_primary"))),
        "model_version_shown_as_default": "v2" if accepted else "v1", "primary_id": prim_id,
        "primary_label": label or "no primary candidate", "model": model, "baselines": baselines,
        "calibration": cal, "calibration_source": cal_src, "false_alarms_per_hour": model["false_alarms_per_hour"],
        "budget_per_hour": budget, "within_budget": bool(model["false_alarms_per_hour"]["value"] is not None and model["false_alarms_per_hour"]["value"] <= budget),
        "detection_rate": model["detection_rate"], "tte": tte,
        "caveats": [
            "Synthetic people from our own generator; held-out replicates share the generator, so this cannot show the model avoided learning it.",
            "If accepted is false, v1 stays the default and the v2 numbers are those of a candidate that did not pass its pre-registered test.",
            "The calibration bins carry Wilson intervals that treat bins as independent; the person-level uncertainty is wider.",
            "False alarms an hour are measured against a budget of 1.0 chosen by us, not a measured tolerance of real workers.",
        ],
    }


def evaluate_mlv2(*, fast: bool = True, seed: int = 0, root: Any = None) -> dict[str, Any]:
    """The section. ``fast`` stays under a minute and never reads or generates held-out data or simulated-participant traces."""
    from understudy_engine.mlv2.genome_part import run_genome_part
    from understudy_engine.mlv2.hazard_part import run_hazard_part

    repro = reproduction_check()
    if not repro["ok"]:
        return {"status": "failed", "reason": "the mlv2 protocol does not reproduce v1's D0 numbers, so nothing is reported", "v1_reproduction": repro,
                "meta": {"origin": "synthetic", "n": 0, "n_unit": "people", "split": None, "note": "reproduction check failed"}}
    haz = run_hazard_part("D0", frozen=None, fast=fast, n_boot=300 if fast else 4000, seed=seed, with_ablation=False, with_controls=True)
    gen = run_genome_part("APP-D0", frozen=None, n_boot=300 if fast else 4000, fast=fast, seed=seed)
    out: dict[str, Any] = {
        "label": LABEL, "plan": PLAN, "mode": "fast" if fast else "full",
        "meta": {"origin": "synthetic", "n": haz["n_people"], "n_unit": "people",
                 "split": "leave-one-person-out on the four v1 personas (dev) and one apprentice cohort (dev); held-out and cross-generator results are listed under heldout",
                 "interval_level": 0.95,
                 "note": "Dev-labelled numbers are never acceptance evidence. Held-out replicates share our generator. Pre-registered in evals/mlv2/PLAN.md. The live study stays not_run."},
        "variants_tried": count_tested(), "v1_reproduction": repro,
        "dev": {"hazard_d0": slim_hazard(haz), "genome_apprentice_d0": slim_genome(gen)},
    }
    held = {}
    if not fast:
        for part, fname in (("hazard", "heldout_hazard.json"), ("genome", "heldout_genome.json"), ("mismatch", "heldout_mismatch.json")):
            res = _load(fname)
            held[part] = {"fingerprint": _fingerprint_note(res, part),
                          "result": None if res is None else {"hazard": slim_hazard, "genome": slim_genome, "mismatch": slim_mismatch}[part](res)}
        dev_all = _load("dev_hazard_dev.json")
        if dev_all:
            out["dev"]["hazard_dev16"] = slim_hazard(dev_all)
        tr = _load("transfer_sim.json")
        out["transfer_simulated_participants"] = tr if tr else {"status": "not_run", "reason": "no transfer result file yet"}
        out["heldout"] = held
        hz_res = _load("heldout_hazard.json")
        frozen = freeze.read_frozen()
        from understudy_engine.mlv2.decision import decide

        mm_res = _load("heldout_mismatch.json")
        decision = decide(hz_res, mm_res)
        out["final_decisions"] = decision
        out["scorecard"] = scorecard(hz_res, haz, fast=False, frozen=frozen, decision=decision)
        out["verdicts"] = verdict_table(*(_load(f) for f in ("heldout_hazard.json", "heldout_genome.json", "heldout_mismatch.json")))
    out["stated_gaps"] = [
        "Not run, for time and compute: the time-to-event head under generator mismatch, and the expert-envelope and counterfactual families (E, Q) under generator mismatch. These are gaps, not negative results.",
    ]
    if fast:
        out["scorecard"] = scorecard(None, haz, fast=True, frozen=freeze.read_frozen())
    out["caveats"] = [
        "Stated gaps: the time-to-event head and families E and Q were not run under generator mismatch (compute and time); a gap is not a negative result.",
        "Dev numbers are for debugging and for choosing each family's primary candidate; the pre-registered decision uses the held-out run only.",
        "A variant that fails its acceptance rule is a null result and v1 stays the default.",
        "Synthetic origin: results show the pipeline recovers planted structure, not that real people behave this way.",
    ]
    out["limitations"] = LIMITATIONS
    return out
