"""The evaluation harness: shape, hermetic, and the PRO-1 acceptance properties it reports. One fast replay is shared by every test."""
from __future__ import annotations

import os

import pytest

from understudy_engine.memory.paths import data_dir as real_data_dir
from understudy_engine.proactive import evaluate as E

REAL = real_data_dir() / "synthetic"
pytestmark = pytest.mark.skipif(not ((REAL / "learners" / "truth.json").exists() and (REAL / "nine-to-five" / "events.jsonl").exists()),
                                reason="run `uv run understudy synth --all` first")


@pytest.fixture(scope="module")
def report():
    before = {k: os.environ.get(k) for k in ("UNDERSTUDY_DATA_DIR", "UNDERSTUDY_HOME", "UNDERSTUDY_MOCK", "UNDERSTUDY_X_GIT", "UNDERSTUDY_X_PROACTIVE")}
    git_dir_existed = (REAL / "git").exists()
    out = E.evaluate_proactive(fast=True)
    assert {k: os.environ.get(k) for k in before} == before, "the evaluation must put the environment back"
    assert git_dir_existed or not (REAL / "git").exists(), "the evaluation must not write git cohorts into the shared data"
    return out


def test_shape_meta_and_limitations(report):
    assert {"meta", "design", "structure", "stale", "worth", "acceptance", "coverage", "limitations"} <= set(report)
    m = report["meta"]
    assert m["origin"] == "synthetic" and m["n_unit"] == "decisions" and m["n"] == report["structure"]["briefings"] > 8 and m["interval_level"] == 0.95
    ids = {x["id"] for x in report["limitations"]}
    assert {"pro-synthetic", "pro-small-n", "pro-acceptance-simulated", "pro-iterated-on-eval", "pro-truth-ours"} <= ids
    assert all(x["severity"] in ("low", "medium", "high") and x["text"] for x in report["limitations"])
    assert report["design"]["truth_revisions"] and report["design"]["first_run_numbers"]["overall"]["precision"]


def test_the_card_cap_always_holds(report):
    s = report["structure"]
    assert s["cap"] == 3 and s["cap_violations"] == 0 and s["largest_briefing"] <= 3
    assert s["cap_stress"]["cap_violations"] == 0 and s["cap_stress"]["per_kind_limit_violations"] == 0 and s["cap_stress"]["largest_briefing"] <= 3
    assert s["cap_stress"]["empty_briefings"] > 0                         # zero cards is a normal outcome


def test_no_card_fires_without_a_press(report):
    s = report["structure"]
    assert s["unprompted_fires"] == 0 and s["unprompted_queue_port_uses"] == 0 and s["unprompted_agent_spawns"] == 0
    assert s["queue_items_on_disk_after_replay"] == 0 and s["draft_files_after_replay"] == 0
    p = s["prompted_presses"]
    assert p["presses"] > 0 and p["presses_that_made_both"] == 0 and p["presses_that_made_nothing"] == 0
    assert p["queue_items"] + p["agent_runs"] == p["presses"]


def test_stale_cards_are_dropped_and_unchanged_ones_kept(report):
    st = report["stale"]
    assert st["overall"]["n"] >= 20 and st["overall"]["still_shown_after_change"] == 0
    assert st["overall"]["dropped"] == st["overall"]["n"]
    assert st["unchanged"]["kept"] == st["unchanged"]["n"] > 0
    assert {r["kind"] for r in st["rows"]} >= {"automate", "practice", "focus_block", "git_habit", "agent_result"}


def test_worth_surfacing_beats_the_baselines_and_the_placebo(report):
    w = report["worth"]
    o = w["overall"]
    assert o["precision"] is not None and o["recall"] is not None and o["opportunities"] > 0 and o["precision_ci"] and o["recall_ci"]
    base = w["baselines"]
    assert o["precision"] > base["raw_value_top3_no_checks"]["precision"] and o["precision"] > base["random_3"]["precision"]
    assert o["precision"] > base["everything_no_cap"]["precision"]
    assert o["precision"] > w["placebo_other_persons_truth"]["precision"]
    assert base["everything_no_cap"]["mean_cards_per_briefing"] > 3          # why the cap matters
    assert set(w["by_kind"]) == {"automate", "practice", "git_habit", "focus_block"} and w["points"] and w["by_person"]
    assert set(w["by_source"]) == {"persona", "learner", "git", "calendar"}
    assert set(w["sensitivity_persona_practice_truth"]) == {"level_1_or_2_only", "any_gap_below_level_4"}


def test_acceptance_estimate_improves_with_labels(report):
    rows = report["acceptance"]["rows"]
    assert rows[0]["labels"] == 0 and rows[-1]["labels"] >= 20
    assert rows[-1]["mean_abs_error"] < rows[0]["mean_abs_error"]
    assert rows[-1]["rank_agreement_tau"] > 0
    assert "generated worker" in report["acceptance"]["note"].lower()


def test_truth_is_defined_before_scoring_and_printed(report):
    t = report["design"]["truth"]
    assert set(t) == {"automate", "practice_personas", "practice_learners", "git_habit", "focus_block"}


def test_experts_are_negatives_for_the_calendar(report):
    pts = [p for p in report["worth"]["points"] if p["source"] == "calendar" and p["person"].startswith("p_exp")]
    assert pts and all(not p["truth"] for p in pts)


def test_score_function_edge_cases():
    alt = E._score({"focus_block": ["cal:auto_hold_scheduling"]}, {"focus_block": {"cal:protect_focus_block|cal:auto_hold_scheduling"}}, ("focus_block",))
    assert alt["focus_block"] == {"tp": 1, "fp": 0, "fn": 0, "opp": 1}                  # either template answers a no-focus-blocks week
    r = E._score({"practice": ["skill:a"], "automate": []}, {"practice": {"skill:*"}, "automate": {"routine:x", "routine:y", "routine:z"}}, ("practice", "automate"))
    assert r["practice"] == {"tp": 1, "fp": 0, "fn": 0, "opp": 1}
    assert r["automate"]["fn"] == 2 and r["automate"]["opp"] == 2           # capped at what the judge may show (two automations)
    quiet = E._score({"practice": ["skill:a"]}, {"practice": set()}, ("practice",))
    assert quiet["practice"] == {"tp": 0, "fp": 1, "fn": 0, "opp": 0}
