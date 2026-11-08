"""RD (7 Nov 2026): the live coach on the deeper role packs. A critical gate speaks when its follower is started without it, and cogs that have
never been seen in any data (no synthetic traces exist for the new cogs) pass through the coach as quietly as any other event."""
from __future__ import annotations

import pytest

from understudy_engine.coach import CoachBrain, StuckScorer
from understudy_engine.store import EventStore

from .helpers import ev


@pytest.fixture()
def brain(tmp_path):
    return CoachBrain(EventStore(tmp_path / "d"), scorer=StuckScorer(fit=False), tone="short")


def case(role: str, steps: list[tuple[float, str, str]], task: str = "t_rd1", person: str = "p_rd"):
    """task_start, then (dt, event type, zone) steps, as a capture with markers would send them."""
    out = [ev(0, "task_start", task=task, source="desk", role=role, person=person)]
    out += [ev(dt, typ, zone, task=task, role=role, person=person) for dt, typ, zone in steps]
    return out


def run(brain, events, person="p_rd"):
    return [(e, brain.next_step(person, e.t, events=events[: i + 1])) for i, e in enumerate(events)]


def spoke(trace):
    return [(e, d) for e, d in trace if d.action != "silent"]


def test_programmer_bisecting_without_reproducing_is_asked_to_reproduce_first(brain):
    events = case("programmer", [(2, "scroll", "ci_log"), (12, "scroll", "ci_log"), (22, "click", "history_view"), (28, "scroll", "history_view")])
    fired = spoke(run(brain, events))
    assert fired, "the critical gate reproduce_locally should have been spoken for"
    _, d = fired[0]
    assert d.missed[0] == "reproduce_locally" and d.candidate["step"] == "reproduce_locally"
    assert d.target is None or d.target["zone"] == "repro_console"       # the ring, if drawn, is on the terminal zone of the missed step
    assert "reproduce" in d.message.lower() or "own machine" in d.message.lower()


def test_analyst_writing_the_finding_before_checking_the_scale_is_asked_to_trace_the_source_first(brain):
    events = case("data-analyst", [(2, "click", "profile_panel"), (12, "click", "run_control"), (25, "focus", "finding_editor"), (31, "paste", "finding_editor")], person="p_rd")
    fired = spoke(run(brain, events))
    assert fired
    _, d = fired[0]
    assert d.missed[0] == "trace_source"                                   # the first critical gate that can be done now, in policy order


@pytest.mark.parametrize("role,zone", [("programmer", "prod_logs"), ("programmer", "profiler_view"), ("data-analyst", "lineage_view"), ("data-analyst", "schedule_panel")])
def test_a_cog_that_has_never_been_seen_in_any_data_does_not_crash_the_coach(brain, role, zone):
    events = case(role, [(2, "click", zone), (8, "scroll", zone), (20, "click", zone)])
    trace = run(brain, events)
    assert len(trace) == len(events)
    assert all(d.action in ("silent", "nudge", "annotate", "takeover_offer") for _, d in trace)


@pytest.mark.parametrize("role", ["programmer", "data-analyst", "benefits-processor"])
def test_the_overall_level_averages_required_critical_cogs_only(brain, role):
    """An optional critical gate is spoken for when its follower starts; it is not part of the person's overall level, so a pack that adds gates
    leaves that level exactly as the frozen checks made it."""
    bundle = brain._bundle(role)
    st = brain._state("p_overall")
    _, _, mastery = brain._overall(st, bundle, 0.0)
    required_critical = {c for s in bundle.policy.steps.values() if s.critical and s.required for c in s.cogs}
    optional_gates = {c for s in bundle.policy.steps.values() if s.critical and not s.required for c in s.cogs}
    assert set(mastery) == required_critical and not set(mastery) & optional_gates
    if role != "benefits-processor":
        assert optional_gates


def test_a_frozen_task_that_never_touches_a_new_cog_hears_nothing_new(brain):
    """The first programmer step set: read the trace, run the tests, then commit. No new cog occurs, so no new step is mentioned."""
    events = case("programmer", [(2, "scroll", "ci_log"), (12, "scroll", "ci_log"), (25, "click", "test_runner"), (40, "click", "code_editor"), (80, "click", "diff_view"), (95, "click", "commit_box")])
    new_steps = {"reproduce_locally", "bisect_change", "add_logging", "write_commit_msg", "open_pr", "read_ci", "answer_review", "review_peer_pr", "watch_prod",
                 "roll_back_safely", "profile_hot_path", "write_migration"}
    for _, d in run(brain, events):
        assert not (set(d.missed or []) & new_steps) and (d.candidate or {}).get("step") not in new_steps
