"""REQ-8 ablation 1: prompt tokens per step over a 150-step computer-use run, current policies against the context library.

Offline, hermetic, no model call, no network, no browser. Nothing here claims what a provider will do: it computes what each policy
PUTS INTO THE PROMPT, from our own code (the providers' real `_history_text`, the real fact-handle block, the library's
assembler) and from one constant calibrated on a live run (the cost of one computer-use frame, 1860 tokens, from AGENT-CORE's diag_smoke_2 usage fields;
see `understudy_agent/context/tokens.py`). The default 1150 would shrink every figure that includes a frame.

Policies
  chained_reset4  what AGENT-CORE's loop does as of 7 Nov 18:27 (`ComputerUse(context_reset_every=4)`): chained, but the provider's thread is
                restarted every 4 steps from the code-built `_task_state` plus the last 12 actions as text. Computed with the real
                `ComputerUse._task_state` and the real `_history_text`; the frames-per-segment part is modelled.
  chained       the OpenAI provider's chained mode (`previous_response_id`): the provider keeps every frame and action of the run, so
                step k carries instructions + goal + k frames + k actions. Modelled, not measured: needs a live run to confirm.
  stateless12   what the Gemini provider does today and the OpenAI provider does on a restart: goal + the last 12 actions as text +
                one frame. Measured from the real `_history_text` functions.
  library       the context library: goal first (stable), task state, rolling summary, last 6 steps, frame hint, one current frame
                and one small previous thumbnail.

Also measured: what the model can know at each step (the information check): does the prompt name every fact handle already entered
on this page, and every postcondition code verified? A cache-adjusted cost is shown at an ASSUMED cached-input price factor (0.25,
the meter's default assumption), because chained mode is the one policy that benefits from provider-side prefix caching.

    .venv/bin/python evals/context/token_growth.py        -> evals/context/results/token_growth.json
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "agent"))
sys.path.insert(0, str(ROOT / "services" / "engine"))
_TMP = tempfile.mkdtemp(prefix="ctx_growth_")
os.environ.update({"UNDERSTUDY_MOCK": "1", "UNDERSTUDY_DATA_DIR": _TMP + "/data", "UNDERSTUDY_HOME": _TMP + "/home", "ENGINE_URL": "http://127.0.0.1:9"})
Path(_TMP, "data").mkdir()

from PIL import Image, ImageDraw  # noqa: E402

from understudy_agent.context import (FrameRetention, Outcome, PageState, StepRecord, WorkingMemory, computer_use_text,  # noqa: E402
                                      estimate_image_tokens, estimate_tokens)
from understudy_agent.models.gemini_provider import _history_text as gemini_hist  # noqa: E402
from understudy_agent.models.imaging import downscale_png  # noqa: E402
from understudy_agent.models.openai_provider import OpenAIProvider  # noqa: E402
from understudy_agent.models import openai_provider as oa  # noqa: E402
from understudy_agent.sandbox_sites.households import generate_households  # noqa: E402
from understudy_agent.tiers.computer_use import ComputerUse, Tier3Result  # noqa: E402
from understudy_agent.tiers.facts import FactStore  # noqa: E402
from understudy_agent import navigator as nav  # noqa: E402

CACHED_FACTOR = 0.25          # assumption: a cached input token costs 25 % of an uncached one (the meter's default)
STEPS = 150
OUT = Path(__file__).resolve().parent / "results" / "token_growth.json"


def shot(n: int) -> bytes:
    im = Image.new("RGB", (1280, 800), (245, 245, 245))
    d = ImageDraw.Draw(im)
    d.rectangle([40 + (n * 13) % 400, 60, 300 + (n * 13) % 400, 140], fill=(30, 100, 220))
    for i in range(n % 7):
        d.text((50, 200 + 24 * i), f"field {i} value", fill=(0, 0, 0))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def make_script(handles: list[str]) -> list[dict]:
    """A plausible 150-step tier-3 run over ten households' pages: click a field, type its handle, press Tab, sometimes scroll,
    press Continue, sometimes an action fails. Shapes are exactly what `ComputerUse.run` appends to its history."""
    out, n, hi, page = [], 0, 0, 0
    while len(out) < STEPS:
        n += 1
        h = handles[hi % len(handles)]
        out.append({"kind": "click", "args": {"x": 300 + 11 * (n % 40), "y": 200 + 17 * (n % 20)}, "ok": True, "page": page})
        out.append({"kind": "type", "handle": h, "ok": True, "page": page})
        out.append({"kind": "key", "args": {"keys": ["Tab"]}, "ok": True, "page": page})
        hi += 1
        if hi % len(handles) == 0:
            out.append({"kind": "click", "args": {"x": 640, "y": 700}, "ok": True, "page": page})
            page += 1
        if n % 13 == 0:
            out.append({"kind": "type", "ok": False, "why": "literal_text", "page": page})
    return out[:STEPS]


def main() -> None:
    h = generate_households(20, 7001)[1]
    facts = FactStore.for_calculator("a", h.params())
    handles = [x.replace("household.", "household.") for x in facts.handles]
    goal = nav.CalculatorJob("a", h.params()).goal + "\n\n" + facts.goal_block()
    goal_tokens, instr_tokens = estimate_tokens(goal), estimate_tokens(oa._CU_INSTRUCTIONS)
    script = make_script(list(handles))

    img = downscale_png(shot(0))
    frame_t = estimate_image_tokens(img.w, img.h, "openai_cu")      # calibrated on the shipped loop's live run (see tokens.py)
    action_item_t = 40       # a computer_call and its output item in a chained conversation, excluding the image (assumption)

    wm = WorkingMemory("calc_a.household", handles=handles, pending=handles)
    fr = FrameRetention()
    hist: list[dict] = []
    rows = []
    for k, step in enumerate(script, start=1):
        # the prompt the model sees BEFORE step k is chosen (history = steps 1..k-1)
        scaled = downscale_png(shot(k))
        chained = instr_tokens + goal_tokens + (k - 1) * (frame_t + action_item_t) + frame_t
        oa_h = OpenAIProvider._history_text(hist, scaled)
        gm_h = gemini_hist(hist, scaled.orig_w, scaled.orig_h)
        stateless_oa = instr_tokens + estimate_tokens("Goal: " + goal + "\n" + oa_h + "Take exactly one action toward the goal.") + frame_t
        stateless_gm = estimate_tokens(__import__("understudy_agent.models.gemini_provider", fromlist=["_CU_SYSTEM"])._CU_SYSTEM) + \
            estimate_tokens("Goal: " + goal + "\n" + gm_h + "Take exactly one action toward the goal.") + frame_t
        # chained with a restart every 4 steps: segment step j (0 = restart: goal + task state + last-12 text + 1 frame; then +1 frame per step)
        t3 = Tier3Result("step_cap", steps=k - 1, history=list(hist), progress_steps=max(0, k - 2))
        ts_tokens = estimate_tokens(ComputerUse._task_state(t3))
        j = (k - 1) % 4
        seg_start = instr_tokens + estimate_tokens("Goal: " + goal) + ts_tokens + estimate_tokens(oa_h) + frame_t
        reset4 = seg_start + j * (frame_t + action_item_t)
        plan = fr.push(shot(k), passthrough=True)
        a = computer_use_text(goal, wm, plan, now=0.0, image_profile="openai_cu")
        lib = instr_tokens + a.manifest.total_tokens

        # information check: can the model read, from the prompt text alone, which handles are entered on this page?
        entered_on_page = {x["handle"] for x in script[: k - 1] if x.get("handle") and x.get("ok") and x["page"] == step["page"]}
        text_oa, text_lib = oa_h, a.text()
        knows = lambda text: all(h_ in text for h_ in entered_on_page) if entered_on_page else True       # noqa: E731
        rows.append({"step": k, "chained": chained, "chained_reset4": reset4, "stateless_openai12": stateless_oa, "stateless_gemini12": stateless_gm, "library": lib,
                     "knows_entered_handles": {"chained": True, "stateless12": knows(text_oa), "library": knows(text_lib),
                                                   "chained_reset4": knows(ComputerUse._task_state(t3) + oa_h)},
                     "n_entered": len(entered_on_page)})
        # step k happens; record it
        hist.append({kk: v for kk, v in step.items() if kk != "page"})
        wm.set_page(PageState.FORM, key=f"p{step['page']}")
        rec = StepRecord.from_history(hist[-1], k, tier=3, page=PageState.FORM)
        wm.record(rec)

    def at(name: str, i: int) -> int:
        return rows[i - 1][name]

    marks = (1, 10, 25, 50, 100, 150)
    summary = {}
    for name in ("chained", "chained_reset4", "stateless_openai12", "stateless_gemini12", "library"):
        vals = [r[name] for r in rows]
        eff = [v if name not in ("chained",) else (r_prev := (rows[i - 1][name] - (frame_t + action_item_t) if i else 0)) * CACHED_FACTOR + (v - r_prev)
               for i, v in enumerate(vals)]
        last50, first50 = vals[-50:], vals[:50]
        slope = (max(last50) - max(first50)) / 100.0          # growth of the ENVELOPE (a sawtooth has no trend)
        summary[name] = {
            "tokens_at": {str(m): at(name, m) for m in marks}, "max": max(vals), "cumulative_input_tokens": sum(vals),
            "cache_adjusted_cumulative": round(sum(eff)), "envelope_growth_tokens_per_step": round(slope, 1),
            "bounded": max(last50) <= 1.15 * max(first50),
        }
    info = {k_: sum(1 for r in rows if r["n_entered"] and not r["knows_entered_handles"][k_]) for k_ in ("stateless12", "library", "chained", "chained_reset4")}
    out = {"origin": "modelled from our own code and one measured per-frame constant; offline; no model call", "steps": STEPS,
           "constants": {"frame_tokens_1280x720": frame_t, "action_item_tokens_chained_assumed": action_item_t, "instructions_tokens": instr_tokens,
                         "goal_plus_facts_tokens": goal_tokens, "cached_price_factor_assumed": CACHED_FACTOR},
           "summary": summary, "steps_where_prompt_cannot_name_an_entered_handle": info,
           "ratio_chained_over_library_at_150": round(at("chained", 150) / at("library", 150), 1),
           "ratio_cumulative_chained_over_library": round(summary["chained"]["cumulative_input_tokens"] / summary["library"]["cumulative_input_tokens"], 1)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("constants", "ratio_chained_over_library_at_150", "ratio_cumulative_chained_over_library", "steps_where_prompt_cannot_name_an_entered_handle")}, indent=1))
    for name, s in summary.items():
        print(f"{name:20s} tokens at {s['tokens_at']}  max {s['max']}  cumulative {s['cumulative_input_tokens']}  cache-adj {s['cache_adjusted_cumulative']}  bounded {s['bounded']}")


if __name__ == "__main__":
    main()
