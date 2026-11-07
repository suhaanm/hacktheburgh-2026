"""The programmer workbench (see ``sandbox_roles/base.py`` for the contract). In-page JavaScript, participant code runs only inside a Web Worker
in the browser (no network APIs, a 1.5 s wall-clock cap, terminated on timeout, strict CSP); nothing runs on the host."""
from __future__ import annotations

from pathlib import Path

from ..base import RoleServer, RoleSpec
from .oracle import score
from .page import render_page
from .programs import program, snippets
from .tasks import SKILLS, TASKS, hidden_payload, naive, reference, ticket

STATIC = Path(__file__).resolve().parent / "static"
SPEC = RoleSpec(role="programmer", static_dir=STATIC, tasks=TASKS, render_page=render_page, title="Programmer workbench")


def make_server(port: int = 0) -> RoleServer:
    return RoleServer(SPEC, port=port)


__all__ = ["SPEC", "TASKS", "SKILLS", "ticket", "hidden_payload", "reference", "naive", "score", "program", "snippets", "make_server"]
