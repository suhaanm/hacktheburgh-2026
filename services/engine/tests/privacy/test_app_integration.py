"""The privacy router inside the real engine app: absent and unreachable when the flag is off, served when it is on."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from understudy_engine.api.app import create_app
from understudy_engine.privacy import egress
from understudy_engine.privacy.testing import CapturingPort


def app_client(tmp_path, monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("AGENT_PORT", "1")
    return TestClient(create_app(tmp_path / "root", warm=False))


def test_flag_off_means_the_privacy_routes_do_not_exist_and_p0_routes_still_work(tmp_path, monkeypatch):
    c = app_client(tmp_path, monkeypatch)
    assert c.get("/privacy/ledger").status_code == 404
    assert c.get("/privacy/summary").status_code == 404
    assert c.get("/health").status_code == 200
    assert c.get("/health").json().get("extensions", {}).get("privacy") in (False, None)
    assert not [p for p in c.app.openapi()["paths"] if p.startswith("/privacy")]


@pytest.mark.parametrize("env", [{"UNDERSTUDY_X_PRIVACY": "1"}, {"UNDERSTUDY_X": "1"}])
def test_flag_on_serves_the_ledger_and_summary(tmp_path, monkeypatch, env):
    c = app_client(tmp_path, monkeypatch, **env)
    egress.send("calendar.suggestion_wording", dict(template="protect_focus_block", role="programmer", risk="low", learner={"meeting_h": 9.0}, expert={}),
                port=CapturingPort())
    led = c.get("/privacy/ledger")
    assert led.status_code == 200 and led.json()["data"][0]["purpose"] == "calendar.suggestion_wording"
    s = c.get("/privacy/summary").json()["data"]
    assert s["calls"] == 1 and "does not claim that nothing else leaves" in s["local_only_note"]
    assert c.get("/health").json()["extensions"]["privacy"] is True
    assert c.post("/privacy/ledger/clear", headers={"x-understudy-actor": "worker"}).json()["cleared"] == 1


def test_the_privacy_package_is_not_imported_by_the_p0_modules():
    """NFR-10: nothing on the demo path imports the privacy layer (it is reached only through the flag-gated router)."""
    import pathlib
    import re

    root = pathlib.Path(__import__("understudy_engine").__file__).parent
    p0 = [root / "routes_data.py", root / "routes_analytics.py", root / "routes_handoff.py", root / "routes_coach.py", root / "core.py"]
    p0 += [p for d in ("store", "personas", "cogs", "genome", "packs", "hazard", "policy", "routing", "trust", "skills", "routines",
                       "presence", "memory", "coach") for p in (root / d).rglob("*.py") if (root / d).is_dir()]
    offenders = [str(p.relative_to(root)) for p in p0 if p.exists() and re.search(r"^\s*(from|import)\s+(\.+|understudy_engine\.)privacy\b", p.read_text(), re.M)]
    assert offenders == [], f"P0 modules import the privacy layer: {offenders}"
