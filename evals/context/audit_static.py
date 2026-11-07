"""REQ-8 audit, static part: token sizes of every fixed prompt in the product, from the source constants. Offline, no model, no page.

    .venv/bin/python evals/context/audit_static.py        -> evals/context/results/audit_static.json

Prints and stores NUMBERS ONLY (estimated tokens by the library's estimator: chars/3.6). The prompts are our own fixed wording;
nothing from a worker, a page or a file is read.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "agent"))
sys.path.insert(0, str(ROOT / "services" / "engine"))
_TMP = tempfile.mkdtemp(prefix="ctx_static_")
os.environ.update({"UNDERSTUDY_MOCK": "1", "UNDERSTUDY_DATA_DIR": _TMP + "/data", "UNDERSTUDY_HOME": _TMP + "/home", "ENGINE_URL": "http://127.0.0.1:9"})
Path(_TMP, "data").mkdir()

from understudy_agent.context.tokens import estimate_tokens  # noqa: E402
from understudy_agent.models import openai_provider as oa  # noqa: E402
from understudy_agent.models import gemini_provider as gm  # noqa: E402
from understudy_agent.models import prompts as P  # noqa: E402
from understudy_agent.security import reader as R  # noqa: E402
from understudy_agent.security import drift as D  # noqa: E402
from understudy_agent.tiers import browser_agent as B  # noqa: E402
from understudy_agent import navigator as N  # noqa: E402
from understudy_agent.tiers.facts import FactStore  # noqa: E402
from understudy_agent.sandbox_sites.households import generate_households  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "audit_static.json"
rows: dict[str, int] = {}


def add(name: str, text: str) -> None:
    rows[name] = estimate_tokens(text)


add("openai.cu_instructions", oa._CU_INSTRUCTIONS)
add("openai.reader_instructions", oa._READER_INSTRUCTIONS)
add("openai.check_instructions", oa._CHECK_INSTRUCTIONS)
add("openai.vision_instructions", oa._VISION_INSTRUCTIONS)
add("gemini.cu_system", gm._CU_SYSTEM)
add("models.prompts.system_screen", P.SYSTEM_SCREEN)
add("models.prompts.glance_prompt", P.glance_prompt())
add("models.prompts.point_prompt(desc)", P.point_prompt("the Calculate button"))
add("models.prompts.verify_prompt", P.verify_prompt("page_shows_result"))
add("pipeline.planner_system", R.PLANNER_SYSTEM)
add("tier2.tool_help", B.TOOL_HELP)
add("tier2.schema_json", json.dumps(B.TIER2_SCHEMA))
add("tier2.param_meaning(18)", json.dumps(N.PARAM_HELP, sort_keys=True))
add("drift.prompt_template", D._PROMPT)
h = generate_households(20, 7001)[1]
fs = FactStore.for_calculator("a", h.params())
add("tier3.facts_goal_block", fs.goal_block())
job = N.CalculatorJob("a", h.params())
add("tier3.goal_words", job.goal)
add("tier3.goal_plus_facts", job.goal + "\n\n" + fs.goal_block())
add("reader.result_schema_json", json.dumps(N.RESULT_SCHEMA))
try:
    from understudy_agent.runtime import privacy as rp
    from understudy_agent.runtime.exemplars.base import MENUS
    add("runtime.parent_instructions", rp.parent_instructions())
    for role in sorted(MENUS):
        add(f"runtime.child_instructions[{role}]", rp.child_instructions(role))
    add("runtime.child_system(raw mode)", __import__("understudy_agent.runtime.child", fromlist=["CHILD_SYSTEM"]).CHILD_SYSTEM)
except Exception as exc:  # noqa: BLE001
    rows["runtime.error"] = -1
    print("runtime import failed:", type(exc).__name__)
try:
    from understudy_engine.evidence import explain as E
    add("evidence.explain_instructions", E.INSTRUCTIONS)
except Exception as exc:  # noqa: BLE001
    print("evidence import failed:", type(exc).__name__)
live = (ROOT / "apps/desktop/src/main/live/prompt.ts").read_text()
m = re.search(r"LIVE_SYSTEM_INSTRUCTION = \[(.*?)\]\.join", live, re.S)
if m:
    add("live.system_instruction", " ".join(re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(rows, indent=1, sort_keys=True))
for k, v in sorted(rows.items()):
    print(f"{v:6d}  {k}")
