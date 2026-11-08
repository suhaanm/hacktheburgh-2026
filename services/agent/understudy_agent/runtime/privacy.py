"""The runtime's model-bound payloads, registered with the egress guard (PRV-1; the lead's privacy rule for children).

Every request the runtime makes to a model, other than the existing quarantined-reader path used in foreground mode on
files the worker named, is a registered `SafePayload` sent through `egress.send`:

* `agents.parent_plan`            the run kind and mode (fixed ids and a count); the model replies with a plan of ids
* `agents.child_step_<role>`      the role, the kind and the code-maintained task state (phases done, pending phase, the last steps
                                  verbatim, a rolled-up summary of older ones, typed readings with age and source); the model replies
                                  with ids (tool, file, template) that code resolves from the role's menu

No file text, path, commit message, name, address or number from the worker's data can be in those payloads, because a
`SafePayload` cannot hold free text. The static instructions of each purpose carry the playbook (plain words, no file
names), and are scanned by the guard's backstop when registered. The engine package is imported lazily: when it is not
installed the runtime cannot plan and says so (it fails closed; it never falls back to an unguarded call).
"""
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field

try:  # the privacy spine lives in the engine package
    from understudy_engine.privacy import egress, ledger
    from understudy_engine.privacy.egress import EgressError
    from understudy_engine.privacy.bucket import Count, Numbers, register_feature
    from understudy_engine.privacy.payload import SafePayload, Vocab, register_payload, register_vocabulary
except ImportError as _exc:  # pragma: no cover - the agent environment includes the engine
    raise ImportError("the agent runtime needs understudy_engine.privacy (the egress guard)") from _exc

from . import context, policy
from .spec import AGENT_PLAN_SCHEMA, TOOL_NAMES, plan_schema, roles

for _name in policy.SIGNAL_NAMES:        # typed signals a script may report; sent as plain numbers (no bucketing: they are step counters)
    register_feature(_name, "raw")

ToolId = Literal["read_file", "list_dir", "git_log", "run_python", "write_workspace", "emit_result", "mcp_call", "none"]   # mcp_call: CONNECTIONS
CheckId = Literal["verified", "uncertain", "failed"]
LastId = Literal["start", "ok", "failed", "rejected", "blocked"]


class ParentPlanPayload(SafePayload):
    """What the parent tells the model: which kind of run, in which mode, how many children at most."""

    description = "Plan a background agent run: the run kind, the mode and the child cap (fixed ids and a count)."
    kind: Annotated[str, Vocab("agents.kind")]
    mode: Literal["foreground", "nightly"]
    max_children: Annotated[int, Field(ge=1, le=policy.MAX_CHILDREN)]


class ResultWordingPayload(SafePayload):
    """An agent run's outcome as codes and counts, for one sentence of wording in the morning report."""

    description = "Reword an agent run's outcome from the run kind, the mode and two counts."
    kind: Annotated[str, Vocab("agents.kind")]
    mode: Literal["foreground", "nightly"]
    n_children: Count
    n_verified: Count


WORDING_RESPONSE = {"title": "agent_result_wording", "type": "object", "required": ["text"], "additionalProperties": False,
                    "properties": {"text": {"type": "string", "maxLength": 280}}}
WORDING_INSTRUCTIONS = ("Write one plain sentence of at most 40 words that says how a background agent run went, from the run "
                        "kind, the mode and the two counts. Use only what is given. Do not mention any person, file, "
                        "project or customer.")


MenuId = Annotated[str, Vocab("agents.menu_id")]


class HistItem(SafePayload):
    tool: ToolId
    file: MenuId
    template: MenuId
    ok: bool
    check: CheckId


class StepSummary(SafePayload):
    """Older steps rolled up by code, one line per tool: how many succeeded and how many failed."""
    tool: ToolId
    n_ok: Annotated[int, Field(ge=0, le=999)]
    n_failed: Annotated[int, Field(ge=0, le=999)]


class TaskState(SafePayload):
    """The code-maintained state of a child (see runtime/context.py): what is done and verified, what is pending, the last few steps
    verbatim, a rolled-up summary of the older ones, and the typed readings of the last script run with their age and provenance."""

    description = "A child agent's task state: phases done, pending phase, recent and older steps, typed readings with age and source."
    completed: Annotated[list[MenuId], Field(max_length=context.COMPLETED_MAX)]
    written: Annotated[list[MenuId], Field(max_length=context.WRITTEN_MAX)]
    pending: MenuId
    recent: Annotated[list[HistItem], Field(max_length=context.K_RECENT)]
    summary: Annotated[list[StepSummary], Field(max_length=context.SUMMARY_MAX)]
    elided: Annotated[int, Field(ge=0, le=999)]
    signals: Numbers = Field(default_factory=dict)
    signals_age: Annotated[int, Field(ge=0, le=999)]
    signals_from: Literal["last_run", "none"]
    steps_left: Annotated[int, Field(ge=0, le=policy.MAX_STEPS)]
    verified: Annotated[int, Field(ge=0, le=999)]
    failures: Annotated[int, Field(ge=0, le=999)]
    recoveries: Annotated[int, Field(ge=0, le=99)]
    last: LastId


class ChildStepPayload(SafePayload):
    """What a child tells the model: its role and kind (static, first) and its code-maintained task state (volatile, last)."""

    description = "Choose the next step of a child agent: role id, kind and the code-maintained task state (no file content)."
    kind: Annotated[str, Vocab("agents.kind")]
    role: Annotated[str, Vocab("agents.role")]
    task: TaskState


_registered_sig: tuple | None = None


def parent_instructions() -> str:
    from .exemplars.base import KINDS, kind_id

    lines = [
        "You plan a background agent run. You receive the kind of run, the mode and the child cap, as fixed ids and a count.",
        "Reply with JSON listing the children to start, using ids from the lists below and nothing else.",
        "Rules: at most the child cap; each child has its own id c1 to c4, one role, only tools its role allows, a step "
        "budget, a time budget in seconds and a size budget, a workspace kind, and the output shape and playbook of its role. "
        "Children cannot start other children. Typical budgets: 10 steps, 120 seconds and 20000 size units per child.",
        "Roles:",
    ]
    for r in sorted(roles().values(), key=lambda r: r.id):
        lines.append(f"- {r.id}: {r.description} Tools: {', '.join(sorted(r.allowed_tools))}. Workspaces: "
                     f"{', '.join(sorted(r.workspaces))}. Output shape: {r.output_schema}. Playbook: {r.playbook}.")
    lines.append("Kinds and the roles each one uses:")
    for k, ex in sorted(KINDS.items()):
        lines.append(f"- {kind_id(k)}: {', '.join(ex.roles)}.")
    return "\n".join(lines)


def child_instructions(role: str) -> str:
    from .exemplars.base import MENUS, load_playbook

    rd, menu = roles()[role], MENUS[role]
    return (
        "You are one child of a background agent run. Each turn you choose ONE step from fixed menus and code runs it. "
        "You only receive codes and counts: your role, how many steps are left and a short history of earlier steps with "
        "their checks. Reply with JSON holding a tool id, a file id and, for write_workspace, a template id. Use ids from "
        "the menus below and nothing else.\n"
        f"Tool ids: {', '.join(sorted(rd.allowed_tools))}.\n"
        f"File ids: {', '.join(menu.files)}.\n"
        f"Template ids: {', '.join(menu.templates) or 'none'}.\n"
        f"Playbook:\n{load_playbook(rd.playbook)}"
    )


def ensure_registered() -> None:
    """Register vocabularies and purposes for every known kind and role. Idempotent."""
    global _registered_sig
    from . import exemplars  # noqa: F401
    from .exemplars.base import KINDS, MENUS, known_playbooks, kind_id
    from .results import output_schemas
    from .tools import menu_step_schema

    sig = (tuple(sorted(KINDS)), tuple(sorted((r, tuple(sorted(m.files)), tuple(sorted(m.templates))) for r, m in MENUS.items())),
           tuple(sorted(known_playbooks())), tuple(sorted(output_schemas())))
    if sig == _registered_sig:
        return

    register_vocabulary("agents.kind", [kind_id(k) for k in KINDS], extend=True)
    register_vocabulary("agents.role", list(MENUS), extend=True)
    register_vocabulary("agents.menu_id", sorted({"none", *(f for m in MENUS.values() for f in m.files),
                                                  *(t for m in MENUS.values() for t in m.templates)}), extend=True)
    register_payload("agents.parent_plan", ParentPlanPayload, instructions=parent_instructions(), replace=True,
                     response_schema=plan_schema(sorted(MENUS), sorted(output_schemas()), sorted(known_playbooks())))
    register_payload("agents.result_wording", ResultWordingPayload, instructions=WORDING_INSTRUCTIONS,
                     response_schema=WORDING_RESPONSE, replace=True)
    rdefs = roles()
    for role, menu in MENUS.items():
        register_payload(f"agents.child_step_{role}", ChildStepPayload, instructions=child_instructions(role), replace=True,
                         response_schema=menu_step_schema(role, sorted(rdefs[role].allowed_tools), list(menu.files),
                                                          list(menu.templates)))
    _registered_sig = sig


def parent_plan(kind: str, mode: str, port: Any) -> Any:
    from .exemplars.base import kind_id

    ensure_registered()
    return egress.send("agents.parent_plan", {"kind": kind_id(kind), "mode": mode, "max_children": policy.MAX_CHILDREN},
                       port=port).output


def child_step(role: str, kind: str, task: dict[str, Any], port: Any) -> Any:
    from .exemplars.base import kind_id

    ensure_registered()
    return egress.send(f"agents.child_step_{role}", {"role": role, "kind": kind_id(kind), "task": task}, port=port).output


def word_result(kind: str, mode: str, n_children: int, n_verified: int, port: Any, fallback: str) -> str:
    """One sentence for the morning report, worded by the model from codes and counts only (through the egress guard).
    Any guard or model failure returns `fallback`, the deterministic sentence."""
    from .exemplars.base import kind_id

    ensure_registered()
    try:
        out = egress.send("agents.result_wording", {"kind": kind_id(kind), "mode": mode, "n_children": n_children,
                                                    "n_verified": n_verified}, port=port).output
        text = str(out.get("text", "")).strip()
        return text if text else fallback
    except Exception:  # noqa: BLE001 - the report never depends on a model
        return fallback


def record_raw_call(method: str, model: str, bytes_sent: int, note: str) -> None:
    """Foreground mode on files the worker named: the raw-content path (the quarantined reader and the planner prompt built
    from it) is not a SafePayload, so it gets a ledger line that says so: metadata only, the content is not stored."""
    ledger.record_direct(method=method, model=model, bytes_sent=bytes_sent, purpose="worker_requested", note=note)


__all__ = ["EgressError", "word_result", "ResultWordingPayload", "ChildStepPayload", "ParentPlanPayload", "ensure_registered", "parent_plan", "child_step",
           "record_raw_call", "parent_instructions", "child_instructions"]
