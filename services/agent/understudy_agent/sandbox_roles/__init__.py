"""Role sandboxes for the simulated study (STU): a programmer workbench and a data-analyst workbench.

Local only, synthetic data only, on PRIVATE ports (never the shared 7801-7803 sites, the engine :7700, the agent :7710 or the
dashboard). Fixed port blocks, so the pack capture configs can name them and several private worlds can run side by side:

    programmer  7941 .. 7948      data analyst  7951 .. 7958      (tests use ephemeral ports: ``RoleServer(spec, port=0)``)

``base.py`` holds the shared server (state log, reset, state dump, glitches, static files); ``programmer/`` and ``analyst/`` hold
the task catalogue, the page, the oracle and the scripted programs of each role. See ``base.py`` for the contract the study harness
(`evals/study_roles`) relies on.
"""
from __future__ import annotations

HOST = "127.0.0.1"
PROGRAMMER_PORTS = tuple(range(7941, 7949))
ANALYST_PORTS = tuple(range(7951, 7959))
ROLE_PORTS = {"programmer": PROGRAMMER_PORTS, "data-analyst": ANALYST_PORTS}

__all__ = ["HOST", "PROGRAMMER_PORTS", "ANALYST_PORTS", "ROLE_PORTS"]
