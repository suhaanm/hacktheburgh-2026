"""Read role packs for the handoff modules (onboarding, routine templates, expert policy, priors).

Reads ``<packs_dir>/<id>/pack.yaml`` and the files it points at with ``yaml.safe_load``; formats follow
``packages/schema/pack.schema.json``. Until the platform track ships packs (or when one is missing) a
small built-in fallback keeps mock mode and the tests running. It is flagged ``source="builtin"`` and the
fallbacks are deliberately plain: they exist so nothing crashes, not to stand in for a real pack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import packs_dir

QUESTION_IDS = ("tools", "risky", "tone", "pace", "hours")


@dataclass
class PackView:
    id: str
    name: str
    summary: str
    depth: str = "thin"
    source: str = "dir"
    questions: list[dict[str, Any]] = field(default_factory=list)
    extra_cogs: list[str] = field(default_factory=list)
    risk_irreversible: list[str] = field(default_factory=list)
    risk_outward: list[str] = field(default_factory=list)
    tone_defaults: dict[str, str] = field(default_factory=dict)
    expert_checks: list[dict[str, Any]] = field(default_factory=list)
    allowed_reorderings: list[dict[str, Any]] = field(default_factory=list)
    templates: list[dict[str, Any]] = field(default_factory=list)
    template_defaults: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    priors: dict[str, Any] = field(default_factory=dict)
    persona: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def pack_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "extra_cogs": list(self.extra_cogs),
            "risk_classes": {"irreversible": list(self.risk_irreversible), "outward": list(self.risk_outward)},
            "tone_defaults": {k: v for k, v in self.tone_defaults.items() if k in ("length", "voice")},
        }

    def question(self, qid: str) -> dict[str, Any] | None:
        return next((q for q in self.questions if q.get("id") == qid), None)

    def template(self, template_id: str) -> dict[str, Any] | None:
        return next((t for t in self.templates if t.get("id") == template_id), None)

    def judgement_cogs(self) -> set[str]:
        d = self.template_defaults.get("judgement_cogs")
        return set(d) if d else {"SEARCH", "REFORMULATE", "COMPARE", "DECIDE"}

    def presence_prior(self) -> dict[str, Any]:
        p = self.priors.get("presence") if isinstance(self.priors, dict) else None
        if p:
            return p
        return {"hours": {"start": "09:00", "end": "17:30", "days": ["mon", "tue", "wed", "thu", "fri"]},
                "active_in_hours": 0.8, "active_out_of_hours": 0.05}


def _yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def list_pack_ids() -> list[str]:
    root = packs_dir()
    ids = {p.parent.name for p in root.glob("*/pack.yaml")} if root.exists() else set()
    return sorted(ids | set(_BUILTIN))  # built-in fallbacks fill any role the platform pack set does not have yet


def load_pack(role: str) -> PackView:
    """Load a pack by id. Unknown ids raise ``KeyError``."""
    p = packs_dir() / role / "pack.yaml"
    if p.exists():
        view = _from_dir(p.parent)
        if view is not None:
            return view
    if role in _BUILTIN:
        return _builtin(role)
    raise KeyError(role)


def _from_dir(d: Path) -> PackView | None:
    pack = _yaml(d / "pack.yaml")
    if not isinstance(pack, dict) or "id" not in pack:
        return None

    def sub(*path: str) -> Any:
        node: Any = pack
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if not isinstance(node, str):
            return None
        return _yaml(d / node)

    expert = sub("expert_policy", "steps") or {}
    routines = sub("routines") or {}
    curriculum = sub("curriculum") or {}
    priors = sub("priors") or {}
    persona = sub("persona") or {}
    qs = [q for q in ((pack.get("onboarding") or {}).get("questions") or []) if isinstance(q, dict)]
    risk = pack.get("risk_classes") or {}
    return PackView(
        id=str(pack["id"]),
        name=str(pack.get("name", pack["id"])),
        summary=str(pack.get("summary", "")),
        depth=str(pack.get("depth", "thin")),
        source="dir",
        questions=qs,
        extra_cogs=list((pack.get("cogs") or {}).get("extra") or []),
        risk_irreversible=list(risk.get("irreversible") or []),
        risk_outward=list(risk.get("outward") or []),
        tone_defaults=dict(pack.get("tone_defaults") or {}),
        expert_checks=list(expert.get("checks") or []) if isinstance(expert, dict) else [],
        allowed_reorderings=list(expert.get("allowed_reorderings") or []) if isinstance(expert, dict) else [],
        templates=list(routines.get("templates") or []) if isinstance(routines, dict) else [],
        template_defaults=dict(routines.get("defaults") or {}) if isinstance(routines, dict) else {},
        skills=sorted(list(curriculum.get("skills") or []), key=lambda s: s.get("order", 0)) if isinstance(curriculum, dict) else [],
        priors=priors if isinstance(priors, dict) else {},
        persona=persona if isinstance(persona, dict) else {},
        raw=pack,
    )


# ------------------------------------------------------------------------------------------------
# Built-in fallbacks (used only when packages/packs/<id> is missing)
# ------------------------------------------------------------------------------------------------
def _opts(*pairs: tuple[str, str], **extra: Any) -> list[dict[str, Any]]:
    return [{"value": v, "label": lab} for v, lab in pairs]


_BUILTIN: dict[str, dict[str, Any]] = {
    "benefits-processor": {
        "name": "UK benefits processor",
        "summary": "Runs entitlement checks for households and writes the case note.",
        "depth": "deep",
        "extra_cogs": ["ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE"],
        "irreversible": ["submit", "send", "pay", "delete", "post"],
        "outward": ["email", "notify"],
        "tone": {"length": "short", "voice": "plain", "pace": "steady"},
        "tools": [("gov-uk-check", "GOV.UK benefits check"), ("turn2us", "Turn2us calculator"), ("case-notes", "Case notes system")],
        "risky": [("submit", "Submitting a case note or claim"), ("send", "Sending anything to a claimant"), ("pay", "Anything that moves money")],
        "checks": [
            {"id": "enter-household", "label": "Enter the household", "cogs": ["ENTER_HOUSEHOLD"], "required": True, "after": []},
            {"id": "child-benefits", "label": "Check child-related benefits", "cogs": ["OPEN_CALCULATOR", "READ_RESULT"], "required": True, "after": ["enter-household"]},
            {"id": "housing", "label": "Check housing support", "cogs": ["OPEN_CALCULATOR", "READ_RESULT"], "required": True, "after": ["enter-household"]},
            {"id": "cliff", "label": "Check for cliff edges", "cogs": ["CHECK_CLIFF"], "required": True, "critical": True, "after": ["child-benefits", "housing"]},
            {"id": "note", "label": "Write the case note", "cogs": ["COPY_TO_NOTE"], "required": True, "after": ["cliff"]},
        ],
        "skills": [("enter-household", "Entering the household", ["ENTER_HOUSEHOLD"]), ("read-results", "Reading results", ["READ_RESULT"]), ("cliff-check", "Cliff edges", ["CHECK_CLIFF"])],
        "templates": [{
            "id": "calc-entry-3x", "title": "Enter the household into three calculators",
            "cogs": ["ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "COPY_TO_NOTE"], "match_distance": 0.34,
            "automatable": True, "learning_relevant": True, "skill_cogs": ["ENTER_HOUSEHOLD"],
            "touches": ["gov.uk check", "turn2us", "case note"], "never": ["submit"],
            "proposal": {"what": "Open the three calculators, enter the household once, and copy each result to the note."},
        }],
        "hours": {"start": "09:00", "end": "17:30", "days": ["mon", "tue", "wed", "thu", "fri"]},
    },
    "data-analyst": {
        "name": "Data analyst",
        "summary": "Pulls data, cleans it, runs the checks and writes up the finding.",
        "depth": "thin",
        "extra_cogs": ["RUN_QUERY", "INSPECT_TABLE", "PLOT", "SUMMARISE"],
        "irreversible": ["drop", "delete", "overwrite", "publish", "send"],
        "outward": ["share", "export"],
        "tone": {"length": "detailed", "voice": "precise", "pace": "quick"},
        "tools": [("sql", "SQL console"), ("notebook", "Notebook"), ("dashboard", "Dashboard tool")],
        "risky": [("drop", "Dropping or overwriting tables"), ("publish", "Publishing a dashboard or report"), ("send", "Sending results to others")],
        "checks": [
            {"id": "run-query", "label": "Run the query", "cogs": ["RUN_QUERY"], "required": True, "after": []},
            {"id": "inspect", "label": "Inspect the table", "cogs": ["INSPECT_TABLE"], "required": True, "after": ["run-query"]},
            {"id": "plot", "label": "Plot it", "cogs": ["PLOT"], "required": False, "after": ["inspect"]},
            {"id": "summarise", "label": "Write the summary", "cogs": ["SUMMARISE"], "required": True, "after": ["inspect"]},
        ],
        "skills": [("sql-basics", "Writing the query", ["RUN_QUERY"]), ("sanity-checks", "Sanity-checking the table", ["INSPECT_TABLE"]), ("summaries", "Writing the finding", ["SUMMARISE"])],
        "templates": [{
            "id": "weekly-refresh", "title": "Refresh the weekly report",
            "cogs": ["RUN_QUERY", "INSPECT_TABLE", "PLOT", "SUMMARISE"], "match_distance": 0.34,
            "automatable": True, "learning_relevant": False, "touches": ["sql console", "dashboard"], "never": ["publish"],
            "proposal": {"what": "Re-run the saved queries, refresh the plots and draft the summary for review."},
        }],
        "hours": {"start": "09:30", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
    },
    "programmer": {
        "name": "Programmer",
        "summary": "Reads code, makes changes, runs tests and opens reviews.",
        "depth": "thin",
        "extra_cogs": ["READ_CODE", "EDIT_CODE", "RUN_TESTS", "REVIEW_DIFF"],
        "irreversible": ["push", "merge", "deploy", "delete", "force"],
        "outward": ["comment", "request review"],
        "tone": {"length": "short", "voice": "terse", "pace": "quick"},
        "tools": [("editor", "Editor or IDE"), ("terminal", "Terminal"), ("git-host", "Git host")],
        "risky": [("push", "Pushing or merging"), ("deploy", "Deploying"), ("delete", "Deleting branches or data")],
        "checks": [
            {"id": "read", "label": "Read the code", "cogs": ["READ_CODE"], "required": True, "after": []},
            {"id": "edit", "label": "Make the change", "cogs": ["EDIT_CODE"], "required": True, "after": ["read"]},
            {"id": "test", "label": "Run the tests", "cogs": ["RUN_TESTS"], "required": True, "critical": True, "after": ["edit"]},
            {"id": "review", "label": "Review the diff", "cogs": ["REVIEW_DIFF"], "required": True, "after": ["test"]},
        ],
        "skills": [("reading-code", "Reading unfamiliar code", ["READ_CODE"]), ("testing", "Running the right tests", ["RUN_TESTS"]), ("diff-review", "Reviewing your own diff", ["REVIEW_DIFF"])],
        "templates": [{
            "id": "test-and-lint", "title": "Run tests and lint before a push",
            "cogs": ["RUN_TESTS", "REVIEW_DIFF"], "match_distance": 0.34,
            "automatable": True, "learning_relevant": False, "touches": ["terminal"], "never": ["push"],
            "proposal": {"what": "Run the test suite and the linter, and show you the failures."},
        }],
        "hours": {"start": "10:00", "end": "18:30", "days": ["mon", "tue", "wed", "thu", "fri"]},
    },
}


def _builtin(role: str) -> PackView:
    b = _BUILTIN[role]
    questions = [
        {"id": "tools", "prompt": "Which of these do you use?", "kind": "multi",
         "options": _opts(*b["tools"])},
        {"id": "risky", "prompt": "Which actions must never run without you?", "kind": "multi",
         "options": [{"value": v, "label": lab, "risk_class": "irreversible", "patterns": [v]} for v, lab in b["risky"]]},
        {"id": "tone", "prompt": "Short answers or detailed ones?", "kind": "single",
         "options": [{"value": "short", "label": "Short"}, {"value": "medium", "label": "A little detail"}, {"value": "detailed", "label": "Detailed"}]},
        {"id": "pace", "prompt": "How fast should help fade as you improve?", "kind": "single",
         "options": [{"value": "gentle", "label": "Gently"}, {"value": "steady", "label": "Steadily"}, {"value": "quick", "label": "Quickly"}]},
        {"id": "hours", "prompt": "What are your usual working hours?", "kind": "hours", "default_hours": b["hours"]},
    ]
    return PackView(
        id=role, name=b["name"], summary=b["summary"], depth=b["depth"], source="builtin",
        questions=questions, extra_cogs=list(b["extra_cogs"]),
        risk_irreversible=list(b["irreversible"]), risk_outward=list(b["outward"]),
        tone_defaults=dict(b["tone"]), expert_checks=[dict(c) for c in b["checks"]],
        templates=[dict(t) for t in b["templates"]],
        skills=[{"id": i, "label": lab, "order": n + 1, "cogs": cogs, "prerequisites": []} for n, (i, lab, cogs) in enumerate(b["skills"])],
        priors={"presence": {"hours": b["hours"], "active_in_hours": 0.8, "active_out_of_hours": 0.05},
                "mastery": {"start": 0.2, "decay_half_life_days": 30.0},
                "accept": {"alpha": 2.0, "beta": 2.0}},
    )
