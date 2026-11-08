"""The tasks router is an optional router of the agent server: /health says whether it loaded, and a broken one never breaks the rest."""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from understudy_agent.server import create_app

URLS = {"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"}


def test_health_reports_the_tasks_router():
    app = create_app(base_urls=URLS, autostart_sandbox=False, shared_sites=False)
    assert app.state.extensions["tasks"] is True and app.state.extension_status["tasks"] == "enabled"
    with TestClient(app) as c:
        h = c.get("/health").json()
        assert h["ok"] is True and h["extensions"]["tasks"] is True
        assert c.get("/tasks").json() == []


def test_a_broken_tasks_router_never_breaks_the_server(monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_agent.tasks.routes", None)          # makes `from .tasks.routes import ...` fail
    app = create_app(base_urls=URLS, autostart_sandbox=False, shared_sites=False)
    assert app.state.extensions["tasks"] is False and app.state.extension_status["tasks"].startswith("not loaded: ")
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"] is True and c.get("/tasks").status_code == 404
