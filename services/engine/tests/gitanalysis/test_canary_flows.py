"""The privacy track's discovery contract (``gitanalysis/canary_flows.py``) and the plugin manifest."""
from __future__ import annotations

from pathlib import Path

import pytest

from understudy_engine.gitanalysis import canary_flows
from understudy_engine.privacy.testing import CanaryFlow, assert_vocabularies_clean, run_flow


def test_flows_are_registered_the_way_the_privacy_track_expects():
    assert len(canary_flows.FLOWS) >= 1
    for f in canary_flows.FLOWS:
        assert isinstance(f, CanaryFlow) and f.layer == "git" and f.min_requests >= 1
        fx = f.make_fixtures()
        assert fx is not f.make_fixtures()                       # fresh fixtures every call


@pytest.mark.parametrize("seed", range(8))
def test_real_flow_leaks_nothing_across_seeds(service_env, seed):
    flow = canary_flows.FLOWS[0]
    r = run_flow(flow, seed=seed)
    assert r.error is None, r.error
    assert r.requests >= 1 and r.planted >= 10
    assert r.leaked == 0 and r.leaked_kinds == []
    assert r.ledger_complete and r.ledger_lines == r.ledger_expected == r.requests, r.note
    assert {"person_name", "email", "commit_message", "file_path", "customer_name"} <= set(r.by_kind)


def test_vocabularies_and_purposes_are_clean_after_the_git_layer_extended_them(service_env):
    from understudy_engine.gitanalysis import suggest
    from understudy_engine.privacy.testing import CapturingPort
    # a wording call registers the extra habit id first; the whole vocabulary set must still pass the backstop
    rows = [{"id": "vague_messages", "label": "x", "learner": 0.5, "expert": 0.04, "delta": 0.46, "ci": [0.3, 0.6], "bad": 1, "min_delta": 0.15,
             "n_den": 40, "n_num": 20, "flagged": True, "reason": "flagged"}]
    suggest.reword(suggest.select(rows), rows, port=CapturingPort())
    assert_vocabularies_clean()


def test_the_manifest_is_valid_and_loads_our_class(learner_repo):
    from understudy_engine.plugins import loader
    from understudy_engine.gitanalysis.source import GitSource
    manifest = Path(loader.BUILTIN_DIR) / "git" / "plugin.yaml"
    res = loader.validate_paths([manifest])
    assert res[0].ok, res[0].problems
    src = loader.load_source("git", repo=learner_repo)
    assert isinstance(src, GitSource) and next(iter(src.read())).kind == "commit"
