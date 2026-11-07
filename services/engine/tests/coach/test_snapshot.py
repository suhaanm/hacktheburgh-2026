from __future__ import annotations

import dataclasses

import pytest

from understudy_engine.coach import CoachBrain, CoachSnapshot, CogView, SkillView, StuckScorer
from understudy_engine.store import EventStore

from .helpers import expert_task, signature_events


@pytest.fixture()
def brain(tmp_path):
    return CoachBrain(EventStore(tmp_path / "d"), scorer=StuckScorer(fit=False), tone="short")


def test_snapshot_of_an_open_case(brain):
    evs = signature_events()
    brain.feed("p_hand", evs)
    now = evs[-1].t.timestamp() + 1
    s = brain.snapshot("p_hand", now, sync=False)
    assert isinstance(s, CoachSnapshot) and s.person == "p_hand" and s.role == "benefits-processor" and s.origin == "synthetic"
    assert s.task_open and s.task_id == "t_h1" and not s.implicit and s.tasks_finished == 0
    assert [c.id for c in s.cogs] == ["READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "COPY_TO_NOTE"]
    assert s.current_cog == "COPY_TO_NOTE" and all(isinstance(c, CogView) and c.t0 > 0 for c in s.cogs) and [c.t0 for c in s.cogs] == sorted(c.t0 for c in s.cogs)
    prog = next(e for e in evs if e.type == "progress")
    assert s.last_progress_t == pytest.approx(prog.t.timestamp()) and s.last_input_t == pytest.approx(evs[-1].t.timestamp())
    assert 0.0 <= s.p_stuck <= 1.0 and s.p_source == "rule"                         # no model fitted here: the time-since-progress rule


def test_snapshot_is_immutable_and_carries_no_events(brain):
    evs = signature_events()
    brain.feed("p_hand", evs)
    s = brain.snapshot("p_hand", evs[-1].t.timestamp() + 1, sync=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.p_stuck = 0.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.cogs[0].id = "X"  # type: ignore[misc]
    assert isinstance(s.cogs, tuple) and isinstance(s.skills, tuple)
    flat = repr(s)
    assert "Event(" not in flat and "meta" not in flat and "zone" not in flat and "task_start" not in flat   # ids and times only
    for f in dataclasses.fields(s):
        v = getattr(s, f.name)
        assert not isinstance(v, (list, dict, set)), f.name


def test_snapshot_changes_nothing(brain, tmp_path):
    evs = signature_events()
    brain.feed("p_hand", evs)
    now = evs[-1].t.timestamp()
    st = brain._people["p_hand"]
    before = (st.gate, len(st.open), st.last_key, dict(st.prompted), len(brain._records))
    for _ in range(3):
        brain.snapshot("p_hand", now, sync=False)
    assert (st.gate, len(st.open), st.last_key, dict(st.prompted), len(brain._records)) == before
    assert not [e for e in brain.store.read("synthetic", person="p_hand") if e.source == "coach"]       # nothing written
    d = brain.next_step("p_hand", now, commit=False)
    assert d.action == "silent"                                                                           # and the gate has not been advanced by looking


def test_snapshot_reports_level_and_mastery_per_cog_after_finished_cases(brain):
    hist = []
    for k in range(3):
        hist += expert_task(f"t_c{k}", 1000 * k)
    brain.feed("p_hand", hist)
    s = brain.snapshot("p_hand", hist[-1].t.timestamp() + 5, sync=False)
    assert not s.task_open and s.cogs == () and s.p_stuck is None and s.p_source is None and s.tasks_finished == 3
    by = {k.cog: k for k in s.skills}
    assert isinstance(by["CHECK_CLIFF"], SkillView) and by["CHECK_CLIFF"].level == 2 and 0.0 < by["CHECK_CLIFF"].mastery <= 1.0     # three clean cases: L1 -> L2
    assert set(by) >= {"CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE", "READ_RESULT"} and list(by) == sorted(by)


def test_snapshot_reads_the_store_and_unknown_people_are_empty(brain):
    s = brain.snapshot("p_nobody", 1.0e9)
    assert not s.task_open and s.cogs == () and s.last_input_t is None and s.skills == () and s.p_stuck is None
    evs = signature_events()
    for e in evs:
        brain.store.append(e)
    fresh = CoachBrain(EventStore(brain.store.root), scorer=StuckScorer(fit=False))
    s2 = fresh.snapshot("p_hand", evs[-1].t.timestamp() + 1)                                              # sync from the store
    assert s2.task_open and s2.current_cog == "COPY_TO_NOTE" and s2.last_input_t is not None


def test_snapshot_marks_an_implicit_case(brain):
    from .test_implicit import no_marker_case

    evs = no_marker_case()
    brain.feed("p_hand", evs)
    s = brain.snapshot("p_hand", evs[-1].t.timestamp() + 1, sync=False)
    assert s.task_open and s.implicit and s.task_id.startswith("t_imp")
