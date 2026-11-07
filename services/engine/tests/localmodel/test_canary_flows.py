"""The canary flows the privacy evaluation runs (PRV-1, PRV-4), checked here the same way: eight seeds, zero leaks."""
from __future__ import annotations

import pytest

from understudy_engine.localmodel import canary_flows, config, digest, server
from understudy_engine.privacy import testing
from understudy_engine.privacy.testing import hermetic


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """The privacy kit's hermetic environment (own data dir and home, mock off) but with no model: rules path."""
    hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL", str(tmp_path / "nope" / "missing.gguf"))
    server._server = None
    return tmp_path


def test_flows_are_declared_for_this_layer():
    assert [f.name for f in canary_flows.FLOWS] == ["localmodel.digest_pipeline", "localmodel.digest_pipeline_leaky_model"]
    assert all(f.layer == "localmodel" and f.mode == "append" for f in canary_flows.FLOWS)


@pytest.mark.parametrize("seed", range(8))
def test_every_flow_leaks_nothing_with_the_rules_path(isolated, seed):
    for flow in canary_flows.FLOWS:
        r = testing.run_flow(flow, seed=seed)
        assert r.error is None, r.error
        assert r.planted > 0 and r.requests >= flow.min_requests, r
        assert r.leaked == 0 and r.artifact_leaked == 0, (flow.name, r.leaked_kinds)
        assert r.ledger_complete, r.note


@pytest.mark.parametrize("seed", range(3))
def test_every_flow_leaks_nothing_with_the_model_path_and_its_log(stub, monkeypatch, tmp_path, seed):
    hermetic(monkeypatch, tmp_path)                                    # keeps the stub's model and binary settings
    monkeypatch.setenv("UNDERSTUDY_X_LOCALMODEL", "1")
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL", str(stub.model_path))
    server._server = None
    for flow in canary_flows.FLOWS:
        r = testing.run_flow(flow, seed=seed)
        assert r.error is None, r.error
        assert r.leaked == 0 and r.artifact_leaked == 0 and r.ledger_complete, (flow.name, r.leaked_kinds, r.note)
    assert digest.last_run()["source"] in ("model", "rules")
    assert config.log_path().exists()


def test_the_pipeline_flow_really_used_the_model_when_available(stub):
    from understudy_engine.privacy.testing import CapturingPort

    fx = canary_flows.make_fixtures()
    canary_flows.run(fx, CapturingPort())
    assert digest.last_run()["source"] == "model"


def test_the_leaky_control_is_fully_rejected(isolated):
    r = testing.run_flow(canary_flows.FLOWS[1], seed=3)
    assert r.error is None and r.leaked == 0 and r.requests == 2


def test_meta_payload_is_counts_and_minutes_only():
    from understudy_engine.localmodel.bridge import meta_payload

    p = meta_payload("event", [{"category": "one_to_one", "duration_bucket": "30to59"}, {"category": "focus", "duration_bucket": "180plus"},
                               {"category": "social", "duration_bucket": "60to89"}])
    assert p == {"kind": "event", "window_days": 7, "counts": {"meeting": 1, "focus": 1, "other": 1}, "minutes": {"meeting": 45, "focus": 240, "other": 75}}
    assert meta_payload("commit", [{"category": "fix"}, {"category": "fix"}])["counts"] == {"bugfix": 2}


def test_privacy_vocabularies_are_clean():
    testing.assert_vocabularies_clean()
