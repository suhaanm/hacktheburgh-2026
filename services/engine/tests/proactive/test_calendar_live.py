"""The real calendar reader against the calendar track's service (flag on), including the demo person's stand-in."""
from __future__ import annotations


import pytest

from understudy_engine.memory.paths import data_dir as real_data_dir
from understudy_engine.proactive import briefing as B
from understudy_engine.proactive import seed as S
from understudy_engine.proactive.candidates import Ctx, Reading, calendar_candidates
from understudy_engine.proactive.sources import Readers, read_calendar
from understudy_engine.proactive.store import BriefingStore

from .conftest import NOW

REAL = real_data_dir() / "synthetic" / "calendars"
pytestmark = pytest.mark.skipif(not (REAL / "truth.json").exists(), reason="run `uv run understudy synth --all` first")


@pytest.fixture
def cal_env(env, monkeypatch):
    (env.data / "synthetic").mkdir()
    (env.data / "synthetic" / "calendars").symlink_to(REAL)
    monkeypatch.setenv("UNDERSTUDY_X_CALENDAR", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    from understudy_engine.calendar.store import reset_default

    reset_default()
    yield env
    reset_default()


def test_a_persona_with_planted_problems_gets_calendar_candidates(cal_env):
    rd = read_calendar(Ctx("p_nightowl", NOW))
    assert rd.available and not rd.meta.get("stand_in")
    templates = {i["template"] for i in rd.items}
    assert {"auto_hold_scheduling", "offcomputer_break"} <= templates               # planted: no focus blocks, no breaks
    cands = calendar_candidates(Ctx("p_nightowl", NOW), rd)
    assert {c.title for c in cands} >= {"Let scheduling hold time for you", "Schedule a break away from the screen", "Trim the meeting load"}
    assert all(c.value >= 0.3 and "calendar priority" == c.meta["value_source"] for c in cands)
    draft = next(c for c in cands if c.subject == "cal:auto_hold_scheduling")
    advice = next(c for c in cands if c.subject == "cal:trim_meeting_load")
    assert draft.fire.type == "draft" and draft.risk_class == "outward" and advice.fire.type == "queue" and advice.risk_class == "normal"


def test_an_expert_and_an_unknown_person_get_no_card(cal_env):
    assert read_calendar(Ctx("p_exp01", NOW)).items == []
    unk = read_calendar(Ctx("p_nobody", NOW))
    assert unk.available is True and unk.items == [] and "no calendar" in unk.note


def test_the_demo_person_borrows_a_stand_in_and_says_so(cal_env):
    rd = read_calendar(Ctx("p_learn01", NOW))
    assert rd.available and rd.meta["stand_in"] == "p_ninetofive" and rd.items
    c = next(x for x in calendar_candidates(Ctx("p_learn01", NOW), rd) if x.subject == "cal:auto_hold_scheduling")
    assert "stand-in" in c.why and c.meta["stand_in"] is True


def test_the_seed_uses_the_live_calendar_card_and_survives_the_first_read(cal_env):
    readers = Readers(routines=lambda c: Reading([{"id": "calc-entry-3x", "title": "Enter the household into three calculators", "status": "proposed",
                                                    "proposable": True, "automatable": True, "episodes": 14, "minutes_per_week": 96.0, "hours_lo": 3.1,
                                                    "hours_hi": 5.2, "confidence": 0.8, "horizon_weeks": 4, "skill_gate_ok": True, "skill_cogs": [],
                                                    "touches": [], "never": ["submit"], "irreversible_classes": [], "last_seen": None,
                                                    "buy_after_runs": 3}], True),
                      skills=lambda c: Reading([{"id": "check-the-cliff", "label": "Probe the cliff edge", "order": 3, "cogs": ["CHECK_CLIFF"],
                                                  "prerequisites": [], "expert_signal": "", "prompts": {}, "level": 2, "mastery": 0.45,
                                                  "days_idle": 3.0, "days_until_drop": 2.0}], True),
                      calendar=read_calendar, git=lambda c: Reading([], False), runs=lambda c: Reading([], False))
    out = S.seed_demo(cal_env.home, cal_env.data, now=NOW, readers=readers)
    assert sorted(out["kinds"]) == ["automate", "focus_block", "practice"]
    store = BriefingStore(cal_env.data / "briefing.json")
    cal = next(c for c in store.cards(S.DEMO_PERSON) if c.kind == "focus_block")
    assert cal.subject == "cal:auto_hold_scheduling" and cal.fire_type == "draft" and "stand-in" in cal.why
    b = B.build(S.DEMO_PERSON, store=store, readers=readers, now=NOW)
    assert b.dropped == [] and sorted(c.kind for c in b.cards) == ["automate", "focus_block", "practice"]
