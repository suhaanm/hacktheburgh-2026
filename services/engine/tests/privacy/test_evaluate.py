from __future__ import annotations

import json

import pytest

from understudy_engine.privacy import canary, egress, evaluate, ledger
from understudy_engine.privacy.purposes import CalendarSuggestionWording
from understudy_engine.privacy.testing import CanaryFlow, CapturingPort, run_flow


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
    assert 0 < h["leak_rate_upper_95"] < 0.02                      # an upper bound, never "zero risk"
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
        assert v["status"] in ("registered", "none_registered", "adapter", "error")
    uncovered = set(report["headline"]["layers_without_integration_flows"])
    assert uncovered == {l for l, v in report["layers"].items() if v["status"] in ("none_registered", "error")}
    assert any("none_registered" in l["text"] for l in report["limitations"])


def test_every_negative_control_passed_so_the_instrument_can_fail(report):
    assert report["headline"]["controls_total"] >= 8 and report["headline"]["controls_passed"] == report["headline"]["controls_total"]
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


def test_evaluation_does_not_touch_the_callers_ledger_and_restores_the_environment(tmp_path):
    import os

    before = os.environ["UNDERSTUDY_DATA_DIR"]
    ledger.append({"purpose": "t.keep", "payload": {}})
    evaluate.evaluate_privacy(seeds=[0], record=False)
    assert os.environ["UNDERSTUDY_DATA_DIR"] == before
    assert [r["purpose"] for r in ledger.read_all()] == ["t.keep"]


def test_record_true_writes_the_aggregate_the_summary_route_shows():
    r = evaluate.evaluate_privacy(seeds=[0, 1], record=True)
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
