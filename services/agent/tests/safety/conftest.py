"""Safety-track test setup: offline by default; live tests run only with UNDERSTUDY_LIVE=1."""
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
def _offline_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, tmp_path):
    """Non-live tests never touch the network or the real data directory."""
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    if "live" not in request.keywords:
        monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
        monkeypatch.delenv("UNDERSTUDY_MOCK_SCENARIO", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        monkeypatch.setenv("OPENAI_MODEL_PLANNER", "test-planner")
        monkeypatch.setenv("OPENAI_MODEL_FAST", "test-fast")
        monkeypatch.setenv("OPENAI_MODEL_COMPUTER_USE", "test-computer")
    yield
