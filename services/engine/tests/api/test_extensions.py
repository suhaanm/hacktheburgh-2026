"""Extension routers (REQ-2): included only when the module imports AND its flag is on; a broken one never breaks the app."""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from understudy_engine.api.app import EXTENSIONS, create_app, extension_flags

LAYERS = list(EXTENSIONS)
FLAG_VARS = ["UNDERSTUDY_X"] + [f"UNDERSTUDY_X_{layer.upper()}" for layer in LAYERS]


def fake_router_module(layer: str) -> types.ModuleType:
    mod = types.ModuleType(f"understudy_engine.{EXTENSIONS[layer]}")
    r = APIRouter()

    @r.get(f"/{layer}/ping")
    def ping():  # pragma: no cover - exercised through the client
        return {"layer": layer}

    mod.router = r
    return mod


@pytest.fixture()
def fakes(monkeypatch):
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    for layer in LAYERS:
        monkeypatch.setitem(sys.modules, f"understudy_engine.{EXTENSIONS[layer]}", fake_router_module(layer))
    return monkeypatch


def app_and_client(tmp_path):
    app = create_app(tmp_path / "data", warm=False)
    return app, TestClient(app)


def test_flags_off_exclude_every_extension_even_when_the_module_exists(fakes, tmp_path):
    app, c = app_and_client(tmp_path)
    for layer in LAYERS:
        assert c.get(f"/{layer}/ping").status_code == 404
        assert app.state.router_status[EXTENSIONS[layer]].startswith("off")
    h = c.get("/health").json()
    assert h["extensions"] == {layer: False for layer in LAYERS} and h["x_flag"] is False


def test_a_layer_flag_includes_only_that_layer(fakes, tmp_path):
    fakes.setenv("UNDERSTUDY_X_CALENDAR", "1")
    app, c = app_and_client(tmp_path)
    assert c.get("/calendar/ping").json() == {"layer": "calendar"}
    for layer in LAYERS:
        if layer != "calendar":
            assert c.get(f"/{layer}/ping").status_code == 404
    h = c.get("/health").json()
    assert h["extensions"] == {layer: layer == "calendar" for layer in LAYERS} and h["x_flag"] is False
    assert app.state.router_status["routes_calendar"] == "included"


def test_the_master_flag_includes_all_five(fakes, tmp_path):
    fakes.setenv("UNDERSTUDY_X", "1")
    app, c = app_and_client(tmp_path)
    for layer in LAYERS:
        assert c.get(f"/{layer}/ping").json() == {"layer": layer}
    h = c.get("/health").json()
    assert h["extensions"] == {layer: True for layer in LAYERS} and h["x_flag"] is True


@pytest.mark.parametrize("value,on", [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("", False), ("no", False), ("2", False)])
def test_flag_values(fakes, value, on):
    fakes.setenv("UNDERSTUDY_X_GIT", value)
    assert extension_flags()["git"] is on and extension_flags()["privacy"] is False


class _Boom:
    """A module whose import raises something other than ImportError."""

    def __init__(self, name):
        self.name = name

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name:
            raise RuntimeError("boom at import")
        return None


def test_import_errors_are_tolerated_and_recorded(fakes, tmp_path):
    fakes.setenv("UNDERSTUDY_X", "1")
    fakes.delitem(sys.modules, "understudy_engine.routes_privacy")
    boom = _Boom("understudy_engine.routes_privacy")
    sys.meta_path.insert(0, boom)                                                           # importing it raises RuntimeError
    try:
        broken = types.ModuleType("understudy_engine.routes_git")                           # imports, but has no router
        fakes.setitem(sys.modules, "understudy_engine.routes_git", broken)
        fakes.setitem(sys.modules, "understudy_engine.routes_localmodel", None)             # import halted (None in sys.modules)
        app, c = app_and_client(tmp_path)
    finally:
        sys.meta_path.remove(boom)
    st = app.state.router_status
    assert st["routes_privacy"] == "import failed: RuntimeError: boom at import"
    assert st["routes_git"].startswith("import failed") and "router" in st["routes_git"]
    assert st["routes_localmodel"] in ("absent",) or st["routes_localmodel"].startswith("import failed")
    for layer in ("privacy", "git", "localmodel"):
        assert c.get(f"/{layer}/ping").status_code == 404
    h = c.get("/health").json()
    assert [h["extensions"][k] for k in ("privacy", "git", "localmodel")] == [False, False, False]
    assert h["extensions"]["calendar"] is True and h["extensions"]["proactive"] is True and h["x_flag"] is True
    assert c.get("/packs").status_code == 200 and c.get("/coach/next", params={"person": "p_x"}).status_code == 200      # everything else is untouched


def test_a_missing_module_is_reported_absent(tmp_path, monkeypatch):
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("UNDERSTUDY_X_PROACTIVE", "1")
    for k in [k for k in sys.modules if k == "understudy_engine.routes_proactive"]:
        monkeypatch.delitem(sys.modules, k)
    app, c = app_and_client(tmp_path)
    import importlib.util

    if importlib.util.find_spec("understudy_engine.routes_proactive") is None:
        assert app.state.router_status["routes_proactive"] == "absent" and c.get("/health").json()["extensions"]["proactive"] is False
    else:                                                                                   # the real router has landed
        assert app.state.router_status["routes_proactive"] in ("included",) or app.state.router_status["routes_proactive"].startswith("import failed")


def test_flags_are_read_at_startup_not_per_request(fakes, tmp_path):
    app, c = app_and_client(tmp_path)
    fakes.setenv("UNDERSTUDY_X", "1")                                                       # set after the app exists: no effect
    assert c.get("/privacy/ping").status_code == 404 and c.get("/health").json()["extensions"]["privacy"] is False


def test_existing_routers_and_cors_are_unchanged(fakes, tmp_path):
    fakes.setenv("UNDERSTUDY_X", "1")
    app, c = app_and_client(tmp_path)
    assert app.state.router_status["routes_data"] == "included" and app.state.router_status["routes_coach"] == "included"
    paths = c.get("/openapi.json").json()["paths"]
    assert "/coach/next" in paths and "/genome/{task}" in paths and "/privacy/ping" in paths
    ok = c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in c.get("/health", headers={"Origin": "http://evil.example"}).headers
    pre = c.options("/events", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                        "Access-Control-Request-Headers": "x-understudy-actor,content-type"})
    assert pre.status_code == 200 and "x-understudy-actor" in pre.headers["access-control-allow-headers"].lower()


# ---------------------------------------------------------------------------------------- local model shutdown
def fake_localmodel(monkeypatch, shutdown):
    mod = types.ModuleType("understudy_engine.localmodel")
    mod.shutdown = shutdown
    monkeypatch.setitem(sys.modules, "understudy_engine.localmodel", mod)


def test_shutdown_is_called_once_when_the_engine_stops(fakes, tmp_path):
    calls = []
    fake_localmodel(fakes, lambda: calls.append(1))
    app = create_app(tmp_path / "data", warm=False)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200 and calls == []          # not before shutdown
    assert calls == [1]


def test_a_raising_shutdown_does_not_break_the_exit(fakes, tmp_path):
    def boom():
        raise RuntimeError("llama-server would not stop")

    fake_localmodel(fakes, boom)
    app = create_app(tmp_path / "data", warm=False)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200                           # leaving the context must not raise


def test_a_slow_shutdown_never_holds_the_exit_up_longer_than_the_timeout(fakes, tmp_path):
    import threading
    import time

    from understudy_engine.api import app as appmod

    release = threading.Event()
    fake_localmodel(fakes, lambda: release.wait(10))
    fakes.setattr(appmod, "SHUTDOWN_TIMEOUT_S", 0.3)
    t = time.time()
    assert appmod.shutdown_localmodel() is False and time.time() - t < 1.5   # gave up after 0.3 s, did not hang
    release.set()
    assert appmod.shutdown_localmodel(timeout=2.0) is True                   # a quick one reports success


def test_no_localmodel_module_loaded_means_nothing_to_stop(fakes, tmp_path):
    from understudy_engine.api.app import shutdown_localmodel

    fakes.delitem(sys.modules, "understudy_engine.localmodel", raising=False)
    fakes.setitem(sys.modules, "understudy_engine.localmodel", types.ModuleType("understudy_engine.localmodel"))   # no shutdown() defined
    assert shutdown_localmodel() is False
    fakes.delitem(sys.modules, "understudy_engine.localmodel")
    assert shutdown_localmodel() is False
    app = create_app(tmp_path / "data", warm=False)
    with TestClient(app):
        pass
