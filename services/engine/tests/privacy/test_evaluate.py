from __future__ import annotations

import json

import pytest

from understudy_engine.privacy import egress, evaluate, ledger
from understudy_engine.privacy.testing import CanaryFlow, run_flow


@pytest.fixture(scope="module")
def report():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("UNDERSTUDY_DATA_DIR")
        os.environ["UNDERSTUDY_DATA_DIR"] = tmp
        try:
            return evaluate.evaluate_privacy(seeds=range(3), record=False)
        finally:
            if old is None:
                os.environ.pop("UNDERSTUDY_DATA_DIR", None)
            else:
                os.environ["UNDERSTUDY_DATA_DIR"] = old


def test_report_is_json_ready_with_meta_and_honest_labels(report):
    json.dumps(report)
    m = report["meta"]
    assert m["origin"] == "synthetic" and m["n_unit"] == "tokens" and m["n"] == report["headline"]["planted"] > 100
    assert m["interval_level"] == 0.95 and "Synthetic" in m["note"] and "seeds per flow" in m["note"]
    assert {l["severity"] for l in report["limitations"]} <= {"low", "medium", "high"} and len(report["limitations"]) >= 6


def test_zero_planted_canaries_reached_the_port_in_every_flow_that_ran(report):
    h = report["headline"]
    assert h["flows"] >= 5 and h["requests"] >= 15 and h["planted"] > 0
    assert h["leaked"] == 0 and h["ledger_complete"] is True and h["all_meet_min_requests"] is True
    assert h["leak_bound_unit"] == "run" and h["runs_with_leak"] == 0 and h["flows_with_leak"] == 0
    # the headline is the PER-RUN bound (tokens planted in one run are not independent trials), with the others beside it, labelled
    assert h["leak_rate_upper_95"] == round(evaluate.upper_bound_95(0, h["runs"]), 4) and h["leak_rate_upper_95"] > 0.02
    assert h["leak_rate_upper_95_per_flow"] == round(evaluate.upper_bound_95(0, h["flows"]), 4) and h["leak_rate_upper_95_per_flow"] > h["leak_rate_upper_95"]
    assert 0 < h["leak_rate_upper_95_token_level"] < h["leak_rate_upper_95"] and "per-run bound is the headline" in h["leak_bound_note"]
    for f in report["flows"]:
        assert f["leaked"] == 0 and f["ledger_complete"] and f["ledger_lines"] == f["ledger_expected"] == f["requests"]
        assert f["flow_errors"] == []


def test_reference_and_integration_flows_are_reported_separately(report):
    ref, integ = report["by_kind"]["reference"], report["by_kind"]["integration"]
    assert ref["flows"] == 4 and {f["flow"] for f in report["flows"] if f["kind"] == "reference"} == {
        "reference.calendar_suggestion_wording", "reference.git_habit_wording", "reference.briefing_card_wording", "reference.digest_meta"}
    assert ref["flows"] + integ["flows"] == report["headline"]["flows"]


def test_layers_without_integration_flows_are_listed_not_counted_as_passed(report):
    for layer, v in report["layers"].items():
        assert v["status"] in ("registered", "none_registered", "adapter", "error", "not_applicable", "pure_compute", "not_present")
    uncovered = set(report["headline"]["layers_without_integration_flows"])
    assert uncovered == {l for l, v in report["layers"].items() if v["status"] in ("none_registered", "error")}
    assert any("none_registered" in l["text"] for l in report["limitations"])


def test_logs_audit_and_queue_were_scanned_and_clean_for_every_flow(report):
    h = report["headline"]
    assert h["artifact_leaked"] == 0 and h["artifact_files_scanned"] >= h["flows"]       # at least the ledger file each run
    assert all(f["artifact_leaked"] == 0 and f["artifact_files_scanned"] > 0 for f in report["flows"])


def test_every_negative_control_passed_so_the_instrument_can_fail(report):
    names = " ".join(c["name"] for c in report["negative_controls"])
    assert "log record" in names and "approval-queue item" in names
    assert report["headline"]["controls_total"] >= 10 and report["headline"]["controls_passed"] == report["headline"]["controls_total"]
    assert all(c["passed"] for c in report["negative_controls"]), [c for c in report["negative_controls"] if not c["passed"]]


def test_bucketing_property_sweeps_have_no_failures_and_real_case_counts(report):
    assert report["headline"]["bucketing_failures"] == 0 and report["headline"]["bucketing_cases"] > 500_000
    rules = {r["rule"] for r in report["bucketing"]}
    assert {"count", "time_15min", "duration_5min", "ratio_10pct", "hours_5min", "attendees"} <= rules


def test_backstop_corpus_catches_every_must_catch_shape_with_no_false_positives(report):
    b = report["backstop"]
    assert b["must_catch_caught"] == b["must_catch_total"] > 20
    assert b["ordinary_false_positives"] == 0 and b["hashed_id_false_positives"] == 0 and b["sensitive_snake_case_names_matched"] is True


def test_static_guard_result_is_included(report):
    g = report["static_guard"]
    assert g["files"] > 0 and g["violations"] == [] and "calendar" in g["scanned_dirs"]
    assert g["runtime"]["violations"] == [] and g["runtime"]["files"] >= 0
    assert report["headline"]["static_guard_violations"] == 0


def test_evaluation_does_not_touch_the_callers_ledger_and_restores_the_environment(tmp_path):
    import os

    before = os.environ["UNDERSTUDY_DATA_DIR"]
    ledger.append({"purpose": "t.keep", "payload": {}})
    evaluate.evaluate_privacy(seeds=[0], record=False, discover=False)
    assert os.environ["UNDERSTUDY_DATA_DIR"] == before
    assert [r["purpose"] for r in ledger.read_all()] == ["t.keep"]


def test_record_true_writes_the_aggregate_the_summary_route_shows():
    r = evaluate.evaluate_privacy(seeds=[0, 1], record=True, discover=False)
    c = ledger.canary_summary()
    assert c["runs"] == r["headline"]["flows"] and c["planted"] == r["headline"]["planted"] and c["leaked"] == 0
    assert ledger.summary()["canary"]["planted"] == r["headline"]["planted"]


def test_a_leaky_extra_flow_shows_up_as_leaks_and_a_missing_ledger_line():
    def run(fx, port):
        port.plan([{"role": "user", "content": fx["events"][0]["title"]}], None)

    leaky = CanaryFlow("test.leaky", evaluate._cal_fixture, run, layer="calendar", kind="integration", min_requests=0)
    r = evaluate.evaluate_privacy(seeds=[0, 1], record=False, extra_flows=[leaky], discover=False)
    row = next(f for f in r["flows"] if f["flow"] == "test.leaky")
    assert row["leaked"] == 2 and row["ledger_complete"] is False and "meeting_title" in row["leaked_kinds"]
    assert r["headline"]["leaked"] == 2 and r["by_kind"]["integration"]["leaked"] == 2


def test_a_flow_that_makes_fewer_requests_than_it_promised_is_flagged():
    quiet = CanaryFlow("test.quiet", evaluate._cal_fixture, lambda fx, port: None, min_requests=1)
    r = evaluate.evaluate_privacy(seeds=[0], record=False, extra_flows=[quiet], discover=False)
    row = next(f for f in r["flows"] if f["flow"] == "test.quiet")
    assert row["meets_min_requests"] is False and r["headline"]["all_meet_min_requests"] is False


def test_layer_supplied_canary_flows_are_discovered(monkeypatch):
    import sys
    import types

    mod = types.ModuleType("understudy_engine.calendar.canary_flows")
    mod.FLOWS = [CanaryFlow("calendar.fake", evaluate._cal_fixture, evaluate._cal_run, layer="calendar")]
    monkeypatch.setitem(sys.modules, "understudy_engine.calendar.canary_flows", mod)
    flows, layers = evaluate.discover_flows()
    assert any(f.name == "calendar.fake" for f in flows) and layers["calendar"]["status"] == "registered"


def test_a_flow_that_raises_is_recorded_as_an_error_not_a_pass():
    def run(fx, port):
        egress.send("calendar.suggestion_wording", dict(template="not a template", role="programmer", risk="low", learner={}, expert={}), port=port)

    r = run_flow(CanaryFlow("t.raises", evaluate._cal_fixture, run, min_requests=0), seed=0)
    assert r.error == "PayloadRejected" and r.requests == 0 and r.leaked == 0


def test_upper_bound_matches_the_rule_of_three_and_handles_edges():
    assert evaluate.upper_bound_95(0, 100) == pytest.approx(0.0295, abs=0.001)
    assert evaluate.upper_bound_95(0, 752) == pytest.approx(0.00398, abs=0.0002)
    assert evaluate.upper_bound_95(5, 100) > 0.05 and evaluate.upper_bound_95(0, 0) == 1.0 and evaluate.upper_bound_95(3, 3) == 1.0


def test_a_layer_may_declare_it_has_no_model_path_and_is_then_not_counted_as_uncovered(monkeypatch):
    import sys
    import types

    mod = types.ModuleType("understudy_engine.plugins.canary_flows")
    mod.FLOWS = []
    mod.NOT_APPLICABLE = "source plugins only read; nothing is sent to a model"
    monkeypatch.setitem(sys.modules, "understudy_engine.plugins.canary_flows", mod)
    flows, layers = evaluate.discover_flows()
    assert layers["plugins"]["status"] == "not_applicable" and "nothing is sent" in layers["plugins"]["note"]
    r = evaluate.evaluate_privacy(seeds=[0], record=False)
    assert "plugins" not in r["headline"]["layers_without_integration_flows"] and r["layers"]["plugins"]["status"] == "not_applicable"


def test_the_scan_is_shown_to_be_able_to_see_rewrites_and_not_to_cry_wolf(report):
    sens, spec = report["scan_sensitivity"], report["scan_specificity"]
    assert sens["cases"] >= 1000 and sens["detected"] == sens["cases"]
    assert all(v["detected"] == v["cases"] for v in sens["by_rewrite"].values()) and "paraphrase" in sens["not_tested"]
    assert spec["clean_bodies"] >= 3000 and spec["false_positives"] == 0
    assert report["headline"]["scan_detects_known_rewrites"] == f"{sens['detected']}/{sens['cases']}" and report["headline"]["scan_false_positives"] == 0


# --------------------------------------------------------------------------- REQ-5: the image block
def test_the_report_has_an_image_block_with_runs_zero_leaks_and_blocked_by_reason(report):
    im = report["image"]
    assert im["runs"] >= 80 and im["seeds"] >= 8 and im["frames_planted"] == im["seeds"]
    assert im["leaks"] == 0 and im["leak_details"] == []
    assert im["blocked_by_reason"] == {"denylisted_app": im["seeds"], "no_consent": im["seeds"], "secure_input": im["seeds"], "unattended": im["seeds"]}
    assert im["sent"] == 2 * im["seeds"] and im["provider_failed"] == im["seeds"] and im["output_rejected"] == im["seeds"]
    h = report["headline"]
    assert h["image_runs"] == im["runs"] and h["image_leaks"] == 0 and h["image_blocked_by_reason"] == im["blocked_by_reason"]


def test_unattended_real_screen_never_reached_a_provider_and_a_block_never_called_one(report):
    im = report["image"]
    assert im["unattended_real_screen"] == {"attempts": im["seeds"], "reached_a_provider": 0} and im["provider_calls_after_a_block"] == 0
    assert im["gate"]["cases"] == 33 and im["gate"]["failures"] == 0


def test_every_image_call_has_exactly_one_row_with_only_allowed_fields_and_nothing_was_left_in_temp_or_logs(report):
    im = report["image"]
    assert im["ledger"]["one_row_per_call"] is True and im["ledger"]["rows_with_disallowed_fields"] == 0
    assert im["ledger"]["physical_lines"] > im["ledger"]["image_rows"]             # image + image_result lines, merged on read
    assert im["scanned"]["temp_dir"] == "empty after every seed" and im["scanned"]["log_records"] >= im["seeds"] and im["scanned"]["error_messages"] > 0


def test_image_controls_prove_the_residue_scan_and_the_gates_can_fail(report):
    c = report["image"]["controls"]
    assert len(c) >= 7 and all(x["passed"] for x in c), [x for x in c if not x["passed"]]


def test_image_static_guard_and_caveats_are_reported_with_the_sandbox_convention_stated(report):
    g = report["image"]["static_guard"]
    assert g["provider_endpoint_violations"] == [] and g["sandbox_claim_violations"] == [] and g["provider_endpoint_files"] > 100
    assert isinstance(g["ts_provider_references"], list)
    ids = {c["id"]: c for c in report["image"]["caveats"]}
    assert {"img_raw_by_nature", "img_sandbox_convention", "img_gate_is_caller_truth", "img_memory_best_effort"} <= set(ids)
    assert "BY CONVENTION ONLY" in ids["img_sandbox_convention"]["text"] and "ENFORCED" in ids["img_sandbox_convention"]["text"]
    assert {c["id"] for c in report["image"]["caveats"]} <= {l["id"] for l in report["limitations"]}


def test_image_evaluation_runs_alone_and_does_not_touch_the_callers_ledger():
    import os

    before = os.environ["UNDERSTUDY_DATA_DIR"]
    ledger.append({"purpose": "t.keep", "payload": {}})
    r = evaluate.image_evaluation(seeds=[0, 1])
    assert r["leaks"] == 0 and r["runs"] == 22 and os.environ["UNDERSTUDY_DATA_DIR"] == before
    assert [x["purpose"] for x in ledger.read_all()] == ["t.keep"]


# --------------------------------------------------------------------------- the coverage table for the Evidence map
def test_coverage_has_one_row_per_guarded_layer_plus_the_agent_runtime(report):
    from understudy_engine.privacy import guard

    cov = {c["layer"]: c for c in report["coverage"]}
    assert list(cov)[: len(guard.GUARDED_DIRS)] == list(guard.GUARDED_DIRS) and "agent_runtime" in cov and "agent_service" in cov
    for c in cov.values():
        assert {"layer", "present", "pure_compute", "files_scanned", "static_guard_violations", "canary_flow", "flows", "registered_by_layer",
                "real_code_flow", "runs", "requests", "planted", "leaked", "image_flows", "image_runs", "image_residue", "note"} <= set(c)
        assert c["canary_flow"] in ("registered", "adapter", "none_registered", "not_applicable", "pure_compute", "not_present", "error", "not_checked",
                                    "static_guard_only")
        assert c["static_guard_violations"] == 0 and c["leaked"] == 0 and c["image_residue"] == 0
    assert cov["mlv2"]["pure_compute"] and cov["personas_v2"]["pure_compute"]


def test_coverage_counts_real_code_flows_and_lists_the_gaps_without_calling_them_covered(report):
    cov = {c["layer"]: c for c in report["coverage"]}
    s = report["headline"]["coverage_summary"]
    for layer, c in cov.items():
        if c["canary_flow"] in ("none_registered", "error", "not_checked"):
            assert layer in s["gaps"] and c["real_code_flow"] is False
        if c["real_code_flow"]:
            assert layer in s["with_real_code_flow"] and (c["flows"] or c["image_flows"])
            assert (c["planted"] > 0 and c["requests"] > 0) or c["image_runs"] > 0
    assert set(s["pure_compute"]) == {l for l, c in cov.items() if c["canary_flow"] == "pure_compute"}
    assert cov["calendar"]["real_code_flow"] is True and cov["localmodel"]["real_code_flow"] is True
    assert report["headline"]["layers_without_integration_flows"] == [l for l in report["layers"] if report["layers"][l]["status"] in ("none_registered", "error")]


def test_a_layer_whose_directory_does_not_exist_yet_is_not_present_not_a_gap(monkeypatch):
    from understudy_engine.privacy import guard

    monkeypatch.setattr(guard, "GUARDED_DIRS", guard.GUARDED_DIRS + ("not_written_yet",))
    monkeypatch.setattr(evaluate, "LAYERS", guard.GUARDED_DIRS)
    r = evaluate.evaluate_privacy(seeds=[0], record=False, discover=True)
    row = next(c for c in r["coverage"] if c["layer"] == "not_written_yet")
    assert row["canary_flow"] == "not_present" and row["present"] is False and "not_written_yet" in r["headline"]["coverage_summary"]["not_present"]
    assert "not_written_yet" not in r["headline"]["coverage_summary"]["gaps"]


def test_layer_supplied_image_flows_are_run_and_a_leaky_one_shows_residue_in_the_coverage_row(monkeypatch):
    import sys
    import types

    from understudy_engine.privacy.egress import send_image
    from understudy_engine.privacy.image import ImageGate
    from understudy_engine.privacy.testing import ImageCanaryFlow

    def clean(pi, port):
        send_image("glance.screen_state", pi.safe_image(), {"mode": "triggered", "trigger": "stuck", "strict": False}, gate=ImageGate(True, False, False, False), port=port)

    def leaky(pi, port):
        import base64
        import logging
        clean(pi, port)
        logging.getLogger("awareness").info("frame %s", base64.b64encode(pi.data).decode())

    mod = types.ModuleType("understudy_engine.cue.canary_flows")
    mod.FLOWS = []
    mod.IMAGE_FLOWS = [ImageCanaryFlow("cue.clean", clean, "cue"), ImageCanaryFlow("cue.leaky", leaky, "cue")]
    monkeypatch.setitem(sys.modules, "understudy_engine.cue.canary_flows", mod)
    r = evaluate.evaluate_privacy(seeds=[0, 1], record=False, discover=True)
    row = next(c for c in r["coverage"] if c["layer"] == "cue")
    assert row["canary_flow"] == "registered" and row["real_code_flow"] is True and set(row["image_flows"]) == {"cue.clean", "cue.leaky"}
    assert row["image_runs"] == 4 and row["image_residue"] >= 2
    lf = {f["flow"]: f for f in r["image"]["layer_flows"]}
    assert lf["cue.clean"]["residue"] == 0 and lf["cue.leaky"]["residue"] >= 2
    assert r["image"]["leaks"] >= 2 and r["headline"]["image_leaks"] >= 2


# --------------------------------------------------------------------------- the hardened guard in the report
def test_the_report_shows_the_guard_catching_its_evasion_battery_and_not_crying_wolf(report):
    b = report["static_guard"]["battery"]
    assert b["evasion_cases"] >= 130 and b["flagged"] == b["evasion_cases"] and b["missed"] == []
    assert b["runtime_missed"] == [] and b["clean_controls"] >= 20 and b["clean_flagged"] == 0
    assert b["sources"] == {"reviewer_layer": 21, "reviewer_agent": 5, "reviewer_round2": 20, "further": b["sources"]["further"]}
    assert "STATIC NET FOR HONEST MISTAKES" in b["limits"] and "egress.send" in b["limits"] and "run time" in b["limits"]
    assert report["headline"]["static_guard_evasions_flagged"] == f"{b['flagged']}/{b['evasion_cases']}" and report["headline"]["static_guard_clean_flagged"] == 0


def test_the_report_scans_the_agent_service_and_lists_pending_exceptions_honestly(report):
    a = report["static_guard"]["agent"]
    assert a["files"] > 40 and a["violations"] == [] and "understudy_agent/handoff_io.py" in a["reviewed_entries"]
    pend = {p["file"]: p for p in report["static_guard"]["pending_exceptions"]}
    assert "understudy_agent/voice/tts.py" in pend and report["headline"]["pending_exceptions"] == len(pend) >= 1
    assert report["headline"]["static_guard_violations"] == 0


def test_the_coverage_note_for_the_agent_service_states_the_reviewed_entries_pending_exceptions_and_the_legacy_ts_gap(report):
    cov = {c["layer"]: c for c in report["coverage"]}
    a = cov["agent_service"]
    assert a["canary_flow"] == "static_guard_only" and a["real_code_flow"] is False and a["files_scanned"] > 40 and a["static_guard_violations"] == 0
    assert "reviewed entry" in a["note"] and "pending" in a["note"] and "/privacy/ledger/direct" in a["note"] and "loopback" in a["note"]
    assert "agent_service" not in report["headline"]["coverage_summary"]["gaps"] and "agent_service" in report["headline"]["coverage_summary"]["static_guard_only"]
    assert "children have no network" in cov["agent_runtime"]["note"]


def test_the_leak_bound_is_per_run_in_the_headline_with_the_honest_numbers_for_80_runs_and_10_flows():
    assert evaluate.upper_bound_95(0, 80) == pytest.approx(0.0368, abs=0.0005)         # about 3.7%
    assert evaluate.upper_bound_95(0, 10) == pytest.approx(0.2589, abs=0.0005)         # about 26%
    assert evaluate.upper_bound_95(0, 11_456) < 0.0003                                  # the token-level figure the review called misleading


def test_the_limitation_explains_the_unit_and_a_leaky_flow_moves_the_per_run_figures(report):
    lim = {l["id"]: l for l in report["limitations"]}
    assert lim["prv_leak_bound_unit"]["severity"] == "high" and "per RUN" in lim["prv_leak_bound_unit"]["text"] and "3.7%" in lim["prv_leak_bound_unit"]["text"]
    assert report["image"]["leak_bound_unit"] == "run" and report["image"]["leak_rate_upper_95_per_run"] > 0.02

    def run(fx, port):
        port.plan([{"role": "user", "content": fx["events"][0]["title"]}], None)

    leaky = CanaryFlow("test.leaky_bound", evaluate._cal_fixture, run, layer="calendar", kind="integration", min_requests=0)
    r = evaluate.evaluate_privacy(seeds=[0, 1, 2, 3], record=False, extra_flows=[leaky], discover=False)
    row = next(f for f in r["flows"] if f["flow"] == "test.leaky_bound")
    assert row["runs_with_leak"] == 4 and row["leak_rate_upper_95"] == 1.0 or row["leak_rate_upper_95"] > 0.5
    assert r["headline"]["runs_with_leak"] == 4 and r["headline"]["flows_with_leak"] == 1
    assert r["headline"]["leak_rate_upper_95"] > 0.03


def test_coverage_lists_the_agent_context_package_as_pure_compute_when_it_exists_and_not_present_otherwise(report):
    cov = {c["layer"]: c for c in report["coverage"]}
    assert "context" in cov and cov["context"]["pure_compute"] is True and cov["context"]["static_guard_violations"] == 0
    assert cov["context"]["canary_flow"] in ("pure_compute", "not_present") and "attention" in cov
    assert cov["attention"]["canary_flow"] in ("pure_compute", "not_present")
    assert cov["context"]["canary_flow"] != "none_registered" and "context" not in report["headline"]["coverage_summary"]["gaps"]
