"""Commit-habit features per person and repository. Numbers and enums only (PRV-4).

``build_table`` turns a person's ``CommitRecord`` list into numpy arrays; ``compute_features`` summarises them into a
JSON-able dict; ``HABITS`` defines the six habit measures that ``compare`` bootstraps and ``suggest`` acts on. Every habit
is a ratio ``sum(num) / sum(den)`` over commits, so a day-block bootstrap needs only per-day sums.

Habit definitions (merges are excluded everywhere; "code commit" = category feature, fix or other, i.e. not test, docs, chore, refactor or revert):

    big_commits         commits over 250 lines changed (size bucket large or huge) / all commits
    tests_with_changes  code commits that also touch a test file / code commits           (lower is the habit)
    fix_after_fix       fix commits followed by another fix within ``fix_window_min`` / fix commits
    reverts             revert commits / all commits
    vague_messages      commits whose message digest is "vague" / all commits
    late_night          commits made between 00:00 and 05:00 in the author's own time zone / all commits

Time zone: hours and days use the commit's own recorded UTC offset, so "late night" means the author's night.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .records import CommitRecord
from .vocab import CATEGORIES, GIANT_BUCKETS, SIZE_BUCKETS

FIX_WINDOW_MIN = 60
LATE_START_H, LATE_END_H = 0, 5      # [0, 5)
SESSION_GAP_MIN = 90
CODE_CATEGORIES = frozenset({"feature", "fix", "other"})     # "other": no keyword matched, and not a test, docs or chore path


@dataclass(frozen=True)
class HabitDef:
    id: str
    label: str
    bad: int                 # +1: a higher value than the experts is the habit; -1: a lower value is
    min_delta: float         # smallest learner-minus-expert difference (in the bad direction) worth a suggestion
    unit: str = "share"
    num_label: str = ""      # how the numbers are described in suggestion text
    den_label: str = ""


HABITS: dict[str, HabitDef] = {h.id: h for h in (
    HabitDef("big_commits", "Large commits (over 250 lines)", +1, 0.10, num_label="commits over 250 lines", den_label="commits"),
    HabitDef("tests_with_changes", "Feature and fix commits that touch tests", -1, 0.20, num_label="feature or fix commits that touched a test", den_label="feature and fix commits"),
    HabitDef("fix_after_fix", "Fixes followed by another fix within an hour", +1, 0.15, num_label="fixes followed by another fix within an hour", den_label="fix commits"),
    HabitDef("reverts", "Reverted work", +1, 0.03, num_label="reverts", den_label="commits"),
    HabitDef("vague_messages", "Vague commit messages", +1, 0.15, num_label="vague messages", den_label="commits"),
    HabitDef("late_night", "Commits between midnight and 5am", +1, 0.06, num_label="commits between midnight and 5am", den_label="commits"),
)}
HABIT_IDS = tuple(HABITS)


@dataclass
class CommitTable:
    """Per-commit arrays for one person (merges removed), oldest first."""

    n: int
    n_merge: int
    t: np.ndarray
    day: np.ndarray          # local calendar day number (days since 1970-01-01 in the author's time)
    hour: np.ndarray         # local hour 0..23
    dow: np.ndarray          # 0 = Monday
    lines: np.ndarray
    files: np.ndarray
    touch: np.ndarray        # commit touches a test file (0/1)
    cat: list[str]
    bucket: list[str]
    num: dict[str, np.ndarray] = field(default_factory=dict)
    den: dict[str, np.ndarray] = field(default_factory=dict)
    fix_window_min: int = FIX_WINDOW_MIN
    _day_cache: dict = field(default_factory=dict, repr=False)

    def ratio(self, habit: str) -> float:
        d = self.den[habit].sum()
        return float(self.num[habit].sum() / d) if d > 0 else float("nan")

    def day_sums(self, habit: str) -> tuple[np.ndarray, np.ndarray]:
        """(numerator, denominator) summed per active local day, for block bootstrap."""
        hit = self._day_cache.get(habit)
        if hit is None:
            _, inv = np.unique(self.day, return_inverse=True)
            k = int(inv.max()) + 1 if self.n else 0
            hit = (np.bincount(inv, weights=self.num[habit], minlength=k), np.bincount(inv, weights=self.den[habit], minlength=k))
            self._day_cache[habit] = hit
        return hit


def build_table(records: Sequence[CommitRecord], *, fix_window_min: int = FIX_WINDOW_MIN) -> CommitTable:
    recs = sorted((r for r in records if r.parents <= 1), key=lambda r: r.t)
    n_merge = sum(1 for r in records if r.parents > 1)
    n = len(recs)
    t = np.array([r.t for r in recs], dtype=float)
    local = t + np.array([r.tz_min for r in recs], dtype=float) * 60.0
    day = np.floor(local / 86400.0).astype(np.int64)
    sec = local - day * 86400.0
    hour = (sec // 3600).astype(np.int64)
    dow = (day + 3) % 7
    cat = [r.category for r in recs]
    bucket = [r.size_bucket for r in recs]
    is_fix = np.array([c == "fix" for c in cat], dtype=float)
    is_code = np.array([c in CODE_CATEGORIES for c in cat], dtype=float)
    touch = np.array([r.touches_tests for r in recs], dtype=float)

    followed = np.zeros(n)
    fix_idx = np.flatnonzero(is_fix)
    for a, i in enumerate(fix_idx[:-1]):
        j = fix_idx[a + 1]
        if t[j] - t[i] <= fix_window_min * 60.0:
            followed[i] = 1.0

    ones = np.ones(n)
    late = ((hour >= LATE_START_H) & (hour < LATE_END_H)).astype(float)
    num = {
        "big_commits": np.array([b in GIANT_BUCKETS for b in bucket], dtype=float),
        "tests_with_changes": is_code * touch,
        "fix_after_fix": is_fix * followed,
        "reverts": np.array([c == "revert" for c in cat], dtype=float),
        "vague_messages": np.array([r.message_quality == "vague" for r in recs], dtype=float),
        "late_night": late,
    }
    den = {"big_commits": ones, "tests_with_changes": is_code, "fix_after_fix": is_fix, "reverts": ones, "vague_messages": ones, "late_night": ones}
    return CommitTable(n=n, n_merge=n_merge, t=t, day=day, hour=hour, dow=dow,
                       lines=np.array([r.lines for r in recs], dtype=float), files=np.array([r.n_files for r in recs], dtype=float),
                       touch=touch, cat=cat, bucket=bucket, num=num, den=den, fix_window_min=fix_window_min)


def _r(x: float, nd: int = 4):
    return None if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else round(float(x), nd)


def _longest_streak(days: np.ndarray) -> int:
    if days.size == 0:
        return 0
    u = np.unique(days)
    best = run = 1
    for a, b in zip(u[:-1], u[1:]):
        run = run + 1 if b - a == 1 else 1
        best = max(best, run)
    return int(best)


def sessions(table: CommitTable, gap_min: int = SESSION_GAP_MIN) -> list[tuple[int, int]]:
    """(first, last) commit index of each work session: commits less than ``gap_min`` minutes apart."""
    if table.n == 0:
        return []
    out, start = [], 0
    for i in range(1, table.n):
        if table.t[i] - table.t[i - 1] > gap_min * 60.0:
            out.append((start, i - 1))
            start = i
    out.append((start, table.n - 1))
    return out


def compute_features(records: Sequence[CommitRecord], *, fix_window_min: int = FIX_WINDOW_MIN, table: CommitTable | None = None) -> dict:
    """Numbers and enums for one person and repo. No text of any kind."""
    tb = table or build_table(records, fix_window_min=fix_window_min)
    n = tb.n
    if n == 0:
        return {"n_commits": 0, "n_merge": tb.n_merge}
    uniq_days = np.unique(tb.day)
    span = int(uniq_days[-1] - uniq_days[0]) + 1
    by_hour = np.bincount(tb.hour, minlength=24).tolist()
    by_dow = np.bincount(tb.dow, minlength=7).tolist()
    counts = np.bincount(tb.day - uniq_days[0], minlength=span)[-120:]
    size_share = {b: _r(sum(1 for x in tb.bucket if x == b) / n) for b in SIZE_BUCKETS}
    cat_share = {c: _r(sum(1 for x in tb.cat if x == c) / n) for c in CATEGORIES if c != "merge"}
    late_days = tb.day[tb.num["late_night"] > 0]
    burst = 0
    if late_days.size:
        d, c = np.unique(late_days, return_counts=True)
        burst = int((c >= 3).sum())
    n_code = int(tb.den["tests_with_changes"].sum())
    n_fix = int(tb.den["fix_after_fix"].sum())
    sess = sessions(tb)
    return {
        "n_commits": n,
        "n_merge": tb.n_merge,
        "n_active_days": int(uniq_days.size),
        "span_days": span,
        "commits_per_active_day": _r(n / uniq_days.size, 2),
        "commits_by_hour": by_hour,
        "commits_by_dow": by_dow,
        "daily_counts": [int(x) for x in counts],
        "size": {"share": size_share, "lines_median": _r(np.median(tb.lines), 1), "lines_p90": _r(np.percentile(tb.lines, 90), 1)},
        "files_per_commit": {"mean": _r(tb.files.mean(), 2), "median": _r(np.median(tb.files), 1), "p90": _r(np.percentile(tb.files, 90), 1)},
        "category_share": cat_share,
        "habits": {h: {"value": _r(tb.ratio(h)), "num": int(tb.num[h].sum()), "den": int(tb.den[h].sum())} for h in HABIT_IDS},
        "test_touch": {"share_all": _r(float(tb.touch.mean())), "share_code": _r(tb.ratio("tests_with_changes")), "n_code": n_code},
        "fix": {"n_fix": n_fix, "share": _r(n_fix / n), "followed_by_fix_share": _r(tb.ratio("fix_after_fix")), "window_min": tb.fix_window_min},
        "revert_share": _r(tb.ratio("reverts")),
        "vague_share": _r(tb.ratio("vague_messages")),
        "late_night": {"share": _r(tb.ratio("late_night")), "burst_days": burst, "window": [LATE_START_H, LATE_END_H]},
        "streak": {"longest_days": _longest_streak(tb.day)},
        "sessions": {"n": len(sess), "gap_min": SESSION_GAP_MIN, "commits_per_session_mean": _r(n / max(1, len(sess)), 2)},
    }
