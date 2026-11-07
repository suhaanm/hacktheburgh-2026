"""The hit list evaluator: its worlds, its small statistics, the shape it returns, and the exact checks that must hold (determinism, the held-back audit,
k-anonymity, the edge cases). The soft measures (recall, false rows, coverage) are REPORTED by the evaluator, not asserted here: a miss must show up
in the evaluation, not be hidden by a test that was tuned to pass."""
from __future__ import annotations

import json

import pytest

from understudy_engine.hitlist import evaluate as E

from .conftest import DAY


# ------------------------------------------------------------------------------------------------ statistics
def test_wilson_interval_known_values_and_edges():
    assert E.wilson(0, 10)[0] == 0.0 and 0.27 < E.wilson(0, 10)[1] < 0.28
    assert E.wilson(10, 10)[1] == 1.0 and 0.72 < E.wilson(10, 10)[0] < 0.73
    lo, hi = E.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert E.wilson(0, 0) == [0.0, 1.0]
    r = E.rate(3, 4)
    assert r == {"k": 3, "n": 4, "rate": 0.75, "ci": E.wilson(3, 4)}
    assert E.rate(0, 0)["rate"] is None


def test_person_level_bootstrap_is_deterministic_and_handles_tiny_samples():
    a = E.boot_mean([0.1, 0.2, 0.3, 0.4], seed=5)
    assert a == E.boot_mean([0.1, 0.2, 0.3, 0.4], seed=5) and a["mean"] == 0.25 and a["ci"][0] <= 0.25 <= a["ci"][1]
    assert E.boot_mean([], seed=1) == {"n": 0, "mean": None, "ci": None}
    assert E.boot_mean([0.5], seed=1)["ci"] is None


# ------------------------------------------------------------------------------------------------ the worlds
def test_a_world_is_the_same_for_the_same_seed_and_different_for_another():
    plant = [E.Plant(E.CALC, runs=8)]
    a = E.make_world(E._rng("w", 1), plant)
    b = E.make_world(E._rng("w", 1), plant)
    c = E.make_world(E._rng("w", 2), plant)
    sig = lambda eps: [(e.task_id, round(e.t0, 3), tuple(x.id for x in e.cogs)) for e in eps]            # noqa: E731
    assert sig(a) == sig(b) and sig(a) != sig(c)


def test_planted_runs_land_in_the_last_seven_days_on_different_days_and_keep_their_first_step():
    eps = E.make_world(E._rng("plant"), [E.Plant(E.SUBMIT_FIRST, runs=9, slip=1.0)], noise_per_day=0.0)
    assert len(eps) == 9
    assert all(E.NOW0 - 7 * DAY <= e.t0 <= E.NOW0 for e in eps)
    assert len({int((e.t0 - (E.NOW0 - 7 * DAY)) // DAY) for e in eps[:3]}) == 3                      # the first runs fall on three different days
    assert all(e.cogs[0].id == "SUBMIT_CASE" for e in eps)                                           # a slip never changes the first step
    assert any(len(e.cogs) != len(E.SUBMIT_FIRST) for e in eps)                                        # and with slip 1.0 every run did slip


def test_noise_is_spread_over_the_history_and_a_null_world_has_no_planted_task():
    eps = E.make_world(E._rng("null"), [], noise_per_day=5.0)
    assert 80 < len(eps) < 220 and min(e.t0 for e in eps) < E.NOW0 - 20 * DAY and max(e.t1 for e in eps) <= E.NOW0 + 1
    assert not any(e.task_id.startswith("p") for e in eps)
    assert E.make_world(E._rng("none"), [], noise_per_day=0.0) == []


def test_poisson_plants_follow_the_weekly_mean():
    runs = [len(E.make_world(E._rng("poisson", i), [E.Plant(E.CALC, weekly=8.0)], noise_per_day=0.0)) for i in range(200)]
    assert 7.5 < sum(runs) / len(runs) < 8.5


def test_the_planted_unnamed_sequences_match_no_pack_routine_and_name_no_judgement_or_risky_first_step():
    from understudy_engine.hitlist import vocab as V
    from understudy_engine.routines.scoring import match_template

    pack = E._pack()
    for seq in E.UNNAMED:
        sk = E._skel(seq)
        assert match_template(sk, pack.templates)[0] is None
        assert not (set(sk) & pack.judgement_cogs()) and V.step_risk(sk[0]) is None
    assert match_template(E._skel(E.CALC), pack.templates)[0]["id"] == "calc-entry-3x"
    assert match_template(E._skel(E.QUEUE), pack.templates)[0]["id"] == "queue-sweep"


# ------------------------------------------------------------------------------------------------ the measures
def test_each_measure_is_deterministic_on_a_small_cell():
    people = [(0, 0), (0, 1)]
    for m in (E.m_recall, E.m_merging, E.m_audit, E.m_determinism):
        assert json.dumps(m(people), sort_keys=True) == json.dumps(m(people), sort_keys=True)


def test_the_audit_is_exact_in_a_noise_free_world():
    out = E.m_audit([(0, 0), (0, 1), (1, 0)])
    for name in ("irreversible_first_step", "outward_first_step", "judgement_pack_routine", "judgement_share", "denylist"):
        assert out[name]["rate"] == 1.0, (name, out[name])


def test_the_kanonymity_check_counts_what_it_should():
    out = E.m_kanon((0, 1))
    assert out["rows_listed_with_under_5_people"] == 0 and out["firms_with_a_person_id_in_the_answer"] == 0
    assert out["firms_with_wrong_suppressed_count"] == 0 and out["built_in_firm_violations"] == 0
    assert out["groups"] == 2 * 18 and out["groups_under_5"] > 0


def test_the_edge_cases_all_pass():
    out = E.m_edge_cases()
    failed = [c for c in out["cases"] if not c["pass"]]
    assert not failed, failed
    assert out["passed"]["k"] == out["passed"]["n"] == len(out["cases"]) >= 9


# ------------------------------------------------------------------------------------------------ the whole evaluation
@pytest.fixture(scope="module")
def result():
    return E.evaluate_hitlist(fast=True)


def test_the_plan_is_written_at_the_top_of_the_module_before_the_code():
    doc = E.__doc__ or ""
    assert doc.index("PLAN (written before the first run") < doc.index("Measures and what I expect") < doc.index("Limits stated up front")
    assert "NO held-out claim" in doc and "no tuning" in doc


def test_the_result_has_the_shape_the_evidence_harness_expects(result):
    for k in ("status", "meta", "recall", "null", "audit", "merging", "stability", "interval_coverage", "determinism", "k_anonymity", "edge_cases", "claims", "statement", "limitations"):
        assert k in result, k
    assert result["status"] == "ok"
    m = result["meta"]
    assert m["origin"] == "synthetic" and m["n"] == 24 and m["interval_level"] == 0.95 and "no held-out" in m["split"] and m["generated_at"]
    assert all(isinstance(x, str) and len(x) > 20 for x in result["limitations"]) and len(result["limitations"]) >= 6
    assert any("held-out" in x for x in result["limitations"]) and any("real people" in x.lower() or "nobody" in x.lower() for x in result["limitations"])
    json.dumps(result)


def test_the_claims_and_the_statement_are_generated_from_the_numbers(result):
    assert len(result["claims"]) >= 9 and all(isinstance(c, str) and "None" not in c for c in result["claims"])
    r = result["recall"]["named"]["8"]
    assert f"{round(r['rate'] * 100)}%" in result["claims"][0]
    assert "held-out" in result["statement"] and "dev seeds" in result["statement"].lower() and result["statement"].count(".") >= 3


def test_the_exact_checks_hold_in_the_fast_run(result):
    assert all(v["rate"] == 1.0 for k, v in result["audit"].items() if isinstance(v, dict) and "rate" in v)
    assert result["determinism"]["same_input_twice"]["rate"] == 1.0 and result["determinism"]["episodes_in_a_random_order"]["rate"] == 1.0
    k = result["k_anonymity"]
    assert k["rows_listed_with_under_5_people"] == 0 and k["firms_with_a_person_id_in_the_answer"] == 0 and k["firms_with_wrong_suppressed_count"] == 0
    assert result["edge_cases"]["passed"]["k"] == result["edge_cases"]["passed"]["n"]


def test_every_rate_is_a_proper_interval_and_the_unnamed_design_floor_is_visible(result):
    def walk(x):
        if isinstance(x, dict):
            if {"k", "n", "rate", "ci"} <= set(x):
                yield x
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)

    rates = list(walk(result))
    assert len(rates) >= 25
    for r in rates:
        assert 0 <= r["k"] <= r["n"] and r["ci"][0] <= r["ci"][1] and (r["rate"] is None or r["ci"][0] <= r["rate"] <= r["ci"][1])
    assert result["recall"]["unnamed"]["3"]["rate"] == 0.0                                           # by design: 5 repeats are asked for
    assert result["recall"]["met"]["unnamed"]["3"] is True


def test_every_expectation_from_the_plan_is_checked_and_a_miss_is_named_in_the_statement(result):
    import copy

    ex = result["expectations"]
    assert len(ex) == 27 and all(isinstance(x["met"], bool) and x["measure"] and x["expected"] and x["observed"] for x in ex)
    assert result["expectations_met"]["n"] == len(ex) and result["expectations_met"]["k"] == sum(x["met"] for x in ex)
    # break one number on a copy: that expectation turns false (whatever the real run already missed stays missed), and the statement names it and what was seen
    already = {x["measure"] for x in ex if not x["met"]}
    bad = copy.deepcopy(result)
    bad["stability"]["episode_loss_5pct"]["same_top_row"] = E.rate(40, 60)
    bad["expectations"] = E._expectations(bad)
    missed = {x["measure"]: x for x in bad["expectations"] if not x["met"]}
    assert set(missed) == already | {"top row unchanged, episode loss 5pct"} and missed["top row unchanged, episode loss 5pct"]["observed"] == "40 of 60"
    assert "Missed: " in E._statement(bad) and "top row unchanged, episode loss 5pct (40 of 60, expected at least 0.9)" in E._statement(bad)
    # the real result's statement names exactly its own misses, and says nothing is missed only when nothing is
    stmt = E._statement(result)
    assert all(m in stmt for m in already) and (("Missed:" in stmt) == bool(already))


def test_the_design_floor_is_a_pass_and_a_hit_there_would_be_a_miss():
    import copy

    r = {"recall": {"named": {n: E.rate(60, 60) for n in ("3", "5", "8")}, "unnamed": {"3": E.rate(0, 60), "5": E.rate(60, 60), "8": E.rate(60, 60)}},
         "null": {}, "audit": {}, "merging": {"one_row_for_two_tools": E.rate(60, 60), "two_different_tasks_stay_two_rows": E.rate(60, 60)},
         "stability": {n: {"same_top_row": E.rate(60, 60), "relative_change_in_top_minutes": {"mean": 0.01}} for n in ("step_loss_5pct", "episode_loss_5pct")},
         "interval_coverage": {}, "determinism": {}, "k_anonymity": {"rows_listed_with_under_5_people": 0, "firms_with_a_person_id_in_the_answer": 0,
                                                                    "firms_with_wrong_suppressed_count": 0, "built_in_firm_violations": 0, "groups": 1},
         "edge_cases": {"passed": {"k": 9, "n": 9}}}
    assert all(x["met"] for x in E._expectations(r))
    r2 = copy.deepcopy(r)
    r2["recall"]["unnamed"]["3"] = E.rate(5, 60)                 # the 5-repeat rule would have been broken
    r2["stability"]["step_loss_5pct"]["relative_change_in_top_minutes"]["mean"] = 0.30
    assert [x["measure"] for x in E._expectations(r2) if not x["met"]] == ["recall, unnamed routine, 3 repeats", "minutes of the top row, step loss 5pct"]
