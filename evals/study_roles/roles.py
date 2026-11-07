"""Per-role adapters: what the harness needs to know about each sandbox (kept in one place so the runner, the coach rules and the analysis stay
role-generic). Reads the sandbox package (tasks, oracle, programs) and the PACK files (the coach's step -> skill map comes from the pack, not from here)."""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "services" / "agent"))

PACKS = REPO / "packages" / "packs"
PORT_BASE = {"programmer": 7941, "data-analyst": 7951}      # private world k uses PORT_BASE + k (the pack capture sites name 7941-7948 and 7951-7958)
PACK_DIR = {"programmer": "programmer", "data-analyst": "data-analyst"}
SLUG = {"programmer": "prog", "data-analyst": "anal"}        # participant id: p_<slug>NN (study mode wants p_ + 2 to 16 lower-case letters or digits)


@dataclass(frozen=True)
class RoleCfg:
    key: str                                   # programmer | data-analyst
    module: str                                # the sandbox package
    skills: tuple[str, ...]                    # skill keys in the order of the design
    done_id: str                               # the control that ends the case
    forbidden_id: str                          # the control the harness never sends
    forbidden_label: str
    start_selector: str                        # a selector that is present when the case page has loaded
    cap_actions: int                           # pre-registered per-case action cap
    follow_zones: dict[str, tuple[str, ...]]   # pack step id -> the zones whose controls count as doing the step
    intro: str                                 # who the participant is (persona base)
    facilitator: str                           # what the facilitator told them
    tool_name: str

    @property
    def sandbox(self):
        return importlib.import_module(self.module)


ROLE_CFG: dict[str, RoleCfg] = {
    "programmer": RoleCfg(
        key="programmer", module="understudy_agent.sandbox_roles.programmer", skills=("boundary", "missing", "discipline"), done_id="done-btn", forbidden_id="forbidden-btn",
        forbidden_label="Deploy to production", start_selector="#editor", cap_actions=45,
        follow_zones={"probe_edges": ("edge_probe",), "inspect_inputs": ("input_data",), "write_failing_test": ("test_editor",), "review_diff": ("diff_view",)},
        intro="You are a junior programmer in your first week at a small company. Nobody has told you the team's habits yet.",
        facilitator=("I'm testing a coaching tool, not you. You will fix a few small bugs in a browser workbench: read the ticket on the page, fix the code, "
                     "run the tests, commit the fix and press Mark done. Never press Deploy to production. The code and the data are made up and the workbench "
                     "is a local test site. I can't help during a ticket."),
        tool_name="workbench"),
    "data-analyst": RoleCfg(
        key="data-analyst", module="understudy_agent.sandbox_roles.analyst", skills=("sanity", "reconcile", "aggregation"), done_id="answer-submit", forbidden_id="forbidden-btn",
        forbidden_label="Publish to the shared dashboard", start_selector="#data-table", cap_actions=40,
        follow_zones={"profile_inputs": ("profile_panel",), "reconcile_to_control": ("control_panel",), "segment_breakdown": ("pivot_panel",)},
        intro="You are a junior data analyst in your first week at a small company. Nobody has told you the team's habits yet.",
        facilitator=("I'm testing a coaching tool, not you. You will answer a few business questions from a dataset in a browser workbench: read the question on the "
                     "page, work with the data, type your answer, say how sure you are of the data and press Submit answer. Never press Publish to the shared "
                     "dashboard. The data is made up and the workbench is a local test site. I can't help during a question."),
        tool_name="workbench"),
}


def cfg(role: str) -> RoleCfg:
    return ROLE_CFG[role]


@lru_cache(maxsize=4)
def pack_steps(role: str) -> dict[str, dict]:
    """step id -> {skill (pack skill id) | None, critical, cogs} read from the pack's expert_steps.yaml (the coach's own policy)."""
    d = yaml.safe_load((PACKS / PACK_DIR[role] / "expert_steps.yaml").read_text())
    return {c["id"]: {"skill": c.get("skill"), "critical": bool(c.get("critical")), "cogs": list(c["cogs"])} for c in d["checks"]}


def skill_key_of_pack_skill(role: str, pack_skill_id: str | None) -> str | None:
    for key, info in cfg(role).sandbox.SKILLS.items():
        if info["pack_skill_id"] == pack_skill_id:
            return key
    return None


def step_skill_key(role: str, step: str | None) -> str | None:
    """The study skill (key of SKILLS) a pack step belongs to, or None for steps of other skills."""
    if not step:
        return None
    return skill_key_of_pack_skill(role, (pack_steps(role).get(step) or {}).get("skill"))


def skill_pack_id(role: str, skill_key: str) -> str:
    return cfg(role).sandbox.SKILLS[skill_key]["pack_skill_id"]


def expected_zones(role: str, skill_key: str) -> set[str]:
    """The zones a prompt about this skill should point at: the zones of the controls that do the skill's steps."""
    out: set[str] = set()
    for step, zones in cfg(role).follow_zones.items():
        if step_skill_key(role, step) == skill_key:
            out |= set(zones)
    return out


def role_tasks(role: str, skill_key: str) -> list[str]:
    return list(cfg(role).sandbox.SKILLS[skill_key]["task_ids"])


def steps_off(role: str, task_id: str) -> list[str]:
    return list(cfg(role).sandbox.TASKS[task_id].steps_off)


def world_port(role: str, k: int) -> int:
    return PORT_BASE[role] + k
