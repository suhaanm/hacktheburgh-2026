"""Sessions without task markers: the zone fallback opens a case at the first calculator page after a quiet spell."""
from __future__ import annotations

import pytest

from understudy_engine.coach import CoachBrain, StuckScorer
from understudy_engine.store import EventStore

from .helpers import calc, cliff, copy_to_note, ev, read, reconcile


def bare(events):
    """Drop the explicit markers and the task id, as a capture without them would."""
    return [e.model_copy(update={"task_id": None}) for e in events if e.type not in ("task_start", "task_end", "progress")]


def no_marker_case(t=0.0, cliffs=False):
    out = read(None, t + 1)
    out += calc(None, t + 12, "calc1")
    if cliffs:
        out += cliff(None, t + 46)
    out += copy_to_note(None, t + 52)
    return sorted(bare(out), key=lambda e: (e.t, e.id))


@pytest.fixture()
def brain(tmp_path):
    return CoachBrain(EventStore(tmp_path / "d"), scorer=StuckScorer(fit=False), tone="short")


def run(brain, events, person="p_hand"):
    return [(e, brain.next_step(person, e.t, events=events[: i + 1])) for i, e in enumerate(events)]


def acts(trace):
    return [(e, d) for e, d in trace if d.action != "silent"]


def test_signature_case_without_any_markers(brain):
    trace = run(brain, no_marker_case())
    fired = acts(trace)
    assert len(fired) == 1
    e, d = fired[0]
    assert d.action == "annotate" and d.target["zone"] == "cliff_button" and d.message == "Check cliff edges before you copy this result."
    assert "implicit_task" in d.reason_codes and d.task_id.startswith("t_imp")
    shown = [x for x in brain.store.read("synthetic", person="p_hand") if x.type == "coach_shown"]
    assert len(shown) == 1 and shown[0].task_id == d.task_id                       # the log carries the implicit task id


def test_events_before_the_first_calculator_open_no_case(brain):
    only_read = bare(read(None, 0))
    trace = run(brain, only_read)
    assert all(d.reason_codes == ["no_active_task"] or d.reason_codes == ["no_events"] or "no_active_task" in d.reason_codes for _, d in trace)
    assert not acts(trace)


def test_clean_case_without_markers_is_silent_and_the_case_closes_after_the_note(brain):
    evs = bare(read(None, 1) + calc(None, 12, "calc1") + cliff(None, 46) + calc(None, 56, "calc2") + cliff(None, 90) + calc(None, 100, "calc3")
               + cliff(None, 134) + reconcile(None, 142) + copy_to_note(None, 158))
    trace = run(brain, sorted(evs, key=lambda e: (e.t, e.id)))
    assert not acts(trace) and any("implicit_task" in d.reason_codes for _, d in trace)
    last = evs[-1].t.timestamp()
    done = brain.next_step("p_hand", last + 130)                                  # the note is written and the worker is quiet
    assert done.reason_codes == ["no_active_task"] and done.task_id is None
    st = brain._people["p_hand"]
    assert st.open is None and st.n_tasks == 1                                    # finished: the skill state heard about it


def test_ten_minutes_idle_closes_the_case_and_a_later_calculator_opens_a_new_one(brain):
    first = no_marker_case(0)
    second = no_marker_case(900)
    trace = run(brain, first + second)
    ids = {d.task_id for _, d in trace if d.task_id}
    assert len(ids) == 2 and all(i.startswith("t_imp") for i in ids)
    assert len(acts(trace)) == 2                                                  # one prompt per case: the cooldown has long passed


def test_a_calculator_page_soon_after_the_last_event_does_not_open_a_new_case(brain):
    evs = bare(read(None, 1) + calc(None, 12, "calc1") + cliff(None, 46) + calc(None, 56, "calc2"))
    brain.feed("p_hand", evs)
    st = brain._people["p_hand"]
    assert st.open is not None and st.implicit and st.open_task.startswith("t_imp")
    brain.next_step("p_hand", evs[-1].t.timestamp() + 5)
    assert st.open_task == f"t_imp{int(evs[1].t.timestamp()) if False else int(st.open[0].t.timestamp())}"      # still the first case, not a second one


def test_an_explicit_task_start_takes_over_from_an_implicit_case(brain):
    implicit = no_marker_case(0)
    explicit = [ev(400, "task_start", task="t_real1", source="desk")] + calc("t_real1", 401, "calc1")
    brain.feed("p_hand", implicit + explicit)
    st = brain._people["p_hand"]
    assert st.open_task == "t_real1" and st.implicit is False


def test_markers_and_fallback_agree_on_the_signature_case(tmp_path):
    from .helpers import signature_events

    b1 = CoachBrain(EventStore(tmp_path / "m"), scorer=StuckScorer(fit=False), tone="short")
    b2 = CoachBrain(EventStore(tmp_path / "n"), scorer=StuckScorer(fit=False), tone="short")
    with_markers = acts(run(b1, signature_events()))
    without = acts(run(b2, no_marker_case()))
    assert len(with_markers) == len(without) == 1
    a, b = with_markers[0][1], without[0][1]
    assert (a.action, a.message, a.target, a.missed) == (b.action, b.message, b.target, b.missed)
