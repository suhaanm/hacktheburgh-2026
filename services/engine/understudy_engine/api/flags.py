"""Extension flags (REQ-2, D24 to D27): ``UNDERSTUDY_X=1`` turns every extension layer on; ``UNDERSTUDY_X_<LAYER>=1`` turns one on.

Kept free of imports from the app so the demo seed and the routers can read the same answer without building an app.
"""
from __future__ import annotations

import os

# layer -> the module holding its router (understudy_engine.<module>). The first five are flat routes_* modules; the later layers
# are packages with a `routes` module. A module that has not landed yet is simply skipped (reported "absent").
EXTENSIONS = {
    "privacy": "routes_privacy",
    "localmodel": "routes_localmodel",
    "calendar": "routes_calendar",
    "git": "routes_git",
    "proactive": "routes_proactive",
    "cue": "cue.routes",
    "awareness": "awareness.routes",
    "evidence": "evidence.routes",
}
_TRUE = ("1", "true", "yes", "on")


def env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def extension_flags(env_on_fn=env_on) -> dict[str, bool]:
    """``{layer: bool}`` from the environment: the master flag UNDERSTUDY_X, or the layer's own UNDERSTUDY_X_<LAYER>."""
    master = env_on_fn("UNDERSTUDY_X")
    return {layer: master or env_on_fn(f"UNDERSTUDY_X_{layer.upper()}") for layer in EXTENSIONS}
