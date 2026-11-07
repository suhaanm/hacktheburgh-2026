"""REGRESSION FORM (the http_guard fix landed in the engine at about 17:45; assertions below now require REFUSAL). Original finding: the Origin allow-list on the engine's write routes is a string PREFIX test ("http://127.0.0.1"), so a page served
from http://127.0.0.1.evil.example or http://localhost.evil.example is "the app". Cross-site simple requests (no body, no custom
header) need no CORS preflight, so the write lands even though the page cannot read the answer. The queue approve/reject routes have
no Origin check at all. Hermetic: in-process TestClient, temp data dir, no network.
Run: UNDERSTUDY_MOCK=1 .venv/bin/python -m pytest evals/review/privacy/test_p3_origin_prefix_csrf.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

EVIL_PREFIX_ORIGINS = ["http://127.0.0.1.evil.example", "http://localhost.evil.example", "https://localhost.evil.example"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    monkeypatch.setenv("UNDERSTUDY_NO_WARM", "1")
    from understudy_engine.api.app import create_app
    app = create_app(root=tmp_path / "root", warm=False)
    return TestClient(app), tmp_path / "data"


def _seed_ledger(data):
    data.mkdir(parents=True, exist_ok=True)
    (data / "egress_ledger.jsonl").write_text(json.dumps({"id": "e_1", "t": "2026-11-07T00:00:00.000Z", "kind": "extension", "purpose": "x.y"}) + "\n")


@pytest.mark.parametrize("origin", EVIL_PREFIX_ORIGINS)
def test_prefix_origin_clears_the_egress_ledger(client, origin):
    c, data = client
    _seed_ledger(data)
    # what a cross-site <form method=post> or fetch(..., {mode:'no-cors'}) sends: Origin only, no custom header, no body
    r = c.post("/privacy/ledger/clear", headers={"Origin": origin})
    print("\nledger/clear with Origin", origin, "->", r.status_code, r.text[:120])
    assert r.status_code in (403, 401, 415, 421), "a prefix-style Origin (127.0.0.1.evil.example) may not clear the ledger"
    assert (data / "egress_ledger.jsonl").exists() and (data / "egress_ledger.jsonl").read_text().strip(), "the ledger was cleared"


def test_control_a_real_foreign_origin_is_refused(client):
    c, data = client
    _seed_ledger(data)
    r = c.post("/privacy/ledger/clear", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_queue_approve_has_no_origin_check_at_all(client):
    c, _ = client
    r = c.post("/queue/q_00000000000aaaa/approve", headers={"Origin": "http://evil.example"})
    print("\nqueue approve with a foreign Origin ->", r.status_code, r.text[:100])
    assert r.status_code in (401, 403, 415, 421), "queue approve from a foreign Origin must be refused before the id is looked up"


def test_agent_spawn_accepts_a_text_plain_cross_site_post_from_a_prefix_origin(tmp_path, monkeypatch):
    """The agent service's POST /agents/spawn reads request.json() whatever the Content-Type is, and applies the same prefix Origin
    test, so a page on http://127.0.0.1.evil.example can start a background run with raw_ok=true (its raw-file path sends file text
    to the model provider) using a CORS-safelisted 'text/plain' POST that needs no preflight."""
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X_AGENTS", "1")
    from understudy_agent.runtime import routes as rt
    from fastapi import FastAPI
    app = FastAPI(); app.include_router(rt.router)
    c = TestClient(app)
    kind = rt.spawn_kinds()[0]
    r = c.post("/agents/spawn", content=json.dumps({"kind": kind, "mode": "foreground", "params": {"raw_ok": True}}),
               headers={"Origin": "http://localhost.evil.example", "Content-Type": "text/plain;charset=UTF-8"})
    print("\nPOST /agents/spawn  Origin=http://localhost.evil.example  Content-Type=text/plain ->", r.status_code, r.text[:100])
    try:
        assert r.status_code in (401, 403, 415, 421, 422), "a text/plain cross-site POST from a prefix Origin may not start a run"
    finally:
        try:
            rid = r.json().get("run_id")
            if rid:
                c.post(f"/agents/runs/{rid}/stop")
        except Exception:
            pass
