"""Models-track test setup: hermetic and offline. No network, no real key, no real data dir, no real .env.

Every test gets a tmp data dir and home and a restored environment; python-dotenv cannot load a real .env. The Gemini and OpenAI
keys are obviously fake strings so a leak test can look for them. Live calls are never made from pytest (the bake-off CLI does that).
"""
from __future__ import annotations

import os

import pytest

FAKE_GEMINI_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE12345"
FAKE_OPENAI_KEY = "sk-test-FAKEFAKEFAKEFAKEFAKE1234567890"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    before = dict(os.environ)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    except Exception:
        pass
    for k in list(os.environ):
        if k.startswith(("UNDERSTUDY_X", "UNDERSTUDY_PRICE_", "GEMINI_", "UNDERSTUDY_MODELS_YAML")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_GEMINI_KEY)
    monkeypatch.setenv("GEMINI_MODEL_FAST", "test-fast")
    monkeypatch.setenv("GEMINI_MODEL_ACCURATE", "test-accurate")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)
    monkeypatch.setenv("OPENAI_MODEL_PLANNER", "test-planner")
    monkeypatch.setenv("OPENAI_MODEL_FAST", "test-openai-fast")
    monkeypatch.setenv("OPENAI_MODEL_COMPUTER_USE", "test-computer")
    yield
    monkeypatch.undo()
    for k in list(os.environ):
        if k not in before:
            del os.environ[k]
    for k, v in before.items():
        if os.environ.get(k) != v:
            os.environ[k] = v
