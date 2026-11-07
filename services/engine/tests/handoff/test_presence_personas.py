"""Presence on engine-data's synthetic personas (skipped when data/synthetic is not generated). Truth is used only to score."""
from __future__ import annotations

import pytest

from understudy_engine.presence.personas import PERSONAS, evaluate_presence_all, have_persona, report_section

pytestmark = pytest.mark.skipif(not all(have_persona(p) for p in PERSONAS), reason="run `uv run understudy synth --all` first")


@pytest.fixture(scope="module")
def result():
    return evaluate_presence_all()


def test_pooled_decision_rule_stays_under_the_cap_and_uses_more_idle_time_than_the_fixed_window(result):
    s = result["summary"]
    assert s["interruption_rate_rule"] <= 0.10
    assert s["interruption_rate_rule"] < s["interruption_rate_idle5"] / 3
    assert s["idle_used_rule"] > s["idle_used_fixed_overnight"]
    assert result["origin"] == "synthetic" and result["n"] == 4 and result["n_unit"] == "personas"


def test_window_forecast_beats_the_memoryless_baseline_on_every_persona(result):
    for name, p in result["personas"].items():
        w = p["by_split"]["forward"]["window"]
        assert w["model"]["brier"] < w["exponential"]["brier"], name


def test_fitted_map_recovers_the_planted_schedule_better_than_prior_and_global_rate(result):
    for name, p in result["personas"].items():
        r = p["recovery"]["pre_change"]
        assert r["rmse"] < r["rmse_prior_only"], name
        assert r["rmse"] < r["rmse_global_rate"], name


def test_report_section_has_the_contract_shape(result):
    sec = report_section(result)
    assert {"reliability", "brier", "baselines", "interruption_rate", "cap", "idle_time_used", "meta"} <= set(sec)
    assert set(sec["baselines"]) == {"fixed_overnight", "idle_5min"}
    assert all({"p_mean", "freq", "n"} == set(r) for r in sec["reliability"])
