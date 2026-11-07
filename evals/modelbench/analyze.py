"""Turn cached call results into the report sections. Pure: reads the manifest and the cache rows, calls nothing.

Rules every number follows: n is stated, a proportion carries a Wilson 95% interval, latency percentiles and means carry a seeded
bootstrap interval, every cell carries its split (condition, site, role), and the origin is "synthetic sandbox UI, headless
screenshots". A call that failed counts as a miss on a positive and as not-correct on a negative (conservative); failures are also
listed on their own. Latency percentiles are over successful calls only. Nothing here claims anything about screens other than the
sandbox sites.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

from understudy_agent.models.schemas import parse_point

from . import stats

ORIGIN = "synthetic sandbox UI, headless screenshots"
DEADLINE_MS = 6000.0
ESCALATE_BELOW = 0.7
OLD_PROJECT = {
    "origin": "OLD PROJECT (Alongside), 31 Oct 2026, old key, different fixtures; reported by that project's GROUNDING_AB.md; NOT our measurement",
    "flash_lite_box": {"n_positives": 59, "hit_rate": 0.95, "negatives": "15 of 15 rejected", "p50_s": 0.88, "p95_s": 1.21},
    "flash_box": {"n_positives": 78, "hit_rate": 0.98, "negatives": "18 of 18 rejected", "p50_s": 3.8, "p95_s": 7.0},
    "stage_fast_preset": {"n_positives": 85, "hit_rate": 0.88, "negatives": "15 of 15 rejected", "p50_s": 1.16, "p95_s": 1.68},
}


# ------------------------------------------------------------------------------------------------ pointing
def _rows(rows: list[dict[str, Any]], kind: str) -> dict[tuple[str, str, int], dict[str, Any]]:
    return {(r["contender"], r["case_id"], int(r.get("rep", 0))): r for r in rows if r["kind"] == kind}


def point_record(case: dict[str, Any], shot: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
    """One (case, contender) outcome. `case` has kind positive|negative and a truth `box` (px) for a positive."""
    rec: dict[str, Any] = {"case_id": case["case_id"], "kind": case["kind"], "cond": case.get("cond"), "site": case.get("site"),
                           "role": case.get("role", "control"), "present": row is not None, "ok": bool(row and row["ok"]),
                           "error_kind": row.get("error_kind") if row else "missing", "latency_ms": row.get("latency_ms") if row else None,
                           "cost_usd": row.get("cost_usd") if row else None, "input_tokens": row.get("input_tokens") if row else None,
                           "output_tokens": (row.get("output_tokens") or 0) + (row.get("thought_tokens") or 0) if row and row["ok"] else None,
                           "found": False, "reason": None, "confidence": None, "hit": False, "iou": None, "correct_negative": False}
    if not (row and row["ok"] and row.get("value") is not None):
        return rec
    try:
        res = parse_point(row["value"])
    except Exception:  # noqa: BLE001 - a malformed answer is a failed call for scoring
        rec["ok"], rec["error_kind"] = False, "schema"
        return rec
    rec.update(found=res.found, reason=res.reason, confidence=res.confidence)
    w, h = shot["width"], shot["height"]
    if case["kind"] == "negative":
        rec["correct_negative"] = not res.found
        return rec
    if res.found and res.box_2d:
        px = res.to_pixels(w, h)
        cx, cy = (px[0] + px[2]) / 2, (px[1] + px[3]) / 2
        truth = case["box"]
        rec["hit"] = stats.point_in_box(cx, cy, truth)
        rec["iou"] = stats.iou(px, truth)
    return rec


def agg_point(recs: list[dict[str, Any]]) -> dict[str, Any]:
    pos = [r for r in recs if r["kind"] == "positive"]
    neg = [r for r in recs if r["kind"] == "negative"]
    hits = sum(1 for r in pos if r["hit"])
    ious = [r["iou"] for r in pos if r["iou"] is not None]
    lat = [r["latency_ms"] for r in recs if r["ok"] and r["latency_ms"] is not None]
    costs = [r["cost_usd"] for r in recs if r["cost_usd"] is not None]
    fails = Counter(r["error_kind"] for r in recs if not r["ok"])
    out: dict[str, Any] = {
        "positives": {"hit": stats.rate(hits, len(pos)),
                      "found": stats.rate(sum(1 for r in pos if r["found"]), len(pos)),
                      "wrong_place": sum(1 for r in pos if r["found"] and not r["hit"]),
                      "said_not_found": sum(1 for r in pos if r["ok"] and not r["found"]),
                      "mean_iou_over_found": (round(sum(ious) / len(ious), 3) if ious else None),
                      "mean_iou_ci": stats.bootstrap_ci(ious, lambda v: sum(v) / len(v)) if len(ious) > 1 else None,
                      "n_iou": len(ious)},
        "negatives": {"correct": stats.rate(sum(1 for r in neg if r["correct_negative"]), len(neg)),
                      "false_positives": sum(1 for r in neg if r["ok"] and r["found"])},
        "latency_ms": stats.summarize(lat) if lat else {"n": 0},
        "over_6s": stats.rate(sum(1 for v in lat if v > DEADLINE_MS), len(lat)),
        "failed_calls": dict(fails), "n_failed": sum(fails.values()),
        "tokens": {"mean_input": (round(statistics.mean(r["input_tokens"] for r in recs if r["input_tokens"] is not None), 1)
                                  if any(r["input_tokens"] is not None for r in recs) else None),
                   "mean_output_billed": (round(statistics.mean(r["output_tokens"] for r in recs if r["output_tokens"] is not None), 1)
                                          if any(r["output_tokens"] is not None for r in recs) else None)},
        "cost_usd_est": {"total": round(sum(costs), 4), "per_call": (round(sum(costs) / len(costs), 6) if costs else None),
                         "n": len(costs)},
    }
    return out


def _split(recs: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        groups[str(r[key])].append(r)
    return {g: {"n_cases": len(v), **agg_point(v)} for g, v in sorted(groups.items())}


def point_cell(recs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"n_cases": len(recs), **agg_point(recs), "by_cond": _split(recs, "cond"), "by_site": _split(recs, "site"),
            "by_role": _split(recs, "role")}


def _weak(r: dict[str, Any]) -> bool:
    """The router's escalation rule applied to a recorded answer: failed, not found, or confidence under the bar."""
    return (not r["ok"]) or (not r["found"]) or (r["confidence"] is not None and r["confidence"] < ESCALATE_BELOW)


def routed_simulation(lite: dict[str, dict[str, Any]], flash: dict[str, dict[str, Any]], *, deadline: bool) -> list[dict[str, Any]]:
    """flash-lite first, flash when weak, from the paired per-case measurements (NOT a separate live run). With `deadline`, the 6 s
    hard cap of the point role: a lite call over 6 s is a timeout (no answer, nothing left to escalate with); flash is used only if
    lite plus flash fit inside 6 s, otherwise lite's own valid answer stands."""
    out = []
    for cid, L in lite.items():
        F = flash.get(cid)
        rec = dict(L)
        lat = float(L["latency_ms"] or 0)
        cost = float(L["cost_usd"] or 0.0)
        escalated = False
        if deadline and L["ok"] and lat > DEADLINE_MS:
            rec.update(ok=False, error_kind="timeout", found=False, hit=False, iou=None, correct_negative=False, confidence=None)
            lat = DEADLINE_MS
        elif _weak(L) and F is not None and F["ok"]:
            flat = float(F["latency_ms"] or 0)
            if not deadline or lat + flat <= DEADLINE_MS:
                rec = dict(F)
                escalated = True
                lat += flat
                cost += float(F["cost_usd"] or 0.0)
        rec["latency_ms"] = lat
        rec["cost_usd"] = cost
        rec["escalated"] = escalated
        out.append(rec)
    return out


def pointing_section(manifest: dict[str, Any], rows: list[dict[str, Any]], contenders: list[str], *, kind: str, id_key: str) -> dict[str, Any]:
    """`kind` is point_desc (cases from manifest['cases'] under the seeded sample) or point_step (manifest['step_cases'])."""
    shots = {s["shot_id"]: s for s in manifest["shots"]}
    by = _rows(rows, kind)
    cases = manifest[id_key]
    out: dict[str, Any] = {"origin": ORIGIN, "cells": {}, "n_cases_defined": len(cases)}
    per: dict[str, dict[str, dict[str, Any]]] = {}
    for c in contenders:
        recs = []
        for case in cases:
            if (c, case["case_id"], 0) not in by:
                continue                                   # never called (dropped by the budget guard or not yet run): not a miss
            recs.append(point_record(case, shots[case["shot_id"]], by[(c, case["case_id"], 0)]))
        per[c] = {r["case_id"]: r for r in recs}
        out["cells"][c] = point_cell(recs)
    both = [c for c in ("gemini_fast", "gemini_accurate") if c in per]
    if len(both) == 2 and per["gemini_fast"] and per["gemini_accurate"]:
        common = sorted(set(per["gemini_fast"]) & set(per["gemini_accurate"]))
        lite = {i: per["gemini_fast"][i] for i in common}
        flash = {i: per["gemini_accurate"][i] for i in common}
        for label, dl in (("routed_lite_then_flash_no_deadline", False), ("routed_lite_then_flash_6s_deadline", True)):
            sim = routed_simulation(lite, flash, deadline=dl)
            cell = point_cell(sim)
            cell["escalation_rate"] = stats.rate(sum(1 for r in sim if r["escalated"]), len(sim))
            cell["note"] = ("simulated from the paired per-case measurements of flash-lite and flash (the routing rule applied to "
                            "recorded answers); not a separate live run" + ("; latency is the sum of the calls used, capped by the 6 s deadline rule" if dl else ""))
            out["cells"][label] = cell
    # paired differences on positives (same cases)
    pairs = {}
    names = [c for c in contenders if c in per]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = sorted(set(per[a]) & set(per[b]))
            pos = [cid for cid in common if per[a][cid]["kind"] == "positive"]
            if len(pos) >= 5:
                pairs[f"{a}_minus_{b}"] = {"on": "positive hit", **stats.paired_diff([int(per[a][c]["hit"]) for c in pos], [int(per[b][c]["hit"]) for c in pos])}
    out["paired_hit_differences"] = pairs
    # baselines (no model): where would a click land without looking?
    if kind == "point_desc":
        pos_cases = [c for c in cases if c["kind"] == "positive"]
        if pos_cases:
            centre = sum(1 for c in pos_cases if stats.point_in_box(640, 400, c["box"]))
            area = [((c["box"][2] - c["box"][0]) * (c["box"][3] - c["box"][1])) / (1280 * 800) for c in pos_cases]
            out["baselines"] = {
                "click_viewport_centre": {"hit": stats.rate(centre, len(pos_cases)), "what": "centre of the 1280x800 viewport lies in the target box"},
                "uniform_random_click": {"expected_hit": round(sum(area) / len(area), 4), "what": "mean share of the viewport the target box covers"},
                "always_say_not_found": {"hit": stats.rate(0, len(pos_cases)),
                                         "negatives_correct": stats.rate(sum(1 for c in cases if c["kind"] == "negative"), sum(1 for c in cases if c["kind"] == "negative"))},
                "n_positive_cases_defined": len(pos_cases)}
    return out


# ------------------------------------------------------------------------------------------------ verifier
def verifier_section(manifest: dict[str, Any], rows: list[dict[str, Any]], contenders: list[str]) -> dict[str, Any]:
    by = _rows(rows, "verify")
    items = manifest["verifier"]
    out: dict[str, Any] = {"origin": ORIGIN, "question": "page_shows_result: the page shows a completed calculation with a numeric result",
                           "n_images_defined": len(items), "groups": dict(Counter(i["group"] for i in items)),
                           "n_truth_accept": sum(1 for i in items if i["truth_accept"]),
                           "n_truth_reject": sum(1 for i in items if not i["truth_accept"]), "cells": {}}
    for c in contenders:
        recs = []
        for it in items:
            row = by.get((c, it["id"], 0))
            if row is None:
                continue
            ok = bool(row["ok"] and row.get("value"))
            verdict = row["value"]["verdict"] if ok else None
            conf = row["value"]["confidence"] if ok else None
            recs.append({"id": it["id"], "group": it["group"], "truth": it["truth_accept"], "ok": ok, "verdict": verdict, "conf": conf,
                         "accept": verdict == "yes", "gated_accept": verdict == "yes" and (conf or 0) >= ESCALATE_BELOW,
                         "latency_ms": row.get("latency_ms"), "cost_usd": row.get("cost_usd")})
        out["cells"][c] = _verify_cell(recs)
    # baselines
    n_acc, n_rej = out["n_truth_accept"], out["n_truth_reject"]
    if items:
        out["baselines"] = {"always_accept": {"accuracy": stats.rate(n_acc, len(items)), "false_accept": stats.rate(n_rej, n_rej)},
                            "always_reject": {"accuracy": stats.rate(n_rej, len(items)), "false_accept": stats.rate(0, n_rej)}}
    out["context_live_runs"] = live_runs_context()
    return out


def _verify_cell(recs: list[dict[str, Any]]) -> dict[str, Any]:
    acc_t = [r for r in recs if r["truth"]]
    rej_t = [r for r in recs if not r["truth"]]

    def block(accept_key: str) -> dict[str, Any]:
        fa = sum(1 for r in rej_t if r[accept_key])
        fr = sum(1 for r in acc_t if not r[accept_key])
        correct = sum(1 for r in recs if r[accept_key] == r["truth"])
        return {"accuracy": stats.rate(correct, len(recs)), "false_accept": stats.rate(fa, len(rej_t)),
                "false_reject": stats.rate(fr, len(acc_t))}

    groups: dict[str, Any] = {}
    for g in sorted({r["group"] for r in recs}):
        gr = [r for r in recs if r["group"] == g]
        truth = gr[0]["truth"]
        k = sum(1 for r in gr if r["accept"] == truth)
        groups[g] = {"truth_accept": truth, "n": len(gr), "correct": stats.rate(k, len(gr)),
                     "verdicts": dict(Counter(r["verdict"] or "failed" for r in gr))}
    lat = [r["latency_ms"] for r in recs if r["ok"] and r["latency_ms"] is not None]
    costs = [r["cost_usd"] for r in recs if r["cost_usd"] is not None]
    return {"n": len(recs), "n_failed": sum(1 for r in recs if not r["ok"]),
            "verdict_yes_is_accept": block("accept"),
            "code_gate_yes_and_confidence_at_least_0.7": block("gated_accept"),
            "unsure": stats.rate(sum(1 for r in recs if r["verdict"] == "unsure"), len(recs)),
            "by_group": groups, "latency_ms": stats.summarize(lat) if lat else {"n": 0},
            "cost_usd_est": {"total": round(sum(costs), 4), "n": len(costs)}}


def live_runs_context() -> dict[str, Any] | None:
    """Descriptive only: false-claim rows from data/eval/agent_live_runs.json (the agent-core track's live grid; NOT re-run here)."""
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "data" / "eval" / "agent_live_runs.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    rows = d.get("claim_calibration_rows") or []
    by = Counter()
    for r in rows:
        variant = str(r.get("run_id", "")).split("_hh_")[-1].split("_", 1)[-1] if "_hh_" in str(r.get("run_id")) else "?"
        by[(variant, bool(r.get("claimed_success")), bool(r.get("code_check_ok")))] += 1
    return {"origin": "agent-core live grid (real OpenAI model on the sandbox sites), read from data/eval/agent_live_runs.json; "
                      "descriptive context only, NOT re-run and NOT a verifier measurement",
            "n_rows": len(rows), "claimed_success": sum(1 for r in rows if r.get("claimed_success")),
            "false_claims": sum(1 for r in rows if r.get("claimed_success") and not r.get("code_check_ok")),
            "by_run_kind_claimed_ok": {f"{k[0]}|claimed={k[1]}|code_ok={k[2]}": v for k, v in sorted(by.items())}}


# ------------------------------------------------------------------------------------------------ glance
PLAUSIBLE = {   # screen kind -> (acceptable task_phase, acceptable blocker) in the AWARENESS glance enums; an unforced harness choice
    "form": ({"entering", "reading", "idle", "searching"}, {"none"}),
    "result": ({"reviewing", "reading", "comparing", "idle"}, {"none"}),
    "error": ({"waiting", "reading", "reviewing", "idle", "entering", "submitting", "unknown"}, {"error_message", "unexpected_state"}),
}
GLANCE_SCREENS = {"a_landing": "form", "a_step1": "form", "a_result": "result", "a_503": "error", "b_home": "form", "b_result": "result",
                  "c_panel1": "form", "c_result": "result"}


def glance_section(manifest: dict[str, Any], rows: list[dict[str, Any]], contenders: list[str]) -> dict[str, Any]:
    g_rows = [r for r in rows if r["kind"] == "glance"]
    out: dict[str, Any] = {"origin": ORIGIN, "purpose": "awareness.glance (the AWARENESS track's closed enums)",
                           "screens": GLANCE_SCREENS, "repeats_per_screen": max((int(r.get("rep", 0)) for r in g_rows), default=-1) + 1,
                           "plausibility_note": "'plausible' = task_phase and blocker fall in sets chosen by this harness for a sandbox screen kind "
                                                "(form, result, error); it is a sanity check, not ground truth", "cells": {}}
    for c in contenders:
        mine = [r for r in g_rows if r["contender"] == c]
        per_screen = {}
        modal_k = n_ok = plaus_k = 0
        field_agree = {"app_kind": [0, 0], "task_phase": [0, 0], "blocker": [0, 0]}
        for sid, kind in GLANCE_SCREENS.items():
            sr = [r for r in mine if r["case_id"] == sid and r["ok"] and r.get("value")]
            if not sr:
                continue
            triples = [(r["value"]["app_kind"], r["value"]["task_phase"], r["value"]["blocker"]) for r in sr]
            top, cnt = Counter(triples).most_common(1)[0]
            modal_k += cnt
            n_ok += len(triples)
            ph, bl = PLAUSIBLE[kind]
            pk = sum(1 for t in triples if t[1] in ph and t[2] in bl)
            plaus_k += pk
            for idx, f in enumerate(("app_kind", "task_phase", "blocker")):
                fc = Counter(t[idx] for t in triples).most_common(1)[0][1]
                field_agree[f][0] += fc
                field_agree[f][1] += len(triples)
            per_screen[sid] = {"n": len(triples), "modal": top, "modal_share": round(cnt / len(triples), 3),
                               "values": [list(t) for t in dict.fromkeys(triples)], "plausible": stats.rate(pk, len(triples))}
        lat = [r["latency_ms"] for r in mine if r["ok"] and r["latency_ms"] is not None]
        costs = [r["cost_usd"] for r in mine if r["cost_usd"] is not None]
        out["cells"][c] = {
            "n_calls": len(mine), "n_ok": n_ok, "n_failed": sum(1 for r in mine if not r["ok"]),
            "modal_triple_agreement": stats.rate(modal_k, n_ok),
            "agreement_note": "repeats of one screenshot are not independent samples; the interval is indicative",
            "field_agreement": {f: stats.rate(a, b) for f, (a, b) in field_agree.items()},
            "plausible": stats.rate(plaus_k, n_ok), "by_screen": per_screen,
            "latency_ms": stats.summarize(lat) if lat else {"n": 0}, "cost_usd_est": {"total": round(sum(costs), 4), "n": len(costs)}}
    return out
