"""The data-analyst workbench (see ``sandbox_roles/base.py`` for the contract). In-page JavaScript over a deterministic synthetic dataset; nothing is
executed from participant input (the participant uses fixed controls), nothing leaves the page but the action log."""
from __future__ import annotations

from pathlib import Path

from ..base import RoleServer, RoleSpec
from .oracle import score
from .page import render_page
from .programs import program, snippets
from .tasks import SKILLS, TASKS, naive_answer, question, truth

STATIC = Path(__file__).resolve().parent / "static"
SPEC = RoleSpec(role="data-analyst", static_dir=STATIC, tasks=TASKS, render_page=render_page, title="Analysis workbench")


def make_server(port: int = 0) -> RoleServer:
    return RoleServer(SPEC, port=port)


__all__ = ["SPEC", "TASKS", "SKILLS", "question", "truth", "naive_answer", "score", "program", "snippets", "make_server"]
