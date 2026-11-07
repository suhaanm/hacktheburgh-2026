"""The long-horizon suite, offline with the grounded test double: it tests the code, never a model. Slow (real headless browsers)."""
from __future__ import annotations

import pytest

from understudy_agent.lh_suite import lh1, lh2, lh3


async def test_lh1_two_households_in_sequence_reach_the_gate_with_no_false_claims(cluster, tmp_path):
    out = await lh1(cluster, tmp_path, n=2)
    assert out["units_at_gate"] == 2 and out["false_claims"] == 0 and out["submissions_without_approval"] == 0, out["rows"]
    assert out["steps_total"] >= 150


async def test_lh2_a_pause_keeps_the_run_and_the_result_equals_an_uninterrupted_run(cluster, tmp_path):
    out = await lh2(cluster, tmp_path)
    assert out["ok"], {k: v for k, v in out.items() if k not in ("baseline", "interrupted")}
    assert out["pause_latency_s"] <= 1.0 and out["result_equals_uninterrupted"]


async def test_lh3_every_injected_fault_is_survived_or_escalated_without_a_false_claim(cluster, tmp_path):
    out = await lh3(cluster, tmp_path)
    assert out["ok"] and out["crashes"] == 0 and out["false_claims"] == 0, out["rows"]
    assert out["recovered"] >= 4


async def test_lh2b_a_killed_run_resumes_from_its_checkpoint_to_the_same_result(cluster, tmp_path):
    from understudy_agent.lh_suite import lh2_resume

    out = await lh2_resume(cluster, tmp_path)
    assert out["ok"], {k: v for k, v in out.items() if k != "baseline"}
    for r in out["kill_points"]:
        assert r["killed"] and r["amounts_equal_uninterrupted"] and r["submissions"] == 0 and r["approval_items"] == ["irreversible_step"], r
    assert out["resume_after_gate"]["steps_after_resume"] == 0


@pytest.mark.skipif(not __import__("understudy_agent.runtime.sandbox", fromlist=["x"]).sandbox_available(), reason="the runtime child needs macOS sandbox-exec")
async def test_lh4_a_household_whose_earnings_come_from_a_verified_child_profile_of_a_local_file(cluster, tmp_path):
    from understudy_agent.lh_suite import lh4

    out = await lh4(cluster, tmp_path, n=2)
    assert out["ok"], {k: v for k, v in out.items() if k != "rows"} | {"rows": out["rows"]}
    assert out["units_at_gate"] == 2 and out["children_verified"] == 2 and out["false_claims"] == 0 and out["submissions_without_approval"] == 0
    neg = out["negative_controls"]
    assert neg["lying_child_claimed_success"] and not neg["lying_child_verified"] and neg["lying_child_refused_no_value_used"]
    assert neg["forged_verified_flag_refused_by_recomputation"]


def test_figure_from_child_refuses_what_code_did_not_verify_or_cannot_reproduce(tmp_path):
    from types import SimpleNamespace

    from understudy_agent.lh_suite import ChildNotVerified, figure_from_child, make_income_csv

    p = tmp_path / "i.csv"
    make_income_csv(p, 1450.5)
    col = {"name": "take_home", "kind": "numeric", "mean": 1450.5}
    assert figure_from_child(SimpleNamespace(verified=True, status="done", output={"columns": [col]}), p) == 1450.5
    for bad in (SimpleNamespace(verified=False, status="done", output={"columns": [col]}),
                SimpleNamespace(verified=True, status="failed", output={"columns": [col]}),
                SimpleNamespace(verified=True, status="done", output={"columns": []}),
                SimpleNamespace(verified=True, status="done", output={"columns": [{**col, "mean": 1500.5}]}),
                SimpleNamespace(verified=True, status="done", output={"columns": [{**col, "kind": "categorical"}]})):
        with pytest.raises(ChildNotVerified):
            figure_from_child(bad, p)


async def test_lh5_an_overnight_batch_yields_resumes_skips_finished_units_and_the_report_matches_the_audit(cluster, tmp_path):
    from understudy_agent.lh_suite import lh5

    out = await lh5(cluster, tmp_path)
    assert out["ok"], {k: v for k, v in out.items() if k != "night1"} | {"night1": out["night1"]}
    assert out["report_matches_audit"] and out["second_night_all_skipped_by_checkpoint"] and out["yields"] >= 1
    assert out["refusals"] == ["screen_locked", "engine_wait"] and out["approval_items"] == 3
