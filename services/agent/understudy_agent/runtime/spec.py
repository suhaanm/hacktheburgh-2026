"""Typed specs and results for the agent runtime (BGA-1).

`AgentSpec` is what a parent proposes for one child: role, tools, budgets (steps, seconds, tokens), workspace kind,
output schema id and playbook id. `validate_plan` is CODE: it checks every spec against policy before any child starts.
`ChildResult` is the typed outcome; `verified` is set only by code checks (results.py), never from a model's say-so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import policy

TOOL_NAMES: tuple[str, ...] = ("read_file", "list_dir", "git_log", "run_python", "write_workspace", "emit_result")
FILE_TOOLS = frozenset({"read_file", "list_dir", "git_log", "run_python", "write_workspace"})  # need a workspace
GIT_TOOLS = frozenset({"git_log"})                                                              # need a worktree
WorkspaceKind = Literal["tmp", "worktree", "none"]
ChildStatus = Literal["done", "failed", "stopped", "yielded", "timeout", "paused", "budget", "rejected", "killed",
                      "revoked", "no_result"]
_ID = re.compile(r"^c[1-4]$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class PolicyViolation(ValueError):
    """The plan broke policy. `errors` are short stable codes (safe for the audit log); nothing starts."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors[:6]))
        self.errors = errors


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: int = Field(ge=1)
    seconds: float = Field(gt=0)
    tokens: int = Field(ge=1)


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=_ID.pattern)
    role: str = Field(pattern=_SLUG.pattern)
    goal: str = Field(min_length=1, max_length=400)
    tools: list[str] = Field(min_length=1, max_length=len(TOOL_NAMES))
    budget: Budget
    workspace: WorkspaceKind
    output_schema: str = Field(pattern=_SLUG.pattern)
    playbook: str = Field(pattern=_SLUG.pattern)
    depth: int = 1


@dataclass(frozen=True)
class RoleDef:
    """What a role may be given. Registered by the exemplars; the parent can only pick from these."""

    id: str
    description: str
    allowed_tools: frozenset[str]
    workspaces: frozenset[str]
    output_schema: str
    playbook: str


_ROLES: dict[str, RoleDef] = {}


def register_role(role: RoleDef) -> RoleDef:
    bad = role.allowed_tools - set(TOOL_NAMES)
    if bad:
        raise ValueError(f"role {role.id}: unregistered tools {sorted(bad)}")
    _ROLES[role.id] = role
    return role


def roles() -> dict[str, RoleDef]:
    from . import exemplars  # noqa: F401  (registers the exemplar roles)

    return dict(_ROLES)


class Check(BaseModel):
    """One code check on a result. `detail` is a short code or number, never content from a file."""
    name: str
    ok: bool
    detail: str = ""


class Artifact(BaseModel):
    name: str
    kind: Literal["findings", "patch", "chart", "summary", "data", "log"]
    path_ref: str          # relative to the repo root, e.g. data/runs/<run>/artifacts/<child>/<name>
    sha256: str
    bytes: int


class Spent(BaseModel):
    steps: int = 0
    seconds: float = 0.0
    tokens: int = 0


class StepRecord(BaseModel):
    """What a step leaves behind: tool, verdict and the code postcheck. Never text from the workspace."""
    n: int
    tool: str
    ok: bool
    check: Literal["verified", "uncertain", "failed"]
    codes: list[str] = Field(default_factory=list)
    ms: int = 0


class ChildResult(BaseModel):
    child_id: str
    role: str
    status: ChildStatus
    verified: bool = False                      # set by code only
    claimed_success: bool = False               # the child called emit_result; a CLAIM until verified
    output: dict[str, Any] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    steps: list[StepRecord] = Field(default_factory=list)
    spent: Spent = Field(default_factory=Spent)
    reason: str = ""


# ---------------------------------------------------------------------------------------------- the parent's plan
def plan_schema(role_ids: list[str] | None = None, schema_ids: list[str] | None = None,
                playbook_ids: list[str] | None = None) -> dict[str, Any]:
    """The parent's reply shape. Closed menus only (ids and numbers): no free text goes in or comes out, so the whole
    exchange can pass the egress guard. `goal` is NOT part of it; code fills each child's goal from its role."""
    def menu(ids: list[str] | None) -> dict[str, Any]:
        return {"type": "string", "enum": ids} if ids else {"type": "string"}

    return {
        "title": "agent_plan",
        "type": "object",
        "required": ["children"],
        "properties": {
            "children": {
                "type": "array", "maxItems": policy.MAX_CHILDREN, "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["id", "role", "tools", "max_steps", "max_seconds", "max_tokens", "workspace",
                                 "output_schema", "playbook"],
                    "properties": {
                        "id": {"type": "string", "enum": [f"c{i}" for i in range(1, policy.MAX_CHILDREN + 1)]},
                        "role": menu(role_ids),
                        "tools": {"type": "array", "items": {"type": "string", "enum": list(TOOL_NAMES)}},
                        "max_steps": {"type": "integer", "minimum": 1},
                        "max_seconds": {"type": "number", "minimum": 1},
                        "max_tokens": {"type": "integer", "minimum": 1},
                        "workspace": {"type": "string", "enum": list(policy.WORKSPACE_KINDS)},
                        "output_schema": menu(schema_ids),
                        "playbook": menu(playbook_ids),
                    },
                },
            },
        },
    }


AGENT_PLAN_SCHEMA: dict[str, Any] = plan_schema()


def _clean_goal(text: str) -> str:
    return " ".join(str(text).split())


def parse_plan(raw: Any, goals: dict[str, str] | None = None) -> tuple[list[AgentSpec], list[str]]:
    """Turn the model's plan object into specs. Returns (specs, errors). Shape errors are codes, never echoed text."""
    errors: list[str] = []
    if not isinstance(raw, dict) or not isinstance(raw.get("children"), list):
        return [], ["plan:not_an_object_with_children"]
    extra = set(raw) - {"summary", "children"}  # a summary is tolerated and ignored
    if extra:
        errors.append("plan:unknown_keys")
    specs: list[AgentSpec] = []
    for i, c in enumerate(raw["children"]):
        if not isinstance(c, dict):
            errors.append(f"child[{i}]:not_an_object")
            continue
        known = {"id", "role", "goal", "tools", "max_steps", "max_seconds", "max_tokens", "workspace", "output_schema",
                 "playbook"}
        goal = (goals or {}).get(str(c.get("role"))) or c.get("goal", "")
        if set(c) - known:
            errors.append(f"child[{i}]:unknown_keys")
            continue
        try:
            specs.append(AgentSpec(
                id=c.get("id"), role=c.get("role"), goal=_clean_goal(goal), tools=c.get("tools"),
                budget=Budget(steps=c.get("max_steps"), seconds=c.get("max_seconds"), tokens=c.get("max_tokens")),
                workspace=c.get("workspace"), output_schema=c.get("output_schema"), playbook=c.get("playbook")))
        except ValidationError as e:
            fields = sorted({".".join(str(p) for p in err["loc"]) for err in e.errors()})[:4]
            errors.append(f"child[{i}]:invalid:{','.join(fields)}")
    return specs, errors


def validate_plan(specs: list[AgentSpec], *, known_playbooks: set[str] | None = None,
                  known_schemas: set[str] | None = None) -> list[str]:
    """Every check the parent's plan must pass BEFORE anything starts. Returns error codes (empty = valid)."""
    errs: list[str] = []
    rdefs = roles()
    if not specs:
        errs.append("plan:no_children")
    if len(specs) > policy.MAX_CHILDREN:
        errs.append(f"plan:too_many_children:{len(specs)}>{policy.MAX_CHILDREN}")
    ids = [s.id for s in specs]
    if len(set(ids)) != len(ids):
        errs.append("plan:duplicate_child_ids")
    if len({s.role for s in specs}) != len(specs):
        errs.append("plan:duplicate_roles")
    for s in specs:
        p = f"{s.id}:"
        role = rdefs.get(s.role)
        if role is None:
            errs.append(p + "role_unregistered")
        if s.depth != policy.MAX_DEPTH:
            errs.append(p + "depth_not_allowed")
        if len(set(s.tools)) != len(s.tools):
            errs.append(p + "duplicate_tools")
        unknown = [t for t in s.tools if t not in TOOL_NAMES]
        if unknown:
            errs.append(p + "tool_unregistered")
        if role is not None:
            beyond = [t for t in s.tools if t in TOOL_NAMES and t not in role.allowed_tools]
            if beyond:
                errs.append(p + "tool_not_allowed_for_role")
            if s.workspace not in role.workspaces:
                errs.append(p + "workspace_not_allowed_for_role")
            if s.output_schema != role.output_schema:
                errs.append(p + "output_schema_not_for_role")
            if s.playbook != role.playbook:
                errs.append(p + "playbook_not_for_role")
        if s.workspace == "none" and any(t in FILE_TOOLS for t in s.tools):
            errs.append(p + "file_tools_need_a_workspace")
        if s.workspace != "worktree" and any(t in GIT_TOOLS for t in s.tools):
            errs.append(p + "git_tools_need_a_worktree")
        if "emit_result" not in s.tools:
            errs.append(p + "no_emit_result_tool")
        if s.budget.steps > policy.MAX_STEPS:
            errs.append(p + f"budget_steps_over_cap:{s.budget.steps}>{policy.MAX_STEPS}")
        if s.budget.seconds > policy.MAX_SECONDS:
            errs.append(p + "budget_seconds_over_cap")
        if s.budget.tokens > policy.MAX_TOKENS:
            errs.append(p + "budget_tokens_over_cap")
        if known_playbooks is not None and s.playbook not in known_playbooks:
            errs.append(p + "playbook_unknown")
        if known_schemas is not None and s.output_schema not in known_schemas:
            errs.append(p + "output_schema_unknown")
    return errs


def role_catalogue() -> list[dict[str, Any]]:
    """Trusted description of what the parent may choose from (goes into the planner prompt)."""
    out = []
    for r in sorted(roles().values(), key=lambda r: r.id):
        out.append({"role": r.id, "about": r.description, "tools": sorted(r.allowed_tools),
                    "workspaces": sorted(r.workspaces), "output_schema": r.output_schema, "playbook": r.playbook})
    return out
