import json

import numpy as np
import pytest

from understudy_engine.trust import claims_live as CL
from understudy_engine.trust.claims import evaluate_claims

needs_file = pytest.mark.skipif(not CL.default_path().is_file(), reason="data/eval/agent_live_runs.json not present")


def test_tie_aware_recall_does_not_credit_lucky_ordering():
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    tied = np.array([0.5] * 10)
    caught, k = CL._recall_at_share(y, tied, 0.2)
    assert k == 2 and caught == pytest.approx(0.4)             # 2 of 10 flagged at random: 20% of the 2 false claims
    perfect = np.array([0.9, 0.8] + [0.1] * 8)
    assert CL._recall_at_share(y, perfect, 0.2)[0] == pytest.approx(2.0)
    # a cutoff inside a tie group takes its expected share
    partial = np.array([0.9] + [0.5] * 9)
    caught, _ = CL._recall_at_share(y, partial, 0.2)
    assert caught == pytest.approx(1.0 + 1.0 / 9.0)             # the top row is a false claim; the second slot is a 1-in-9 draw
    assert CL._share_to_catch_all(y, perfect) == pytest.approx(0.2)
    assert CL._share_to_catch_all(np.zeros(5, int), np.arange(5.0)) == 0.0


def test_two_level_rule_probabilities_come_from_training_rows_only():
    flag = np.array([1, 1, 1, 0, 0, 0, 1, 0.0])
    y = np.array([1, 1, 0, 0, 0, 0, 1, 1])
    tr = np.array([0, 1, 2, 3, 4, 5])
    te = np.array([6, 7])
    p = CL._two_level(flag, y, tr, te)
    assert p[0] == pytest.approx((2 + 0.5) / (3 + 1))          # flagged training rows: 2 false claims of 3
    assert p[1] == pytest.approx((0 + 0.5) / (3 + 1))          # unflagged: 0 of 3


@needs_file
def test_the_file_has_one_family_of_failures_and_a_degenerate_confidence():
    d = CL.load_live()
    claimed = [r for r in d["rows"] if r["claimed"]]
    assert len(claimed) > 50 and sum(r["y"] for r in claimed) >= 15
    assert {r["condition"] for r in claimed if r["y"] == 1} == {"glitch"}
    assert all(r["variant"] == "v1_no_page_state" for r in claimed if r["y"] == 1)
    conf = [r for r in claimed if r["conf_present"]]
    assert conf and all(r["y"] == 1 for r in conf)             # presence of a stated confidence copies the label


@needs_file
def test_evaluate_claims_live_shape_label_and_honest_context():
    r = CL.evaluate_claims_live(n_boot=80)
    json.dumps(r)
    assert r["label"] == "real model, tiny n, one family of failures"
    assert r["meta"]["n_unit"] == "runs" and r["meta"]["origin"] == "synthetic" and r["n"] == r["all_claims"]["n_claims"]
    assert "leave-one-household-out" in r["split"] and r["limitations"]
    assert {x["id"] for x in r["limitations"]} >= {"ana-claims-live-tiny", "ana-claims-live-artifact"}
    for k in ("reliability", "brier", "base_rate"):
        assert k in r
    sc = r["stated_confidence"]
    assert sc["excluded_from_model"] and sc["rows_with_a_stated_confidence"] == sc["of_which_false_claims"]
    assert "stated_confidence" not in r["features_used"]
    a, v1 = r["all_claims"], r["v1_runs_only"]
    assert set(a["baselines"]) >= {"base_rate", "rule_any_5xx", "rule_any_retry_or_escalation", "confidence_present_indicator"}
    for sub in (a, v1):
        for res in [sub["model"]] + list(sub["baselines"].values()):
            assert 0 <= res["brier"] <= 1 and len(res["ci_brier"]) == 2
            f = res["flag_top_share"]
            assert f["share"] == 0.2 and 0 <= f["false_claims_caught"] <= f["false_claims_total"] and len(f["recall_ci"]) == 2
    # the rule 'any 5xx seen' is perfect where there is no fixed variant, and the classifier is not better than it there
    assert v1["rule_any_5xx_confusion"]["precision"] == 1.0 and v1["rule_any_5xx_confusion"]["recall"] == 1.0
    assert v1["model_minus_rule_any_5xx"]["brier"]["ci"][1] > -1e-9      # not better than the rule on pre-fix runs
    assert "only by learning the version" in r["finding"]
    assert r["by_condition"]["glitch/v1_no_page_state"]["false_claims"] == r["by_condition"]["glitch/v1_no_page_state"]["claimed"]
    # beats the base rate by a wide margin, as any detector of the error page would
    assert a["model_minus_base_rate"]["brier"]["ci"][1] < 0


@needs_file
def test_loho_folds_hold_each_household_out_and_results_are_deterministic():
    d = CL.load_live()
    groups = np.array([r["group"] for r in d["rows"] if r["claimed"]])
    folds = CL._folds_loho(groups)
    assert len(folds) == len(set(groups.tolist())) and sum(len(f) for f in folds) == groups.size
    assert all(len(set(groups[f].tolist())) == 1 for f in folds)
    a, b = CL.evaluate_claims_live(n_boot=40), CL.evaluate_claims_live(n_boot=40)
    for x in (a, b):
        x["meta"].pop("generated_at")
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


@needs_file
def test_agent_claims_section_carries_both_the_synthetic_and_the_live_result():
    r = evaluate_claims(n_boot=40, fast=True)
    assert r["n_unit"] == "runs" and "model" in r and "reliability" in r and r["origin"] == "synthetic"   # synthetic keys unchanged
    assert r["live"]["label"] == "real model, tiny n, one family of failures"
    assert {x["id"] for x in r["limitations"]} >= {"ana-claims-live-tiny", "ana-claims-live-artifact"}
    assert "live" not in evaluate_claims(n_boot=40, fast=True, include_live=False)
    assert "live" not in evaluate_claims(n_boot=40, fast=True, live_path="/nonexistent/agent_live_runs.json")
