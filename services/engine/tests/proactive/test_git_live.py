"""The real git reader against the git track's service, in a temporary data dir (flag on); and the layer switches."""
from __future__ import annotations

import shutil

import pytest

from understudy_engine.proactive import briefing as B
from understudy_engine.proactive.candidates import Ctx
from understudy_engine.proactive.sources import Readers, read_calendar, read_git
from understudy_engine.proactive.store import BriefingStore

from .conftest import NOW

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs the git binary")


def test_the_git_and_calendar_readers_stay_off_when_their_layers_are_off(env, monkeypatch):
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_GIT", "UNDERSTUDY_X_CALENDAR"):
        monkeypatch.delenv(k, raising=False)
    g = read_git(Ctx("p_git_learner_1", NOW))
    c = read_calendar(Ctx("p_x", NOW))
    assert g.available is False and "off" in g.note and c.available is False and "off" in c.note
    assert not (env.data / "synthetic" / "git").exists()                 # nothing was materialised


def test_git_habits_become_cards_from_the_real_analysis(env, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_GIT", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    rd = read_git(Ctx("p_git_learner_1", NOW))
    assert rd.available and {i["id"] for i in rd.items} >= {"smaller_commits", "tests_with_changes"} and rd.meta["digest"] in ("rules", "model")
    assert all(i["flagged"] and i["ci"][0] * i["ci"][1] > 0 for i in rd.items)          # the interval excludes zero
    readers = Readers(routines=lambda c: rd.__class__([], False), skills=lambda c: rd.__class__([], False), calendar=lambda c: rd.__class__([], False),
                      runs=lambda c: rd.__class__([], False))
    b = B.build("p_git_learner_1", store=BriefingStore(env.data / "briefing.json"), readers=readers, now=NOW)
    assert [c.kind for c in b.cards] == ["git_habit"] and b.cards[0].fire_type == "agent" and 0.4 < b.cards[0].score < 1
    assert "%" in b.cards[0].why and b.cards[0].risk_class == "normal"
    unknown = read_git(Ctx("p_somebody_else", NOW))
    assert unknown.available is True and unknown.items == [] and "no repository" in unknown.note
