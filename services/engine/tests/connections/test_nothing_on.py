"""'No defaults on' (D48 turns the layer on; it never turns a connection on): a fresh state has every connection off, nothing connects when the app is
built, when a screen lists them, in mock mode, in a demo or with every default flag applied, and the only code that records a consent is the route
that carries the worker's click."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from understudy_engine.connections import registry, service, state
from understudy_engine.connections.paths import state_path

REPO = Path(__file__).resolve().parents[4]
SOURCES = [REPO / "services" / "engine" / "understudy_engine", REPO / "services" / "agent" / "understudy_agent"]


def test_a_fresh_state_has_every_connection_off_and_no_state_file():
    assert len(registry.all_presets()) == 15
    for p in registry.all_presets().values():
        assert state.status(p) == {"state": "off", "mode": None, "reason": None}
        assert state.record(p.id) is None and state.is_connected(p) is False
    assert [v["state"] for v in service.listing()] == ["off"] * 15
    assert not state_path().exists(), "reading the list writes nothing"


@pytest.mark.parametrize("mock", [False, True])
def test_building_the_engine_app_and_listing_everything_connects_nothing(monkeypatch, mock):
    from understudy_engine.api.flags import apply_default_flags

    if mock:
        monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for name in ("UNDERSTUDY_X", "UNDERSTUDY_X_CONNECTIONS"):
        monkeypatch.delenv(name, raising=False)
    env = {}
    apply_default_flags(env)                                              # every default flag, exactly as a running service sets them
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from understudy_engine.api.app import create_app

    app = create_app()
    client = TestClient(app)
    assert app.state.extensions["connections"] is True, "the layer is on by default (D48)"
    for path in ("/connections", "/connections?role=programmer", "/connections?role=data-analyst", "/connections?role=benefits-processor", "/connections/github",
                 "/connections/github/reads", "/health"):
        assert client.get(path).status_code == 200, path
    assert all(c["state"] == "off" for c in client.get("/connections").json()["data"])
    assert not state_path().exists()


def test_the_agent_app_and_its_service_start_and_connect_nothing(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")
    from understudy_agent.connections.service import default_service
    from understudy_agent.server import create_app

    app = create_app()
    svc = default_service()
    assert svc.runner._conns == {} and svc.runner._launches == {}
    assert TestClient(app).get("/health").status_code == 200
    assert not state_path().exists() and svc.runner._conns == {}
    svc.runner.stop_all()


def _calls(tree: ast.AST, attr: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr:
            yield node


def _scan(attr: str, receiver_hint: str | None = None) -> set[str]:
    found: set[str] = set()
    for base in SOURCES:
        for f in base.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for call in _calls(tree, attr):
                recv = ast.unparse(call.func.value)
                if receiver_hint is None or receiver_hint in recv:
                    found.add(str(f.relative_to(REPO)))
    return found


def test_the_only_code_that_records_a_consent_is_the_route_that_carries_the_workers_click():
    assert _scan("connect", "state") == {"services/engine/understudy_engine/connections/routes.py"}
    assert _scan("reconfirm", "state") == {"services/engine/understudy_engine/connections/routes.py"}
    assert _scan("set_routine", "state") == {"services/engine/understudy_engine/connections/routes.py"}


def test_the_only_code_that_starts_a_connection_process_is_the_service_behind_a_consented_record():
    assert _scan("start", "runner") == {"services/agent/understudy_agent/connections/service.py"}
    assert _scan("start", "default_service()") <= {"services/agent/understudy_agent/connections/routes.py"}
    # and the service only starts what usable() lets through: the worker switched it on and the pin matches
    src = (REPO / "services/agent/understudy_agent/connections/service.py").read_text()
    start = src[src.index("    def _start("):src.index("    def stop(")]
    assert "self.usable(conn_id)" in start and start.index("self.usable(conn_id)") < start.index("self.runner.start(")


def test_no_module_of_ours_creates_a_connection_record_at_import_or_boot():
    import importlib

    for mod in ("understudy_engine.connections", "understudy_engine.connections.routes", "understudy_engine.connections.service", "understudy_engine.connections.registry",
                "understudy_agent.connections", "understudy_agent.connections.service", "understudy_agent.connections.hook", "understudy_agent.connections.routes"):
        importlib.import_module(mod)
    assert not state_path().exists()
    for p in registry.all_presets().values():
        assert p.real is None or p.real["verified"] is True
    import yaml
    from understudy_engine.plugins.loader import presets_dir

    for f in presets_dir().glob("*.yaml"):
        m = yaml.safe_load(f.read_text())
        assert m["default_enabled"] is False, f.name
    assert not any("enabled: true" in f.read_text().lower() for f in presets_dir().glob("*.yaml"))
