"""The hit list rules, one at a time, on small planted data: window, repeats, stability, judgement, irreversible first step, merge,
overlap, status, hidden, reset, denylist, intervals, ranking, and every edge case the owner listed. Pure: no disk, no clock."""
from __future__ import annotations

import json
import random

import pytest

from understudy_engine.hitlist import vocab as V
from understudy_engine.hitlist.build import HitConfig, RoutineView, _rank, build_hitlist, status_of

from .conftest import CALC, DAY, NOTE, NOW, P, ep, many


def run(eps, pack, **kw):
    kw.setdefault("person", P)
    kw.setdefault("now", NOW)
    return build_hitlist(eps, pack, **kw)


def ids(r, key="rows"):
    return [x["id"] for x in r[key]]


# ------------------------------------------------------------------------------------------------ the happy path
def test_planted_routines_are_listed_in_the_pack_vocabulary_biggest_first(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 8, prefix="n", spread_days=4)
    r = run(eps, pack)
    assert r["state"] == "ok" and r["message"] == ""
    assert ids(r) == ["calc-entry-3x", "case-note-copy"]
    a, b = r["rows"]
    assert a["label"] == "Enter the household into three calculators" and a["key"] == "household" and a["family"] == "enter"
    assert b["label"] == "Copy the agreed results into the case note" and b["family"] == "copy"
    assert a["count"] == 12 and b["count"] == 8
    assert a["minutes_per_week"]["point"] > b["minutes_per_week"]["point"] > 0
    assert a["stops_before"] == "submit" and a["status"] == "candidate" and a["judgement_share"] == 0
    assert r["total"]["actions"] == 2 and r["total"]["repeats"] == 20
    assert r["total"]["minutes_per_week"]["point"] == pytest.approx(a["minutes_per_week"]["point"] + b["minutes_per_week"]["point"], abs=0.11)


def test_minutes_follow_the_stated_formula(pack):
    # 12 runs in a week, 40 s each, no judgement: 12 x 40 / 60 = 8 minutes a week
    r = run(many(CALC, 12, prefix="c"), pack)
    row = r["rows"][0]
    assert row["minutes_per_week"]["point"] == pytest.approx(8.0, abs=0.1)
    assert row["seconds_per_time"] == pytest.approx(40.0, abs=0.1)
    lo, pt, hi = (row["minutes_per_week"][k] for k in ("lo", "point", "hi"))
    assert 0 < lo <= pt <= hi


def test_a_longer_window_spreads_the_same_count_over_more_weeks(pack):
    eps = many(CALC, 12, prefix="c", spread_days=20) + [ep(["X01", "X02", "X03", "X04"], NOW - 50 * DAY, task="old")]
    seven = run(eps, pack, window_days=7)
    thirty = run(eps, pack, window_days=30)
    assert seven["rows"] and thirty["rows"]
    assert thirty["rows"][0]["count"] == 12 and seven["rows"][0]["count"] < 12
    # 12 runs over a 30 day window is about 2.8 a week: 40 s each
    assert thirty["rows"][0]["minutes_per_week"]["point"] == pytest.approx(12 / (30 / 7) * 40 / 60, abs=0.1)


def test_a_window_longer_than_the_persons_history_uses_the_history(pack):
    eps = many(CALC, 12, prefix="c", spread_days=13)                       # 14 days of data in all
    row = run(eps, pack, window_days=30)["rows"][0]
    assert row["minutes_per_week"]["point"] == pytest.approx(12 / 2 * 40 / 60, abs=0.15)      # per week of data seen, not per 30 days


def test_rows_are_deterministic_down_to_the_interval(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 8, prefix="n")
    assert json.dumps(run(eps, pack), sort_keys=True) == json.dumps(run(list(reversed(eps)), pack), sort_keys=True)


def test_more_evidence_gives_a_tighter_interval(pack):
    def width(n):
        row = run(many(CALC, n, prefix="c", dur=40.0, slip=lambda i, s: s), pack)["rows"][0]["minutes_per_week"]
        return (row["hi"] - row["lo"]) / row["point"]
    assert width(48) < width(6)


def test_ranking_is_minutes_then_count_then_id():
    row = lambda i, m, c: {"id": i, "count": c, "minutes_per_week": {"point": m}}      # noqa: E731
    rows = [row("b", 5.0, 3), row("a", 5.0, 3), row("c", 5.0, 9), row("d", 9.0, 1)]
    assert [r["id"] for r in sorted(rows, key=_rank)] == ["d", "c", "a", "b"]
    # 5.04 and 5.0 are the same figure to one decimal, so they tie on minutes and the key ignores the noise
    assert _rank(row("a", 5.04, 3)) == _rank(row("a", 5.0, 3))


# ------------------------------------------------------------------------------------------------ window and repeats
def test_a_row_needs_three_repeats_in_the_window(pack):
    assert run(many(CALC, 2, prefix="c"), pack)["rows"] == []
    assert ids(run(many(CALC, 3, prefix="c"), pack)) == ["calc-entry-3x"]


def test_episodes_outside_the_window_do_not_count(pack):
    old = many(CALC, 10, prefix="o", days_back=20, spread_days=5)
    assert run(old, pack, window_days=7)["rows"] == []
    assert run(old, pack, window_days=7)["state"] != "ok"
    assert ids(run(old, pack, window_days=30)) == ["calc-entry-3x"]


def test_a_sequence_that_matches_no_pack_routine_needs_five_repeats_on_two_days(pack):
    seq = ["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY"]
    assert run(many(seq, 4, prefix="u"), pack)["rows"] == []                               # four is not enough
    burst = [ep(seq, NOW - 2 * DAY - 90 * i, task=f"b{i}") for i in range(6)]
    assert run(burst, pack)["rows"] == []                                                    # six in one afternoon is a batch, not a habit
    r = run(many(seq, 6, prefix="u"), pack)
    assert len(r["rows"]) == 1 and r["rows"][0]["id"].startswith("auto-") and r["rows"][0]["count"] == 6
    assert r["rows"][0]["label"].startswith("Open calculator") and r["rows"][0]["key"] == "Open calculator"


# ------------------------------------------------------------------------------------------------ edge states
def test_a_new_user_gets_no_rows_and_an_encouraging_sentence(pack):
    r = run([], pack)
    assert r["state"] == "new_user" and r["rows"] == [] and r["total"] is None
    assert r["message"] == V.sentence_new_user() and r["episodes_in_window"] == 0


def test_too_little_data_in_the_window_says_so(pack):
    eps = [ep(["READ", "COPY", "PASTE", "CHECK"], NOW - DAY * (i + 1), task=f"a{i}") for i in range(2)] + \
          [ep(["NAVIGATE", "SEARCH", "ASK", "ENTER", "PASTE"], NOW - DAY * (i + 1) - 7000, task=f"b{i}") for i in range(2)]
    r = run(eps, pack, window_days=7)
    assert r["state"] == "too_little_data" and r["rows"] == [] and "Only 4 cases in the last 7 days" in r["message"]
    assert "30 day view" in r["message"]


def test_enough_data_but_nothing_repeats_says_that(pack):
    rng = random.Random(5)
    vocab = [f"X{i:02d}" for i in range(40)]
    eps = [ep(rng.sample(vocab, 8), NOW - DAY * rng.uniform(0.1, 6), task=f"r{i}") for i in range(14)]
    r = run(eps, pack)
    assert r["state"] == "nothing_repeats" and r["rows"] == [] and "three times" in r["message"] and "7 days" in r["message"]


def test_counting_again_after_a_reset_only_counts_new_work(pack):
    eps = many(CALC, 12, prefix="c")
    reset_at = NOW - 0.5 * DAY                                  # after all of the work above
    r = run(eps, pack, reset_at=reset_at)
    assert r["state"] == "counting_again" and r["rows"] == [] and r["counting_since"].startswith("2026-11-07")
    assert r["message"].startswith("Counting again since 7 November.") and r["episodes_in_window"] == 0
    later = eps + many(CALC, 4, prefix="n", days_back=0.1, spread_days=0.3)
    r2 = run(later, pack, reset_at=reset_at)
    assert ids(r2) == ["calc-entry-3x"] and r2["rows"][0]["count"] == 4 and r2["counting_since"]
    # a reset older than the window changes nothing
    r3 = run(eps, pack, reset_at=NOW - 40 * DAY)
    assert r3["counting_since"] is None and r3["rows"][0]["count"] == 12


def test_a_short_stretch_since_a_reset_is_not_extrapolated(pack):
    eps = many(CALC, 4, prefix="n", days_back=0.1, spread_days=0.3)
    r = run(eps, pack, reset_at=NOW - 0.5 * DAY)
    assert r["rows"][0]["minutes_per_week"]["point"] == pytest.approx(4 * 40 / 60, abs=0.1)       # under a week counts as a week


# ------------------------------------------------------------------------------------------------ held back
def test_a_routine_that_needs_judgement_is_held_back_not_listed(pack):
    sweep = ["NAVIGATE", "READ", "CHECK", "DECIDE"] * 4                    # the pack's queue-sweep: automatable false
    heavy = ["SEARCH", "COMPARE", "DECIDE", "READ", "SEARCH", "DECIDE"]    # 5 of 6 steps are judgement
    r = run(many(sweep, 10, prefix="q") + many(heavy, 8, prefix="h") + many(CALC, 9, prefix="c"), pack)
    assert ids(r) == ["calc-entry-3x"]
    assert {"reason": "judgement", "count": 2} in r["held_back"]


def test_a_sequence_that_begins_with_an_irreversible_step_is_never_offered(pack):
    seq = ["SUBMIT_CASE", "READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE"]
    r = run(many(seq, 9, prefix="s") + many(CALC, 9, prefix="c"), pack)
    assert ids(r) == ["calc-entry-3x"]
    assert r["held_back"] == [{"reason": "irreversible_first_step", "count": 1}]
    assert V.step_risk("SEND_LETTER") == "message" and V.step_risk("EXPORT_RESULT") == "share"             # outward counts too


def test_an_irreversible_step_later_in_the_sequence_is_where_it_stops(pack):
    seq = ["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "SUBMIT_CASE"]
    r = run(many(seq, 8, prefix="s"), pack)
    assert len(r["rows"]) == 1 and r["rows"][0]["stops_before"] == "submit"
    assert run(many(["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY"], 8, prefix="s"), pack)["rows"][0]["stops_before"] == "none"


def test_a_very_varied_sequence_is_held_back_as_unstable(pack):
    base = ["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY"]
    swap = lambda i, s: [*s[:i % 8], "ENTER", *s[i % 8 + 1:]] if i % 2 else s                                  # noqa: E731
    eps = many(base, 12, prefix="v", slip=swap)
    assert len(run(eps, pack)["rows"]) == 1                                                                  # one slip in eight is still a routine
    strict = run(eps, pack, cfg=HitConfig(max_variation=0.01))
    assert strict["rows"] == [] and strict["held_back"] == [{"reason": "unstable", "count": 1}] and strict["state"] == "all_handled"


def test_the_workers_denylist_removes_a_row_by_the_tools_it_touches(pack):
    eps = many(CALC, 9, prefix="c") + many(NOTE, 9, prefix="n")
    r = run(eps, pack, denylist=[{"kind": "app", "value": "GovCalc"}])
    assert ids(r) == ["case-note-copy"] and r["held_back"] == [{"reason": "denylist", "count": 1}]
    r2 = run(eps, pack, denylist=[{"kind": "domain", "value": "entitledto.co.uk"}])
    assert ids(r2) == ["case-note-copy"]                                    # the domain's name matches the EntitledTo calculator
    assert ids(run(eps, pack, denylist=[{"kind": "app", "value": "1Password"}])) == ["calc-entry-3x", "case-note-copy"]
    assert ids(run(eps, pack, denylist=[{"kind": "app", "value": ""}])) == ["calc-entry-3x", "case-note-copy"]


# ------------------------------------------------------------------------------------------------ merge and overlap
def test_the_same_task_through_different_tools_is_one_row(pack):
    variant = ["NAVIGATE", "ENTER_HOUSEHOLD", "READ", "NAVIGATE", "ENTER_HOUSEHOLD", "READ", "NAVIGATE", "ENTER_HOUSEHOLD", "READ"]
    r = run(many(CALC, 8, prefix="c") + many(variant, 6, prefix="v"), pack)
    assert ids(r) == ["calc-entry-3x"], r["rows"]
    assert r["rows"][0]["count"] == 14 and r["rows"][0]["variants"] == 2


def test_steps_of_an_unknown_kind_never_merge_different_work(pack):
    a = ["X01", "X02", "X03", "X04", "X05"]
    b = ["Y01", "Y02", "Y03", "Y04", "Y05"]
    r = run(many(a, 8, prefix="a") + many(b, 8, prefix="b"), pack)
    assert len(r["rows"]) == 2 and all(x["variants"] == 1 for x in r["rows"])


def test_overlapping_sequences_keep_the_one_worth_more_and_show_the_other_as_part_of_it(pack):
    long_seq = ["NAVIGATE", "READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE", "ENTER", "ENTER_HOUSEHOLD", "OPEN_CALCULATOR"]
    r = run(many(long_seq, 14, prefix="L", dur=90.0) + many(NOTE, 8, prefix="n"), pack)
    assert len(r["rows"]) == 1
    top = r["rows"][0]
    assert top["count"] == 14 and top["overlaps"] == [{"id": "case-note-copy", "label": "Copy the agreed results into the case note", "relation": "includes"}]
    r2 = run(many(long_seq, 5, prefix="L", dur=30.0) + many(NOTE, 20, prefix="n", dur=60.0), pack)
    assert ids(r2) == ["case-note-copy"] and r2["rows"][0]["overlaps"][0]["relation"] == "inside"


# ------------------------------------------------------------------------------------------------ status from the registry
@pytest.mark.parametrize("view,want", [
    (None, "candidate"),
    (RoutineView("x", "proposed", "A0", True), "proposed"),
    (RoutineView("x", "proposed", "A0", False), "candidate"),
    (RoutineView("x", "declined"), "candidate"),
    (RoutineView("x", "shadow", "A1"), "learning"),
    (RoutineView("x", "approval", "A1"), "running"),
    (RoutineView("x", "unattended", "A0"), "running"),
    (RoutineView("x", "approval", "A2"), "automated"),
    (RoutineView("x", "unattended", "A3"), "automated"),
])
def test_status_of(view, want):
    assert status_of(view) == want and want in V.STATUSES


def lookup_of(table):
    return lambda rid, sig: table.get(rid)


def test_status_chips_and_the_automated_fold_come_from_the_workers_decisions(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 9, prefix="n")
    r = run(eps, pack, lookup=lookup_of({"calc-entry-3x": RoutineView("calc-entry-3x", "shadow", "A1")}))
    assert {x["id"]: x["status"] for x in r["rows"]} == {"calc-entry-3x": "learning", "case-note-copy": "candidate"}
    assert r["rows"][0]["actions"]["routine_id"] == "calc-entry-3x" and r["rows"][1]["actions"]["routine_id"] is None
    assert r["rows"][1]["actions"]["can_automate"] is False
    done = run(eps, pack, lookup=lookup_of({"calc-entry-3x": RoutineView("calc-entry-3x", "approval", "A2")}))
    assert ids(done) == ["case-note-copy"] and ids(done, "automated") == ["calc-entry-3x"]
    assert done["automated"][0]["status"] == "automated"
    assert done["total"]["actions"] == 1                                              # the automated one is not in the total


def test_everything_automated_is_a_calm_empty_state_with_the_fold_filled(pack):
    r = run(many(CALC, 12, prefix="c"), pack, lookup=lookup_of({"calc-entry-3x": RoutineView("calc-entry-3x", "unattended", "A3")}))
    assert r["rows"] == [] and r["state"] == "all_handled" and ids(r, "automated") == ["calc-entry-3x"] and r["total"] is None


def test_a_routine_the_worker_declined_for_good_does_not_come_back(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 9, prefix="n")
    r = run(eps, pack, lookup=lookup_of({"calc-entry-3x": RoutineView("calc-entry-3x", "never")}))
    assert ids(r) == ["case-note-copy"] and r["automated"] == []
    assert ids(run(eps, pack, lookup=lookup_of({"calc-entry-3x": RoutineView("calc-entry-3x", "declined")}))) == ["calc-entry-3x", "case-note-copy"]


def test_an_unnamed_routine_keeps_the_registrys_id(pack):
    seq = ["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY"]
    first = run(many(seq, 8, prefix="u"), pack)["rows"][0]["id"]
    r = run(many(seq, 8, prefix="u"), pack, lookup=lambda rid, sig: RoutineView("auto-stored", "proposed", "A0", True))
    assert first.startswith("auto-") and r["rows"][0]["id"] == "auto-stored" and r["rows"][0]["status"] == "proposed"


def test_only_ids_keeps_just_the_routines_a_seeded_demo_lists(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 9, prefix="n")
    r = run(eps, pack, only_ids={"calc-entry-3x"})
    assert ids(r) == ["calc-entry-3x"] and r["total"]["actions"] == 1 and r["held_back"] == []
    assert ids(run(eps, pack, only_ids=set())) == []
    assert ids(run(eps, pack, only_ids=None)) == ["calc-entry-3x", "case-note-copy"]


# ------------------------------------------------------------------------------------------------ hide until the count doubles
def test_a_hidden_row_stays_hidden_until_its_count_doubles(pack):
    marks = {"calc-entry-3x": {"count": 6, "signature": []}}
    r = run(many(CALC, 11, prefix="c"), pack, hidden=marks)
    assert r["rows"] == [] and r["hidden"] == [{"id": "calc-entry-3x", "label": "Enter the household into three calculators", "count": 11, "returns_at": 12}]
    assert r["state"] == "all_handled"
    assert ids(run(many(CALC, 12, prefix="c"), pack, hidden=marks)) == ["calc-entry-3x"]


def test_a_hide_mark_follows_an_unnamed_routine_by_its_steps(pack):
    seq = ["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY"]
    r = run(many(seq, 8, prefix="u"), pack, hidden={"auto-old": {"count": 8, "signature": seq[:-1]}})
    assert r["rows"] == [] and r["hidden"][0]["count"] == 8


# ------------------------------------------------------------------------------------------------ cap and shape
def test_at_most_ten_rows_and_the_rest_are_counted(pack):
    rng = random.Random(11)
    vocab = [f"Z{i:02d}" for i in range(60)]
    eps = []
    for k in range(13):
        seq = rng.sample(vocab, 7)
        eps += many(seq, 7 + k, prefix=f"g{k}_", dur=30.0 + k)
    r = run(eps, pack)
    assert len(r["rows"]) == 10 and r["not_shown"] == 3
    keys = [(-round(x["minutes_per_week"]["point"], 1), -x["count"], x["id"]) for x in r["rows"]]
    assert keys == sorted(keys)


def test_every_row_has_only_ids_numbers_and_enums_beside_pack_words(pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 9, prefix="n") + many(["OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY"], 7, prefix="u")
    r = run(eps, pack)
    sigs: dict = {}
    r = run(eps, pack, sig_out=sigs)
    assert set(sigs) == {x["id"] for x in r["rows"]}
    for row in r["rows"]:
        assert row["status"] in V.STATUSES and row["stops_before"] in V.STOPS and row["family"] in V.FAMILIES
        assert set(row) == {"id", "label", "key", "family", "count", "minutes_per_week", "judgement_share", "status", "stops_before", "variation",
                            "variants", "overlaps", "seconds_per_time", "t", "actions", "what", "touches", "never"}
        assert row["key"] is None or row["key"].lower() in row["label"].lower()
        assert row["actions"]["card_id"].startswith("c_") and len(row["actions"]["card_id"]) == 14
    # the proactive layer's own id rule gives the same card id
    from understudy_engine.proactive.candidates import card_id
    assert r["rows"][0]["actions"]["card_id"] == card_id(P, "automate", f"routine:{r['rows'][0]['id']}")


def test_the_answer_is_json_clean_and_has_a_fixed_top_level_shape(pack):
    r = run(many(CALC, 12, prefix="c"), pack)
    assert set(r) == {"state", "message", "window_days", "window_from", "window_to", "counting_since", "episodes_in_window", "rows", "automated",
                      "hidden", "held_back", "not_shown", "total"}
    assert set(r["total"]) == {"actions", "repeats", "minutes_per_week", "hours_per_week"}
    json.dumps(r)
    assert r["state"] in V.STATES
