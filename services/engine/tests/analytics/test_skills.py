import math

import numpy as np
import pytest

from understudy_engine.skills import levels as L
from understudy_engine.skills import tracing as T
from understudy_engine.skills.tracker import SkillTracker, skill_gate

DAY = 86400.0
T0 = 1_793_000_000.0


# ---- an independent reference of the written spec (COA-3), shaped differently from the engine ----
def ref_level(outcomes):
    """Replays the whole history: 3 clean in a row up, 2 errors in the last 5 counted outcomes down,
    assisted runs ignored, a change clears the history."""
    level, hist = 1, []
    for o in outcomes:
        if o == "assisted":
            continue
        hist.append(o)
        if o == "clean" and hist[-3:] == ["clean"] * 3 and level < 4:
            level, hist = level + 1, []
        elif o == "error" and hist[-5:].count("error") >= 2 and level > 1:
            level, hist = level - 1, []
    return level


C, E, A = "clean", "error", "assisted"
SHARED_CASES = [
    ([C, C, C], 2),
    ([C, C, A, C], 2),                      # assisted does not break the streak
    ([C, C, E, C, C], 1),                   # an error does
    ([A, A, A, A, A, E, E], 1),             # floor
    ([E, C, C, C], 2),
    ([C, C, C, E, E], 1),                   # promoted, then two errors in a fresh window
    ([C, C, C, E, C, C, E], 1),             # L2: E C C E -> window has 2 errors -> down
    ([C, C, C, C, E], 2),                   # 1 error in the new window: stays
    ([C] * 12, 4),
    ([C] * 12 + [E], 4),
    ([C] * 12 + [E, E], 3),
    ([C] * 12 + [E, C, C, C, E], 3),        # at the ceiling the window keeps rolling: E C C C E has two errors
    ([E, E, E, C, C, C, C, C, C, E, A, E], 2),
    ([], 1),
]


@pytest.mark.parametrize("seq,expected", SHARED_CASES)
def test_engine_and_reference_agree_with_the_written_spec(seq, expected):
    assert L.run_outcomes(seq).level == expected
    assert ref_level(seq) == expected


def test_engine_matches_reference_on_random_histories():
    rng = np.random.default_rng(0)
    for _ in range(2000):
        n = int(rng.integers(0, 40))
        seq = [str(rng.choice([C, C, C, E, A])) for _ in range(n)]
        assert L.run_outcomes(seq).level == ref_level(seq), seq


def test_assisted_runs_are_neutral_everywhere():
    rng = np.random.default_rng(1)
    for _ in range(300):
        base = [str(rng.choice([C, E])) for _ in range(int(rng.integers(0, 25)))]
        sprinkled = []
        for o in base:
            sprinkled.extend([A] * int(rng.integers(0, 3)))
            sprinkled.append(o)
        a, b = L.run_outcomes(base), L.run_outcomes(sprinkled)
        assert (a.level, a.streak, a.recent) == (b.level, b.streak, b.recent)


def test_level_is_bounded_and_changes_by_at_most_one():
    rng = np.random.default_rng(2)
    s = L.LevelState()
    for _ in range(3000):
        s2, ch = L.apply_outcome(s, str(rng.choice([C, E, A])))
        assert 1 <= s2.level <= 4 and abs(ch) <= 1 and s2.level - s.level == ch
        s = s2


def test_unknown_outcome_rejected():
    with pytest.raises(ValueError):
        L.apply_outcome(L.LevelState(), "fine")  # type: ignore[arg-type]


def test_cap_for_mastery_thresholds():
    assert [L.cap_for_mastery(m) for m in (0.0, 0.39, 0.40, 0.64, 0.65, 0.84, 0.85, 1.0)] == [1, 1, 2, 2, 3, 3, 4, 4]


# ---- tracing ----
def test_mastery_rises_with_clean_falls_with_error_and_assisted_is_no_evidence():
    s = T.CogMastery()
    s1 = T.observe(s, C, T0)
    s2 = T.observe(s1, C, T0 + 60)
    assert s.m < s1.m < s2.m <= 1
    e = T.observe(s2, E, T0 + 120)
    assert e.m < s2.m
    a = T.observe(s2, A, T0 + 120)
    assert a.m == pytest.approx(T.decayed(s2, T0 + 120))  # only time has acted
    assert a.n_clean == s2.n_clean and a.stability_days == s2.stability_days


def test_mastery_decays_with_absence_toward_the_floor_and_never_below():
    s = T.CogMastery()
    for i in range(6):
        s = T.observe(s, C, T0 + i * 60)
    t_last = T0 + 5 * 60
    prev = s.m
    for d in (1, 3, 7, 14, 30, 90, 365, 3650):
        m = T.decayed(s, t_last + d * DAY)
        assert T.DEFAULT.floor <= m < prev + 1e-12
        prev = m
    assert T.decayed(s, t_last + 3650 * DAY) == pytest.approx(T.DEFAULT.floor, abs=1e-3)
    assert T.decayed(s, t_last - 100) == s.m  # no negative time travel


def test_practice_slows_forgetting():
    fresh = T.observe(T.CogMastery(), C, T0)
    for _ in range(4):
        fresh = T.observe(fresh, C, T0)
    practised = fresh
    one_and_done = T.observe(T.CogMastery(), C, T0)
    # same absence: the practised cog keeps more of what it had (relative to its own starting mastery)
    d = 20 * DAY
    keep_p = (T.decayed(practised, T0 + d) - T.DEFAULT.floor) / (practised.m - T.DEFAULT.floor)
    keep_o = (T.decayed(one_and_done, T0 + d) - T.DEFAULT.floor) / (one_and_done.m - T.DEFAULT.floor)
    assert keep_p > keep_o
    assert practised.stability_days > one_and_done.stability_days


def test_assisted_reanchor_composes_decay_exactly():
    s = T.observe(T.observe(T.CogMastery(), C, T0), C, T0 + 10)
    direct = T.decayed(s, T0 + 10 + 9 * DAY)
    stepped = T.observe(T.observe(s, A, T0 + 10 + 4 * DAY), A, T0 + 10 + 9 * DAY)
    assert stepped.m == pytest.approx(direct)


def test_days_until_is_the_inverse_of_decay():
    s = T.CogMastery()
    for i in range(7):
        s = T.observe(s, C, T0 + i)
    now = T0 + 7
    d = T.days_until(s, 0.65, now)
    assert d > 0 and T.decayed(s, now + d * DAY) == pytest.approx(0.65, abs=1e-6)
    assert T.days_until(s, 0.99999, now) == 0.0
    assert math.isinf(T.days_until(s, T.DEFAULT.floor, now))


def test_mastery_stays_in_unit_interval_under_any_history():
    rng = np.random.default_rng(3)
    for _ in range(100):
        s, t = T.CogMastery(), T0
        for _ in range(60):
            t += float(rng.exponential(2 * DAY))
            s = T.observe(s, str(rng.choice([C, E, A])), t)
            assert 0.0 <= s.m <= 1.0 and T.DEFAULT.s_min_days <= s.stability_days <= T.DEFAULT.s_max_days


# ---- tracker: mastery feeds, the level engine decides ----
def practise(tr, cog, n, t0, gap_days=1.0):
    t = t0
    for _ in range(n):
        tr.observe(cog, C, t)
        t += gap_days * DAY
    return t - gap_days * DAY


def test_steady_practice_is_never_capped_by_mastery():
    tr = SkillTracker()
    t = T0
    for _ in range(40):
        info = tr.observe("CHECK", C, t)
        assert info["decay_change"] == 0
        t += 3 * 3600
    assert tr.level_of("CHECK", t) == 4


def test_absence_lowers_the_level_but_never_raises_it():
    tr = SkillTracker()
    last = practise(tr, "ENTER", 9, T0, gap_days=0.5)
    assert tr.level_of("ENTER", last) == 4
    levels = [tr.level_of("ENTER", last + d * DAY) for d in (0, 5, 15, 40, 120, 600)]
    assert levels[0] == 4 and levels == sorted(levels, reverse=True)
    assert levels[-1] == 1
    # snapshot must not mutate
    assert tr.level_of("ENTER", last) == 4


def test_returning_after_absence_starts_from_the_decayed_level():
    tr = SkillTracker()
    last = practise(tr, "ENTER", 9, T0, gap_days=0.5)
    back = last + 120 * DAY
    info = tr.observe("ENTER", C, back)
    assert info["decay_change"] < 0 and info["level"] <= 2
    # coming back with clean runs rebuilds
    t = back
    for _ in range(9):
        t += 3600
        tr.observe("ENTER", C, t)
    assert tr.level_of("ENTER", t) >= 3


def test_skill_gate_requires_level_4_on_every_cog():
    tr = SkillTracker()
    last = practise(tr, "ENTER", 9, T0, gap_days=0.2)
    last = max(last, practise(tr, "CHECK", 3, T0, gap_days=0.2))
    g = skill_gate(tr, ["ENTER", "CHECK"], last)
    assert not g["eligible"] and "CHECK at L2" in g["reason"]
    assert skill_gate(tr, ["ENTER"], last)["eligible"]
    assert skill_gate(tr, ["ENTER", "CHECK"], last, learning_relevant=False)["eligible"]
    assert not skill_gate(tr, ["NEVER_SEEN"], last)["eligible"]


def test_coach_state_uses_the_lowest_level_among_the_cogs():
    tr = SkillTracker()
    last = practise(tr, "ENTER", 9, T0, gap_days=0.2)
    practise(tr, "CHECK", 3, T0, gap_days=0.2)
    cs = tr.coach_state(["ENTER", "CHECK"], last)
    assert cs["level"] == "L2" and cs["chip"] == "small"
    assert set(cs["mastery"]) == {"ENTER", "CHECK"} and all(0 <= v <= 1 for v in cs["mastery"].values())
    assert tr.coach_state([], last)["level"] == "L1"
