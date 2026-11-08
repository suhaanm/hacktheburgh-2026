"""The evaluation harness itself (REQ-9): the edge-case matrix passes, the worlds and helpers behave, the held-out guard holds, and ``evaluate_insights(fast=True)``
returns the agreed structure. The numbers are the evaluation's, not the tests' (evals/insights/PLAN.md)."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from understudy_engine.insights import evaluate as E
from understudy_engine.insights.firm import NOW0, build_firm
from understudy_engine.insights.rows import row_t


def test_every_edge_case_in_the_matrix_passes():
    m = E.edge_cases(fast=True)
    assert len(m) >= 20
    failed = [e["edge_case"] for e in m if not e["pass"]]
    assert failed == []
    assert all({"edge_case", "scenario", "expected", "pass", "test"} <= set(e) for e in m)
    assert len({e["edge_case"] for e in m}) == len(m)


def test_the_held_out_seeds_cannot_be_run_by_accident(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_INSIGHTS_HELDOUT", raising=False)
    with pytest.raises(RuntimeError, match="held-out"):
        E.evaluate_insights(fast=True, heldout=True)
    assert set(E.DEV_SEEDS).isdisjoint(E.HELDOUT_SEEDS) and E.HELDOUT_SEEDS[0] == 100 and E.HELDOUT_SEEDS[-1] == 139


def test_worlds_are_deterministic_and_the_planted_effect_is_where_it_should_be():
    a = E.world("time_loss", np.random.default_rng(1), "p_x", NOW0, 30.0)
    b = E.world("time_loss", np.random.default_rng(1), "p_x", NOW0, 30.0)
    assert a == b
    recent = [r["lost_s"] for r in a if r["skill"] == E.SK and row_t(r) > NOW0 - 28 * 86400]
    early = [r["lost_s"] for r in a if r["skill"] == E.SK and row_t(r) < NOW0 - 56 * 86400]
    assert np.median(recent) > 20 and abs(np.median(early)) < 6
    assert E.world("null", np.random.default_rng(1), "p_x", NOW0) != a


def test_a_planted_time_loss_is_found_and_a_holiday_is_never_called_a_relapse():
    r = E.recall_worker(8, True)
    assert r["worlds"]["time_loss_30s"]["selected"]["rate"] >= 0.75
    assert r["false_relapse_after_absence"]["k"] == 0
    assert r["worlds"]["retention"]["selected"]["rate"] >= 0.75


def test_the_null_worker_world_has_a_low_false_insight_rate_and_the_diagnostic_shows_what_family_control_does():
    r = E.null_worker((0,), True)
    pw = r["person_weeks"]
    assert pw["n"] > 100 and pw["rate"] <= 0.05
    assert r["without_family_control"]["rate"] >= pw["rate"]
    assert r["target"] == 0.05


def test_the_null_admin_world_raises_no_false_comparison():
    r = E.null_admin((0,), True)
    assert r["admin_weeks"]["n"] == 2 and r["admin_weeks"]["k"] == 0


def test_cluster_rate_pools_and_brackets():
    r = E.cluster_rate([(1, 10), (0, 10), (2, 10), (0, 10)], 200, 1)
    assert r["k"] == 3 and r["n"] == 40 and abs(r["rate"] - 0.075) < 1e-9 and r["ci"][0] <= r["rate"] <= r["ci"][1]
    assert E.cluster_rate([(0, 5)], 50, 1)["ci"] is None and E.cluster_rate([], 50, 1)["rate"] is None


def test_cut_and_drop_rows_do_what_they_say():
    snap = build_firm(0).snapshot
    c = E.cut(snap, snap.now - 30 * 86400)
    assert c.now == snap.now - 30 * 86400 and all(row_t(r) <= c.now for p in c.people for r in p.rows)
    assert sum(len(p.rows) for p in c.people) < sum(len(p.rows) for p in snap.people)
    d = E.drop_rows(snap, 0.05, 1)
    n0, n1 = sum(len(p.rows) for p in snap.people), sum(len(p.rows) for p in d.people)
    assert 0.9 * n0 < n1 < 0.99 * n0
    assert E.drop_rows(snap, 0.05, 1).people[3].rows == d.people[3].rows


def test_the_k_anonymity_scan_finds_a_violation_when_there_is_one_and_none_in_a_small_firm():
    from understudy_engine.insights import admin as A
    from understudy_engine.insights.summary import AdminView

    v = AdminView(E._small_firm())
    cs = A.admin_run(v)
    assert E.kanon_violations(v, cs) == []
    bad = replace(next(c for c in A.admin_run(AdminView(build_firm(0).snapshot)) if c.kind == "role_gap" and c.value is not None), n=3)
    assert any("candidate:role_gap" in x for x in E.kanon_violations(v, [bad]))


def test_the_truth_the_audit_reads_comes_from_the_generator_not_the_selection():
    firm = build_firm(0)
    eff = [e for t in firm.truth["persons"].values() for e in t["effects"]]
    assert eff and {e["kind"] for e in eff} <= {"time_loss_habit", "habit_improved", "independence_milestone"} and all("size" in e for e in eff)
    assert all(not t["effects"] for t in build_firm(0, scenario="null").truth["persons"].values())
    assert all(not t["effects"] for t in firm.truth["persons"].values() if t["level"] == "expert")


@pytest.fixture(scope="module")
def result():
    return E.evaluate_insights(fast=True)


def test_evaluate_insights_returns_the_agreed_structure_with_generated_claims(result):
    assert set(result) >= {"meta", "null_worker", "null_admin", "recall_worker", "recall_admin", "nothing_stands_out", "stability", "determinism", "suppression", "k_anonymity", "edge_cases",
                           "claims", "limitations"}
    assert result["meta"]["origin"] == "synthetic" and result["meta"]["seeds"] == "dev" and result["meta"]["fast"] is True
    assert len(result["claims"]) >= 10 and all(isinstance(c, str) and c for c in result["claims"]) and len(result["limitations"]) >= 4
    assert any("Made-up firm data" in c for c in result["claims"])
    ns = result["nothing_stands_out"]
    assert ns["empty_lists"] == ns["genuinely_null"] + ns["missed_a_planted_effect"] and ns["by_size"]
    assert result["determinism"]["run_twice_identical"] and result["determinism"]["shuffled_rows_and_people_identical"] and result["determinism"]["regenerated_firm_identical"]
    assert result["k_anonymity"]["violations"] == 0 and result["k_anonymity"]["small_firm_comparisons"] == 0
    assert all(e["pass"] for e in result["edge_cases"])


def test_the_claims_are_generated_from_the_numbers_not_typed(result):
    w = result["null_worker"]["person_weeks"]
    assert str(w["rate"]) in result["claims"][0] and str(w["n"]) in result["claims"][0]
    mutated = dict(result, null_worker=dict(result["null_worker"], person_weeks=dict(w, rate=0.5, k=210)))
    assert "0.5" in E.claims(mutated)[0] and "not met" in E.claims(mutated)[0]
