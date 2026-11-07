"""Shared fixtures for the proactive tests: isolated dirs, stub readers, fixed clock. Hermetic: no network, no model, no real home."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from understudy_engine.proactive.candidates import Reading
from understudy_engine.proactive.sources import Readers
from understudy_engine.proactive.store import BriefingStore

NOW = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
P = "p_test01"


def routine_row(**kw: Any) -> dict[str, Any]:
    base = {"id": "calc-entry-3x", "title": "Enter the household into three calculators", "status": "proposed", "proposable": True,
            "automatable": True, "episodes": 14, "minutes_per_week": 96.0, "hours_lo": 3.1, "hours_hi": 5.2, "confidence": 0.82,
            "horizon_weeks": 4, "skill_gate_ok": True, "skill_cogs": ["ENTER_HOUSEHOLD"], "touches": ["GovCalc", "EntitledTo"],
            "never": ["submit"], "irreversible_classes": ["submit"], "last_seen": "2026-11-06T16:00:00Z", "buy_after_runs": 3}
    base.update(kw)
    return base


def skill_row(**kw: Any) -> dict[str, Any]:
    base = {"id": "check-the-cliff", "label": "Probe the cliff edge on every calculator", "order": 3, "cogs": ["CHECK_CLIFF"], "prerequisites": [],
            "expert_signal": "Re-runs each calculator with a figure nudged near a limit.",
            "prompts": {"L1": "Is any figure close to a limit?", "L2": "Close to a limit anywhere?", "L3": "Probe the edge."},
            "level": 2, "mastery": 0.45, "days_idle": 4.0, "days_until_drop": 2.0}
    base.update(kw)
    return base


def cal_row(**kw: Any) -> dict[str, Any]:
    base = {"id": "protect_focus_block", "template": "protect_focus_block", "can_draft": True,
            "numbers": {"longest_focus_min": 55, "gain_h": 2.5, "suggested_min": 120}, "expert_ref": {"longest_focus_min": 110}}
    base.update(kw)
    return base


def git_row(**kw: Any) -> dict[str, Any]:
    base = {"id": "huge_commits", "learner": 420.0, "expert": 90.0, "delta": 330.0, "ci": [250.0, 410.0], "n_commits": 60}
    base.update(kw)
    return base


def run_row(**kw: Any) -> dict[str, Any]:
    base = {"run_id": "r_bg_001", "kind": "programming.commit_analyst", "state": "done", "finished_at": NOW.timestamp() - 3 * 3600,
            "children": 2, "viewed": False}
    base.update(kw)
    return base


def make_readers(*, routines=None, skills=None, calendar=None, git=None, runs=None, available: dict[str, bool] | None = None,
                 in_flight=None) -> Readers:
    av = available or {}

    def mk(name: str, items):
        return lambda ctx: Reading(list(items or []), av.get(name, True), None)

    return Readers(routines=mk("routines", routines), skills=mk("skills", skills), calendar=mk("calendar", calendar),
                   git=mk("git", git), runs=mk("runs", runs), in_flight=in_flight or (lambda key: False))


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, home = tmp_path / "data", tmp_path / "home"
    data.mkdir()
    home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home))
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    return SimpleNamespace(data=data, home=home, store=BriefingStore(data / "briefing.json"), tmp=tmp_path)


class FakeQueue:
    """Records every enqueue so a test can assert what was (not) created."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        return {"id": f"q_fake{len(self.calls):03d}", "status": "pending", **kw}


class FakeSpawner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def __call__(self, kind: str, params: dict[str, Any], mode: str) -> dict[str, Any]:
        self.calls.append((kind, params, mode))
        return {"run_id": f"r_fake{len(self.calls):03d}"}
