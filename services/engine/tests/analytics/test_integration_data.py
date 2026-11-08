"""Integration with engine-data's synthetic files. Skipped when `data/synthetic` is absent
(regenerate with `uv run understudy synth --all`)."""
import json

import pytest

from understudy_engine.store import data_dir

pytestmark = pytest.mark.skipif(not (data_dir() / "synthetic" / "nine-to-five" / "events.jsonl").exists(),
                                reason="generated personas not generated")


@pytest.fixture(scope="module")
def hazard_report():
    from understudy_engine.hazard import evaluate_hazard_data
    return evaluate_hazard_data(n_boot=60)


def test_persona_episodes_load_with_planted_spells():
    from understudy_engine.hazard.data import load_persona_episodes
    eps, planted, info = load_persona_episodes()
    assert len({e.person for e in eps}) == 4 and info["n_episodes"] == len(eps) > 1000
    assert all(e.origin == "synthetic" for e in eps) and sum(len(v) for v in planted.values()) > 100
    assert all(e.cogs for e in eps[:50])


def test_hazard_on_personas_beats_both_baselines_and_is_calibrated(hazard_report):
    r = hazard_report
    assert r["data_source"].startswith("engine-data") and r["meta"]["n"] == 4 and r["meta"]["origin"] == "synthetic"
    m, b = r["model"], r["baselines"]
    assert m["log_loss"] < b["time_since_progress"]["log_loss"] < 0.6
    assert r["model_minus_tsp_log_loss_ci"][1] < 0 and r["model_minus_base_log_loss_ci"][1] < 0
    assert m["ece"] < 0.05
    # contract keys the Evidence page reads
    for k in ("log_loss", "brier", "ece", "ci_log_loss"):
        assert k in m
    assert set(r["baselines"]) == {"base_rate", "time_since_progress"}
    assert r["calibration"] and r["split"] == "leave-one-person-out" and "false_alarms_per_hour" in r
    json.dumps(r)


def test_hazard_agrees_with_planted_stuck_spells_better_than_chance(hazard_report):
    vp = hazard_report["vs_planted"]
    assert vp["auc"] > 0.6 and vp["auc"] > vp["auc_time_since_progress_proxy"]


def test_apprentice_secondary_is_labelled_as_scripted(hazard_report):
    sec = hazard_report["secondary"]
    assert sec["meta"]["n"] == 24 and any("script" in c for c in sec["caveats"])


def test_skills_on_personas_runs_and_reports_the_weak_result_honestly():
    from understudy_engine.skills.evaluate import evaluate_skills
    r = evaluate_skills()
    assert r["n"] == 4 and r["n_unit"] == "personas" and r["caveats"]
    for p in r["per_persona"].values():
        assert p["first_day_level_4"] is not None and p["first_day_level_4"] <= 3   # saturates early: reported, not hidden
        assert 0.0 <= p["final_mastery"] <= 1.0
    json.dumps(r)
