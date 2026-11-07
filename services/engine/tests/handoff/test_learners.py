"""Learner trajectories feed a SkillTracker case by case (assisted is neutral, absence decays, only outcomes go in)."""
from __future__ import annotations

import pytest

from understudy_engine.memory.paths import data_dir
from understudy_engine.routines.learners import case_outcomes, learner_people, tracker_at

pytestmark = pytest.mark.skipif(not (data_dir() / "synthetic" / "learners" / "truth.json").exists(), reason="learner data not generated")


def test_case_outcomes_error_clean_and_assisted():
    trace = {"cogs": [["READ", 10, None], ["IDLE", 50, "idle_before_enter"], ["ENTER_HOUSEHOLD", 60, None], ["READ_RESULT", 20, None],
                      ["COPY_TO_NOTE", 30, None]],
             "deficits": [{"type": "idle_before_enter"}, {"type": "skipped_check_cliff"}],
             "coach": [{"deficit": "idle_before_enter", "shown": True, "followed": True}, {"deficit": "skipped_check_cliff", "shown": True, "followed": False}]}
    out = case_outcomes(trace)
    assert out["ENTER_HOUSEHOLD"] == "assisted"        # coached and followed: no evidence either way
    assert out["CHECK_CLIFF"] == "error"               # skipped, though never seen in the trace
    assert out["READ"] == out["READ_RESULT"] == out["COPY_TO_NOTE"] == "clean"
    assert "IDLE" not in out


def test_tracker_levels_rise_with_cases_and_absence_can_only_lower_them():
    assert learner_people() == ["p_learn01", "p_learn02", "p_learn03"]
    first = tracker_at("p_learn01", 1)
    last = tracker_at("p_learn01", None)
    assert first.case == 1 and last.case == last.n_cases == 30 and last.t_ref > first.t_ref
    lv = lambda st, cog: st.snapshot[cog]["level"]  # noqa: E731
    assert lv(first, "ENTER_HOUSEHOLD") == 1 and lv(last, "ENTER_HOUSEHOLD") == 4
    # p_learn02 is away for three days after case 15: mastery decays, levels never rise from absence
    before, after = tracker_at("p_learn02", 15), tracker_at("p_learn02", 16)
    m = lambda st: st.snapshot["READ"]["mastery"]  # noqa: E731
    assert m(after) <= m(before) + 0.2
    gap_days = (after.t_ref - before.t_ref) / 86400
    assert gap_days > 2.5
    assert tracker_at("p_learn01", 99).case == 30 and tracker_at("p_nobody") is None


def test_tracker_never_reads_the_planted_skill_curve():
    import inspect

    from understudy_engine.routines import learners

    assert "skill_curve" not in inspect.getsource(learners)
