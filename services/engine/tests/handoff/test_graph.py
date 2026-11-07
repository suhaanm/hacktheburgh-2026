"""VIS-3: the work graph. Link when related, combine when two routines always run together and look alike, fade with disuse."""
from __future__ import annotations

import pytest

from understudy_engine.memory import MemoryStore, load_pack, onboard
from understudy_engine.routines.graph import build_work_graph, co_occurrence, fade
from understudy_engine.routines.store import RoutineStore

from .test_routine_store import _routine

DAY = 86400.0
NOW = 1_800_000_000.0


def _r(rid, sig, t0s, last_seen, mpw=60.0):
    r = _routine(rid, template=None)
    r.update({"signature": sig, "member_t0": t0s, "last_seen": last_seen, "minutes_per_week": mpw, "episodes": len(t0s)})
    return r


@pytest.fixture
def env(tmp_path):
    mem = MemoryStore(tmp_path / "home")
    onboard(mem, "benefits-processor", {})
    return mem, RoutineStore(mem, bundle_root=tmp_path / "r")


def _links(g, kind):
    return {frozenset((l["a"], l["b"])) for l in g["links"] if l["kind"] == kind}


def test_co_occurrence_counts_nearby_runs_both_ways():
    a = [0.0, 1000.0, 2000.0, 90000.0]
    b = [30.0, 1100.0, 2200.0]
    pa, pb = co_occurrence(a, b, window=600)
    assert pa == 0.75 and pb == 1.0
    assert co_occurrence([], b) == (0.0, 0.0)


def test_routines_that_always_run_together_and_look_alike_are_combined_others_only_related(env):
    mem, st = env
    times = [NOW - i * DAY for i in range(10)]
    a = _r("auto-aaaaaa", ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "COPY_TO_NOTE"], times, NOW)
    b = _r("auto-bbbbbb", ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "RECONCILE"], [t + 200 for t in times], NOW)
    c = _r("auto-cccccc", ["NAVIGATE", "READ", "CHECK", "DECIDE"], [t + 4 * 3600 for t in times], NOW)            # same days, far apart in time, different steps
    d = _r("auto-dddddd", ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "COPY_TO_NOTE"], [t + 30000 for t in times], NOW)  # alike steps, never together
    st.merge([a, b, c, d])
    g = build_work_graph(st, mem.read(), load_pack("benefits-processor"), NOW)
    combined, related = _links(g, "combined"), _links(g, "related")
    assert frozenset(("routine:auto-aaaaaa", "routine:auto-bbbbbb")) in combined
    assert not any("routine:auto-cccccc" in pair for pair in combined)
    assert frozenset(("routine:auto-aaaaaa", "routine:auto-dddddd")) not in combined                              # alike but not together: related at most
    assert frozenset(("routine:auto-aaaaaa", "routine:auto-dddddd")) in related
    w = [l["weight"] for l in g["links"] if l["kind"] == "combined"]
    assert w and all(0.8 <= x <= 1.0 for x in w)


def test_strength_fades_with_disuse_along_a_half_life_curve(env):
    mem, st = env
    times = [NOW - i * DAY for i in range(5)]
    st.merge([_r("auto-fresh1", ["READ", "COPY", "PASTE", "CHECK"], times, NOW), _r("auto-stale1", ["NAVIGATE", "ENTER", "COPY", "PASTE"], times, NOW - 42 * DAY)])
    pack = load_pack("benefits-processor")
    g = build_work_graph(st, mem.read(), pack, NOW)
    nodes = {n["id"]: n for n in g["nodes"]}
    half = float(pack.priors["mastery"]["decay_half_life_days"])
    assert nodes["routine:auto-fresh1"]["strength"] == pytest.approx(1.0)
    assert nodes["routine:auto-stale1"]["strength"] == pytest.approx(fade(42, half), abs=0.01)
    assert nodes["routine:auto-stale1"]["strength"] < 0.3
    assert fade(half, half) == pytest.approx(0.5) and fade(0, half) == 1.0


def test_every_node_has_why_editable_and_line_id_and_automation_follows_consent(env):
    mem, st = env
    st.merge([_r("auto-aaaaaa", ["READ", "COPY", "PASTE", "CHECK"], [NOW - i * DAY for i in range(5)], NOW)])
    pack = load_pack("benefits-processor")
    g = build_work_graph(st, mem.read(), pack, NOW)
    assert {"routine", "skill", "memory"} <= {n["type"] for n in g["nodes"]} and not [n for n in g["nodes"] if n["type"] == "automation"]
    for n in g["nodes"]:
        assert n["why"] and isinstance(n["editable"], bool) and "memory_line_id" in n and 0 <= n["strength"] <= 1
    st.consent("auto-aaaaaa", "shadow", skill_override=True, actor="worker")
    g = build_work_graph(st, mem.read(), pack, NOW)
    auto = [n for n in g["nodes"] if n["type"] == "automation"]
    assert len(auto) == 1 and auto[0]["memory_line_id"] and any(l["kind"] == "related" and {l["a"], l["b"]} == {"routine:auto-aaaaaa", "automation:auto-aaaaaa"} for l in g["links"])
    # a memory node links to the routine its line names
    mem_ids = {n["memory_line_id"]: n["id"] for n in g["nodes"] if n["type"] == "memory"}
    assert auto[0]["memory_line_id"] not in mem_ids      # Routines lines are shown as automation nodes, not as plain memory nodes
