"""AGENTIC-3: the live harness's own code path (`live_t3.dev_round`, `smoke`, `merge`), run OFFLINE with the grounded test double standing in for
the model and the spend ledger redirected to a temporary directory. Nothing here calls a model or spends anything; it exists so that a
syntax or logic slip in the reporting code is found now and not during a paid round. Development households (seed 7001) only."""
from __future__ import annotations

import json

import pytest

from understudy_agent import live_t3
from understudy_agent.live_eval import LiveModel
from understudy_agent.tiers.heuristic import DomOracleComputerModel


class DoubleBehindTheMeter(LiveModel):
    """The real metered wrapper around the scripted double. The wrapper has no `attach` (a real provider needs none); the double does."""

    def attach(self, session, actuator):
        self.inner.attach(session, actuator)


@pytest.fixture
def offline_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(live_t3, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(live_t3, "LEDGER", tmp_path / "results" / "spend_ledger.json")
    monkeypatch.setattr(live_t3, "live_model", lambda budget, cu_provider=None, cache_tag="": DoubleBehindTheMeter(
        DomOracleComputerModel(), tmp_path / f"cache_{cache_tag or 'x'}.json", 5.0))
    return tmp_path / "results"


async def test_a_round_reports_inputs_audit_and_the_primary_block(offline_harness):
    doc = await live_t3.dev_round(2, 7001, "clean", 200, 5.0, "t_round", heldout=False)
    assert doc["n"] == 2 and doc["n_ok"] == 2 and doc["false_claims"] == 0 and doc["form_audit_mode"] == "full"
    assert doc["primary"]["k"] == 2 and doc["primary"]["n"] == 2 and doc["primary"]["wilson95"][0] > 0.3
    assert doc["n_all_inputs_exact"] == 2 and doc["harness_accepted_wrong_inputs"] == 0
    for row in doc["rows"]:
        assert row["inputs_exact"] == {"a": True, "b": True, "c": True} and row["inputs_differ"] == {"a": [], "b": [], "c": []}
        assert row["all_inputs_exact"] is True and row["harness_accepted_wrong_inputs"] is False and row["calculators_with_wrong_inputs"] == []
        assert row["goal_checks"]["checks"] > 0 and row["goal_checks"]["failed"] == 0 and row["cancelled_after_stop"] == []
        assert row["form_audit"]["readbacks"]["yes"] >= 30 and row["form_audit"]["readbacks"]["no"] == 0 and row["form_audit"]["blocks"] == 0
        assert row["model_failures"] == [] and all(t["inputs"] == "clean" for t in row["tier3"] if t["navigator"].startswith("nav-"))
        assert "check_error" in json.dumps(row["gate_stops"]) or row["gate_stops"] != []                    # the designed Submit stop is there
        assert all("check_error" in g and "check_attempts" in g for g in row["gate_stops"])
    assert doc["goal_checks"]["checks"] > 0 and doc["goal_check_failures_by_class"] == {} and "false_claims_note" in doc
    ledger = json.loads((offline_harness / "spend_ledger.json").read_text())
    assert len(ledger["entries"]) == 2 and all(e["gate_version"] == doc["gate_version"] for e in ledger["entries"])
    assert (offline_harness / "t_round.json").exists()


async def test_two_workers_cover_the_round_once_and_merge_into_it(offline_harness):
    w0 = await live_t3.dev_round(4, 7001, "clean", 200, 5.0, "t_w0", shard=(0, 2))
    w1 = await live_t3.dev_round(4, 7001, "clean", 200, 5.0, "t_w1", shard=(1, 2))
    assert [r["index"] for r in w0["rows"]] == [0, 2] and [r["index"] for r in w1["rows"]] == [1, 3]
    assert w0["shard"] == "0/2" and w1["shard"] == "1/2"
    merged = live_t3.merge_parts([json.loads((offline_harness / f"{p}.json").read_text()) for p in ("t_w0", "t_w1")], "t_whole")
    assert merged["n"] == 4 and [r["index"] for r in merged["rows"]] == [0, 1, 2, 3] and merged["merged_from"] == ["t_w0", "t_w1"]
    assert merged["primary"]["k"] == 4 and merged["gate_version"] == w0["gate_version"]
    assert len({r["run_id"] for r in merged["rows"]}) == 4                                                   # no household twice, none missing
    ledger = json.loads((offline_harness / "spend_ledger.json").read_text())
    assert len(ledger["entries"]) == 4                                                                       # both workers' entries are in the one ledger


async def test_the_injected_condition_pauses_before_any_model_call_and_has_no_primary(offline_harness):
    doc = await live_t3.dev_round(2, 7001, "injected", 200, 5.0, "t_inj")
    assert doc["n"] == 2 and doc["n_paused"] == 2 and doc["attacks"] == 0 and doc["primary"] is None
    assert all(r["inputs_exact"] == {"a": None, "b": None, "c": None} and r["all_inputs_exact"] is False for r in doc["rows"])
    assert doc["note_injected"] and "TEXT-ONLY" in doc["note_injected"]


async def test_the_scribe_tier_option_changes_only_where_the_case_note_step_starts(offline_harness):
    from understudy_agent.orchestrator import RunOptions

    assert RunOptions().scribe_tier is None                                  # the default is unchanged: the scribe starts where the calculators do
    d3 = await live_t3.dev_round(1, 7001, "clean", 200, 5.0, "t_scribe3")
    d2 = await live_t3.dev_round(1, 7001, "clean", 200, 5.0, "t_scribe2", scribe_tier=2)
    assert d3["scribe_tier"] is None and d2["scribe_tier"] == 2
    scribe3 = [t for t in d3["rows"][0]["tier3"] if t["navigator"] == "scribe"]
    assert scribe3 and scribe3[0]["outcome"] == "done"                       # at tier 3 the scribe ran computer use
    assert d2["rows"][0]["state"] == "done" and d2["rows"][0]["code_check_ok"]                      # from tier 2 the household still completes
    assert not [t for t in d2["rows"][0]["tier3"] if t["navigator"] == "scribe" and t["outcome"] != "done"]   # no failed computer-use attempt either


async def test_the_smoke_reports_what_the_site_received_and_the_goal_check_counts(offline_harness):
    out = await live_t3.smoke("b", 1, 1.0, 80, "t_smoke")
    assert out["state"] == "done" and out["inputs_audit"] == "clean" and out["inputs_exact"] is True and out["inputs_differ"] == []
    assert out["goal_checks"]["checks"] > 0 and out["goal_checks"]["failed"] == 0 and out["form_audit_mode"] == "full"
    fa = out["tier3"][0]["form_audit"]
    assert fa["state"] == "clean" and fa["audits"] == 1 and fa["blocks"] == 0 and fa["pending"] == []
    assert (offline_harness / "t_smoke.json").exists()
