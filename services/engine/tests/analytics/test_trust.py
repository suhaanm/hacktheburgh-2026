import json

import numpy as np
import pytest

from understudy_engine.trust import ladder as L
from understudy_engine.trust.claims import evaluate_claims, simulate_claim_runs
from understudy_engine.trust.stats import wilson_lower


def run_many(state, outcome, n, cap="A3"):
    d = None
    for _ in range(n):
        d = L.record_run(state, outcome, cap=cap)
        state = d.state
    return state, d


def test_a0_to_a1_only_by_worker_action():
    s = L.LadderState()
    s2, d = run_many(s, "clean", 100)
    assert s2.rung == "A0" and s2.runs == 0  # observation only: nothing counts, nothing promotes
    g = L.grant_shadow(s)
    assert g.state.rung == "A1" and g.promoted
    assert L.grant_shadow(g.state).state.rung == "A1"  # idempotent


def test_twenty_clean_shadow_runs_promote_to_a2_with_bound_084():
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 19)
    assert s.rung == "A1" and s.runs == 19   # not enough runs, even though 19/19 has a high rate
    d = L.record_run(s, "clean")
    assert d.promoted and d.state.rung == "A2"
    assert d.state.wilson_lower == pytest.approx(0.8389, abs=1e-3)


def test_one_mismatch_delays_promotion_to_about_25_trials():
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 19)
    s = L.record_run(s, "mismatch").state          # 19/20: lower bound 0.764 < 0.8
    assert s.runs == 20 and s.rung == "A1"
    promoted_at = None
    for i in range(1, 40):
        d = L.record_run(s, "clean")
        s = d.state
        if d.promoted:
            promoted_at = s.runs
            break
    assert promoted_at == 25   # 24 of 25 has Wilson lower bound 0.805; 23 of 24 has 0.798
    assert wilson_lower(s.clean, s.runs) >= 0.8


def test_a3_needs_lower_bound_095_which_is_73_clean_runs():
    assert L.runs_needed("A2") == 20
    assert L.runs_needed("A3") == 73
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 72)
    assert s.rung == "A2"                            # promoted at 20, but 72 is not enough for A3
    d = L.record_run(s, "clean")
    assert d.promoted and d.state.rung == "A3" and d.state.runs == 73
    assert d.state.wilson_lower >= 0.95


def test_consent_cap_holds_the_rung_even_when_evidence_allows_more():
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 200, cap="A1")
    assert s.rung == "A1" and L.earned_rung(s.runs, s.clean) == "A3"
    s, _ = run_many(s, "clean", 1, cap="A2")        # the worker raises the cap to A2
    assert s.rung == "A2"


@pytest.mark.parametrize("outcome", ["failure", "undo", "injection"])
def test_demotion_by_one_rung_resets_evidence(outcome):
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 80)
    assert s.rung == "A3"
    d = L.record_run(s, outcome)
    assert d.demoted and d.state.rung == "A2" and d.state.runs == 0 and d.state.clean == 0
    d2 = L.record_run(d.state, outcome)
    assert d2.state.rung == "A1"
    d3 = L.record_run(d2.state, outcome)
    assert d3.state.rung == "A0"
    d4 = L.record_run(d3.state, outcome)
    assert d4.state.rung == "A0" and not d4.demoted


def test_mismatch_above_a1_counts_as_failure():
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 20)
    assert s.rung == "A2"
    d = L.record_run(s, "mismatch")
    assert d.demoted and d.state.rung == "A1"


def test_unknown_outcome_is_rejected():
    s = L.grant_shadow(L.LadderState()).state
    with pytest.raises(ValueError):
        L.record_run(s, "great")  # type: ignore[arg-type]


def test_to_dict_matches_routes_contract_shape():
    s = L.grant_shadow(L.LadderState()).state
    s, _ = run_many(s, "clean", 5)
    d = s.to_dict()
    assert set(d) == {"rung", "runs", "matches", "wilson_lower"} and d["runs"] == 5 and d["matches"] == 5


def test_ladder_property_rung_never_exceeds_evidence_nor_cap():
    rng = np.random.default_rng(0)
    for _ in range(200):
        s = L.grant_shadow(L.LadderState()).state
        cap = ["A1", "A2", "A3"][int(rng.integers(0, 3))]
        for _ in range(int(rng.integers(5, 120))):
            o = rng.choice(["clean"] * 12 + ["mismatch", "failure", "undo", "injection"])
            s = L.record_run(s, str(o), cap=cap).state
            assert L.RUNGS.index(s.rung) <= L.RUNGS.index(cap)
            if s.rung in ("A2", "A3"):
                assert s.runs >= 20 and s.wilson_lower >= 0.8
            if s.rung == "A3":
                assert s.wilson_lower >= 0.95


def test_claim_classifier_is_calibrated_and_beats_baselines_grouped_cv():
    runs = simulate_claim_runs(n=1500, n_groups=60, seed=3)
    r = evaluate_claims(runs, n_boot=100)
    json.dumps(r)
    m, b = r["model"], r["baselines"]
    assert m["log_loss"] < b["base_rate"]["log_loss"] - 0.05
    assert m["log_loss"] < b["stated_confidence_platt"]["log_loss"]
    assert m["ece"] < 0.08
    assert m["ci_log_loss"][0] <= m["log_loss"] <= m["ci_log_loss"][1]
    assert r["n_unit"] == "households" and r["origin"] == "synthetic"
    assert r["calibration"] and r["caveats"]
    op = r["operating_point"]
    assert op["recall"] > 2 * op["review_share"]  # flagging 20% of claims catches well over 20% of the false ones
    # grouped folds: no household straddles train and test
    from understudy_engine.trust.claims import _folds
    folds = _folds(runs.group, 5)
    seen = [set(runs.group[f].tolist()) for f in folds]
    assert all(not (seen[i] & seen[j]) for i in range(5) for j in range(i + 1, 5))
