from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from understudy_engine.api.app import create_app
from understudy_engine.personas import PERSONA_BY_SLUG, apprentices, write_persona


@pytest.fixture(scope="session")
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("apidata")
    apprentices.generate(root)
    write_persona(PERSONA_BY_SLUG["irregular"], root, with_mc=False)
    return root


@pytest.fixture()
def env(data_root, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data_root))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("AGENT_PORT", "1")          # nothing listens there: the agent is "down" in tests
    return data_root


@pytest.fixture()
def client(env):
    return TestClient(create_app(env))


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    """An empty data dir (no synthetic data), for queue, audit, kill and event-write tests."""
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_PORT", "1")
    return TestClient(create_app(tmp_path)), tmp_path
