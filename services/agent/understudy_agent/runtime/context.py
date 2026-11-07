"""Context engineering for children (REQ-8): minimal sufficient context, bounded over a long task, code-maintained state.

What the model sees at each step of a child (menu mode) is the role and kind, then ONE typed `task` object that CODE maintains:

    completed    the phases finished and verified: a control id that was written and then run successfully, in order
    written      the engine scripts written to the workspace
    pending      a phase written but not yet run (the step to repeat after a crash, a yield or a restart)
    recent       the last K steps, verbatim and typed (tool, file, template, ok, check)
    summary      the OLDER steps, rolled up by a code template: one line per tool with counts of ok and failed
    elided       how many older steps the summary does not list (so the model knows what was dropped)
    signals      the typed numbers the last script run reported, with their AGE (steps since) and their provenance
    counters     steps left, verified, failures, recoveries, last outcome (artifacts stay in the code state, not in the payload)

It is the source of truth after a yield and resume: nothing about the task lives in the model. A resumed child rebuilds the same
payload from the same state. The model never sees file text, a path or a name (those stay in code), and nothing in this module
reads untrusted content.

Order: the role's static instructions (menu, playbook, result shape) are the system message and come first, so a provider can
cache them; inside the payload the static fields (`kind`, `role`) sort before the volatile `task`, and inside the task the
stable lists come before the fast-changing ones.

Budget per section, in estimated tokens (characters / 4), with a stated truncation order. When the task object is over its
total budget, code drops the OLDEST summary lines first, then shrinks `recent` from K to half of K, and
never touches `completed`, `pending`, `signals` or the counters. Counts per section are logged (numbers only, no content).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import policy

K_RECENT = 6
K_RECENT_MIN = 3
SUMMARY_MAX = 6
COMPLETED_MAX = 24
WRITTEN_MAX = 8
SCRIPT_FILE = "script"                         # menus name the runnable file "script"; writes to other files are phase controls
# estimated tokens per section (characters / 4); the sum is the budget of the whole task object
SECTION_BUDGET = {"completed": 90, "written": 30, "recent": 170, "summary": 100, "signals": 90, "counters": 40}
TOTAL_BUDGET = sum(SECTION_BUDGET.values())
TRUNCATION_ORDER = ("summary:oldest", "recent:half")
NEVER_TRUNCATED = ("completed", "written", "pending", "signals", "counters")


def est(obj: Any) -> int:
    return policy.estimate_tokens(json.dumps(obj, separators=(",", ":"), default=str))


@dataclass
class TaskState:
    """The code-maintained state of one child. `record` is the only writer."""

    steps: list[dict[str, Any]] = field(default_factory=list)       # every step: tool, file, template, ok, check
    written: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    pending: str = "none"
    verified: int = 0
    failures: int = 0
    recoveries: int = 0
    artifacts: int = 0
    last: str = "start"
    signals: dict[str, Any] = field(default_factory=dict)
    signals_at: int | None = None                                   # the step number the signals were read at

    def record(self, step: dict[str, Any], *, signals: dict[str, Any] | None = None, artifacts: int | None = None) -> None:
        """Fold one finished step into the state (ids and booleans only)."""
        self.steps.append({k: step[k] for k in ("tool", "file", "template", "ok", "check")})
        good = bool(step["ok"]) and step["check"] == "verified"
        self.verified += int(good)
        self.failures += int(not step["ok"])
        self.last = "ok" if good else "failed"
        tool, file, tpl = step["tool"], step["file"], step["template"]
        if tool == "write_workspace" and step["ok"] and tpl != "none":
            if file == SCRIPT_FILE:
                if tpl not in self.written:
                    self.written.append(tpl)
            else:
                self.pending = tpl                                  # a phase control written and not yet run
        elif tool == "run_python":
            if step["ok"] and self.pending != "none":
                if self.pending not in self.completed:
                    self.completed.append(self.pending)
                self.pending = "none"
            if signals is not None:
                self.signals, self.signals_at = dict(signals), len(self.steps)
        if artifacts is not None:
            self.artifacts = artifacts

    def mark_rejected(self, tool: str = "none", kind: str = "rejected") -> None:
        self.steps.append({"tool": tool, "file": "none", "template": "none", "ok": False, "check": "failed"})
        self.failures += 1
        self.last = kind

    def payload(self, steps_left: int) -> tuple[dict[str, Any], dict[str, Any]]:
        """(the typed `task` object for the egress guard, metadata-only counts for the audit log)."""
        n = len(self.steps)
        k = K_RECENT
        older = self.steps[: max(0, n - k)]
        agg: dict[str, list[int]] = {}
        for s in older:                                             # the rolling summary: one line per TOOL (which phases are done is
            a = agg.setdefault(s["tool"], [0, 0])                   # already in `completed`, so the per-phase detail is not repeated)
            a[0 if s["ok"] else 1] += 1
        every = [{"tool": t, "n_ok": c[0], "n_failed": c[1]} for t, c in agg.items()]
        dropped = every[:-SUMMARY_MAX] if len(every) > SUMMARY_MAX else []
        elided = sum(x["n_ok"] + x["n_failed"] for x in dropped)    # STEPS the summary does not list
        summary = every[-SUMMARY_MAX:]
        recent = [dict(s) for s in self.steps[-k:]]
        age = (n - self.signals_at) if self.signals_at is not None else 0
        task: dict[str, Any] = {
            "completed": self.completed[-COMPLETED_MAX:], "written": self.written[-WRITTEN_MAX:], "pending": self.pending,
            "recent": recent, "summary": summary, "elided": elided, "signals": dict(self.signals),
            "signals_age": age, "signals_from": "last_run" if self.signals_at is not None else "none",
            "steps_left": steps_left, "verified": self.verified, "failures": self.failures, "recoveries": self.recoveries,
            "last": self.last if n else "start",
        }
        truncated = []
        # stated truncation order when over the total budget
        while est(task) > TOTAL_BUDGET and task["summary"]:
            gone = task["summary"][0]
            task["summary"] = task["summary"][1:]                    # oldest summary line first
            task["elided"] += gone["n_ok"] + gone["n_failed"]
            if "summary:oldest" not in truncated:
                truncated.append("summary:oldest")
        if est(task) > TOTAL_BUDGET and len(task["recent"]) > K_RECENT_MIN:
            task["recent"] = task["recent"][-K_RECENT_MIN:]
            truncated.append("recent:half")
        meta = {"n_steps": n, "n_completed": len(task["completed"]), "n_recent": len(task["recent"]), "n_summary": len(task["summary"]),
                "n_elided": task["elided"], "n_signals": len(task["signals"]), "signals_age": age, "tok_task": est(task),
                "tok_budget": TOTAL_BUDGET, "truncated": len(truncated), "tok_recent": est(task["recent"]),
                "tok_summary": est(task["summary"]), "tok_signals": est(task["signals"])}
        return task, meta

    def to_json(self) -> dict[str, Any]:
        """Everything the state holds, as typed JSON (ids, booleans and counts only): safe to keep next to the run's other files."""
        return {"steps": self.steps, "written": self.written, "completed": self.completed, "pending": self.pending,
                "verified": self.verified, "failures": self.failures, "recoveries": self.recoveries, "artifacts": self.artifacts,
                "last": self.last, "signals": self.signals, "signals_at": self.signals_at}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "TaskState":
        t = cls()
        t.steps = [dict(x) for x in d.get("steps", [])]
        t.written, t.completed = list(d.get("written", [])), list(d.get("completed", []))
        t.pending = str(d.get("pending", "none"))
        t.verified, t.failures = int(d.get("verified", 0)), int(d.get("failures", 0))
        t.recoveries, t.artifacts = int(d.get("recoveries", 0)), int(d.get("artifacts", 0))
        t.last, t.signals, t.signals_at = str(d.get("last", "start")), dict(d.get("signals", {})), d.get("signals_at")
        return t

    def snapshot(self) -> dict[str, Any]:
        """A small, content-free view for the run record and the Agents screen."""
        return {"steps": len(self.steps), "verified": self.verified, "failures": self.failures, "recoveries": self.recoveries,
                "completed": list(self.completed), "pending": self.pending, "artifacts": self.artifacts, "last": self.last,
                "signals": dict(self.signals), "signals_age": (len(self.steps) - self.signals_at) if self.signals_at is not None else None}
