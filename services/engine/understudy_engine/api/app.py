"""FastAPI app for the engine (port ENGINE_PORT, default 7700).

``routes_data`` is ours; ``routes_analytics`` and ``routes_handoff`` belong to the other engine tracks and are
included only if they import. A router that exists but fails to import is reported on /health-adjacent logs and in
``app.state.router_status`` rather than silently skipped.
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..genome import GenomeService
from ..store import EventStore
from .errors import install_error_handlers

log = logging.getLogger("understudy.engine")
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
OPTIONAL_ROUTERS = ("routes_analytics", "routes_handoff", "routes_coach")


def warm_up(app: FastAPI) -> threading.Thread:
    """Fill the expensive caches in the background so the first dashboard request is fast: the genome (null, placebo,
    decomposition) and, if the analytics router has one, its own warm-up. Never raises, never blocks startup."""

    def run() -> None:
        from ..genome import TASK, GenomeError

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

    th = threading.Thread(target=run, name="engine-warm-up", daemon=True)
    th.start()
    return th


def create_app(root: Path | str | None = None, warm: bool | None = None) -> FastAPI:
    """``warm``: start the cache warm-up when the app starts serving (default: yes, unless UNDERSTUDY_NO_WARM is set)."""
    if warm is None:
        warm = not os.environ.get("UNDERSTUDY_NO_WARM")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if warm:
            warm_up(app)
        yield

    app = FastAPI(title="Understudy engine", version=__version__, lifespan=lifespan,
                  description="Event store, analytics, packs, queue, audit and kill switch. See docs/API_CONTRACT.md.")
    app.state.warm = {}
    extra = [o.strip() for o in os.environ.get("UNDERSTUDY_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=DASHBOARD_ORIGINS + extra, allow_methods=["*"], allow_headers=["*"], max_age=600,
    )
    install_error_handlers(app)
    app.state.store = EventStore(root)
    app.state.genome = GenomeService(app.state.store)
    from ..coach import CoachBrain

    app.state.coach = CoachBrain(app.state.store, root=root)

    from .. import routes_data

    app.include_router(routes_data.router)
    status: dict[str, str] = {"routes_data": "included"}
    for name in OPTIONAL_ROUTERS:
        try:
            mod = importlib.import_module(f"understudy_engine.{name}")
            app.include_router(mod.router)
            status[name] = "included"
        except ModuleNotFoundError as exc:
            if exc.name == f"understudy_engine.{name}":
                status[name] = "absent"
            else:
                status[name] = f"import failed: {exc}"
                log.warning("router %s not included: %s", name, exc)
        except Exception as exc:  # a broken sibling track must not take the data routes down
            status[name] = f"import failed: {type(exc).__name__}: {exc}"
            log.warning("router %s not included: %s", name, exc)
    app.state.router_status = status
    return app


app = create_app()
