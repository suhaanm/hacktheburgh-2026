"""agent_runs (agent-core's 20-household results) and the routines table with the raw finder beside the value gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from understudy_engine.eval import build_report, schema_errors
from understudy_engine.eval.adapters import AGENT_CLEAN, AGENT_LIVE, AGENT_ROBUST
from understudy_engine.eval.render_md import render
from understudy_engine.eval.stats import wilson

REPO = Path(__file__).resolve().parents[4]
NOW = "2026-11-07T15:00:00Z"


def rep_for(root, sections=("agent_runs",)):
    return build_report(sections=list(sections), root=root, now=NOW, regenerate=False, log=lambda m: None)


def validates(rep) -> bool:
    return schema_errors(rep) == []


def household_rows(n=20, tiers_for=lambda i: [1], passed=lambda i: True):
    return [{"household_id": f"hh_{i + 1:04d}", "pass": passed(i), "tiers": tiers_for(i), "elapsed_s": 2.0} for i in range(n)]


def eval_file(label, rows, flagged=7, seed=2026, no_false=None, mean=2.0):
    n = len(rows)
    k = sum(1 for r in rows if r["pass"])
    return {"meta": {"origin": "synthetic", "n": n, "n_unit": "households", "split": None, "interval_level": 0.95, "label": label, "seed": seed, "note": "x"},
            "pass_rate": {"passed": k, "n": n, "rate": k / n, "wilson_95": wilson(k, n)},
            "check_pass_counts": {"no_false_claims": n if no_false is None else no_false}, "flagged_discrepancies": {"count": flagged, "households": []},
            "tiers_seen": sorted({t for r in rows for t in r["tiers"]}), "mean_elapsed_s": mean, "rows": rows}


@pytest.fixture()
def root(tmp_path):
    d = tmp_path / "eval"
    d.mkdir()
    (d / AGENT_CLEAN).write_text(json.dumps(eval_file("clean", household_rows())))
    (d / AGENT_ROBUST).write_text(json.dumps(eval_file("robust", household_rows(tiers_for=lambda i: [1, 2] if i % 4 != 3 else [1]), mean=4.0)))
    return tmp_path


def test_absent_files_give_a_pending_stub_that_names_the_file(tmp_path):
    s = rep_for(tmp_path)["sections"]["agent_runs"]
    assert s["status"] == "pending" and AGENT_CLEAN in s["reason"] and "agent-core" in s["reason"]
    assert validates(rep_for(tmp_path))
    ids = {e["id"] for e in rep_for(tmp_path)["sections"]["limitations"]}
    assert "eval-agent_runs-pending" in ids


def test_clean_and_robust_blocks_follow_the_contract(root):
    rep = rep_for(root)
    s = rep["sections"]["agent_runs"]
    assert validates(rep)
    assert s["clean"]["n"] == 20 and s["clean"]["pass"] == 20 and s["clean"]["mean_s"] == 2.0 and s["clean"]["tiers"] == [1]
    assert s["clean"]["wilson"] == wilson(20, 20)
    assert s["robust"]["tiers"] == [1, 2] and s["robust"]["mean_s"] == 4.0
    assert s["discrepancies_flagged"] == {"n": 7, "of": 20}
    assert s["false_claims"] == 0 and s["live"] is None
    assert s["meta"]["origin"] == "synthetic" and s["meta"]["n_unit"] == "runs" and s["meta"]["n"] == 40
    assert "compiled path" in s["meta"]["note"] and "robust and injected" in s["meta"]["note"]


def test_injected_failures_come_from_the_agent_core_plan_and_are_scored_from_the_rows(root):
    inj = rep_for(root)["sections"]["agent_runs"]["robust"]["injected"]
    assert sum(x["n"] for x in inj) == 20 and len(inj) == 4
    by = {x["injection"]: x for x in inj}
    only_503 = by["one-off 503 on site c"]
    assert only_503["n"] == 5 and only_503["pass"] == 5 and only_503["used_tier2"] == 0       # rows with i % 4 == 3 stayed on tier 1
    layout_b = by["layout change on site b"]
    assert layout_b["used_tier2"] == 5


def test_a_failed_robust_household_shows_in_its_injection_group_and_the_register(root):
    d = root / "eval"
    rows = household_rows(tiers_for=lambda i: [1, 2], passed=lambda i: i != 0)       # hh_0001 fails under "layout change on site b"
    (d / AGENT_ROBUST).write_text(json.dumps(eval_file("robust", rows)))
    rep = rep_for(root)
    s = rep["sections"]["agent_runs"]
    assert s["robust"]["pass"] == 19
    assert next(x for x in s["robust"]["injected"] if x["injection"] == "layout change on site b")["pass"] == 4
    reg = next(e for e in rep["sections"]["limitations"] if e["id"] == "eval-agent-runs-injected")
    assert "4 of 5 passed" in reg["text"]


def test_register_says_the_clean_path_is_not_the_evidence_and_that_no_real_model_ran(root):
    reg = {e["id"]: e for e in rep_for(root)["sections"]["limitations"]}
    assert "compiled path" in reg["eval-agent-runs-clean-path"]["text"] and "discriminating evidence" in reg["eval-agent-runs-clean-path"]["text"]
    assert "lower bound 84%" in reg["eval-agent-runs-clean-path"]["text"]
    assert "no real-model run" in reg["eval-agent-live-absent"]["text"]
    assert "7 of 20" in reg["eval-agent-runs-discrepancies"]["text"]


def test_robust_file_absent_leaves_the_clean_block_and_a_high_severity_entry(root):
    (root / "eval" / AGENT_ROBUST).unlink()
    rep = rep_for(root)
    assert validates(rep) and rep["sections"]["agent_runs"]["robust"] is None
    e = next(e for e in rep["sections"]["limitations"] if e["id"] == "eval-agent-runs-no-robust")
    assert e["severity"] == "high"


def test_live_block_is_labelled_real_model_small_n_with_cost(root):
    rows = household_rows(n=3, tiers_for=lambda i: [1, 3])
    live = eval_file("live", rows)
    live["cost_usd_est"] = 0.42
    (root / "eval" / AGENT_LIVE).write_text(json.dumps(live))
    rep = rep_for(root)
    s = rep["sections"]["agent_runs"]
    assert validates(rep)
    assert s["live"]["n"] == 3 and s["live"]["cost_usd_est"] == 0.42 and s["live"]["label"] == "real model" and "small n" in s["live"]["note"]
    assert s["meta"]["n"] == 43
    ids = {e["id"] for e in rep["sections"]["limitations"]}
    assert "eval-agent-live-small-n" in ids and "eval-agent-live-absent" not in ids
    md = render(rep)
    assert "Real model, small n" in md and "0.42" in md


def test_an_unreadable_live_file_does_not_take_the_section_down(root):
    (root / "eval" / AGENT_LIVE).write_text(json.dumps({"unexpected": True}))
    rep = rep_for(root)
    s = rep["sections"]["agent_runs"]
    assert "status" not in s and s["live"] is None and "could not be read" in s["live_error"] and validates(rep)


def test_false_claims_are_counted_and_flagged_high(root):
    d = root / "eval"
    (d / AGENT_CLEAN).write_text(json.dumps(eval_file("clean", household_rows(), no_false=18)))
    rep = rep_for(root)
    assert rep["sections"]["agent_runs"]["false_claims"] == 2
    assert next(e for e in rep["sections"]["limitations"] if e["id"] == "eval-agent-runs-false-claims")["severity"] == "high"


def test_markdown_has_the_caveat_and_both_run_rows(root):
    md = render(rep_for(root))
    assert "Clean path (compiled)" in md and "Failure injection" in md and "discriminating evidence" in md
    assert "layout change on site b" in md


def test_real_agent_core_files_if_present_are_read_as_they_are(synthetic_data):
    clean = REPO / "data" / "eval" / AGENT_CLEAN
    if not clean.is_file():
        pytest.skip("agent-core's results are not on this machine")
    raw = json.loads(clean.read_text())
    rep = rep_for(None)
    s = rep["sections"]["agent_runs"]
    assert validates(rep) and "status" not in s
    assert (s["clean"]["n"], s["clean"]["pass"]) == (raw["pass_rate"]["n"], raw["pass_rate"]["passed"])
    assert s["clean"]["wilson"][0] == pytest.approx(wilson(s["clean"]["pass"], s["clean"]["n"])[0], abs=0.002)


# --------------------------------------------------------------------------------------- routines: raw finder beside the gate
@pytest.fixture(scope="module")
def routines_report(synthetic_data):
    return build_report(fast=True, sections=["routines"], now=NOW, regenerate=False, log=lambda m: None)


def test_routines_rows_and_overall_carry_the_raw_finder_beside_the_value_gate(routines_report):
    s = routines_report["sections"]["routines"]
    assert validates(routines_report)
    o = s["overall"]
    raw, gate = o["raw_finder"], o["after_value_gate"]
    assert raw["clusters"] > gate["proposals"] > 0 and raw["precision"] < gate["precision"]
    assert raw["precision"] == pytest.approx(raw["correct"] / raw["clusters"], abs=0.001)
    assert gate["precision"] == o["precision"] == pytest.approx(gate["correct"] / gate["proposals"], abs=0.001)
    assert raw["clusters"] == sum(r["raw_finder"]["clusters"] for r in s["rows"])
    assert gate["proposals"] == sum(r["after_value_gate"]["proposals"] for r in s["rows"])
    for r in s["rows"]:
        assert set(r["raw_finder"]) == {"clusters", "correct", "precision", "precision_ci"} and r["after_value_gate"]["precision"] is not None
    assert "value gate" in o["precision_basis"] and "not the finder's" in s["meta"]["note"]


def test_routines_markdown_puts_both_precisions_in_one_table(routines_report):
    md = render(routines_report)
    sec = md[md.index("## Routine finder"):md.index("##", md.index("## Routine finder") + 5)]
    assert "Raw finder" in sec and "After value gate" in sec and "of the finder's accuracy" not in sec
    raw = routines_report["sections"]["routines"]["overall"]["raw_finder"]
    assert f"{raw['correct']} of {raw['clusters']} clusters are planted routines" in sec


def test_routines_raw_counts_are_taken_from_the_owner_not_typed(routines_report):
    s = copy.deepcopy(routines_report["sections"]["routines"])
    assert s["overall"]["raw_finder"]["clusters"] == sum(r["raw_finder"]["clusters"] for r in s["rows"]) > 0
