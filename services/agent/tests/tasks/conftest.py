"""Task tests: hermetic and offline. Own data dir, own HOME (so ~/.claude and ~/Knack are temporary), a FAKE claude, a fake model port.
No test runs the real `claude` and none calls a model."""
from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REAL_DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "uhome"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")
    monkeypatch.delenv("UNDERSTUDY_GUARD_STRICT", raising=False)
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("KNACK_CLAUDE_BIN", raising=False)
    # Knack's own keys exist in the PARENT environment: the tests prove the child never gets them
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-not-real")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven-test-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    except Exception:
        pass
    from understudy_agent.tasks import reset_manager

    reset_manager()
    had_kill = (REAL_DATA / "KILL").exists()
    yield
    reset_manager()
    if not had_kill:
        assert not (REAL_DATA / "KILL").exists(), "a test left data/KILL in the REAL data dir"


@pytest.fixture
def fake_claude(tmp_path) -> str:
    p = tmp_path / "bin" / "claude"
    p.parent.mkdir()
    src = (HERE / "fake_claude.py").read_text()
    p.write_text(src.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return str(p)


class FakePort:
    """A model port that records every call and answers from a script. `name` is not 'mock'; `offline` is False."""

    name = "fake"
    offline = False

    def __init__(self, plan_out=None, check_out=None):
        self.calls: list[tuple[str, object]] = []
        self.plan_out = plan_out or {"text": "Edinburgh is the capital of Scotland. It has about half a million people."}
        self.check_out = check_out or {"route": "unclear"}

    def plan(self, messages, schema=None):
        self.calls.append(("plan", messages))
        if schema and schema.get("title") == "task_show_steps":
            return {"steps": ["Open the app", "Press the button"]}
        return self.plan_out

    def check(self, prompt, schema):
        self.calls.append(("check", prompt))
        return self.check_out

    def read(self, untrusted, schema):  # pragma: no cover - a task never uses the reader
        raise AssertionError("tasks must not use the quarantined reader")

    def vision(self, *a, **k):  # pragma: no cover
        raise AssertionError("tasks must not use vision")

    def computer_step(self, *a, **k):  # pragma: no cover
        raise AssertionError("tasks must not use computer use")


@pytest.fixture
def port() -> FakePort:
    return FakePort()


def wait_for(fn, timeout=15.0, step=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


def claude_text(mode: str = "ok", extra: str = "") -> str:
    """A request that the router sends to claude_agent, carrying the shim's mode marker."""
    return f"write a python script that summarises the csv data {extra} FAKE:{mode}".replace("  ", " ")


@pytest.fixture
def make_manager(tmp_path, fake_claude, port):
    from understudy_agent.tasks import TaskManager

    made = []

    def make(**kw):
        kw.setdefault("claude_bin", fake_claude)
        kw.setdefault("port_factory", lambda: port)
        kw.setdefault("offline", False)
        kw.setdefault("grace_s", 1.0)
        kw.setdefault("tick_s", 0.05)
        m = TaskManager(**kw)
        made.append(m)
        return m

    yield make
    for m in made:
        try:
            m.shutdown()
        except Exception:
            pass
