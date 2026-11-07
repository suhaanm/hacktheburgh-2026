from __future__ import annotations

import json

import numpy as np
import pytest

from understudy_engine.gitanalysis.features import HABIT_IDS, HABITS, build_table, compute_features
from understudy_engine.gitanalysis.records import CommitRecord, load_records

H = 3600.0
DAY = 86400.0
T0 = 1_790_000_000 - (1_790_000_000 % 86400)       # a UTC midnight


def rec(t, cat="feature", bucket="small", tests=True, quality="ok", tz=0, parents=1, files=2, added=10, deleted=2):
    return CommitRecord(t=T0 + t, tz_min=tz, author_key="a_x", parents=parents, n_files=files, added=added, deleted=deleted, category=cat,
                        size_bucket=bucket, touches_tests=tests, risk="low", message_quality=quality)


def test_big_commits_and_vague_and_reverts():
    rs = [rec(1 * H, bucket="large"), rec(2 * H, bucket="huge"), rec(3 * H), rec(4 * H, cat="revert"), rec(5 * H, quality="vague")]
    tb = build_table(rs)
    assert tb.ratio("big_commits") == pytest.approx(2 / 5)
    assert tb.ratio("reverts") == pytest.approx(1 / 5)
    assert tb.ratio("vague_messages") == pytest.approx(1 / 5)


def test_merges_are_excluded():
    tb = build_table([rec(H), rec(2 * H, parents=2), rec(3 * H)])
    assert tb.n == 2 and tb.n_merge == 1


def test_tests_with_changes_uses_code_commits_only():
    rs = [rec(H, "feature", tests=True), rec(2 * H, "fix", tests=False), rec(3 * H, "docs", tests=False), rec(4 * H, "chore", tests=False),
          rec(5 * H, "test", tests=True), rec(6 * H, "other", tests=True), rec(7 * H, "refactor", tests=False), rec(8 * H, "revert", tests=False)]
    tb = build_table(rs)
    assert tb.den["tests_with_changes"].sum() == 3 and tb.ratio("tests_with_changes") == pytest.approx(2 / 3)


def test_fix_after_fix_window():
    rs = [rec(H, "fix"), rec(H + 30 * 60, "fix"), rec(10 * H, "fix"), rec(10 * H + 61 * 60, "fix"), rec(20 * H, "fix")]
    tb = build_table(rs, fix_window_min=60)
    # first fix is followed within 60 min; third is followed after 61 min (no); the second, fourth and fifth are not followed
    assert tb.num["fix_after_fix"].tolist() == [1, 0, 0, 0, 0] and tb.den["fix_after_fix"].sum() == 5
    assert build_table(rs, fix_window_min=90).num["fix_after_fix"].sum() == 2


def test_late_night_uses_the_authors_own_clock():
    # 03:00 UTC is 03:00 for tz 0 but 08:00 for tz +300 and 22:00 the evening before for tz -300
    assert build_table([rec(3 * H, tz=0)]).ratio("late_night") == 1.0
    assert build_table([rec(3 * H, tz=300)]).ratio("late_night") == 0.0
    assert build_table([rec(27 * H, tz=-300)]).ratio("late_night") == 0.0       # 22:00 local
    assert build_table([rec(5 * H, tz=-300)]).ratio("late_night") == 1.0        # 00:00 local
    assert build_table([rec(4.99 * H)]).ratio("late_night") == 1.0 and build_table([rec(5.0 * H)]).ratio("late_night") == 0.0


def test_streak_days_and_hours():
    rs = [rec(d * DAY + 10 * H) for d in (0, 1, 2, 5, 6)] + [rec(2 * DAY + 11 * H)]
    f = compute_features(rs)
    assert f["streak"]["longest_days"] == 3 and f["n_active_days"] == 5 and f["span_days"] == 7
    assert f["commits_by_hour"][10] == 5 and f["commits_by_hour"][11] == 1 and sum(f["commits_by_dow"]) == 6
    assert f["daily_counts"][2] == 2 and f["sessions"]["n"] == 5


def test_late_night_burst_days():
    rs = [rec(DAY + 0.5 * H), rec(DAY + 1 * H), rec(DAY + 2 * H), rec(3 * DAY + 1 * H), rec(3 * DAY + 2 * H), rec(10 * H)]
    assert compute_features(rs)["late_night"]["burst_days"] == 1


def test_features_are_numbers_only(learner_repo):
    recs, _ = load_records(learner_repo)
    f = compute_features(recs)
    json.dumps(f)

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                assert isinstance(k, str)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        else:
            assert x is None or isinstance(x, (int, float, bool)), type(x)
    walk(f)
    assert set(f["habits"]) == set(HABIT_IDS) == set(HABITS)


def test_empty_history():
    assert compute_features([])["n_commits"] == 0
    tb = build_table([])
    assert tb.n == 0 and np.isnan(tb.ratio("big_commits"))


def test_day_sums_reconcile_with_totals(learner_repo):
    tb = build_table(load_records(learner_repo)[0])
    for h in HABIT_IDS:
        n, d = tb.day_sums(h)
        assert n.sum() == tb.num[h].sum() and d.sum() == tb.den[h].sum()
