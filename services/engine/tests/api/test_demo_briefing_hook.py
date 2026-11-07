"""The demo seed calls proactive.seed.seed_demo(home, data_dir): only when the proactive layer is on, idempotently, and again
(reseed=True) after the extension flags changed."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pytest

from understudy_engine import demo
from understudy_engine.api.flags import EXTENSIONS
from understudy_engine.memory import MemoryStore

FLAG_VARS = ["UNDERSTUDY_X", "UNDERSTUDY_X_PROACTIVE", "UNDERSTUDY_X_GIT", "UNDERSTUDY_X_PRIVACY", "UNDERSTUDY_X_LOCALMODEL", "UNDERSTUDY_X_CALENDAR"]


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    for v in FLAG_VARS:
        monkeypatch.delenv(v, raising=False)
    home, dd = tmp_path / "home", tmp_path / "demo-data"
    home.mkdir()
    dd.mkdir()
    return home, dd


def flags_seen(home):
    return MemoryStore(home).load_state()["demo"]["extension_flags"]


def fake_seed(monkeypatch, calls, result=None, raises=None):
    mod = types.ModuleType("understudy_engine.proactive.seed")

    def seed_demo(home, data_dir, *, person="p_learn01", now=None, reseed=False, readers=None):
        calls.append({"home": home, "data_dir": data_dir, "reseed": reseed, "now": now})
        if raises:
            raise raises
        return result or {"seeded": not reseed or True, "cards": ["a", "b", "c"]}

    mod.seed_demo = seed_demo
    monkeypatch.setitem(sys.modules, "understudy_engine.proactive.seed", mod)


def test_layer_off_means_no_call_but_the_flags_are_remembered(dirs, monkeypatch):
    home, dd = dirs
    calls: list = []
    fake_seed(monkeypatch, calls)
    out: list[str] = []
    assert demo._seed_briefing(home, dd, None, out.append) is None
    assert calls == [] and any("proactive layer is off" in line for line in out)
    assert flags_seen(home) == []


def test_layer_on_calls_seed_demo_with_home_and_data_dir(dirs, monkeypatch):
    home, dd = dirs
    calls: list = []
    fake_seed(monkeypatch, calls)
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    now = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
    res = demo._seed_briefing(home, dd, now, lambda m: None)
    assert res["cards"] == ["a", "b", "c"]
    assert calls == [{"home": home, "data_dir": dd, "reseed": False, "now": now}]
    assert flags_seen(home) == ["proactive"]
    assert sorted(p.name for p in dd.iterdir()) == []                                  # no marker file in the demo data dir


def test_same_flags_again_does_not_ask_for_a_reseed(dirs, monkeypatch):
    home, dd = dirs
    calls: list = []
    fake_seed(monkeypatch, calls)
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    demo._seed_briefing(home, dd, None, lambda m: None)
    demo._seed_briefing(home, dd, None, lambda m: None)
    assert [c["reseed"] for c in calls] == [False, False]                    # seed_demo itself is idempotent; we do not force it


def test_a_flag_change_reseeds_and_so_does_reset(dirs, monkeypatch):
    home, dd = dirs
    calls: list = []
    fake_seed(monkeypatch, calls)
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    demo._seed_briefing(home, dd, None, lambda m: None)
    monkeypatch.setenv("UNDERSTUDY_X_GIT", "1")                               # another layer switched on: the briefing's sources changed
    out: list[str] = []
    demo._seed_briefing(home, dd, None, out.append)
    assert calls[-1]["reseed"] is True and any("reseeded" in line for line in out)
    demo._seed_briefing(home, dd, None, lambda m: None)
    assert calls[-1]["reseed"] is False                                       # flags unchanged since the reseed
    demo._seed_briefing(home, dd, None, lambda m: None, force=True)           # demo --reset
    assert calls[-1]["reseed"] is True
    monkeypatch.setenv("UNDERSTUDY_X", "1")                                   # the master flag
    demo._seed_briefing(home, dd, None, lambda m: None)
    assert calls[-1]["reseed"] is True and flags_seen(home) == sorted(EXTENSIONS)


def test_a_failing_or_missing_seed_never_fails_the_demo(dirs, monkeypatch):
    home, dd = dirs
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    calls: list = []
    fake_seed(monkeypatch, calls, raises=RuntimeError("calendar unreadable"))
    out: list[str] = []
    res = demo._seed_briefing(home, dd, None, out.append)
    assert res == {"seeded": False, "error": "RuntimeError: calendar unreadable"} and any("not seeded" in line for line in out)
    monkeypatch.setitem(sys.modules, "understudy_engine.proactive.seed", None)               # package missing
    assert demo._seed_briefing(home, dd, None, lambda m: None) is None


def test_the_real_seed_demo_runs_when_the_layer_is_on(tmp_path, monkeypatch):
    """With the real proactive.seed and an empty demo data dir (no routines or skills to draw on, so fewer than the full demo's three
    cards): it seeds, and the second call changes nothing."""
    for v in FLAG_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    home, dd = tmp_path / "home", tmp_path / "demo-data"
    home.mkdir()
    dd.mkdir()
    first = demo._seed_briefing(home, dd, None, lambda m: None)
    assert first is not None and "error" not in first and first["seeded"] is True and len(first["cards"]) >= 1
    second = demo._seed_briefing(home, dd, None, lambda m: None)
    assert second["seeded"] is False and second["cards"] == first["cards"]
    assert (dd / "briefing.json").exists()
