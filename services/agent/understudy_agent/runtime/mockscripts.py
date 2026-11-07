"""Deterministic offline runs: scripted model replies for the mock provider (UNDERSTUDY_MOCK=1, NFR-2).

The agent-safety `MockProvider` (and the privacy kit's `CapturingPort`) return a scripted reply for a call whose schema
`title` matches. The runtime's titles are `agent_plan` (the parent) and `child_step_<role>` (one per role), so a run is
scripted by queueing, through the providers' public hooks only, one plan and the steps of each role. The scripts are
menu replies (ids), exactly what a real model would return; the work they trigger is real (real sandboxed scripts, real
checks). Nothing in the providers is edited.
"""
from __future__ import annotations

from typing import Any

from .spec import roles


def mock_plan(kind: str) -> dict[str, Any]:
    from .exemplars.base import KINDS

    rdefs = roles()
    children = []
    for i, role in enumerate(KINDS[kind].roles, 1):
        rd = rdefs[role]
        ws = "worktree" if "worktree" in rd.workspaces else "tmp" if "tmp" in rd.workspaces else "none"
        children.append({"id": f"c{i}", "role": role, "tools": sorted(rd.allowed_tools), "max_steps": 10, "max_seconds": 120,
                         "max_tokens": 20000, "workspace": ws, "output_schema": rd.output_schema, "playbook": rd.playbook})
    return {"children": children}


def scripts_for(kind: str, params: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """{schema title: [replies]} for one run of `kind`."""
    from .exemplars.base import KINDS

    ex = KINDS[kind]
    out: dict[str, list[dict[str, Any]]] = {"agent_plan": [mock_plan(kind)]}
    for role in ex.roles:
        out[f"child_step_{role}"] = [{"template": "none", **step} for step in ex.mock_steps(role, params)]
    return out


def install(port: Any, scripts: dict[str, list[dict[str, Any]]]) -> bool:
    hook = getattr(port, "script_plan", None) or getattr(port, "script", None)
    if hook is None:
        return False
    for title, replies in scripts.items():
        hook(title, *replies)
    return True


def install_if_mock(port: Any, kind: str, params: dict[str, Any]) -> bool:
    """Queue the scripted replies when the port is the mock or the capturing test port; real providers are untouched."""
    if getattr(port, "name", "") not in ("mock", "capturing"):
        return False
    return install(port, scripts_for(kind, params))
