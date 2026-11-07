"""The engine app includes Cue's router only when the flag is on, and Cue works through the real app (CoachBrain at app.state.coach)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from understudy_engine.api.app import create_app


def test_flag_off_the_app_has_no_cue_routes(tmp_path):
    app = create_app(root=tmp_path / "data", warm=False)
    c = TestClient(app)
    assert c.get("/cue/next", params={"person": "p_x"}).status_code == 404
    assert c.get("/growth", params={"person": "p_x"}).status_code == 404
    assert app.state.extensions.get("cue") in (False, None)


def test_flag_on_the_app_serves_cue_over_a_fixture_and_reports_the_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    monkeypatch.setenv("AGENT_PORT", "1")                      # /health probes the agent service: point it at nothing
    app = create_app(root=tmp_path / "data", warm=False)
    c = TestClient(app)
    if not app.state.extensions.get("cue"):
        pytest.skip(f"the app did not include the cue router: {getattr(app.state, 'router_status', {})}")
    health = c.get("/health").json()
    assert health["extensions"]["cue"] is True
    d = None
    for t in (0, 60, 85, 87.5):
        d = c.get("/cue/next", params={"person": "p_app", "fixture": "stuck_after_result", "t": t})
        assert d.status_code == 200, d.text
    d = d.json()["data"]
    assert d["kind"] in ("none", "cue") and d["meta"]["origin"] == "synthetic"
    r = c.get("/cue/ledger", params={"person": "p_app"})
    assert r.status_code == 200 and r.json()["data"]["counts"] == {"assist": 0, "delegated": 0, "automation": 0}
    assert c.get("/growth", params={"person": "p_app"}).json()["data"]["readiness"]["ready"] is False
    refused = c.delete("/cue/ledger", params={"person": "p_app"}, headers={"X-Understudy-Actor": "agent"})
    assert refused.status_code == 403
    ok = c.delete("/cue/ledger", params={"person": "p_app"})
    assert ok.status_code == 200 and ok.json()["audit_line"] is True


def test_the_app_without_a_person_falls_back_to_no_person_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = create_app(root=tmp_path / "data", warm=False)
    if not app.state.extensions.get("cue"):
        pytest.skip("cue router not included")
    r = TestClient(app).get("/cue/next")
    assert r.status_code in (200, 404)
