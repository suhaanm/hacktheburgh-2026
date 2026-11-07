"""The hit list on the repo's own synthetic personas (read only; skipped when `make synth` has not been run). Planted truth: each persona
repeats a known set of routines, and the hit list must list the automatable ones, hold back the ones that need judgement, and count
them the way the generator did."""
from __future__ import annotations

from pathlib import Path

import pytest

from understudy_engine.hitlist.build import build_hitlist
from understudy_engine.memory import load_pack
from understudy_engine.routines.sources import PersonSource

DATA = Path(__file__).resolve().parents[4] / "data"
pytestmark = pytest.mark.skipif(not (DATA / "synthetic" / "nine-to-five" / "truth.json").exists(), reason="synthetic personas not generated")


@pytest.fixture(scope="module")
def src():
    return PersonSource(DATA)


def listing(src, person, window):
    pd = src.load(person)
    return pd, build_hitlist(src.episodes(pd), load_pack(pd.role), person=person, now=pd.t_last, window_days=window)


def planted(pd):
    return {r["name"]: len(r["instances"]) for r in (pd.truth or {}).get("routines", [])}


@pytest.mark.parametrize("person,listed,held", [
    ("p_ninetofive", {"calc-entry-3x", "case-note-copy"}, set()),
    ("p_nightowl", {"calc-entry-3x"}, {"judgement"}),
    ("p_irregular", {"calc-entry-3x", "weekly-report"}, {"judgement"}),
    ("p_shiftwkr", {"calc-entry-3x", "case-note-copy"}, {"judgement"}),
])
def test_planted_routines_are_listed_counted_and_the_judgement_ones_held_back(src, person, listed, held):
    pd, r = listing(src, person, 30)
    truth = planted(pd)
    assert {x["id"] for x in r["rows"]} == listed, r["rows"]
    assert {h["reason"] for h in r["held_back"]} == held
    for row in r["rows"]:
        # never more than were planted; the finder splits off some slipped runs, so it may count fewer (at least 60%)
        assert 0.6 * truth[row["id"]] <= row["count"] <= truth[row["id"]], (person, row["id"], row["count"], truth)
        assert 0 < row["minutes_per_week"]["lo"] <= row["minutes_per_week"]["point"] <= row["minutes_per_week"]["hi"]
    assert "queue-sweep" not in {x["id"] for x in r["rows"]} and "cliff-recheck" not in {x["id"] for x in r["rows"]}


def test_a_week_is_a_subset_of_a_month_and_never_shows_more_repeats(src):
    _, week = listing(src, "p_ninetofive", 7)
    _, month = listing(src, "p_ninetofive", 30)
    wk = {x["id"]: x["count"] for x in week["rows"]}
    mo = {x["id"]: x["count"] for x in month["rows"]}
    assert set(wk) <= set(mo) and all(wk[k] <= mo[k] for k in wk) and week["episodes_in_window"] < month["episodes_in_window"]


def test_an_apprentice_with_two_episodes_has_too_little_data(src):
    pd, r = listing(src, "p_nov01", 7)
    assert r["rows"] == [] and r["state"] in ("too_little_data", "nothing_repeats") and r["episodes_in_window"] <= 2
    assert r["state"] == "too_little_data" and "Only" in r["message"]


def test_a_learner_with_one_long_habit_gets_one_unnamed_row_with_plain_words(src):
    _, r = listing(src, "p_learn01", 30)
    assert len(r["rows"]) == 1 and r["rows"][0]["id"].startswith("auto-")
    assert r["rows"][0]["label"].startswith("Read, open calculator") and r["rows"][0]["stops_before"] == "none"
