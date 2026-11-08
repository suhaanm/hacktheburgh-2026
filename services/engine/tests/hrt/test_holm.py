"""The family size and the Holm-adjusted p-values in the brief: arithmetic, ordering, and what the table claims about itself."""
from __future__ import annotations

import importlib.util

import pytest

from understudy_engine.store.paths import repo_root

ROOT = repo_root()


@pytest.fixture(scope="module")
def hb():
    spec = importlib.util.spec_from_file_location("hrt_brief_holm", ROOT / "scripts" / "hrt_brief.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_p_value_from_a_95_percent_interval_is_the_normal_two_sided_tail(hb):
    assert hb.p_from_interval(0.0, -1.0, 1.0) == pytest.approx(1.0)
    assert hb.p_from_interval(1.959964, 0.0, 2 * 1.959964) == pytest.approx(0.05, abs=1e-4)              # an interval whose end touches zero is p = 0.05
    assert hb.p_from_interval(-1.959964, -2 * 1.959964, 0.0) == pytest.approx(0.05, abs=1e-4)             # sign does not matter
    assert hb.p_from_interval(5.0, 4.9, 5.1) < 1e-100                                                       # a huge z underflows towards zero, never NaN
    assert hb.p_from_interval(1.0, 1.0, 1.0) == 0.0                                                         # a degenerate interval away from zero
    assert hb.p_from_interval(0.0, 0.0, 0.0) == 1.0


def test_holm_matches_the_textbook_step_down_and_never_goes_below_the_raw_value(hb):
    adj = hb.holm([0.01, 0.04, 0.03, 0.005])
    assert adj == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert all(a >= p for a, p in zip(adj, [0.01, 0.04, 0.03, 0.005]))
    assert hb.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])                                                 # capped at 1, and the step-down keeps the adjusted values non-decreasing in the sorted order
    assert hb.holm([]) == []
    assert hb.holm([0.2]) == [0.2]
    assert hb.holm([1e-300] * 3) == pytest.approx([3e-300] * 3, rel=1e-9)                                  # ties: every adjusted value is m times the common raw value


def test_the_family_lists_every_directional_contrast_with_its_raw_and_adjusted_p(hb):
    fam = hb.holm_family()
    rows = fam["rows"]
    assert fam["m"] == len(rows) >= 17
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert 0.0 <= r["p"] <= r["p_holm"] <= 1.0, r
        assert r["ci"][0] <= r["est"] <= r["ci"][1], r
    assert {"P1a", "P1b", "P3-markov", "P5", "R1", "D1", "D4"} <= set(ids)
    assert fam["table"].count("\n") >= fam["m"] + 1
    assert "normal approximation" in fam["note"] and "not a registered computation" in fam["note"]


def test_holm_is_at_least_as_strict_as_the_raw_threshold_and_never_more_than_bonferroni(hb):
    fam = hb.holm_family()
    m = fam["m"]
    for r in fam["rows"]:
        assert r["p_holm"] <= min(1.0, m * r["p"]) + 1e-12
        assert r["survives"] == (r["p_holm"] < 0.05)
