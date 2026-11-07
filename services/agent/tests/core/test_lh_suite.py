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
