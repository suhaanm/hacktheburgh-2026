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


# ---------------------------------------------------------------------------------------- enabled() and warm()
def test_a_module_that_reports_disabled_is_left_out_even_when_the_flag_is_on(fakes, tmp_path):
    fakes.setenv("UNDERSTUDY_X", "1")
    git = fake_router_module("git")
    git.enabled = lambda: False
    fakes.setitem(sys.modules, "understudy_engine.routes_git", git)
    cal = fake_router_module("calendar")
    cal.enabled = lambda: True
    fakes.setitem(sys.modules, "understudy_engine.routes_calendar", cal)
    app, c = app_and_client(tmp_path)
    assert app.state.router_status["routes_git"] == "off (module reports disabled)" and c.get("/git/ping").status_code == 404
    assert app.state.router_status["routes_calendar"] == "included" and c.get("/calendar/ping").status_code == 200
    ext = c.get("/health").json()["extensions"]
    assert ext["git"] is False and ext["calendar"] is True


def test_warm_runs_only_for_extensions_that_are_on_and_only_at_startup(fakes, tmp_path):
    calls = []
    for layer in ("git", "calendar"):
        mod = fake_router_module(layer)
        mod.warm = lambda background=True, _l=layer: calls.append((_l, background))
        fakes.setitem(sys.modules, f"understudy_engine.{EXTENSIONS[layer]}", mod)
    fakes.setenv("UNDERSTUDY_X_GIT", "1")                                   # git on, calendar off
    app = create_app(tmp_path / "data", warm=True)
    assert calls == []                                                      # nothing before the app starts serving
    with TestClient(app):
        pass
    assert calls == [("git", True)]                                         # background=True, and only the layer that is on
    calls.clear()
    with TestClient(create_app(tmp_path / "d2", warm=False)):
        pass
    assert calls == []                                                      # warm=False: no warm-up at all


def test_a_raising_warm_does_not_break_startup(fakes, tmp_path):
    def boom(background=True):
        raise RuntimeError("cannot warm")

    mod = fake_router_module("git")
    mod.warm = boom
    fakes.setitem(sys.modules, "understudy_engine.routes_git", mod)
    fakes.setenv("UNDERSTUDY_X_GIT", "1")
    with TestClient(create_app(tmp_path / "data", warm=True)) as c:
        assert c.get("/git/ping").status_code == 200


# ---------------------------------------------------------------------------------------- the real routers
REAL_ROUTES = {"privacy": "/privacy/ledger", "localmodel": "/localmodel/status", "calendar": "/calendar/week", "git": "/git/habits",
               "proactive": "/briefing"}


FIRST_FIVE = ["privacy", "localmodel", "calendar", "git", "proactive"]
LATER = ["cue", "awareness", "evidence", "attention"]


def test_every_real_extension_router_is_included_behind_its_flag_and_listed_in_health(tmp_path, monkeypatch):
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    app, c = app_and_client(tmp_path)
    st = app.state.router_status
    assert {st[EXTENSIONS[layer]] for layer in FIRST_FIVE} == {"included"}, st      # the five routers have landed
    # the later layers: included once their module exists, simply skipped before that; never a failed import
    for layer in LATER:
        assert st[EXTENSIONS[layer]] in ("included", "absent"), (layer, st[EXTENSIONS[layer]])
    ext = c.get("/health").json()["extensions"]
    assert set(ext) == set(LAYERS) and all(ext[layer] for layer in FIRST_FIVE)
    assert all(ext[layer] == (st[EXTENSIONS[layer]] == "included") for layer in LATER)
    paths = c.get("/openapi.json").json()["paths"]
    for layer, path in REAL_ROUTES.items():
        assert any(p == path or p.startswith(path) for p in paths), (layer, path)


def test_with_no_flags_none_of_the_real_extension_routes_exist(tmp_path, monkeypatch):
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    app, c = app_and_client(tmp_path)
    paths = c.get("/openapi.json").json()["paths"]
    for layer, path in REAL_ROUTES.items():
        assert not any(p == path or p.startswith(path) for p in paths), (layer, path)
    assert c.get("/health").json()["extensions"] == {layer: False for layer in LAYERS}


def test_the_later_layers_are_found_by_their_dotted_module_and_skipped_when_missing(tmp_path, monkeypatch):
    """understudy_engine.cue.routes, awareness.routes, evidence.routes: try-import; a missing package or module is skipped, not an error."""
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    assert EXTENSIONS["cue"] == "cue.routes" and EXTENSIONS["awareness"] == "awareness.routes" and EXTENSIONS["evidence"] == "evidence.routes"
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    for layer in LATER:
        monkeypatch.delitem(sys.modules, f"understudy_engine.{EXTENSIONS[layer]}", raising=False)
    # a package that does not exist at all (not even its parent) is "absent", and a fake that does is included
    monkeypatch.setitem(sys.modules, "understudy_engine.evidence.routes", fake_router_module("evidence"))
    app, c = app_and_client(tmp_path)
    st = app.state.router_status
    assert st["evidence.routes"] == "included" and c.get("/evidence/ping").status_code == 200
    assert st["cue.routes"] in ("included", "absent") and st["awareness.routes"] in ("included", "absent")
    ext = c.get("/health").json()["extensions"]
    assert ext["evidence"] is True and set(ext) == set(LAYERS)


def test_the_attention_layer_is_wired_by_try_import_and_its_own_flag(tmp_path, monkeypatch):
    """understudy_engine.attention.routes (router + enabled()): listed in /health extensions, on with UNDERSTUDY_X or UNDERSTUDY_X_ATTENTION,
    skipped (never an error) while the module is missing."""
    assert EXTENSIONS["attention"] == "attention.routes"
    for var in FLAG_VARS:
        monkeypatch.delenv(var, raising=False)
    assert extension_flags()["attention"] is False
    monkeypatch.setenv("UNDERSTUDY_X_ATTENTION", "1")
    flags = extension_flags()
    assert flags["attention"] is True and not any(v for k, v in flags.items() if k != "attention")
    monkeypatch.delitem(sys.modules, "understudy_engine.attention.routes", raising=False)
    app, c = app_and_client(tmp_path)
    assert app.state.router_status["attention.routes"] in ("included", "absent")                   # absent until the ATTENTION track lands
    assert c.get("/health").json()["extensions"]["attention"] == (app.state.router_status["attention.routes"] == "included")
    monkeypatch.setitem(sys.modules, "understudy_engine.attention.routes", fake_router_module("attention"))
    app, c = app_and_client(tmp_path)
    assert app.state.router_status["attention.routes"] == "included" and c.get("/attention/ping").status_code == 200
    assert c.get("/health").json()["extensions"]["attention"] is True
    monkeypatch.delenv("UNDERSTUDY_X_ATTENTION")
    app, c = app_and_client(tmp_path)
    assert c.get("/health").json()["extensions"]["attention"] is False                               # no flag: not even imported
    assert c.get("/attention/ping").status_code == 404
