"""Run a program on an analyst case, score it, return (verdict, state)."""
from __future__ import annotations

import httpx

from understudy_agent.sandbox_roles import analyst as A
from understudy_agent.sandbox_roles.programs_util import run_program


def play(page, server, task_id: str, variant: int, steps: list[tuple], *, layout: str = "", glitch: str = "", pace: float = 0.0):
    httpx.post(server.url + "/__reset", timeout=5)
    page.goto(server.case_url(task_id, variant, layout=layout, glitch=glitch))
    page.wait_for_selector("#data-table")
    run_program(page, steps, pace=pace)
    page.evaluate("window.__flush()")
    state = httpx.get(server.url + "/__state", timeout=5).json()
    return A.score(task_id, variant, state), state
