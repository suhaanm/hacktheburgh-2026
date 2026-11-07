"""REQ-8 audit probes: three facts about the OpenAI computer-use provider that decide how context behaves over a long run.
Offline: a fake client records the request kwargs the real provider code builds. No network, no model call, booleans and counts only.

    .venv/bin/python evals/context/audit_probes.py    -> evals/context/results/audit_probes.json
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "agent"))
sys.path.insert(0, str(ROOT / "services" / "engine"))
_TMP = tempfile.mkdtemp(prefix="ctx_probe_")
os.environ.update({"UNDERSTUDY_MOCK": "1", "UNDERSTUDY_DATA_DIR": _TMP + "/data", "UNDERSTUDY_HOME": _TMP + "/home", "ENGINE_URL": "http://127.0.0.1:9",
                   "OPENAI_API_KEY": "sk-test-not-real", "OPENAI_MODEL_PLANNER": "p", "OPENAI_MODEL_FAST": "f", "OPENAI_MODEL_COMPUTER_USE": "c"})
Path(_TMP, "data").mkdir()

from understudy_agent.models.config import ModelIds  # noqa: E402
from understudy_agent.models.imaging import make_test_png  # noqa: E402
from understudy_agent.models.openai_provider import OpenAIProvider  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "audit_probes.json"


def msg(text):
    return NS(type="message", content=[NS(type="output_text", text=text)])


def resp(output, text="", rid="r1"):
    return NS(id=rid, output=output, output_text=text, status="completed", usage=NS(input_tokens=10, output_tokens=5))


def call(actions, call_id="call_1"):
    return NS(type="computer_call", call_id=call_id, pending_safety_checks=None, status="completed", actions=actions, action=None)


class Fake:
    def __init__(self, *rs):
        self.q, self.req = list(rs), []
        self.responses = NS(create=self._c)

    def _c(self, **kw):
        self.req.append(kw)
        return self.q.pop(0)


def flat(req) -> str:
    return json.dumps(req.get("input"), default=str)


def main() -> None:
    shot = make_test_png(1280, 800)
    ids = ModelIds(planner="p", fast="f", computer_use="c")

    # probe 1: the chained turn after a refused action. The loop appends a history entry and sets `feedback` (a NOTE for the
    # model) on the goal; does the NOTE reach the provider?
    f = Fake(resp([call([NS(type="type", text="12345")])], rid="r1"), resp([call([NS(type="click", x=5, y=5, button="left", keys=None)], "call_2")], rid="r2"))
    p = OpenAIProvider(client=f, models=ids)
    p.computer_step("Goal G", shot, [], session="s")
    refused = [{"kind": "type", "ok": False, "why": "literal_text"}]
    p.computer_step("Goal G\nNOTE: your last action was refused. Type only a handle.", shot, refused, session="s")
    second = f.req[-1]
    chained_second = {"uses_previous_response_id": "previous_response_id" in second,
                      "input_item_types": [i.get("type") or i.get("role") for i in second["input"]],
                      "feedback_note_in_request": "NOTE" in flat(second) or "refused" in flat(second),
                      "goal_in_request": "Goal G" in flat(second)}

    # probe 2: is the request stored by the provider? (`store` unset means the vendor default applies for the computer-use calls)
    cu_kwargs = f.req[0]
    store = {"computer_use_request_sets_store": "store" in cu_kwargs, "truncation": cu_kwargs.get("truncation"), "has_instructions": "instructions" in cu_kwargs}

    # probe 3: history=[] forces the stateless path (the library's adoption route): goal and ONE image in the input, no chain.
    g = Fake(resp([call([NS(type="screenshot")])], rid="a1"), resp([call([NS(type="click", x=5, y=5, button="left", keys=None)], "c2")], rid="a2"),
             resp([call([NS(type="screenshot")])], rid="b1"), resp([call([NS(type="click", x=6, y=6, button="left", keys=None)], "c3")], rid="b2"))
    q = OpenAIProvider(client=g, models=ids)
    q.computer_step("G1", shot, [], session="s")
    q.computer_step("G2 with task state", shot, [], session="s")
    stateless = {"second_call_uses_previous_response_id": any("previous_response_id" in r and r["input"][0].get("type") != "computer_call_output" for r in g.req[2:3]),
                 "goal_text_in_second_logical_call": "G2 with task state" in flat(g.req[2]),
                 "images_in_second_logical_call_first_request": flat(g.req[2]).count("input_image")}
    out = {"origin": "offline probe of the provider's request building with a fake client", "chained_turn_after_refusal": chained_second,
           "store_and_truncation": store, "stateless_via_empty_history": stateless}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
