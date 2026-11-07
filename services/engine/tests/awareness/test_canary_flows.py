"""The image canary flows run over eight seeds, as the privacy evaluation does: the planted frame must leave no residue anywhere."""
from __future__ import annotations

import pytest

from understudy_engine.awareness import canary_flows
from understudy_engine.privacy.evaluate import discover_image_flows
from understudy_engine.privacy.testing import ImageCanaryFlow, image_canary_flow

SEEDS = range(8)


def test_the_flows_are_discoverable_by_the_privacy_evaluation():
    flows = [f for f in discover_image_flows() if f.layer == "awareness"]
    assert len(flows) == len(canary_flows.IMAGE_FLOWS) >= 8
    assert all(isinstance(f, ImageCanaryFlow) for f in flows)
    assert canary_flows.FLOWS == []


@pytest.mark.parametrize("flow", canary_flows.IMAGE_FLOWS, ids=lambda f: f.name)
def test_no_seed_leaves_any_residue_of_the_planted_frame(flow):
    for seed in SEEDS:
        out = image_canary_flow(flow.name, flow.run, seed=seed, strict=False)
        assert out["residue"] == [], (flow.name, seed, out["residue"][:3])
        assert out["ok"] is True


def test_the_open_gate_flow_really_sends_one_frame_and_the_closed_ones_send_none():
    sent = image_canary_flow(canary_flows.IMAGE_FLOWS[0].name, canary_flows.IMAGE_FLOWS[0].run, seed=1, strict=True)
    assert sent["requests"] == 1 and sent["ledger_rows"] == 1
    for flow in canary_flows.IMAGE_FLOWS[1:5]:
        out = image_canary_flow(flow.name, flow.run, seed=1, strict=True)
        assert out["requests"] == 0, flow.name


@pytest.mark.parametrize("flow", canary_flows.IMAGE_FLOWS, ids=lambda f: f.name)
def test_each_flow_itself_behaves_as_it_says_not_only_leaves_no_residue(flow):
    """image_canary_flow records an exception as text and carries on, so a flow whose own assertion fails would still look clean. Run it bare."""
    from understudy_engine.privacy import canary
    from understudy_engine.privacy.testing import CapturingPort

    flow.run(canary.plant_image(3), CapturingPort())
