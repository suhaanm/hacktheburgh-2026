"""REGRESSION FORM (fixes landing from 17:45; assertions require REFUSAL; a failure means still open). Original finding: (1) the kill switch can be set AND CLEARED by any web page (no Origin, actor or Host check, text/plain POST needs no
preflight) on both the engine and the agent service; (2) events can be injected into the store the same way; (3) no route checks the Host
header, so a DNS-rebinding page (Host: evil.example -> 127.0.0.1) reads every GET route and, because the same-origin request needs no
preflight, can also send JSON writes; combined with the Origin prefix bug the guards are no obstacle. Hermetic, in-process.
Run: UNDERSTUDY_MOCK=1 .venv/bin/python -m pytest evals/review/privacy/test_p3b_kill_switch_and_dns_rebinding.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

TEXT = {"Content-Type": "text/plain;charset=UTF-8"}


@pytest.fixture()
def apps(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    from understudy_engine.api.app import create_app as engine_app
    from understudy_agent.server import create_app as agent_app
    return TestClient(engine_app(root=tmp_path / "root", warm=False)), TestClient(agent_app()), tmp_path / "data"


@pytest.mark.parametrize("svc", [0, 1], ids=["engine", "agent"])
def test_foreign_origin_can_set_then_clear_the_kill_switch(apps, svc):
    c = apps[svc]
    evil = {"Origin": "http://evil.example", **TEXT}
    # setting the flag from a foreign page is a nuisance (stop is allowed to be easy); CLEARING it must be refused
    r0 = c.post("/kill", content=b"", headers=evil)
    r = c.post("/kill/clear", content=b"", headers=evil)
    print("\n", ["engine", "agent"][svc], "foreign Origin: POST /kill ->", r0.status_code, "| POST /kill/clear ->", r.status_code, r.text[:60])
    assert r.status_code in (401, 403, 415, 421), "a foreign Origin may not clear the kill switch"


def test_foreign_origin_can_inject_events_into_the_store(apps):
    c = apps[0]
    r = c.post("/events", content=json.dumps({"events": []}), headers={"Origin": "http://evil.example", **TEXT})
    print("\nPOST /events (text/plain, foreign Origin) ->", r.status_code, r.text[:100])
    assert r.status_code in (401, 403, 415, 421), "events from a foreign Origin must be refused"


READ_ROUTES = ["/events", "/audit", "/queue?status=all", "/privacy/ledger", "/privacy/ledger/export", "/memory", "/eval/report", "/awareness/summary",
               "/replay", "/health"]


def test_no_route_checks_the_host_header(apps):
    c = apps[0]
    ok = {}
    for p in READ_ROUTES:
        r = c.get(p, headers={"Host": "evil.example"})
        ok[p] = r.status_code
    print("\nGET with Host: evil.example ->", ok)
    served = [p for p, s in ok.items() if s == 200]
    assert not served, f"routes that answered a foreign Host: {served}"


def test_agent_service_reads_with_foreign_host(apps):
    c = apps[1]
    codes = {p: c.get(p, headers={"Host": "evil.example"}).status_code for p in ["/health", "/offhours/report", "/voice/status", "/agents/runs"]}
    print("\nagent GET with Host: evil.example ->", codes)
    assert 200 not in codes.values(), f"agent routes that answered a foreign Host: {[p for p, c_ in codes.items() if c_ == 200]}"


def test_rebound_page_passes_the_prefix_origin_guard_with_json(apps):
    """A page on localhost.evil.example that has rebound to 127.0.0.1 is same-origin with the service: no CORS preflight, JSON body
    and the actor header are all it needs; the Origin it sends starts with 'http://localhost'."""
    c = apps[0]
    h = {"Host": "localhost.evil.example", "Origin": "http://localhost.evil.example", "Content-Type": "application/json", "x-understudy-actor": "worker"}
    r = c.post("/privacy/ledger/clear", content=b"", headers=h)
    assert r.status_code in (401, 403, 421), f"a rebound page (Host and Origin localhost.evil.example) must be refused, got {r.status_code}"
