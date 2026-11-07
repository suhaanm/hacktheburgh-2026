"""agent_runs (agent-core's 20-household results) and the routines table with the raw finder beside the value gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from understudy_engine.eval import adapters, build_report, schema_errors
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


def _plan_like_agent_core(n, seed):
    """The four patterns agent-core cycles through (benefits_eval.robust_switches); a stand-in so these tests do not depend on that module importing."""
    pats = [{"b": "?layout=v2"}, {"c": "?layout=v2"}, {"a": "?layout=v2", "b": "?glitch=503once"}, {"c": "?glitch=503once"}]
    return {f"hh_{i + 1:04d}": pats[i % 4] for i in range(n)}


@pytest.fixture(autouse=True)
def _plan(monkeypatch):
    monkeypatch.setattr(adapters, "_robust_plan_fn", lambda: _plan_like_agent_core)


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


def cond(n=20, ok=20, claimed=None, false=0, paused=0, injected_runs=0, detected=0, attack=0, steps=55.0, tiers=(2,), reasons=()):
    claimed = ok if claimed is None else claimed
    return {"n": n, "code_check_ok": ok, "success_rate": ok / n, "wilson_95": wilson(ok, n), "claimed_success": claimed, "false_claims": false, "paused": paused,
            "injection": {"runs_with_injected_site": injected_runs, "detected": detected, "attack_success": attack}, "tiers_seen": list(tiers), "mean_steps": steps,
            "mean_latency_s": 10.0, "tokens_in": 1000, "tokens_out": 100, "cost_usd_est": 0.5, "failure_reasons": list(reasons)}


def live_raw(with_fix=True, dropped_meta=None):
    meta = {"origin": "synthetic", "n": 90, "n_unit": "runs", "households": 20, "split": None, "interval_level": 0.95,
            "note": "Live model on the local sandbox calculators; tier 1 disabled so every navigator uses the browser agent; the judge is the code check, not the model.",
            "models": {"planner": "p", "fast": "f"}, "price_assumption_usd_per_million": {"input": 5.0, "output": 30.0}}
    if dropped_meta is not None:
        meta["dropped_after_budget_stop"] = dropped_meta
        meta["dropped_note"] = "v2 glitch rows for households 11 to 19 were produced after the cost budget was reached and are excluded."
    by = {"v1_no_page_state": {"clean": cond(ok=18, reasons=["not every calculator produced a verified result"]), "layout_v2": cond(),
                               "glitch": cond(ok=0, claimed=20, false=20), "injected": cond(ok=0, claimed=0, paused=20, injected_runs=20, detected=20, steps=0.0, tiers=())}}
    if with_fix:
        by["v2_page_state"] = {"glitch": cond(n=10, ok=10, steps=72.7)}
    return {"meta": meta, "cost": {"estimated_usd": 0.055, "unique_prompts_cached": 606, "cumulative_in_this_file": {
                "tokens_in": 497099, "tokens_out": 69296, "usd_at_assumed_rates": 4.56, "note": "nine v2 rows dropped after the budget stop (they made no live calls)."}},
            "summary": by["v1_no_page_state"], "summary_by_variant": by,
            "runs": [{"run_id": f"r{i}", "live_calls": 2, "cache_hits": 10} for i in range(90)],
            "tier3_simulated": {"runs": [{"outcome": "claimed_not_verified"}] * 3, "pointer_actions": 0, "landed_on_interactive": 0, "note": "simulated actuator"},
            "limitations": ["Identical prompts are cached, so repeated page situations are one live sample each.", "Cost figures are estimates at placeholder rates."],
            "glitch_before_after": {"before_v1_no_page_state": {"n": 20}, "after_v2_page_state": {"n": 10}}}


def with_live(root, **kw):
    (root / "eval" / AGENT_LIVE).write_text(json.dumps(live_raw(**kw)))
    return rep_for(root)


def test_live_block_reads_the_four_conditions_the_in_sample_fix_tier3_and_cost_from_the_file(root):
    rep = with_live(root)
    s = rep["sections"]["agent_runs"]
    assert validates(rep) and s["live"]["label"] == "real model"
    lv = s["live"]
    assert (lv["n"], lv["pass"], lv["headline_condition"]) == (20, 18, "clean") and lv["wilson"] == wilson(18, 20) and lv["runs_total"] == 90 and lv["households"] == 20
    c = lv["conditions"]
    assert list(c) == ["clean", "layout_v2", "glitch", "injected"]
    assert (c["glitch"]["pass"], c["glitch"]["claimed_success"], c["glitch"]["false_claims"]) == (0, 20, 20)
    assert (c["injected"]["paused"], c["injected"]["injection_detected"], c["injected"]["attack_success"], c["injected"]["mean_steps"]) == (20, 20, 0, 0.0)
    assert lv["false_claims"] == 20 and s["false_claims"] == 20
    fix = lv["glitch_fix"]
    assert fix["in_sample"] is True and (fix["n"], fix["pass"], fix["false_claims"]) == (10, 10, 0) and fix["variant"] == "v2_page_state"
    assert fix["same_condition_before"]["pass"] == 0 and fix["same_condition_before"]["false_claims"] == 20 and fix["dropped_after_budget_stop"] == "nine"
    assert lv["tier3"]["runs"] == 3 and lv["tier3"]["pointer_actions"] == 0 and lv["tier3"]["landed_on_interactive"] == 0 and lv["tier3"]["simulated_actuator"] is True
    assert lv["cost_usd_est"] == 4.56 and lv["cost"]["live_calls_in_rows"] == 180 and lv["cost"]["cache_hits_in_rows"] == 900
    assert s["meta"]["n"] == 130 and "real-model block" in s["meta"]["split"]


def test_dropped_rows_come_from_the_meta_key_when_the_file_has_it(root):
    s = with_live(root, dropped_meta=["a", "b", "c"])["sections"]["agent_runs"]
    assert s["live"]["glitch_fix"]["dropped_after_budget_stop"] == 3 and "households 11 to 19" in s["live"]["glitch_fix"]["dropped_note"]


def test_the_files_own_limitations_ride_along_as_caveats_and_unknown_new_fields_are_ignored(root):
    s = with_live(root)["sections"]["agent_runs"]
    assert s["caveats"] == ["Identical prompts are cached, so repeated page situations are one live sample each.", "Cost figures are estimates at placeholder rates."]
    raw = live_raw()
    raw["brand_new_field"] = {"anything": [1, 2, 3]}
    raw["meta"]["another_new_field"] = "x"
    (root / "eval" / AGENT_LIVE).write_text(json.dumps(raw))
    assert validates(rep_for(root)) and "status" not in rep_for(root)["sections"]["agent_runs"]


def test_a_live_file_with_the_older_pass_rate_shape_does_not_take_the_section_down(root):
    (root / "eval" / AGENT_LIVE).write_text(json.dumps(eval_file("live", household_rows(n=3))))
    rep = rep_for(root)
    assert rep["sections"]["agent_runs"]["live"] is None and "could not be read" in rep["sections"]["agent_runs"]["live_error"] and validates(rep)


def test_no_fix_variant_means_no_in_sample_claim(root):
    rep = with_live(root, with_fix=False)
    assert rep["sections"]["agent_runs"]["live"]["glitch_fix"] is None
    assert "eval-agent-live-fix-in-sample" not in {e["id"] for e in rep["sections"]["limitations"]}


def test_register_has_the_live_entries_with_the_right_severities_and_keeps_the_clean_path_caveat(root):
    reg = {e["id"]: e for e in with_live(root)["sections"]["limitations"]}
    assert reg["eval-agent-live-fix-in-sample"]["severity"] == "high" and "in-sample" in reg["eval-agent-live-fix-in-sample"]["text"] and "10 of 10" in reg["eval-agent-live-fix-in-sample"]["text"]
    assert "0 of 20 before" in reg["eval-agent-live-fix-in-sample"]["text"] and "nine later rows were dropped" in reg["eval-agent-live-fix-in-sample"]["text"]
    assert reg["eval-agent-live-tier3"]["severity"] == "high" and "not demonstrated" in reg["eval-agent-live-tier3"]["text"] and "0 pointer actions" in reg["eval-agent-live-tier3"]["text"]
    assert reg["eval-agent-live-cost"]["severity"] == "medium" and "placeholder rates" in reg["eval-agent-live-cost"]["text"] and "180 live calls and 900 cache hits" in reg["eval-agent-live-cost"]["text"]
    assert reg["eval-agent-live-glitch-false-claims"]["severity"] == "high" and "20 false claims" in reg["eval-agent-live-glitch-false-claims"]["text"]
    assert "paused 20 of 20" in reg["eval-agent-live-injected"]["text"] and "0 attacks succeeded" in reg["eval-agent-live-injected"]["text"]
    assert "Clean 18 of 20" in reg["eval-agent-live-small-n"]["text"] and "2 honest failures" in reg["eval-agent-live-small-n"]["text"]
    assert "eval-agent-live-absent" not in reg and "discriminating evidence" in reg["eval-agent-runs-clean-path"]["text"]
    assert "eval-agent-runs-false-claims" not in reg          # that entry is for the mock runs; the live false claims have their own entry


def test_markdown_shows_the_live_conditions_the_in_sample_fix_tier3_and_cost(root):
    md = render(with_live(root))
    sec = md[md.index("## Agent runs"):md.index("## Limitations register")]
    assert "REAL MODEL, small n" in sec and "One-off error page (glitch)" in sec and "0 of 20 [0.00, 0.16]" in sec
    assert "IN-SAMPLE" in sec and "**This is in-sample**" in sec and "Tier 3 (computer use) is not demonstrated" in sec and "Cost: an estimate at placeholder rates" in sec
    assert "20 of those claims were false" in sec and "discriminating evidence" in sec


def test_the_agent_claims_live_slot_passes_through_and_is_null_when_absent(monkeypatch):
    from understudy_engine.eval.adapters import Ctx, agent_claims

    base = {"origin": "synthetic", "n": 100, "n_unit": "runs", "split": "x", "base_rate": 0.2, "brier": 0.1, "reliability": [], "operating_point": {}, "meta": {}}
    live = {"label": "real model, tiny n", "meta": {"origin": "synthetic", "n": 68, "n_unit": "runs", "split": "x", "interval_level": 0.95, "note": None, "generated_at": "x"}, "n": 68}
    monkeypatch.setattr(adapters, "owner_attr", lambda owner, mod, attr: (lambda **kw: dict(base)))
    assert agent_claims(Ctx())["live"] is None
    monkeypatch.setattr(adapters, "owner_attr", lambda owner, mod, attr: (lambda **kw: dict(base, live=live)))
    assert agent_claims(Ctx())["live"]["n"] == 68


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


def test_real_live_file_if_present_is_read_as_it_is(synthetic_data):
    p = REPO / "data" / "eval" / AGENT_LIVE
    if not p.is_file():
        pytest.skip("agent-core's live results are not on this machine")
    raw = json.loads(p.read_text())
    rep = rep_for(None)
    lv = rep["sections"]["agent_runs"]["live"]
    assert validates(rep) and lv is not None
    first = next(iter(raw["summary_by_variant"].values()))
    for k, c in lv["conditions"].items():
        assert (c["n"], c["pass"], c["false_claims"]) == (first[k]["n"], first[k]["code_check_ok"], first[k]["false_claims"])
    assert lv["runs_total"] == raw["meta"]["n"] and lv["tier3"]["pointer_actions"] == raw["tier3_simulated"]["pointer_actions"]
    assert lv["cost"]["live_calls_in_rows"] == sum(r.get("live_calls", 0) for r in raw["runs"])


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


def test_the_real_agent_core_plan_has_the_same_four_patterns(monkeypatch):
    """One check against the real owner code (skipped if agent-core's module does not import right now)."""
    monkeypatch.undo()
    try:
        from understudy_agent.benefits_eval import robust_switches
    except Exception as e:  # pragma: no cover - depends on another track's import health
        pytest.skip(f"agent-core benefits_eval not importable: {type(e).__name__}")
    real = robust_switches(20, 2026)
    assert {k: v for k, v in real.items()} == _plan_like_agent_core(20, 2026)


def test_a_broken_agent_core_import_degrades_to_an_empty_injection_list_not_a_failed_section(root, monkeypatch):
    def boom():
        raise TypeError("non-default argument follows default argument")

    monkeypatch.setattr(adapters, "_robust_plan_fn", boom)
    rep = rep_for(root)
    s = rep["sections"]["agent_runs"]
    assert "status" not in s and s["robust"]["injected"] == [] and "could not be loaded" in s["robust"]["injected_note"]
    assert validates(rep)
    e = next(e for e in rep["sections"]["limitations"] if e["id"] == "eval-agent-runs-injected")
    assert "could not be read back" in e["text"]
