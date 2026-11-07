"""The extension, the engine's cog mapping, the pack validator and the sandbox pages must agree on the zone vocabulary and on what each zone means."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from evals.study_roles import experts as X
from evals.study_roles.roles import PACKS, REPO, cfg

STATIC = {"programmer": REPO / "services/agent/understudy_agent/sandbox_roles/programmer/static/programmer.js",
          "data-analyst": REPO / "services/agent/understudy_agent/sandbox_roles/analyst/static/analyst.js"}
NEW_COGS = {"programmer": {"PROBE_EDGE": "edge_probe", "INSPECT_INPUT": "input_data", "WRITE_TEST": "test_editor"},
            "data-analyst": {"CLEAN_DATA": "clean_panel", "RECONCILE_CONTROL": "control_panel", "GROUP_AGG": "pivot_panel"}}


def page_zones(role: str) -> set[str]:
    src = STATIC[role].read_text()
    zones = set(re.findall(r'data-understudy-zone="([a-z_]+)"', src)) | set(re.findall(r"zone: '([a-z_]+)'", src))
    zones |= set(re.findall(r"'(code_editor|test_editor)'", src))
    return zones


def test_every_zone_a_page_uses_is_in_the_pack_vocabulary_and_in_the_extension_bundle(role):
    pack = yaml.safe_load((PACKS / role / "mapping.yaml").read_text())
    bundle = json.loads((REPO / "extension/src/generated/bundled.json").read_text())
    used = page_zones(role)
    assert used and used <= set(pack["zones"]), used - set(pack["zones"])
    assert used <= set(bundle["zones"]["vocabulary"]), used - set(bundle["zones"]["vocabulary"])


def test_the_bundle_has_the_role_capture_sites_on_the_private_ports_with_markers(role):
    bundle = json.loads((REPO / "extension/src/generated/bundled.json").read_text())
    site = next(s for s in bundle["zones"]["sites"] if s["pack"] == role and s["id"] == "roles_sandbox")
    ports = range(7941, 7949) if role == "programmer" else range(7951, 7959)
    assert {f"127.0.0.1:{p}" for p in ports} <= set(site["hosts"])
    assert site["markers"]["task_start"] and site["markers"]["task_end"]["when"] == "#case-done" and site["markers"]["progress"]


def test_the_engine_mapping_turns_each_new_zone_into_its_cog(role):
    from understudy_engine.cogs import to_cogs
    from understudy_engine.core import Event
    from understudy_engine.packs import load_pack

    mp = load_pack(role).cog_mapping()
    for cog, zone in NEW_COGS[role].items():
        ev = Event.model_validate({"schema": 1, "id": "e1", "t": "2026-11-07T10:00:00Z", "origin": "real", "actor": "human", "person": "p_x1", "role": role, "source": "browser",
                                   "type": "click", "meta": {"zone": zone}})
        assert [c.id for c in to_cogs([ev], mp)] == [cog], (cog, zone)
        assert cog in load_pack(role).extra_cogs


def test_the_sandbox_navigation_zones_map_to_cogs(role):
    from understudy_engine.cogs import to_cogs
    from understudy_engine.core import Event
    from understudy_engine.packs import load_pack

    mp = load_pack(role).cog_mapping()
    navs = {"programmer": {"test_report": "READ_TRACE", "commit_box": "COMMIT", "decision_btn": "DECIDE"},
            "data-analyst": {"profile_panel": "PROFILE_DATA", "pivot_panel": "GROUP_AGG", "control_panel": "RECONCILE_CONTROL", "clean_panel": "CLEAN_DATA", "decision_btn": "DECIDE"}}[role]
    for zone, cog in navs.items():
        ev = Event.model_validate({"schema": 1, "id": "e1", "t": "2026-11-07T10:00:00Z", "origin": "real", "actor": "human", "person": "p_x1", "role": role, "source": "browser",
                                   "type": "nav", "meta": {"zone": zone, "spa": True}})
        assert [c.id for c in to_cogs([ev], mp)] == [cog], (zone, cog)


def test_every_critical_study_step_target_is_a_zone_with_a_page_element_or_is_documented(role):
    """The coach targets the zone of the step's first cog. Those zones exist on the pages (test_editor only while the test file is open: a documented limit)."""
    from understudy_engine.cogs import load_mapping
    from understudy_engine.coach.messages import target_for
    from understudy_engine.coach.steps import StepPolicy
    from understudy_engine.packs import load_pack

    pk = load_pack(role)
    policy = StepPolicy.from_pack(pk)
    mp = pk.cog_mapping()
    page = page_zones(role)
    for step, zones in cfg(role).follow_zones.items():
        tgt = target_for(policy.steps[step], mp)
        assert tgt["zone"] in zones and tgt["zone"] in page, (step, tgt)


def test_expert_plan_covers_every_task_and_is_deterministic(role):
    plan = X.expert_plan(role, 8)
    assert plan == X.expert_plan(role, 8) and len(plan) == 8 and set(t for t, _, _ in plan) == set(cfg(role).sandbox.TASKS)
    assert {v for _, v, _ in plan} == {1, 2} and len({(t, v) for t, v, _ in plan}) == 8


def test_synthetic_expert_cogs_follow_the_pack_mapping(role):
    ev = lambda i, t, typ, zone: {"schema": 1, "id": f"e{i}", "t": f"2026-11-07T10:{t // 60:02d}:{t % 60:02d}Z", "origin": "real", "actor": "human", "person": "p_x1", "role": role, "source": "browser", "type": typ, "meta": {"zone": zone}}  # noqa: E731
    zones = {"programmer": ["test_runner", "input_data", "code_editor", "edge_probe", "diff_view", "commit_box"], "data-analyst": ["profile_panel", "clean_panel", "control_panel", "pivot_panel"]}[role]
    events = [ev(i, i * 20, "click", z) for i, z in enumerate(zones)]
    cogs = [c["cog"] for c in X.events_to_cogs(role, events) if c["cog"] != "IDLE"]        # silences of more than 15 s become IDLE segments
    want = {"programmer": ["RUN_TESTS", "INSPECT_INPUT", "EDIT_CODE", "PROBE_EDGE", "REVIEW_DIFF", "COMMIT"], "data-analyst": ["PROFILE_DATA", "CLEAN_DATA", "RECONCILE_CONTROL", "GROUP_AGG"]}[role]
    assert cogs == want
