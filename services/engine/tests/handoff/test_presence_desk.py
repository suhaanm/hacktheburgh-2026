"""The desktop app's real desk events: idle rows with meta.state start/end beside the persona rows with meta.idle_s only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from understudy_engine.presence import ACTIVE, day_states_from_events, spells_from_events
from understudy_engine.presence.timeline import input_times

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)  # a Monday


def ev(minutes, typ, **meta):
    return {"t": T0 + timedelta(minutes=minutes), "type": typ, "actor": "human", "source": "desk", "meta": meta}


def test_idle_end_row_closes_the_spell_and_idle_s_gives_its_length():
    # desk-only machine: unlock, idle starts (last input 2 minutes before), the worker returns 25 minutes after leaving
    rows = [ev(0, "unlock"), ev(12, "idle", state="start", idle_s=120), ev(37, "idle", state="end", idle_s=1620), ev(38, "lock")]
    sp = spells_from_events(rows)
    assert len(sp) == 1
    assert round(sp[0].duration_min, 1) == 27.0                  # from t0 + 10 (12 - 2) to t0 + 37
    assert sp[0].start == (T0 + timedelta(minutes=10)).timestamp() and sp[0].ended


def test_end_row_alone_is_enough_and_its_idle_s_wins_over_the_gap_before_it():
    rows = [ev(0, "unlock"), ev(60, "idle", state="end", idle_s=1800)]       # last input at 30 minutes, back at 60
    (sp,) = [s for s in spells_from_events(rows) if s.duration_min >= 25]
    assert round(sp.duration_min) == 30 and sp.start == (T0 + timedelta(minutes=30)).timestamp()
    assert ACTIVE in day_states_from_events(rows, first_day=T0.date(), last_day=T0.date())[0].states      # the return counts as presence


def test_persona_style_idle_rows_with_idle_s_only_change_nothing():
    base = [ev(0, "click"), ev(1, "click"), ev(20, "click"), ev(21, "click")]
    with_idle = base + [ev(10, "idle", idle_s=120), ev(11, "idle", idle_s=13)]
    assert input_times(with_idle) == input_times(base)
    assert [(s.start, s.duration_min) for s in spells_from_events(with_idle)] == [(s.start, s.duration_min) for s in spells_from_events(base)]


def test_both_shapes_together_and_agent_rows_ignored():
    rows = [ev(0, "click"), ev(2, "click"), ev(30, "idle", state="end", idle_s=1680), {"t": T0 + timedelta(minutes=10), "type": "idle", "actor": "agent",
            "meta": {"state": "end", "idle_s": 99999}}, ev(31, "click"), ev(45, "idle", idle_s=300)]
    sp = spells_from_events(rows)
    assert len(sp) == 1 and round(sp[0].duration_min) == 28            # 2 -> 30 minutes; the agent row did not create a spell
    assert input_times(rows) == sorted(input_times(rows))


def test_sleep_and_lock_rows_from_the_desk_still_drive_the_machine_state():
    rows = [ev(0, "unlock"), ev(5, "click"), ev(10, "lock"), ev(11, "sleep"), ev(300, "resume"), ev(301, "unlock")]
    (day,) = day_states_from_events(rows, first_day=T0.date(), last_day=T0.date())
    assert day.states[36] == ACTIVE                                       # 09:00 bin has the unlock and click
    assert day.states[40] == 0 and day.states[55] == 0                    # asleep from 09:11 until 14:00
