"""Deterministic offline runs: scripted model replies for the mock provider (UNDERSTUDY_MOCK=1, NFR-2).

The agent-safety `MockProvider` (and the privacy kit's `CapturingPort`) return a scripted reply for a call whose schema
`title` matches. The runtime's titles are `agent_plan` (the parent) and `child_step_<role>` (one per role), so a run is
scripted by queueing, through the providers' public hooks only, one plan and the steps of each role. The scripts are
menu replies (ids), exactly what a real model would return; the work they trigger is real (real sandboxed scripts, real
checks). Nothing in the providers is edited.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from ..models.mock_provider import MockProvider
from .spec import roles


class AdaptiveMock(MockProvider):
    """The mock provider plus optional POLICIES: a function that stands in for the model on a schema title and chooses its reply
    from the typed payload (what the model would receive through the egress guard). It lets a long-horizon run be deterministic
    AND adaptive (what it does next depends on the typed signals), and a step that was interrupted is simply planned again.
    Only subclasses the public provider; nothing in it is edited."""

    def __init__(self, scenario: str = "benefits_clean") -> None:
        super().__init__(scenario)
        self._policies: dict[str, Any] = {}

    def set_policy(self, title: str, fn: Any) -> None:
        self._policies[title] = fn

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        fn = self._policies.get((schema or {}).get("title", ""))
        if fn is None:
            return super().plan(messages, schema)
        self._record("plan", messages=copy.deepcopy(messages), schema=schema)
        payload = json.loads(messages[-1]["content"])["payload"]
        return copy.deepcopy(fn(payload))


def mock_plan(kind: str) -> dict[str, Any]:
    from .exemplars.base import KINDS

    rdefs = roles()
    children = []
    for i, role in enumerate(KINDS[kind].roles, 1):
        rd = rdefs[role]
        ws = "worktree" if "worktree" in rd.workspaces else "tmp" if "tmp" in rd.workspaces else "none"
        steps, secs, toks = KINDS[kind].budget
        children.append({"id": f"c{i}", "role": role, "tools": sorted(rd.allowed_tools), "max_steps": steps, "max_seconds": secs,
                         "max_tokens": toks, "workspace": ws, "output_schema": rd.output_schema, "playbook": rd.playbook})
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
    """Queue the scripted replies when the port is the mock or the capturing test port; real providers are untouched. A kind
    with a policy gets it on an AdaptiveMock (the policy replaces the child-step script); the parent's plan is always scripted."""
    if getattr(port, "name", "") not in ("mock", "capturing"):
        return False
    from .exemplars.base import KINDS

    ex = KINDS[kind]
    scripts = scripts_for(kind, params)
    if ex.policy is not None and hasattr(port, "set_policy"):
        for role in ex.roles:
            scripts.pop(f"child_step_{role}", None)
            port.set_policy(f"child_step_{role}", lambda payload, role=role: ex.policy(role, params, payload))  # type: ignore[misc]
    return install(port, scripts)
