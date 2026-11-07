"""Safety-track test setup: hermetic, offline by default; live tests run only with UNDERSTUDY_LIVE=1.

Other agents run their tests at the same time on this machine, so nothing here may touch the real data directory
(data/KILL, data/queue, data/audit.jsonl), the real ~/.understudy, or leak environment variables into later tests.
Every test gets its own tmp data dir and home; the environment is snapshotted and restored around each test; python-dotenv
cannot load a real .env into a test process.
"""
from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: calls the real OpenAI API (a handful of tiny calls); needs UNDERSTUDY_LIVE=1")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("UNDERSTUDY_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test: set UNDERSTUDY_LIVE=1 and load .env to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, tmp_path):
    """Per-test tmp data dir and home, a restored environment, and no way to load a real .env."""
    before = dict(os.environ)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    live = "live" in request.keywords
    if not live:
        try:
            import dotenv

            monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
        except Exception:
            pass
        monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
        monkeypatch.delenv("UNDERSTUDY_MOCK_SCENARIO", raising=False)
        monkeypatch.delenv("UNDERSTUDY_VOICE", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        monkeypatch.setenv("OPENAI_MODEL_PLANNER", "test-planner")
        monkeypatch.setenv("OPENAI_MODEL_FAST", "test-fast")
        monkeypatch.setenv("OPENAI_MODEL_COMPUTER_USE", "test-computer")
        for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL", "GEMINI_API_KEY"):
            monkeypatch.delenv(k, raising=False)
    yield
    monkeypatch.undo()
    # anything a test (or code under test) added to os.environ directly is removed; anything it changed is put back
    for k in list(os.environ):
        if k not in before:
            del os.environ[k]
    for k, v in before.items():
        if os.environ.get(k) != v:
            os.environ[k] = v
