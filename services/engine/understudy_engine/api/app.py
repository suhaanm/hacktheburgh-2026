"""FastAPI app for the engine (port ENGINE_PORT, default 7700).

``routes_data`` is ours; ``routes_analytics`` and ``routes_handoff`` belong to the other engine tracks and are
included only if they import. A router that exists but fails to import is reported on /health-adjacent logs and in
``app.state.router_status`` rather than silently skipped.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..genome import GenomeService
from .. import http_guard
from ..store import EventStore
from .errors import install_error_handlers

log = logging.getLogger("understudy.engine")
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
OPTIONAL_ROUTERS = ("routes_analytics", "routes_handoff", "routes_coach")
# Extensions (REQ-2, D24 to D27): each router is included only when it imports AND its flag is on (api/flags.py). A module that
# also defines enabled() must agree. UNDERSTUDY_X=1 turns them all on; UNDERSTUDY_X_<LAYER>=1 turns one on. Flags are read once,
# when the app is created.
from .flags import EXTENSIONS, env_on as _env_on, extension_flags  # noqa: E402,F401  (re-exported: the tests and the demo seed use them)


def _include(app: FastAPI, name: str, status: dict[str, str], *, extension: bool = False) -> bool:
    """Import ``understudy_engine.<name>`` and include its ``router``. Never raises: the reason goes into ``status``.

    For an extension module that defines ``enabled()``, the module has the last word: if it says off, the router is left out."""
    try:
        mod = importlib.import_module(f"understudy_engine.{name}")
        if extension and callable(getattr(mod, "enabled", None)) and not mod.enabled():
            status[name] = "off (module reports disabled)"
            return False
        app.include_router(mod.router)
        status[name] = "included"
        return True
    except ModuleNotFoundError as exc:
        if f"understudy_engine.{name}".startswith(exc.name or "\0"):         # the module or one of its parent packages is not there
            status[name] = "absent"
        else:
            status[name] = f"import failed: {exc}"
            log.warning("router %s not included: %s", name, exc)
    except Exception as exc:  # a broken sibling track must not take the data routes down
        status[name] = f"import failed: {type(exc).__name__}: {exc}"
        log.warning("router %s not included: %s", name, exc)
    return False


SHUTDOWN_TIMEOUT_S = 3.0      # the local model's shutdown may never hold the engine's exit up longer than this


def shutdown_localmodel(timeout: float | None = None) -> bool:
    """Stop the llama-server this process started, if the local-model layer was loaded: ``understudy_engine.localmodel.shutdown()``.

    Only looks at the module if something already imported it (a process that never loaded it started no server). It never
    raises and never blocks longer than ``timeout`` seconds; returns True when shutdown() ran to completion in time."""
    mod = sys.modules.get("understudy_engine.localmodel")
    fn = getattr(mod, "shutdown", None) if mod is not None else None
    if not callable(fn):
        return False
    done = threading.Event()

    def run() -> None:
        try:
            fn()
        except Exception as exc:  # shutdown must not fail the exit
            log.warning("localmodel.shutdown() raised: %s", exc)
        finally:
            done.set()

    threading.Thread(target=run, name="localmodel-shutdown", daemon=True).start()
    return done.wait(SHUTDOWN_TIMEOUT_S if timeout is None else timeout)


def warm_extensions(app: FastAPI) -> list[str]:
    """Start ``warm(background=True)`` for every extension router that is on and defines one (routes_git does). Never raises."""
    started = []
    for layer, on in getattr(app.state, "extensions", {}).items():
        if not on:
            continue
        mod = sys.modules.get(f"understudy_engine.{EXTENSIONS[layer]}")
        fn = getattr(mod, "warm", None)
        if callable(fn):
            try:
                fn(background=True)
                started.append(layer)
            except Exception as exc:  # pragma: no cover
                log.warning("%s warm-up failed: %s", layer, exc)
    return started


def tune_gc(*, freeze: bool = True) -> None:
    """Keep Python's cycle collector from re-scanning the engine's large, long-lived caches on every allocation burst.

    The warmed cohorts, the seeded role histories and the firm roster make a heap of a few GB of long-lived objects. With the default thresholds a busy
    moment (a page that fires six data requests) triggered full collections that each walk that whole heap: the process sat at 100% CPU inside the
    collector and even /health timed out, which the app reports as "Knack cannot reach its engine". Freezing what is already loaded moves it out of the
    collector's reach, and larger thresholds make the collections that remain rare. Nothing is disabled: new garbage cycles are still collected."""
    import gc

    gc.set_threshold(200_000, 50, 50)
    if freeze:
        gc.collect()
        gc.freeze()


def _freeze_loop(interval_s: float = 60.0) -> None:
    """Freeze again now and then: role histories and cohorts are loaded lazily, after the warm-up, and become long-lived too."""
    import gc
    import time

    while True:
        time.sleep(interval_s)
        try:
            gc.freeze()
        except Exception:  # pragma: no cover
            return


def warm_up(app: FastAPI) -> threading.Thread:
    """Fill the expensive caches in the background so the first dashboard request is fast: the genome (null, placebo,
    decomposition) and, if the analytics router has one, its own warm-up. Never raises, never blocks startup."""

    def run() -> None:
        from ..genome import TASK, GenomeError

        try:
            tune_gc(freeze=False)        # the warm-up itself builds the big heap: do not let the collector re-walk it while it grows
        except Exception as exc:  # pragma: no cover
            log.warning("gc tuning failed: %s", exc)
        t0 = __import__("time").time()
        try:
            app.state.genome.genome(TASK)
            app.state.genome.transitions(TASK)
            app.state.warm["genome"] = True
        except GenomeError:
            app.state.warm["genome"] = False          # no cohort yet (run `understudy synth --all`)
        except Exception as exc:  # pragma: no cover
            log.warning("genome warm-up failed: %s", exc)
            app.state.warm["genome"] = False
        try:
            app.state.coach.scorer.warm(background=False)
            app.state.warm["coach"] = app.state.coach.scorer.state == "ready"
        except Exception as exc:  # pragma: no cover
            log.warning("coach warm-up failed: %s", exc)
        try:
            mod = importlib.import_module("understudy_engine.routes_analytics")
            if hasattr(mod, "warm"):
                mod.warm(background=False)
                app.state.warm["analytics"] = True
        except Exception as exc:
            log.warning("analytics warm-up failed: %s", exc)
            app.state.warm["analytics"] = False
        app.state.warm["seconds"] = round(__import__("time").time() - t0, 2)
        try:
            tune_gc()
            threading.Thread(target=_freeze_loop, name="engine-gc-freeze", daemon=True).start()
        except Exception as exc:  # pragma: no cover
            log.warning("gc tuning failed: %s", exc)

    th = threading.Thread(target=run, name="engine-warm-up", daemon=True)
    th.start()
    return th


def create_app(root: Path | str | None = None, warm: bool | None = None) -> FastAPI:
    """``warm``: start the cache warm-up when the app starts serving (default: yes, unless UNDERSTUDY_NO_WARM is set)."""
    if warm is None:
        warm = not os.environ.get("UNDERSTUDY_NO_WARM")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not http_guard.test_relaxed():
            http_guard.rotate_token()          # the per-boot token for release routes: every server start writes a fresh one (mode 0600)
        if warm:
            warm_up(app)
            warm_extensions(app)
        try:
            yield
        finally:
            shutdown_localmodel()

    app = FastAPI(title="Understudy engine", version=__version__, lifespan=lifespan,
                  description="Event store, analytics, packs, queue, audit and kill switch. See docs/API_CONTRACT.md.")
    app.state.warm = {}
    # CORS answers preflights from exactly the origins the guard allows (the same parsed allow-list); the guard itself is added last,
    # so it is the outermost layer: Host, Origin, content type, actor and token are judged before anything else runs.
    ext_origins, ext_regex = http_guard.cors_extension()
    app.add_middleware(
        CORSMiddleware, allow_origins=http_guard.cors_origins() + ext_origins, allow_origin_regex=ext_regex,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=http_guard.CORS_ALLOW_HEADERS, max_age=600,
    )
    app.add_middleware(http_guard.GuardMiddleware, port=int(os.environ.get("UNDERSTUDY_ENGINE_LISTEN_PORT") or os.environ.get("ENGINE_PORT", "7700")), policy=http_guard.ENGINE_POLICY,
                   on_refusal=http_guard.RefusalAudit())
    install_error_handlers(app)
    if not http_guard.test_relaxed():
        http_guard.ensure_token()              # make sure data/.token exists; importing this module (tests, tools) never rotates a live token
    app.state.store = EventStore(root)
    app.state.genome = GenomeService(app.state.store)
    from ..coach import CoachBrain

    app.state.coach = CoachBrain(app.state.store, root=root)

    from .. import routes_data

    app.include_router(routes_data.router)
    status: dict[str, str] = {"routes_data": "included"}
    for name in OPTIONAL_ROUTERS:
        _include(app, name, status)
    flags = extension_flags()
    ext: dict[str, bool] = {}
    for layer, name in EXTENSIONS.items():
        if flags[layer]:
            ext[layer] = _include(app, name, status, extension=True)
        else:
            status[name] = "off (flag not set)"            # not even imported: a switched-off layer has no side effects
            ext[layer] = False
    app.state.extensions = ext
    app.state.x_flag = _env_on("UNDERSTUDY_X")
    app.state.router_status = status
    return app


app = create_app()
