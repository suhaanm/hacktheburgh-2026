"""The role-generic coach rules: step -> skill from the PACK, following by zone, false and lagging prompts, study-mode violations."""
from __future__ import annotations

from evals.study_roles import roles as R
from evals.study_roles.coach_roles import NudgeCounts, Rules, Shown, target_step
from evals.study_sim.coach import Mode
from evals.study_sim.observe import Executed


def ex(kind="click", zone="", t=0.0, ok=True):
    e = Executed(t=t, kind=kind, ok=ok)
    e.extra["zone"] = zone
    return e


def test_step_to_skill_map_comes_from_the_pack():
    assert R.step_skill_key("programmer", "probe_edges") == "boundary" and R.step_skill_key("programmer", "inspect_inputs") == "missing"
    assert R.step_skill_key("programmer", "write_failing_test") == "discipline" and R.step_skill_key("programmer", "review_diff") == "discipline"
    assert R.step_skill_key("programmer", "edit_and_commit") is None and R.step_skill_key("programmer", None) is None
    assert R.step_skill_key("data-analyst", "profile_inputs") == "sanity" and R.step_skill_key("data-analyst", "reconcile_to_control") == "reconcile"
    assert R.step_skill_key("data-analyst", "segment_breakdown") == "aggregation"


def test_every_follow_step_is_a_real_critical_step_of_its_skill(role):
    steps = R.pack_steps(role)
    for step, zones in R.cfg(role).follow_zones.items():
        assert step in steps and steps[step]["critical"] and R.step_skill_key(role, step) in R.cfg(role).skills and zones
    for skill in R.cfg(role).skills:
        assert R.expected_zones(role, skill)


def test_the_pack_zones_for_each_followed_step_exist_in_the_sandbox_pages(role):
    import yaml
    pack = yaml.safe_load((R.PACKS / role / "mapping.yaml").read_text())
    for zones in R.cfg(role).follow_zones.values():
        assert set(zones) <= set(pack["zones"])


def test_following_is_an_action_in_the_steps_zone():
    r = Rules("programmer")
    assert r.followed_by("probe_edges", ex("fill", "edge_probe")) and r.followed_by("probe_edges", ex("click", "edge_probe"))
    assert not r.followed_by("probe_edges", ex("click", "test_runner")) and not r.followed_by("probe_edges", ex("click", "edge_probe", ok=False))
    assert not r.followed_by("probe_edges", ex("wait", "edge_probe")) and not r.followed_by(None, ex("click", "edge_probe"))
    assert r.followed_by("write_failing_test", ex("fill", "test_editor")) and not r.followed_by("write_failing_test", ex("fill", "code_editor"))
    a = Rules("data-analyst")
    assert a.followed_by("segment_breakdown", ex("select", "pivot_panel")) and a.followed_by("reconcile_to_control", ex("click", "control_panel"))


def test_false_and_lagging_prompts():
    r = Rules("programmer")
    done = [ex("click", "edge_probe", t=10.0)]
    assert r.false_nudge("probe_edges", done, t=11.0) == "lag" and r.false_nudge("probe_edges", done, t=30.0) == "false"
    assert r.false_nudge("probe_edges", [], t=30.0) == "" and r.false_nudge("probe_edges", [ex("click", "edge_probe", t=40.0)], t=30.0) == ""


def test_study_mode_violations():
    r = Rules("programmer")
    d = {"action": "annotate", "missed": ["probe_edges"]}
    assert r.violation_of(Mode("train", "boundary", "x"), d) == ""
    assert "while only missing" in r.violation_of(Mode("train", "missing", "x"), d)
    assert "post_test" in r.violation_of(Mode("post_test", None, "x"), d) and "off" in r.violation_of(Mode("off", None, "x"), d)
    assert r.violation_of(Mode("post_test", None, "x"), {"action": "silent"}) == ""
    assert "edit_and_commit" in r.violation_of(Mode("train", "boundary", "x"), {"action": "nudge", "missed": ["edit_and_commit"]})


def test_target_step_prefers_missed_then_candidate_then_step():
    assert target_step({"missed": ["a"], "step": "b"}) == "a" and target_step({"candidate": {"step": "c"}, "step": "b"}) == "c" and target_step({"step": "b"}) == "b"


def test_nudge_counts_zone_ok_and_ring():
    sh = Shown("d1", "annotate", "m", "edge_probe", "probe_edges", "boundary", ["probe_edges"], "expert_policy", 0.0, 0.0, ring_found=True, outcome="followed", false="")
    sh2 = Shown("d2", "annotate", "m", "code_editor", "probe_edges", "boundary", [], "expert_policy", 0.0, 0.0, ring_found=False, outcome="ignored", false="lag")
    c = NudgeCounts.of([sh, sh2], "programmer")
    assert (c.shown, c.followed, c.ignored, c.dismissed, c.rings_drawn, c.banners_only, c.zone_ok, c.lag_prompts) == (2, 1, 1, 1, 1, 1, 1, 1)
