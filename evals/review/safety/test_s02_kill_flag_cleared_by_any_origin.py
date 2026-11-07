"""S-02 (High): the kill flag can be cleared (and queue items approved: see also REVIEW-PRIVACY p3) by ANY caller of 127.0.0.1:7700 or
:7710. Neither service checks Origin, Host or a token on /kill, /kill/clear, /human-input or /run/{id}/stop; the CORS middleware only
hides the answer from a foreign page, it does not stop the request. POST with no body and no custom header is a "simple" cross-site
request (no preflight), so any page open in the agent's own browser (or the owner's) can do
    setInterval(() => fetch("http://127.0.0.1:7710/kill/clear", {method: "POST", mode: "no-cors"}), 50)
and defeat Option-Shift-Command-K for any code path that polls data/KILL (MacActuator, supervisor watchdog, SafetyPipeline).
Hermetic: in-process TestClients, temp data dir."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

EVIL = {"Origin": "http://evil.example", "Host": "evil.example:7710"}


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    from understudy_agent.server import create_app
    return TestClient(create_app(base_urls={"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"},
                                 autostart_sandbox=False, shared_sites=False))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    from understudy_engine.api.app import create_app
    return TestClient(create_app(root=tmp_path / "root", warm=False))


def kill_file(tmp_path):
    return (tmp_path / "data" / "KILL").exists()


def test_agent_service_kill_clear_accepts_a_foreign_origin_and_host(agent, tmp_path):
    assert agent.post("/kill").status_code == 200 and kill_file(tmp_path)          # the worker pressed the hotkey
    r = agent.post("/kill/clear", headers=EVIL)                                      # a page in the agent's browser answers
    assert r.status_code in (401, 403, 421), f"kill/clear answered {r.status_code} to Origin {EVIL['Origin']}"   # 421: the Host check fires first
    assert kill_file(tmp_path), "the kill flag was cleared by a foreign origin"


def test_engine_kill_clear_accepts_a_foreign_origin_and_host(engine, tmp_path):
    assert engine.post("/kill").status_code == 200 and kill_file(tmp_path)
    r = engine.post("/kill/clear", headers={"Origin": "http://evil.example", "Host": "evil.example:7700"})
    assert r.status_code in (401, 403, 421), f"engine kill/clear answered {r.status_code} to a foreign origin"
    assert kill_file(tmp_path), "the kill flag was cleared by a foreign origin"


def test_human_input_signal_can_be_forged_by_a_foreign_origin(agent):
    # /human-input makes background runs yield (a denial of service); the same missing check lets a page keep them yielding forever
    r = agent.post("/human-input", headers=EVIL)
    assert r.status_code in (401, 403, 421), f"/human-input answered {r.status_code} to a foreign origin"
