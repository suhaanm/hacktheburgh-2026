"""Assemble data/eval/modelbench.json and evals/modelbench/REPORT.md from the analysis sections; derive the recommended routing table.

The recommendation is arithmetic on the measured cells with its rules written next to it: the lead decides the default after reading
the report. The routing config is data (`routing.recommended.yaml`), not code.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from . import analyze

ROOT = Path(__file__).resolve().parents[2]
LIMITATIONS = [
    "Screens are synthetic: three sandbox calculators and a case-note page, rendered headless at 1280x800. Nothing here measures a real "
    "macOS desktop (Retina, many windows), real websites, or the worker's own screen.",
    "Ground truth is getBoundingClientRect() of one element; a target description can be ambiguous (for example a label above a text box), "
    "so a few misses are the description's fault, not the model's.",
    "The sites have no dark theme: the 'dark' condition is a CSS invert and hue-rotate filter added by the harness.",
    "Pointing descriptions were generated from the page's own labels, by the same author as the harness; the production path names a fixed step "
    "id instead ('point_step' cells, smaller n).",
    "The injected condition only matters where the injection is visible in the screenshot (site c and the case-note page); the hidden DOM "
    "injections on sites a and b cannot reach a screenshot model.",
    "Verifier negatives are synthetic: real 503 pages, harness-written invalid totals and a harness-added false-success banner. A screenshot "
    "verifier cannot tell a plausible but wrong amount from a right one; the code check does that. Small n.",
    "The escalation rows are simulated from paired per-case measurements of flash-lite and flash, not run live as a router.",
    "Latency is wall-clock from this laptop's network on 7 Nov 2026 with one call at a time per contender (the three contenders ran side by "
    "side); it varies by hour and region. Percentiles over successful calls; the 6 s pointing deadline is applied afterwards.",
    "The laptop was heavily loaded by other build agents during this session (the lead reported a 1-minute load average of 107 to 120 on 12 "
    "cores; 55 to 92 was seen at 18:08). The main run did not record load per call (the field was added afterwards), so its latencies may be "
    "inflated by client-side CPU contention and cannot be corrected; the latency re-check cell records the load at every call. API "
    "latency is dominated by the network and the model, so the effect is probably small, but that is an inference, not a measurement.",
    "Cost is an estimate from token counters at assumed per-million prices (see meta.prices_assumed), not from an invoice. Thinking tokens are billed as output.",
    "The glance cell uses the AWARENESS track's awareness.glance enums; 'plausible' sets are this harness's choice and the repeats of one screenshot are not independent.",
    "OpenAI fast was called through OpenAIProvider.vision (detail auto, frame downscaled to at most 1280x720 by that provider) with the same "
    "prompt and closed schema; its box output was not tuned or prompted further.",
    "Old-project numbers (GROUNDING_AB.md, 31 Oct) are shown separately and are not ours.",
]


def git_info() -> dict[str, Any]:
    def run(*a: str) -> str:
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    return {"sha": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain", "--", "services/agent", "evals/modelbench"))}


def build_json(sections: dict[str, Any], *, models: dict[str, str], budget: dict[str, Any], counts: dict[str, int], apis: dict[str, str],
               thinking: dict[str, str]) -> dict[str, Any]:
    from understudy_agent.models.prices import assumptions

    return {
        "meta": {
            "origin": analyze.ORIGIN, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "git": git_info(), "model_ids_from_env": models, "api": apis, "thinking": thinking,
            "prices_assumed": assumptions(), "budget": budget, "calls": counts, "interval": "Wilson 95% for proportions; seeded percentile "
            "bootstrap 95% for latency percentiles and means", "viewport": [1280, 800], "image": "JPEG q80, long edge at most 1280",
            "limitations": LIMITATIONS, "old_project_reference": analyze.OLD_PROJECT,
        },
        **sections,
    }


def _p(r: dict[str, Any] | None) -> str:
    if not r or r.get("p") is None:
        return "n/a"
    return f"{100 * r['p']:.0f}% [{100 * r['lo']:.0f}, {100 * r['hi']:.0f}] ({r['k']}/{r['n']})"


def _secs(ms: Any) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.2f} s"


def _lat(s: dict[str, Any]) -> str:
    if not s or not s.get("n"):
        return "n/a"
    def f(v: Any) -> str:
        return "n/a" if v is None else f"{v / 1000:.2f}"
    c50 = s.get("p50_ci")
    c95 = s.get("p95_ci")
    return (f"p50 {f(s['p50'])} s" + (f" [{f(c50[0])}, {f(c50[1])}]" if c50 else "") + f"; p95 {f(s['p95'])} s"
            + (f" [{f(c95[0])}, {f(c95[1])}]" if c95 else "") + f" (n={s['n']})")


LABELS = {"gemini_fast": "Gemini flash-lite", "gemini_accurate": "Gemini flash", "openai_fast": "OpenAI fast",
          "routed_lite_then_flash_no_deadline": "routed: lite, then flash when weak (no deadline, simulated)",
          "routed_lite_then_flash_6s_deadline": "routed: lite, then flash when weak (6 s deadline, simulated)"}


def _sig(d: dict[str, Any] | None) -> str | None:
    """'better' / 'worse' / 'not significant' for a paired difference a - b, from its bootstrap 95% interval."""
    if not d or not d.get("ci"):
        return None
    lo, hi = d["ci"]
    return "better" if lo > 0 else ("worse" if hi < 0 else "not significant")


def recommend(sections: dict[str, Any]) -> dict[str, Any]:
    """Transparent rules over the measured cells, decided by the INTERVALS (paired bootstrap 95% for differences on the same cases,
    Wilson 95% for separate rates), never by point estimates alone. Returns {rules, findings, ...}; the lead decides."""
    findings: list[str] = []
    cells = (sections.get("pointing") or {}).get("cells") or {}
    pairs = (sections.get("pointing") or {}).get("paired_hit_differences") or {}
    rules = [
        "point: flash-lite stays primary unless flash is SIGNIFICANTLY better on the same positives (paired bootstrap 95% interval of "
        "flash minus lite entirely above 0) or lite's p95 is over the 6 s deadline",
        "point: keep the lite-to-flash escalation step only if the simulated routed cell is SIGNIFICANTLY better than lite alone on the same "
        "positives (paired interval of routed minus lite entirely above 0); otherwise it only adds latency and cost",
        "point: make OpenAI fast primary only if its hit-rate Wilson interval lies entirely above both Gemini cells' intervals",
        "verify: a Gemini model is acceptable as the independent verifier unless its false-accept Wilson interval lies entirely above "
        "OpenAI fast's; the code gate (verdict yes and confidence >= 0.7) stays whatever the models do",
    ]
    rec: dict[str, Any] = {"rules": rules, "findings": findings, "significance": {}}
    lite, flash, oa = cells.get("gemini_fast"), cells.get("gemini_accurate"), cells.get("openai_fast")
    if lite and flash:
        lh, fh = lite["positives"]["hit"], flash["positives"]["hit"]
        d_lf = pairs.get("gemini_fast_minus_gemini_accurate")
        flash_better = bool(d_lf and d_lf.get("ci") and d_lf["ci"][1] < 0)
        p95 = (lite["latency_ms"] or {}).get("p95")
        rec["point_lite_primary"] = bool(not flash_better and (p95 is None or p95 <= analyze.DEADLINE_MS))
        d_r = pairs.get("routed_6s_deadline_minus_gemini_fast")
        rec["point_keep_escalation"] = bool(d_r and d_r.get("ci") and d_r["ci"][0] > 0)
        rec["significance"]["lite_vs_flash_hit"] = _sig(d_lf)
        rec["significance"]["routed_vs_lite_hit"] = _sig(d_r)
        findings.append(f"point: lite hit {_p(lh)}, flash hit {_p(fh)}; lite minus flash on the same positives is "
                        f"{_sig(d_lf) or 'n/a'}; routed (6 s) minus lite is {_sig(d_r) or 'n/a'}")
    if oa and lite and flash:
        oh = oa["positives"]["hit"]
        best_g = max((lite["positives"]["hit"], flash["positives"]["hit"]), key=lambda r: r["p"] or 0)
        rec["point_openai_primary"] = bool(oh["lo"] > best_g["hi"])
        rec["significance"]["openai_vs_gemini_hit"] = _sig(pairs.get("gemini_fast_minus_openai_fast"))
        findings.append(f"point: OpenAI fast hit {_p(oh)} vs best Gemini {_p(best_g)}; Gemini lite minus OpenAI is "
                        f"{_sig(pairs.get('gemini_fast_minus_openai_fast')) or 'n/a'} (paired)")
    ver = (sections.get("verifier") or {}).get("cells") or {}
    if ver:
        fa = {c: v["verdict_yes_is_accept"]["false_accept"] for c, v in ver.items()}
        findings.append("verify false-accept (verdict yes on a reject image): " + "; ".join(f"{LABELS.get(c, c)} {_p(r)}" for c, r in fa.items()))
        g = [c for c in ("gemini_fast", "gemini_accurate") if c in fa]
        if g and "openai_fast" in fa:
            rec["verify_gemini_ok"] = all(not (fa[c]["lo"] > fa["openai_fast"]["hi"]) for c in g)
            sep = [c for c in g if fa[c]["lo"] > fa["openai_fast"]["hi"]]
            findings.append("verify: Gemini false-accept is " + ("significantly WORSE than OpenAI's for " + ", ".join(sep) if sep else
                            "not significantly different from OpenAI's (the intervals overlap; the set is small)"))
    return rec


def routing_yaml(rec: dict[str, Any]) -> str:
    """The recommended routing table as models.yaml text (a starting point written from the rules above; the lead decides)."""
    from understudy_agent.models.routing import RoutingConfig

    cfg = RoutingConfig().to_dict()
    steps = cfg["roles"]["point"]["steps"]
    if rec.get("point_openai_primary"):
        steps = [{"provider": "openai", "tier": "fast", "when": "primary"}, {"provider": "gemini", "tier": "fast", "when": "fallback"}]
    else:
        if rec.get("point_lite_primary") is False:
            steps = [{"provider": "gemini", "tier": "accurate", "when": "primary"}, {"provider": "openai", "tier": "fast", "when": "fallback"}]
        elif rec.get("point_keep_escalation") is False:
            steps = [s for s in steps if s["when"] != "escalate"]
    cfg["roles"]["point"]["steps"] = steps
    head = ("# Recommended routing from the 7 Nov 2026 bake-off (evals/modelbench). A starting point, not a decision: the lead decides.\n"
            "# Rules and the numbers behind each choice are in data/eval/modelbench.json (recommendation) and REPORT.md.\n")
    return head + yaml.safe_dump(cfg, sort_keys=False)


def render_markdown(j: dict[str, Any]) -> str:
    m = j["meta"]
    L: list[str] = []
    a = L.append
    a("# Model bake-off: Gemini flash-lite, Gemini flash, OpenAI fast")
    a("")
    a(f"Origin of every number: **{m['origin']}** (n is stated; intervals are {m['interval']}). Generated {m['generated_at']}, "
      f"git {str(m['git']['sha'])[:10]}{' (dirty)' if m['git']['dirty'] else ''}. Origin badge: SYNTHETIC. Not a claim about real screens.")
    a("")
    a("Contenders (model ids read from the environment): " + "; ".join(f"{LABELS.get(k, k)} = `{v}` ({m['api'].get(k, '?')}, {m['thinking'].get(k, '?')})"
                                                                        for k, v in m["model_ids_from_env"].items()) + ".")
    b = m["budget"]
    cn = m["calls"]
    a(f"Spend: estimated US${b['estimated_spend_usd']} of a US${b['cap_usd']} cap (the guard counts {b['safety_factor']}x the estimate; "
      f"includes about US${b['probe_spend_usd_included']} of hand-run probes). Live calls over all runs of this harness: {cn.get('live_calls_all_runs', cn.get('live', 0))}; "
      f"distinct cached results: {cn.get('cache_rows', cn.get('cached', 0))}; cells dropped by the budget guard: {b['n_dropped']}; "
      f"this invocation made {cn.get('live', 0)} live calls ({cn.get('failed', 0)} failed).")
    a("")
    dup = (j.get("recommendation") or {}).get("duplicate_inputs_skipped")
    a("Counting rule: an input (screenshot pixels plus description) is asked once and counted once. A layout=v2 or dark case whose screenshot is "
      "pixel-identical to a base case is the same input, so it cannot fill a secondary sample; "
      + (f"{dup} repeated inputs were skipped in this analysis. " if dup is not None else "") + "A failed call counts as a miss on a positive and as not-correct on a negative.")
    a("")
    pt = j.get("pointing") or {}
    a("## 1. Pointing by description (direct path)")
    a("")
    cells = pt.get("cells") or {}
    if cells:
        a("Hit = predicted box centre inside the element's getBoundingClientRect. Negatives are elements that are not on screen; correct = not found. "
          "A failed call is a miss on a positive and not-correct on a negative.")
        a("")
        a("| Cell | Positives hit | Mean IoU (n found) | Negatives correct | Latency (successful calls) | Over 6 s | Failed calls | Cost est. per call |")
        a("|---|---|---|---|---|---|---|---|")
        for k, c in cells.items():
            iou = c["positives"]["mean_iou_over_found"]
            a(f"| {LABELS.get(k, k)} | {_p(c['positives']['hit'])} | {'n/a' if iou is None else iou} ({c['positives']['n_iou']}) | "
              f"{_p(c['negatives']['correct'])} | {_lat(c['latency_ms'])} | {_p(c['over_6s'])} | "
              f"{c['n_failed']}{' (' + ', '.join(f'{k}: {v}' for k, v in c['failed_calls'].items()) + ')' if c['n_failed'] else ''} | "
              f"US${c['cost_usd_est']['per_call'] if c['cost_usd_est']['per_call'] is not None else 'n/a'} |")
        a("")
        a("Split by condition (hit rate on positives; negatives correct):")
        a("")
        conds = sorted({cn for c in cells.values() for cn in c["by_cond"]})
        a("| Cell | " + " | ".join(conds) + " |")
        a("|---|" + "---|" * len(conds))
        for k, c in cells.items():
            a(f"| {LABELS.get(k, k)} | " + " | ".join(
                (f"{_p(c['by_cond'][cn]['positives']['hit'])}; neg {_p(c['by_cond'][cn]['negatives']['correct'])}" if cn in c["by_cond"] else "n/a")
                for cn in conds) + " |")
        a("")
        a("Split by site:")
        a("")
        sites = sorted({s for c in cells.values() for s in c["by_site"]})
        a("| Cell | " + " | ".join(f"site {s}" for s in sites) + " |")
        a("|---|" + "---|" * len(sites))
        for k, c in cells.items():
            a(f"| {LABELS.get(k, k)} | " + " | ".join(_p(c["by_site"][s]["positives"]["hit"]) if s in c["by_site"] else "n/a" for s in sites) + " |")
        a("")
        bl = pt.get("baselines")
        if bl:
            a(f"Baselines (no model): clicking the viewport centre hits {_p(bl['click_viewport_centre']['hit'])}; a uniform random click is expected to hit "
              f"{100 * bl['uniform_random_click']['expected_hit']:.1f}%; always answering not-found scores 0% on positives and 100% on negatives.")
            a("")
        pd = pt.get("paired_hit_differences") or {}
        if pd:
            a("Paired hit-rate differences on the same positives (a minus b; bootstrap 95% interval; exact McNemar p; 'not significant' means the interval includes 0):")
            a("")
            for k, v in pd.items():
                ci = v["ci"]
                a(f"- {k.replace('_minus_', ' minus ')}: {100 * (v['diff'] or 0):+.1f} points"
                  + (f" [{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}]" if ci else "") + f", only-a {v['only_a']}, only-b {v['only_b']}, p={v['mcnemar_p']} (n={v['n']}): "
                  f"**{_sig(v) or 'n/a'}**")
            a("")
    else:
        a("_No pointing results yet._")
        a("")
    ps = j.get("pointing_step_ids") or {}
    a("## 2. Pointing by fixed step id (the production path through egress.send_image)")
    a("")
    pcells = ps.get("cells") or {}
    if pcells:
        a("| Cell | Positives hit | Negatives correct | Latency | Cost est. per call |")
        a("|---|---|---|---|---|")
        for k, c in pcells.items():
            a(f"| {LABELS.get(k, k)} | {_p(c['positives']['hit'])} | {_p(c['negatives']['correct'])} | {_lat(c['latency_ms'])} | "
              f"US${c['cost_usd_est']['per_call'] if c['cost_usd_est']['per_call'] is not None else 'n/a'} |")
        a("")
    else:
        a("_No step-id results yet._")
        a("")
    vf = j.get("verifier") or {}
    a("## 3. Independent screen verifier")
    a("")
    vc = vf.get("cells") or {}
    if vc:
        a(f"Question (check id `page_shows_result`): {vf['question']}. Images: {vf['n_images_defined']} ({vf['n_truth_accept']} should be accepted, "
          f"{vf['n_truth_reject']} should not); groups {vf['groups']}. Accept = verdict yes; `unsure` is never an accept.")
        a("")
        a("| Cell | Accuracy | False-accept (yes on a reject image) | False-reject | Unsure | With code gate (yes and conf >= 0.7): false-accept | Latency |")
        a("|---|---|---|---|---|---|---|")
        for k, c in vc.items():
            y, g = c["verdict_yes_is_accept"], c["code_gate_yes_and_confidence_at_least_0.7"]
            a(f"| {LABELS.get(k, k)} | {_p(y['accuracy'])} | {_p(y['false_accept'])} | {_p(y['false_reject'])} | {_p(c['unsure'])} | "
              f"{_p(g['false_accept'])} | {_lat(c['latency_ms'])} |")
        a("")
        a("By image group (correct = the verdict matched the truth):")
        a("")
        groups = sorted({g for c in vc.values() for g in c["by_group"]})
        a("| Cell | " + " | ".join(groups) + " |")
        a("|---|" + "---|" * len(groups))
        for k, c in vc.items():
            a(f"| {LABELS.get(k, k)} | " + " | ".join(_p(c["by_group"][g]["correct"]) if g in c["by_group"] else "n/a" for g in groups) + " |")
        a("")
        a("Reading this: all three models were right on every image, so this set cannot tell them apart; the honest statement is that each "
          "model's false-accept rate on these 15 reject images is 0 with an upper 95% bound of 20%. It is too small and too easy to choose a verifier.")
        a("")
        bl = vf.get("baselines")
        if bl:
            a(f"Baselines: always-accept is right {_p(bl['always_accept']['accuracy'])} of the time and falsely accepts every reject image; "
              f"always-reject is right {_p(bl['always_reject']['accuracy'])}.")
            a("")
        ctx = vf.get("context_live_runs")
        if ctx:
            a(f"Context (descriptive, not re-run, a different measurement): {ctx['origin']}: {ctx['n_rows']} rows, {ctx['claimed_success']} claimed success, "
              f"{ctx['false_claims']} of those were false claims by the code check.")
            a("")
    else:
        a("_No verifier results yet._")
        a("")
    gl = j.get("glance") or {}
    a("## 4. Glance: latency and answer stability")
    a("")
    gc = gl.get("cells") or {}
    if gc:
        a(f"Same screenshot, {gl['repeats_per_screen']} repeats, {len(gl['screens'])} screens, purpose {gl['purpose']}. {gl['plausibility_note']}.")
        a("")
        a("| Cell | Same enum triple as the modal answer | app_kind | task_phase | blocker | Plausible | Latency |")
        a("|---|---|---|---|---|---|---|")
        for k, c in gc.items():
            fa = c["field_agreement"]
            a(f"| {LABELS.get(k, k)} | {_p(c['modal_triple_agreement'])} | {_p(fa['app_kind'])} | {_p(fa['task_phase'])} | {_p(fa['blocker'])} | "
              f"{_p(c['plausible'])} | {_lat(c['latency_ms'])} |")
        a("")
        a(f"_{next(iter(gc.values()))['agreement_note']}._")
        a("")
    else:
        a("_No glance results yet._")
        a("")
    a("## 5. Old-project numbers (shown separately, NOT ours)")
    a("")
    o = analyze.OLD_PROJECT
    a(f"{o['origin']}. flash-lite: {100 * o['flash_lite_box']['hit_rate']:.0f}% on {o['flash_lite_box']['n_positives']} targets, negatives {o['flash_lite_box']['negatives']}, "
      f"p50 {o['flash_lite_box']['p50_s']} s, p95 {o['flash_lite_box']['p95_s']} s. flash: {100 * o['flash_box']['hit_rate']:.0f}% on {o['flash_box']['n_positives']}, "
      f"negatives {o['flash_box']['negatives']}, p50 {o['flash_box']['p50_s']} s, p95 {o['flash_box']['p95_s']} s.")
    a("")
    lr = (j.get("latency_recheck") or {}).get("cells") or {}
    if any(c["n_calls"] for c in lr.values()):
        a("## 5b. Latency re-check with the machine load recorded")
        a("")
        a(j["latency_recheck"]["what"] + ".")
        a("")
        a("| Cell | Calls ok / made | Latency | Mean 1-min load (max) at call time | p50 in the main run (load not recorded) |")
        a("|---|---|---|---|---|")
        for k, c in lr.items():
            ld = c["load_avg_1m"]
            a(f"| {LABELS.get(k, k)} | {c['n_ok']} / {c['n_calls']} | {_lat(c['latency_ms'])} | "
              f"{ld['mean'] if ld['mean'] is not None else 'n/a'} ({ld['max'] if ld['max'] is not None else 'n/a'}) | "
              f"{_secs(c['main_run_p50_ms'])} (n={c['main_run_n']}) |")
        a("")
    rec = j.get("recommendation") or {}
    a("## 6. Routing recommendation (arithmetic on the cells above; the lead decides)")
    a("")
    for r in rec.get("findings", []):
        a(f"- {r}")
    a("")
    sig = rec.get("significance") or {}
    if sig:
        a("")
        a("Significance (paired, same cases): " + "; ".join(f"{k.replace('_', ' ')} = {v}" for k, v in sig.items() if v))
    a("")
    a("Rules applied:")
    for r in rec.get("rules", []):
        a(f"- {r}")
    a("")
    a("The resulting table is `evals/modelbench/routing.recommended.yaml` (a `models.yaml` the router reads via `UNDERSTUDY_MODELS_YAML`).")
    a("")
    a("## 7. Limitations")
    a("")
    for x in m["limitations"]:
        a(f"- {x}")
    a("")
    if b["n_dropped"]:
        a(f"Dropped by the budget guard: {b['n_dropped']} cells (first few: {b['dropped_cells'][:3]}).")
        a("")
    return "\n".join(L)


def write_all(j: dict[str, Any], *, out_json: Path, out_md: Path, out_yaml: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(j, indent=1, default=str))
    out_md.write_text(render_markdown(j))
    out_yaml.write_text(routing_yaml(j.get("recommendation") or {}))
