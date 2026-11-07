"""REQ-8 audit measurement: what really goes into the prompts on a real fixture run. Offline, hermetic, no model calls.

It drives the real sandbox sites in headless Chromium through the real tier-2 browser agent and the real tier-3 computer-use loop,
with the repository's own test doubles as the model (a heuristic planner and a DOM-grounded computer-use double), and records
METADATA ONLY about every model-facing request: character and estimated-token counts, history length, whether the prefix repeated,
the size of the screenshot. Nothing from a page, a prompt or a value is written to the result file.

    scripts/heavy.sh .venv/bin/python evals/context/audit_measure.py

Result: evals/context/results/audit_measure.json
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics as st
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "agent"))
sys.path.insert(0, str(ROOT / "services" / "engine"))
_TMP = tempfile.mkdtemp(prefix="ctx_audit_")
os.environ.update({"UNDERSTUDY_MOCK": "1", "UNDERSTUDY_DATA_DIR": _TMP + "/data", "UNDERSTUDY_HOME": _TMP + "/home",
                   "ENGINE_URL": "http://127.0.0.1:9", "UNDERSTUDY_TEST_RELAXED_GUARD": "1"})
Path(_TMP, "data").mkdir()

from understudy_agent.audit import AuditLog  # noqa: E402
from understudy_agent.context.tokens import estimate_image_tokens, estimate_tokens  # noqa: E402
from understudy_agent.models.imaging import downscale_png  # noqa: E402
from understudy_agent.models.mock_provider import MockProvider  # noqa: E402
from understudy_agent.models.openai_provider import OpenAIProvider  # noqa: E402
from understudy_agent.models.gemini_provider import _history_text as gemini_history_text  # noqa: E402
from understudy_agent.navigator import CalculatorJob, Navigator  # noqa: E402
from understudy_agent.queue import ApprovalQueue  # noqa: E402
from understudy_agent.sandbox_sites.households import generate_households  # noqa: E402
from understudy_agent.sandbox_sites.runner import SandboxCluster  # noqa: E402
from understudy_agent.security.denylist import Denylist  # noqa: E402
from understudy_agent.tiers.browser import BrowserHost  # noqa: E402
from understudy_agent.tiers.computer_use import screen_fingerprint  # noqa: E402
from understudy_agent.tiers.heuristic import DomOracleComputerModel, HeuristicModelPort  # noqa: E402
from understudy_agent.tiers.safety import Guard  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "audit_measure.json"


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


class RecordingCU:
    """Wraps the DOM-grounded computer-use double and records metadata about each request the real loop would send."""

    def __init__(self, inner: DomOracleComputerModel) -> None:
        self.inner, self.rows = inner, []
        self.name = "recording-cu"

    def attach(self, session, actuator):
        return self.inner.attach(session, actuator)

    def computer_step(self, goal, screenshot, history, **kw):
        scaled = downscale_png(screenshot)
        oa_text = OpenAIProvider._history_text(history, scaled)
        gm_text = gemini_history_text(history, scaled.orig_w, scaled.orig_h)
        # NOTE (7 Nov 18:40): the shipped tier-3 loop already sends the library's prompt as `goal` and passes history=[], so there is nothing
        # left to re-compute here; this records the size of what the real loop sent.
        self.rows.append({
            "step": len(self.rows) + 1, "prompt_text_tokens": estimate_tokens(goal), "history_len": len(history),
            "openai_hist_tokens": estimate_tokens(oa_text), "gemini_hist_tokens": estimate_tokens(gm_text),
            "openai_hist_names_a_handle": ("household." in oa_text) or ("note." in oa_text),
            "gemini_hist_names_a_handle": ("household." in gm_text) or ("note." in gm_text),
            "png_bytes": len(screenshot), "frame_tokens": estimate_image_tokens(scaled.w, scaled.h),
            "frame_px": [scaled.w, scaled.h],
            "screen_fp_sha": hash(screen_fingerprint(screenshot)) & 0xFFFF,
        })
        return self.inner.computer_step(goal, screenshot, history, **kw)

    def plan(self, m, s=None):
        return self.inner.plan(m, s)

    def read(self, u, s):
        return self.inner.read(u, s)

    def check(self, p, s):
        return self.inner.check(p, s)

    def vision(self, i, p, s=None):
        return self.inner.vision(i, p, s)


async def run_tier3(host, cluster, sinks, site: str, hid: int) -> list[dict]:
    q, a = sinks
    model = RecordingCU(DomOracleComputerModel())
    guard = Guard(model, run_id=f"r_ctx_t3_{site}", routine_id=None, audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    nav = Navigator(f"nav-{site}", context=ctx, model=model, guard=guard, base_url=cluster.urls[site], emit=lambda e: None,
                    use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=False)
    res = await nav.run(CalculatorJob(site, generate_households(20, 7001)[hid].params()))
    return [dict(r, site=site, outcome=res.state) for r in model.rows]


async def run_tier2(host, cluster, sinks, site: str, hid: int) -> dict:
    q, a = sinks
    port = HeuristicModelPort(MockProvider("benefits_clean"))
    guard = Guard(port, run_id=f"r_ctx_t2_{site}", routine_id=None, audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    nav = Navigator(f"nav-{site}", context=ctx, model=port, guard=guard, base_url=cluster.urls[site], emit=lambda e: None,
                    use_tier1=False, start_tier=2, page_state=True, defer_cliff=True)
    res = await nav.run(CalculatorJob(site, generate_households(20, 7001)[hid].params()))
    plans = [c for c in port.calls if c["method"] == "plan" and c["title"] == "tier2_step"]
    reads = [c for c in port.calls if c["method"] == "read"]
    texts = ["\n".join(str(m["content"]) for m in c["messages"]) for c in plans]
    sys_user = [(c["messages"][0]["content"], c["messages"][1]["content"]) for c in plans]
    rows = []
    for i, (t, (s, u)) in enumerate(zip(texts, sys_user)):
        cp = common_prefix_len(texts[i - 1], t) if i else 0
        rows.append({"step": i + 1, "total_tokens": estimate_tokens(t), "system_tokens": estimate_tokens(s),
                     "user_tokens": estimate_tokens(u), "common_prefix_with_previous_tokens": estimate_tokens(t[:cp]),
                     "has_tool_help_before_volatile": t.find("TOOLS (return exactly one") < t.find("STATE:")})
    # where is the stable block (tool help) relative to the page observation?
    first = texts[0] if texts else ""
    layout = {"pos_observation": first.find("Observation 1"), "pos_tool_help": first.find("TOOLS (return"),
              "pos_state": first.find("STATE:"), "pos_labels": first.find("ELEMENT LABELS"), "chars": len(first)}
    return {"site": site, "state": res.state, "steps": rows, "n_plan_calls": len(plans), "n_reader_calls": len(reads),
            "reader_chars": [r["chars"] for r in reads], "reader_distinct_texts_proxy": len({(r["title"], r["chars"]) for r in reads}),
            "reader_titles": sorted({str(r["title"]) for r in reads}), "layout": layout}


async def main() -> None:
    audit = AuditLog(Path(_TMP) / "audit.jsonl")
    queue = ApprovalQueue(Path(_TMP) / "queue", audit=audit)
    sinks = (queue, audit)
    out: dict = {"origin": "synthetic sandbox fixtures, offline test-double models; metadata only", "tier3": [], "tier2": []}
    with SandboxCluster(ephemeral=True) as cluster:
        async with BrowserHost() as host:
            for site in ("a", "b", "c"):
                out["tier3"] += await run_tier3(host, cluster, sinks, site, 1)
                out["tier2"].append(await run_tier2(host, cluster, sinks, site, 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    t3 = out["tier3"]
    print("tier3 steps recorded", len(t3), "by site", {s: sum(1 for r in t3 if r["site"] == s) for s in "abc"})
    for s in out["tier2"]:
        toks = [r["total_tokens"] for r in s["steps"]]
        print("tier2", s["site"], s["state"], "plan calls", s["n_plan_calls"], "tokens/step mean", round(st.mean(toks)) if toks else None,
              "max", max(toks) if toks else None, "reader calls", s["n_reader_calls"])


if __name__ == "__main__":
    asyncio.run(main())
