from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.gitanalysis import synth
from understudy_engine.gitanalysis.compare import flagged_ids, habit_rows, placebo, score_detection
from understudy_engine.gitanalysis.features import HABIT_IDS, build_table
from understudy_engine.gitanalysis.records import load_records


@pytest.fixture(scope="module")
def tables(cohort):
    return {p: build_table(load_records(r)[0]) for grp in ("learners", "experts") for p, r in cohort[grp].items()}


@pytest.fixture(scope="module")
def experts(tables):
    return {p: t for p, t in tables.items() if "expert" in p}


def test_planted_habits_are_recovered(cohort, tables, experts):
    detected, planted = {}, {}
    for p, repo in cohort["learners"].items():
        rows = habit_rows(tables[p], experts, B=400, seed=1)
        detected[p] = flagged_ids(rows)
        planted[p] = set(synth.load_truth(repo)["planted"])
    s = score_detection(detected, planted)
    assert s["pairs"] == 24
    assert s["overall"]["precision"]["value"] >= 0.8, s
    assert s["overall"]["recall"]["value"] >= 0.7, s
    # the strongest, least confounded plants must all be found
    for p in ("p_git_learner_1_r200", "p_git_learner_3_r200"):
        assert planted[p] <= detected[p], (p, planted[p], detected[p])


def test_rows_have_the_contract_fields(tables, experts):
    rows = habit_rows(tables["p_git_learner_4_r200"], experts, B=200, seed=2)
    assert [r["id"] for r in rows] == list(HABIT_IDS)
    for r in rows:
        assert {"id", "label", "learner", "expert", "delta", "ci", "flagged"} <= set(r)
        assert r["ci"][0] <= r["delta"] <= r["ci"][1]


def test_placebo_is_near_zero(experts):
    pl = placebo(experts, B=200)
    assert pl["status"] == "ok" and pl["pairs"] >= 40
    assert pl["false_flags"]["value"] <= 0.12
    assert np.mean([v for v in pl["mean_abs_delta"].values() if v is not None]) < 0.08


def test_same_person_against_themselves_is_not_flagged(experts):
    names = sorted(experts)
    only_self = {names[0]: experts[names[0]], names[1]: experts[names[0]]}
    rows = habit_rows(experts[names[0]], only_self, B=200, seed=3)
    assert not flagged_ids(rows) and all(abs(r["delta"]) < 1e-9 for r in rows if r["delta"] is not None)


def test_bootstrap_is_deterministic_and_seeded(tables, experts):
    a = habit_rows(tables["p_git_learner_1_r200"], experts, B=200, seed=5)
    b = habit_rows(tables["p_git_learner_1_r200"], experts, B=200, seed=5)
    c = habit_rows(tables["p_git_learner_1_r200"], experts, B=200, seed=6)
    assert a == b and a != c


def test_too_few_commits_is_never_flagged(experts):
    tiny = build_table([])
    rows = habit_rows(tiny, experts, B=100, seed=0)
    assert not flagged_ids(rows) and {r["reason"] for r in rows} == {"too_few_commits"}


def test_score_detection_arithmetic():
    s = score_detection({"a": {"x", "y"}, "b": {"x"}}, {"a": {"x", "z"}, "b": {"x"}}, habits=("x", "y", "z"))
    o = s["overall"]
    assert (o["tp"], o["fp"], o["fn"], o["tn"]) == (2, 1, 1, 2)
    assert o["precision"]["value"] == pytest.approx(2 / 3, abs=1e-3) and o["recall"]["value"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["by_habit"]["x"]["recall"]["value"] == 1.0
