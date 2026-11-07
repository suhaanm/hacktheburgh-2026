"""Run a program on a programmer case, grade it, return (verdict, state). Shared by the tests and the screenshot script."""
from __future__ import annotations

import httpx

from understudy_agent.sandbox_roles import programmer as P
from understudy_agent.sandbox_roles.programs_util import run_program


def play(page, server, task_id: str, variant: int, steps: list[tuple], *, layout: str = "", glitch: str = "", grade: bool = True, pace: float = 0.0):
    httpx.post(server.url + "/__reset", timeout=5)
    page.goto(server.case_url(task_id, variant, layout=layout, glitch=glitch))
    page.wait_for_selector("#editor")
    run_program(page, steps, pace=pace)
    page.evaluate("window.__flush()")
    if grade:
        page.evaluate("(h) => window.__grade(h)", P.hidden_payload(task_id, variant))
    state = httpx.get(server.url + "/__state", timeout=5).json()
    verdict = P.score(task_id, variant, state) if grade else None
    return verdict, state
