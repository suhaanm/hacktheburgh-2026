import json

import numpy as np
import pytest

from understudy_engine.skills import learners as LN
from understudy_engine.store import data_dir


def trace(present=(), coach=()):
    return {"deficits": [{"type": d} for d in present], "coach": [dict(deficit=d, shown=s, followed=f, dismissed=False) for d, s, f in coach]}


def test_outcome_rule_assisted_error_clean():
    t = trace(present=["search_loop", "copy_error"], coach=[("search_loop", True, True), ("copy_error", True, False)])
    assert LN._outcome(t, "search_loop") == "assisted"          # shown and followed: neutral for the level engine
    assert LN._outcome(t, "copy_error") == "error"              # shown but not followed: the deficit still happened
    assert LN._outcome(t, "idle_before_enter") == "clean"
    assert LN._outcome(trace(present=["search_loop"]), "search_loop") == "error"


needs_data = pytest.mark.skipif(not (data_dir() / "synthetic" / "learners" / "truth.json").exists(),
                                reason="learner data not generated (uv run understudy synth --learners)")


@needs_data
def test_series_shape_and_bounds():
    s = LN.learner_series("p_learn01")
    assert [x["case"] for x in s] == list(range(1, 31))
    for x in s:
        assert x["level"] in {"L1", "L2", "L3", "L4"} and x["chip"] in {"full", "small", "dot", "gone"}
        assert set(x["mastery"]) == set(LN.COGS) and all(0 <= v <= 1 for v in x["mastery"].values())
        assert int(x["level"][1]) == min(x["level_by_cog"].values())
    assert s[0]["level"] == "L1" and s[0]["true_skill"] == 0.0
    with pytest.raises(KeyError):
        LN.learner_series("p_nobody")


@needs_data
def test_help_level_lightens_as_deficits_fade_for_every_learner():
    for p in ("p_learn01", "p_learn02", "p_learn03"):
        lv = [int(x["level"][1]) for x in LN.learner_series(p)]
        assert np.mean(lv[-10:]) > np.mean(lv[:10]) + 1.0       # heavy help early, lighter help late
        assert lv[-1] >= 3


@needs_data
def test_learner_state_matches_the_series_and_feeds_the_screens():
    s = LN.learner_series("p_learn02")
    st = LN.learner_state("p_learn02", 16)
    assert st["case"] == 16 and st["level"] == s[15]["level"] and st["chip"] == s[15]["chip"]
    for c in LN.COGS:
        assert st["mastery"][c] == pytest.approx(s[15]["mastery"][c])
        assert {"level", "mastery", "stability_days", "days_until_level_drop", "last_seen"} <= set(st["cogs"][c])
    assert LN.learner_state("p_learn01", 1)["case"] == 1
    json.dumps(st)
    with pytest.raises(KeyError):
        LN.learner_state("p_learn01", 0)


@needs_data
def test_evaluation_reports_both_the_wins_and_the_nulls():
    r = LN.evaluate_learner_skills()
    json.dumps(r)
    assert r["n"] == 3 and r["n_cases_each"] == 30 and "3 learners x 30 cases" in r["stated"]
    assert r["meta"]["n_unit"] == "personas" and r["meta"]["origin"] == "synthetic" and r["limitations"]
    for p, d in r["per_learner"].items():
        assert d["spearman_mean_mastery_vs_true_skill"] > 0.5 and len(d["spearman_ci_fisher_z"]) == 2
        # the clock-only control is reported, because a time trend alone can match a rising curve
        assert d["spearman_clock_only_vs_true_skill"] > 0.9
    ab = r["per_learner"]["p_learn02"]["absence"]
    assert ab["after_case"] == 15 and ab["days"] == 3 and "level_stepped_down_at_return" in ab
    assert r["per_learner"]["p_learn01"]["absence"] is None
    assert set(r["cross_sectional_rank_check"]) == {"case_10", "case_20", "case_30"}
    ce = r["coach_effect_on_next_case"]
    assert ce["followed"]["n"] + ce["not_followed"]["n"] > 80 and len(ce["followed"]["ci"]) == 2
    assert set(r["series"]) == {"p_learn01", "p_learn02", "p_learn03"}


@needs_data
def test_evaluate_skills_puts_personas_and_learners_side_by_side():
    from understudy_engine.skills.evaluate import evaluate_skills
    r = evaluate_skills()
    assert "per_persona" in r and "learners" in r and r["learners"]["n"] == 3
    # the saturated personas versus learners whose help level really moves
    assert all(p["first_day_level_4"] <= 3 for p in r["per_persona"].values())
    assert all(int(v["level_by_case"][0][1]) == 1 for v in r["learners"]["per_learner"].values())
    assert evaluate_skills(include_learners=False).get("learners") is None
