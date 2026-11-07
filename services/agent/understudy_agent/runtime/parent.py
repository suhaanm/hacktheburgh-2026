"""The parent agent: plans through the model, then CODE validates every spec before anything starts (BGA-1).

The plan call is a registered `SafePayload` through the egress guard (`agents.parent_plan`, strict schema, title
`agent_plan`): the run kind, the mode and the child cap go out; ids and numbers come back. The reply is parsed, each
child's goal is filled from its role (the model supplies no text), and `validate_plan` checks roles, tools, budgets,
workspace kinds, output shapes and playbooks against policy. A plan that breaks policy starts nothing.
"""
from __future__ import annotations

import re
from typing import Any

from ..audit import AuditLog
from ..models.port import ModelPort
from . import policy
from .spec import AgentSpec, PolicyViolation, parse_plan, validate_plan


class PlanRejected(PolicyViolation):
    """The parent's plan was refused by code. `errors` are stable codes; no child was started."""


class ParentAgent:
    def __init__(self, kind: str, mode: str, port: ModelPort, audit: AuditLog, *, run_id: str, routine_id: str) -> None:
        self.kind, self.mode, self.port, self.audit = kind, mode, port, audit
        self.run_id, self.routine_id = run_id, routine_id
        self.raw_plan: Any = None

    def plan(self) -> list[AgentSpec]:
        from . import exemplars  # noqa: F401
        from . import privacy as rtprivacy
        from .exemplars.base import GOALS, KINDS, known_playbooks
        from .results import output_schemas

        try:
            raw = rtprivacy.parent_plan(self.kind, self.mode, self.port)
        except rtprivacy.EgressError as e:
            self._audit("plan_rejected", [f"egress:{e.code}"])
            raise PlanRejected([f"egress:{e.code}"]) from None
        self.raw_plan = raw
        specs, errors = parse_plan(raw, GOALS)
        errors += validate_plan(specs, known_playbooks=known_playbooks(), known_schemas=set(output_schemas()))
        allowed_roles = set(KINDS[self.kind].roles)
        errors += [f"{s.id}:role_not_for_kind" for s in specs if s.role not in allowed_roles]
        if errors:
            self._audit("plan_rejected", errors)
            raise PlanRejected(errors)
        self._audit("plan_accepted", [f"children:{len(specs)}"])
        return specs

    def _audit(self, outcome: str, codes: list[str]) -> None:
        code = ",".join(codes)[:120]
        self.audit.append("agent", "agent_plan", routine=self.routine_id, run_id=self.run_id, outcome=outcome,
                          note_code=code if re.fullmatch(r"[a-z0-9_.:@,\-\[\]>]{1,200}", code) else None,
                          meta={"children": len(codes) if outcome == "plan_rejected" else None, "mode": self.mode})
