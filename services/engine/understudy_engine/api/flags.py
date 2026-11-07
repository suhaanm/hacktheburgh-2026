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
    "attention": "attention.routes",
    "hitlist": "hitlist.routes",
    "insights": "insights.routes",
}
_TRUE = ("1", "true", "yes", "on")


def env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def extension_flags(env_on_fn=env_on) -> dict[str, bool]:
    """``{layer: bool}`` from the environment: the master flag UNDERSTUDY_X, or the layer's own UNDERSTUDY_X_<LAYER>."""
    master = env_on_fn("UNDERSTUDY_X")
    return {layer: master or env_on_fn(f"UNDERSTUDY_X_{layer.upper()}") for layer in EXTENSIONS}


# ---------------------------------------------------------------------------------------------------------------------------
# Owner decision D48 (7 Nov 2026, chat): the product runs with its layers ON without any environment variable. A running
# service sets these defaults once at startup (``apply_default_flags``): an unset or empty variable becomes "1"; an explicit
# "0" (or any other value) is respected, so a flag can still be turned OFF per run. Tests never call this, so the layers stay
# off in the test environment unless a test turns them on.
#
# Deliberately NOT in this list, and why (docs/FLAGS.md): ALONGSIDE_AGENCY_LOOP and UNDERSTUDY_JXA_CLICK (the loop and the JXA click
# duplicate the Python actuator; the arm switch UNDERSTUDY_REAL_ACTUATOR is on by default in the agent service only, see D50 below), UNDERSTUDY_LEGACY_REMOTE (duplicates the ledgered Gemini and model paths; sends frames outside
# the ledger), the old wake word, scam and file-search flags, UNDERSTUDY_VOICE_DEBUG_TEXT (bypasses the fixed-lines rule),
# UNDERSTUDY_CU_FRAME_HINT (evidence against it), UNDERSTUDY_INSIGHTS_HELDOUT (a run-once guard), and the awareness glance
# settings (they need the worker's recorded consent and macOS Screen Recording).
DEFAULT_ON = (
    "UNDERSTUDY_X",               # every engine and agent extension layer
    "UNDERSTUDY_X_GEMINI",        # the Gemini model routes (glance, pointing, verifier), through the egress guard and ledger
    "UNDERSTUDY_X_LIVE",          # Gemini Live voice (hold to talk)
    "UNDERSTUDY_FLAG_VOICE",      # the voice feature in the desktop build
    "UNDERSTUDY_VOICE",           # ElevenLabs spoken lines (fixed vocabulary; Cue still speaks only on request, D36)
    "UNDERSTUDY_EVIDENCE_CLOUD",  # cloud wording attempt for "explain this": always behind the number check, template fallback
)


# D50 (owner, 7 Nov 2026, in chat, after the lead had left it off and explained why): the arm switch for real desktop clicks is ON by
# default in the AGENT service only (the engine never builds an actuator, so it never gets it). It is the arm switch, not the permission:
# every real action still needs a RunPermit made from the owner's one-time token (or, unattended, a routine's consent record), the pinned
# window, the countdown with the target app in front, the kill file and the supervisor stop; and the real backend needs pyobjc, which the
# agent environment does not install, so the actuator stays inert until the owner runs the documented R1 command. An explicit
# UNDERSTUDY_REAL_ACTUATOR=0 still turns it off.
AGENT_DEFAULT_ON = ("UNDERSTUDY_REAL_ACTUATOR",)


def apply_default_flags(environ: "dict[str, str] | None" = None, *, agent: bool = False) -> list[str]:
    """Set every DEFAULT_ON flag (and, with ``agent=True``, every AGENT_DEFAULT_ON flag) that is unset or empty to "1". Returns the names it
    set. An explicit value, including "0", wins."""
    env = os.environ if environ is None else environ
    changed: list[str] = []
    for name in DEFAULT_ON + (AGENT_DEFAULT_ON if agent else ()):
        if env.get(name, "").strip() == "":
            env[name] = "1"
            changed.append(name)
    return changed
