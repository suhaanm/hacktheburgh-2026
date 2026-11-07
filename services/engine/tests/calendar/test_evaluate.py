"""The calendar evaluation: structure, honest labelling and the headline numbers (fast mode)."""
from __future__ import annotations

import json

import pytest

from understudy_engine.calendar.evaluate import cluster_prf, evaluate_calendar, week_problems


@pytest.fixture(scope="module")
def report(store):
    return evaluate_calendar(fast=True, store=store)


def test_meta_limitations_and_plain_statement(report):
    m = report["meta"]
    assert m["origin"] == "synthetic" and m["n"] == 28 and m["n_unit"] == "people" and m["interval_level"] == 0.95 and "real people" in m["note"]
    assert "nothing is validated on real people" in report["statement"]
    ids = {x["id"] for x in report["limitations"]}
    assert {"cal-synthetic-only", "cal-experts-synthetic", "cal-rules-not-learned", "cal-graph-unverified", "cal-leak-claim-scope"} <= ids
    assert all(x["severity"] in ("low", "medium", "high") and x["text"] for x in report["limitations"])
    json.dumps(report)                                                                # serialisable


def test_read_path_matches_the_construction(report):
    for kind in ("ics", "json"):
        rates = report["read_path"][kind]["match_rate"]
        assert report["read_path"][kind]["person_weeks"] == 84 and min(rates.values()) == 1.0, rates
    assert report["read_path"]["ics_equals_json"] is True
    assert report["read_path"]["decoys_ignored"]["cancelled"] > 10 and report["read_path"]["decoys_ignored"]["declined"] > 10


def test_pattern_recovery_has_intervals_and_honest_misses(report):
    rows = report["pattern_recovery"]["rows"]
    assert set(rows) == {"fragmented_day", "back_to_back_day", "no_focus_blocks", "recurring_in_peak", "no_review_slot", "no_breaks", "unbuffered_external", "late_meetings"}
    assert all(r["positives"] >= 15 for r in rows.values())
    assert rows["fragmented_day"]["precision"] >= 0.9 and rows["fragmented_day"]["recall"] >= 0.95
    assert rows["recurring_in_peak"]["precision"] == 1.0 and rows["recurring_in_peak"]["recall"] == 1.0
    assert rows["late_meetings"]["recall"] < 1.0                                       # one late meeting is within the expert tolerance: missed by design
    assert rows["no_review_slot"]["precision"] < 0.9 and rows["no_review_slot"]["fp_in_weeks_with_implying_problem"] == rows["no_review_slot"]["fp"]
    assert rows["fragmented_day"]["precision_ci"] and rows["fragmented_day"]["precision_ci"][0] <= rows["fragmented_day"]["precision"] <= rows["fragmented_day"]["precision_ci"][1]
    o = report["pattern_recovery"]["overall"]
    assert 0.85 <= o["precision"] <= 1.0 and 0.9 <= o["recall"] <= 1.0


def test_week_gap_placebo_is_near_zero_and_planted_weeks_are_far(report):
    rd = report["week_gap"]["ribbon_distance"]
    assert rd["expert_placebo"]["mean"] < 0.2 and rd["planted"]["mean"] > 0.5 and rd["planted"]["mean"] > 3 * rd["expert_placebo"]["mean"]
    assert rd["planted"]["ci"][0] > rd["expert_placebo"]["ci"][1]                      # the intervals do not overlap
    assert rd["clean_control"]["mean"] < 0.2 and rd["planted_weeks_beyond_placebo_95th"] >= 0.95
    fg = report["week_gap"]["feature_gap"]
    assert fg["expert_false_alarm_rate"] < 0.1 and fg["problem_free_weeks"]["primary_feature_flags"] <= 3
    assert fg["by_problem"]["recurring_in_peak"]["recall"] == 1.0 and fg["by_problem"]["fragmented_days"]["recall"] >= 0.9


def test_suggestions_cover_the_catalogue_and_leave_experts_alone(report):
    s = report["suggestions"]
    assert s["catalogue_size"] >= 8 and s["coverage"] == 1.0 and s["templates_triggered"] == s["catalogue_size"]
    assert s["expert_false_alarm_rate"] <= 0.1 and s["expert_weeks"] == 24
    assert 0.85 <= s["overall"]["precision"] and 0.8 <= s["overall"]["recall"]
    assert set(s["rows"]) >= {"focus_shortfall", "add_review_slot", "reduce_back_to_back", "move_recurring_out_of_peak", "trim_meeting_load"}
    assert s["rows"]["reduce_back_to_back"]["recall"] < 1.0 and "by design" in s["note"]


def test_leak_canary_result_is_zero_with_a_working_control(report):
    lc = report["leak_canary"]
    assert lc["leaked"] == 0 and lc["positive_control_detected"] is True and lc["planted_tokens"] > 5000 and lc["outbound_requests"] > 5 and lc["outputs_scanned"] > 50
    assert lc["verdict"] == "no planted token appeared anywhere"


def test_cluster_prf_and_week_problems():
    units = {"a": [(True, True), (True, False)], "b": [(False, True), (False, False)], "c": [(True, True)]}
    r = cluster_prf(units, 100, 1)
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (2, 1, 1, 1) and r["precision"] == round(2 / 3, 3) and r["recall"] == round(2 / 3, 3)
    assert cluster_prf({"a": [(False, False)]}, 50, 1)["precision"] is None
    t = {"fragmented_days": [1], "no_focus_blocks": False, "back_to_back_days": [], "recurring_in_peak_h_planted": 0.0, "no_review_slot": True,
         "no_breaks": False, "unbuffered_external_days": [], "late_days": [3]}
    assert week_problems(t) == {"fragmented_days", "no_review_slot", "late_meetings"}
