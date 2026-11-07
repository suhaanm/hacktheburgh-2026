"""S-02b: acceptance tests for the S-02 fix (per-boot token in data/.token for release routes); they FAIL until it lands. Properties: mode 0600,
rotation per boot, no leak in a response, the OpenAPI document or a log line, the agent's file tools cannot read it, and a request with NO Origin
and NO token cannot clear the kill flag on either service. Hermetic: in-process clients, temp data dir."""
from __future__ import annotations

import logging
import stat

import pytest
from fastapi.testclient import TestClient

from understudy_agent.security.paths import data_dir
from understudy_agent.security.settings import SettingsGuard


def boot_agent():
    from understudy_agent.server import create_app
    return TestClient(create_app(base_urls={k: "http://127.0.0.1:9" for k in "abc"}, autostart_sandbox=False, shared_sites=False))


def boot_engine(tmp_path):
    from understudy_engine.api.app import create_app
    return TestClient(create_app(root=tmp_path / "root", warm=False))


def token() -> str:
    p = data_dir() / ".token"
    assert p.exists(), "no data/.token after boot: the S-02 token mechanism has not landed (or lives elsewhere: tell the reviewer)"
    return p.read_text().strip()


def test_token_file_is_private_and_rotates_on_restart(tmp_path):
    boot_agent()
    t1, mode = token(), stat.S_IMODE((data_dir() / ".token").stat().st_mode)
    assert mode == 0o600 and len(t1) >= 32, f"mode {oct(mode)}, length {len(t1)}"
    boot_agent()
    assert token() != t1, "the token was reused across boots"


def test_token_is_in_no_response_no_openapi_no_log(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    c = boot_agent()
    t = token()
    bodies = [c.get(p).text for p in ("/health", "/openapi.json", "/docs", "/run/none", "/run/none/stream")]
    bodies.append(c.post("/kill/clear", headers={"Origin": "http://evil.example"}).text)
    assert not any(t in b for b in bodies), "the token leaked into a response body"
    assert t not in caplog.text, "the token reached a log line"


def test_the_agents_own_file_tools_cannot_read_the_token(tmp_path):
    boot_agent(); token()
    assert not SettingsGuard().check_path(data_dir() / ".token").allowed, "settings.check_path does not protect data/.token"


@pytest.mark.parametrize("svc", ["agent", "engine"])
def test_a_request_with_neither_origin_nor_token_cannot_clear_the_kill_flag(tmp_path, svc):
    c = boot_agent() if svc == "agent" else boot_engine(tmp_path)
    assert c.post("/kill").status_code == 200 and (data_dir() / "KILL").exists()
    r = c.post("/kill/clear")                                   # a local process with no Origin header and no token
    assert r.status_code in (401, 403) and (data_dir() / "KILL").exists(), f"{svc} /kill/clear answered {r.status_code} without a token"
