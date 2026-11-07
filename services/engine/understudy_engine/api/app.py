"""FastAPI app for the engine (port ENGINE_PORT, default 7700).

``routes_data`` is ours; ``routes_analytics`` and ``routes_handoff`` belong to the other engine tracks and are
included only if they import. A router that exists but fails to import is reported on /health-adjacent logs and in
``app.state.router_status`` rather than silently skipped.
"""
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..genome import GenomeService
from ..store import EventStore
from .errors import install_error_handlers

log = logging.getLogger("understudy.engine")
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
OPTIONAL_ROUTERS = ("routes_analytics", "routes_handoff")


def create_app(root: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="Understudy engine", version=__version__, description="Event store, analytics, packs, queue, audit and kill switch. See docs/API_CONTRACT.md.")
    extra = [o.strip() for o in os.environ.get("UNDERSTUDY_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=DASHBOARD_ORIGINS + extra, allow_methods=["*"], allow_headers=["*"], max_age=600,
    )
    install_error_handlers(app)
    app.state.store = EventStore(root)
    app.state.genome = GenomeService(app.state.store)

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
