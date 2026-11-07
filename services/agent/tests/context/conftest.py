"""Context-library tests: hermetic, offline, no model call. A tmp data dir and home; mock mode on; no network."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")
