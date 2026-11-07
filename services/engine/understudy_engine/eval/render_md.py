"""evals/report.md: a short human-readable rendering of the report (feeds the README and the submission text).

Every table is headed by a line with origin, n, split and interval level, so no number appears without them.
"""
from __future__ import annotations

from typing import Any

TITLES = {
    "deficit_recovery": "Deficit recovery (EVL-1)",
    "null_placebo": "Controls: placebo and shuffled-label null",
    "hazard": "Stuck hazard (leave one person out)",
    "policy_gate": "Coaching dignity gate",
    "skills": "Skill tracing",
    "ope": "Off-policy evaluation",
    "routing": "Review routing and risk control",
    "ski_rental": "Ski-rental build timing",
    "presence": "Presence and window forecast",
    "routines": "Routine finder",
    "forecast": "Recurrence forecast",
    "agent_claims": "Agent-claim calibration",
    "agent_runs": "Agent runs on the sandbox (AGT-5, AGT-7)",
    "pooling": "Partial pooling for new people",
    "redteam": "Red team with ablations",
    "redteam_live": "Red team, live model (secondary)",
    "study": "Live study (n = 4)",
}


def f(x: Any, nd: int = 2, signed: bool = False) -> str:
    if x is None or isinstance(x, bool):
        return "n/a" if x is None else str(x)
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"
    return str(x)


def pc(x: Any, nd: int = 0) -> str:
    return "n/a" if x is None else f"{100 * float(x):.{nd}f}%"


def ci(c: Any, nd: int = 2, pct: bool = False) -> str:
    if not c or c[0] is None:
        return "n/a"
    return f"[{pc(c[0], 1)}, {pc(c[1], 1)}]" if pct else f"[{f(c[0], nd)}, {f(c[1], nd)}]"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def basis(meta: dict[str, Any]) -> str:
    lvl = int(round(100 * (meta.get("interval_level") or 0.95)))
    return (f"*origin: **{meta.get('origin')}** · n = {meta.get('n')} {meta.get('n_unit')} · split: {meta.get('split') or 'n/a'} · "
            f"intervals: {lvl}%*")


def _deficit(s: dict[str, Any]) -> str:
    rows = [[r["label"] if "label" in r else r["deficit"], f(r["injected_price_s"], 1), f(r["recovered_price_s"], 1), ci(r["ci"], 1),
             f(r.get("bias_s"), 1, True), f"{pc(r['precision'])} {ci(r.get('precision_ci'), pct=True)}", f"{pc(r['recall'])} {ci(r.get('recall_ci'), pct=True)}",
             f(r.get("threshold_s"), 1)] for r in s["rows"]]
    o = s["overall"]
    return (table(["Deficit (synthetic)", "Injected price (s)", "Recovered price (s)", "95% interval", "Bias (s)", "Precision", "Recall", "X (s)"], rows)
            + f"\n\nOverall (all case-deficit pairs): precision {pc(o['precision'])} {ci(o.get('precision_ci'), pct=True)}, recall {pc(o['recall'])} {ci(o.get('recall_ci'), pct=True)}."
            + f"\n\nDetection rule: {s.get('detection_rule')}.")


def _null(s: dict[str, Any]) -> str:
    rows = [["Real: novice vs nearest expert", f(s["real"]["gap_s"], 1), ci(s["real"]["ci"], 1)],
            ["Placebo: expert vs nearest other expert", f(s["placebo"]["gap_s"], 1), ci(s["placebo"]["ci"], 1)],
            ["Null: labels shuffled across people", f(s["null"]["gap_s"], 1), ci(s["null"]["ci"], 1)]]
    return table(["Comparison (synthetic)", "Gap (s per case)", "95% interval"], rows) + f"\n\nPermutation p-value for the real gap against the null: {s['null'].get('p_value')}."


def _hazard(s: dict[str, Any]) -> str:
    m, b = s["model"], s["baselines"]
    rows = [["Stuck hazard", f(m["log_loss"], 3), ci(m.get("ci_log_loss"), 3), f(m["brier"], 3), f(m["ece"], 3)]]
    for k, lab in (("time_since_progress", "Time since progress"), ("base_rate", "Base rate")):
        if k in b:
            rows.append([lab, f(b[k]["log_loss"], 3), ci(b[k].get("ci_log_loss"), 3), f(b[k]["brier"], 3), f(b[k]["ece"], 3)])
    txt = table(["Model (synthetic)", "Log loss", "95% interval", "Brier", "ECE"], rows)
    txt += (f"\n\nFalse alarms: {f(s['false_alarms_per_hour'], 2)} an hour {ci(s.get('false_alarms_per_hour_ci'))} against a budget of "
            f"{s.get('budget_false_alarms_per_hour')}; share of stuck events flagged {pc(s.get('detection_rate'))} {ci(s.get('detection_rate_ci'), pct=True)}.")
    if s.get("secondary"):
        sec = s["secondary"]
        txt += (f"\n\nSecondary data (scripted apprentices, n = {sec['meta']['n']} {sec['meta']['n_unit']}; follows a fixed script, so not the headline): "
                f"log loss {f(sec['model']['log_loss'], 3)}, false alarms {f(sec.get('false_alarms_per_hour'), 2)} an hour.")
    return txt


def _ope(s: dict[str, Any]) -> str:
    tv = s["true_value"]
    rows = []
    for e in s["estimators"]:
        covers = e["ci"][0] is not None and e["ci"][0] <= tv <= e["ci"][1]
        rows.append([e.get("label", e["name"]), f(e["value"], 3), ci(e["ci"], 3), "yes" if covers else "no"])
    txt = table(["Estimator (synthetic)", "Value", "95% interval", "Interval holds the true value"], rows) + f"\n\nTrue value (known, the simulator is ours): {f(tv, 3)}."
    rep = ((s.get("replications") or {}).get("by_target") or {}).get(s.get("headline_target"))
    if rep:
        names = {"naive_on_policy": "Naive on-policy average", "ips": "IPS", "snips": "Self-normalised IPS", "dr": "Doubly robust", "dm": "Direct method", "naive_matched": "Naive, matched rows only"}
        rr = [[names.get(k, k), f(v.get("mean_error"), 3, True), f(v.get("rmse"), 3), pc(v.get("ci_coverage"))] for k, v in rep.items()]
        txt += (f"\n\nOver {s['replications'].get('n_replications')} independent replications (synthetic, {s['replications'].get('n_logged_each')} decisions each):\n\n"
                + table(["Estimator", "Mean error", "RMSE", "Interval covers the truth"], rr))
    return txt


def _routing(s: dict[str, Any]) -> str:
    curve = s.get("curve") or []
    pts = curve[:: max(1, len(curve) // 8)] if curve else []
    txt = (f"Target error rate alpha = {s['alpha']}; chosen coverage {pc(s.get('chosen_coverage'), 1)}; held-out error {pc(s['held_out_error'], 1)} {ci(s['held_out_ci'], pct=True)}; "
           f"bound held: **{s['bound_held']}**; expert time {f(s['expert_minutes_per_case'], 1)} min per case (review time per case is an assumption).")
    if pts:
        txt += "\n\n" + table(["Coverage (synthetic)", "Error rate", "95% interval"], [[pc(p["coverage"], 1), pc(p["risk"], 1), ci(p["ci"], pct=True)] for p in pts])
    return txt


def _ski(s: dict[str, Any]) -> str:
    rows = [[r.get("label", r["rule"]), f(r["regret"], 3), ci(r["ci"], 3)] for r in s["rows"]]
    return table(["Rule (simulated)", "Regret (hindsight = 1.0)", "95% interval"], rows)


def _presence(s: dict[str, Any]) -> str:
    b = s["baselines"]
    rows = [["Start-or-wait rule", pc(s["interruption_rate"], 1), pc(s["idle_time_used"], 1)],
            ["Fixed overnight window", pc(b["fixed_overnight"]["interruption_rate"], 1), pc(b["fixed_overnight"]["idle_time_used"], 1)],
            ["Run whenever idle 5 min", pc(b["idle_5min"]["interruption_rate"], 1), pc(b["idle_5min"]["idle_time_used"], 1)]]
    txt = (f"Window-forecast Brier score {f(s['brier'], 3)} (mean over personas); interruption cap {pc(s['cap'])}. "
           "The pooled numbers are means of four personas; the per-persona rows carry the intervals.\n\n"
           + table(["Policy (synthetic, mean over personas)", "Interruption rate", "Idle time used"], rows))
    per = s.get("per_persona") or {}
    if per:
        pr = [[n, f"{f(p.get('window_brier'), 3)} {ci(p.get('window_brier_ci'), 3)}", f"{pc(p.get('interruption_rate'), 1)} {ci(p.get('interruption_ci'), pct=True)}",
               f"{pc(p.get('idle_time_used'), 1)} {ci(p.get('idle_time_used_ci'), pct=True)}"] for n, p in per.items()]
        txt += "\n\n" + table(["Persona (synthetic)", "Window Brier [95%]", "Interruption rate, start-or-wait rule [95%]", "Idle time used [95%]"], pr)
    return txt


def _routines(s: dict[str, Any]) -> str:
    def cell(d: dict[str, Any] | None, count_key: str) -> str:
        d = d or {}
        if d.get("precision") is None:
            return "n/a"
        noun = "clusters" if count_key == "clusters" else "proposals"
        return f"{d.get('correct')} of {d.get(count_key)} {noun} are planted routines: {pc(d['precision'])} {ci(d.get('precision_ci'), pct=True)}"

    rows = [[r["persona"], str(r["planted"]), str(r["found"]), cell(r.get("raw_finder"), "clusters"), cell(r.get("after_value_gate"), "proposals"), pc(r["recall"])]
            for r in s["rows"]]
    o = s["overall"]
    rows.append(["**All personas**", "", "", f"**{cell(o.get('raw_finder'), 'clusters')}**", f"**{cell(o.get('after_value_gate'), 'proposals')}**", f"**{pc(o['recall'])}** {ci(o.get('recall_ci'), pct=True)}"])
    return (table(["Persona (synthetic)", "Planted routines", "Planted routines found", "Raw finder: precision over all clusters returned [95%]", "After value gate: precision over proposals shown [95%]", "Recall"], rows)
            + "\n\nThe headline precision is the proposals' precision after the value gate. The raw finder alone returns many clusters of one-off work; "
              "read the left precision column as the finder's accuracy and the right one as what the worker is shown.")


def _agent_runs(s: dict[str, Any]) -> str:
    def row(label: str, b: dict[str, Any]) -> list[str]:
        th = ", ".join(f"tier {k}: {v}" for k, v in (b.get("tier_households") or {}).items()) or "n/a"
        return [label, str(b["n"]), f"{b['pass']} of {b['n']}", ci(b["wilson"], 2), f(b.get("mean_s"), 1), th, str(b.get("false_claims", "n/a"))]

    rows = [row("Clean path (compiled)", s["clean"])]
    if s.get("robust"):
        rows.append(row("Failure injection", s["robust"]))
    if s.get("live"):
        rows.append(row("Real model, small n", s["live"]))
    txt = table(["Run (synthetic sandbox)", "Households", "Passed", "95% interval", "Mean seconds", "Households that used each tier", "False claims"], rows)
    rb = s.get("robust") or {}
    if rb.get("injected"):
        txt += "\n\nWhat was injected, and what happened:\n\n" + table(["Injection", "Households", "Passed", "Needed tier 2"], [[x["injection"], str(x["n"]), str(x["pass"]), str(x.get("used_tier2", ""))] for x in rb["injected"]])
    elif rb.get("injected_note"):
        txt += f"\n\nInjection plan not shown: {rb['injected_note']}."
    d = s.get("discrepancies_flagged") or {}
    txt += f"\n\nPlanted calculator discrepancies flagged: {d.get('n')} of {d.get('of')} households. False success claims across all runs: {s.get('false_claims')}."
    if s.get("live"):
        txt += f"\n\nReal-model block (n = {s['live']['n']}, estimated cost {s['live'].get('cost_usd_est')} USD): {s['live'].get('note')}"
    else:
        txt += "\n\nNo real-model run is in this report."
    return txt + ("\n\nCaveat: the clean path is the compiled path on the sandbox it was written against, so a full pass is expected. "
                  "The discriminating evidence is the failure-injection rows.")


def _claims(s: dict[str, Any]) -> str:
    m = s.get("model") or {}
    txt = f"Brier {f(s['brier'], 3)} against {f(((s.get('baselines') or {}).get('base_rate') or {}).get('brier'), 3)} for the base rate; base failure rate {pc(s['base_rate'], 1)}."
    if m.get("ci_brier"):
        txt += f" Brier interval {ci(m['ci_brier'], 3)}."
    if s.get("operating_point"):
        op = s["operating_point"]
        txt += (f" Reviewing the top {pc(op.get('review_share'))} by predicted risk catches {pc(op.get('recall'))} of false claims "
                f"(precision {pc(op.get('precision'))}).")
    return txt


def _redteam(s: dict[str, Any]) -> str:
    rows = [[r.get("label", r["ablation"]), f"{pc(r['attack_success'], 1)} {ci(r['attack_ci'], pct=True)}", f"{pc(r['task_success'], 1)} {ci(r['task_ci'], pct=True)}", str(r.get("n", ""))] for r in s["rows"]]
    return (table(["Condition (synthetic)", "Attack succeeds", "Task still succeeds", "n"], rows)
            + f"\n\nFalse-pause rate on clean pages: {pc(s['false_pause_rate'], 1)} {ci(s['false_pause_ci'], pct=True)}.")


def _study(s: dict[str, Any]) -> str:
    rows = [[r["participant"], f(r["unassisted_before_s"], 0), f(r["unassisted_after_s"], 0), f(r["unassisted_after_s"] - r["unassisted_before_s"], 0, True)] for r in s["rows"]]
    return table(["Participant (real)", "Unassisted before (s)", "Unassisted after (s)", "Change (s)"], rows) + f"\n\nMean change {f(s['mean_change_s'], 1, True)} s, 95% interval {ci(s['mean_change_ci'], 1)}."



def _gate(s: dict[str, Any]) -> str:
    rows = []
    for k, lab in (("bare_threshold", "Bare threshold on every 30 s bin"), ("dignity_gate", "Dignity gate (2 signals in a row, then a cooldown)")):
        v = s.get(k) or {}
        rows.append([lab, f(v.get("false_alarms_per_hour"), 2), pc(v.get("detection_rate")), str(v.get("nudges_total", "")), f(v.get("median_latency_s"), 0)])
    return (table(["Rule (synthetic)", "False nudges per hour", "Stuck events reached", "Nudges", "Median latency (s)"], rows)
            + f"\n\nFalse nudges per hour fall by {pc(s.get('false_nudges_per_hour_reduction'))}, at the price of reaching far fewer stuck events.")


def _skills(s: dict[str, Any]) -> str:
    rows = [[p.get("persona", k), str(p.get("n_tasks")), f(p.get("spearman_mastery_vs_planted_skill"), 2), str(p.get("final_level"))] for k, p in (s.get("per_persona") or {}).items()]
    txt = table(["Persona (synthetic)", "Tasks", "Spearman, mastery vs planted skill", "Final level"], rows)
    txt += f"\n\nMean Spearman across personas: {f(s.get('mean_spearman_mastery_vs_planted_skill'), 2)}. Mastery saturates on these high-volume personas; see the register."
    return txt


def _forecast(s: dict[str, Any]) -> str:
    rows = [[r["persona"], r["routine"], f(r["predicted"], 1), f"[{f(r['lo'], 0)}, {f(r['hi'], 0)}]", f(r["actual"], 0), "yes" if r.get("inside") else "no"] for r in s.get("rows", [])]
    m = s.get("metrics") or {}
    return table(["Persona (synthetic)", "Routine", "Predicted runs", "95% interval", "Actual", "Inside"], rows) + f"\n\nInterval coverage: {pc(m.get('interval_coverage'))} {ci(m.get('interval_coverage_ci'), pct=True)}."


def _pooling(s: dict[str, Any]) -> str:
    ds = (s.get("datasets") or {}).get("stuck_rate_personas") or {}
    rows = [[str(r["n_episodes"]), f(r["no_pooling"], 3), f(r["partial_pooling"], 3), ci(r.get("ci_partial_pooling"), 3), f(r["complete_pooling"], 3), str(r.get("best", ""))] for r in ds.get("rows", [])]
    txt = table(["Own episodes seen (synthetic)", "No pooling", "Partial pooling", "95% interval", "Complete pooling", "Best"], rows) if rows else ""
    return (txt + f"\n\n{s.get('note') or ''}").strip()


RENDER = {"deficit_recovery": _deficit, "null_placebo": _null, "hazard": _hazard, "ope": _ope, "routing": _routing, "ski_rental": _ski,
          "presence": _presence, "routines": _routines, "policy_gate": _gate, "skills": _skills, "forecast": _forecast, "pooling": _pooling, "agent_claims": _claims, "agent_runs": _agent_runs, "redteam": _redteam, "study": _study}


def _generic(s: dict[str, Any]) -> str:
    scal = [(k, v) for k, v in s.items() if k not in ("meta", "limitations", "caveats") and isinstance(v, (int, float, str, bool)) and v is not None]
    return "\n".join(f"- {k}: {f(v, 3) if isinstance(v, float) else v}" for k, v in scal[:14]) or "(see report.json)"


def render(report: dict[str, Any]) -> str:
    out = ["# Understudy evaluation report", ""]
    rev = f" · git {report['git_rev']}" if report.get("git_rev") else ""
    out.append(f"Generated {report['generated_at']} · mock mode: {'yes' if report.get('mock') else 'no'}{rev} · fast run: {'yes' if (report.get('run') or {}).get('fast') else 'no'}")
    out += ["", "Written by `python -m understudy_engine.eval` from the owning tracks' code; no number here is typed in by hand. "
            "Synthetic results are labelled synthetic. A section without numbers says why instead of showing a made-up value.", ""]
    secs = report["sections"]
    for name, title in TITLES.items():
        if name not in secs:
            continue
        s = secs[name]
        out += [f"## {title}", "", basis(s["meta"]), ""]
        if s["meta"].get("note"):
            out += [s["meta"]["note"], ""]
        if "status" in s and name != "study":
            out += [f"**{s['status'].upper().replace('_', ' ')}**: {s['reason']}", ""]
            continue
        if name == "study" and "status" in s:
            out += [f"**NOT RUN**: {s['reason']}. The page says so; no numbers are shown.", ""]
            continue
        out += [RENDER.get(name, _generic)(s), ""]
        if s.get("caveats"):
            out += ["Caveats:", ""] + [f"- {c}" for c in s["caveats"]] + [""]
    lim = secs.get("limitations") or []
    out += ["## Limitations register", "", f"{len(lim)} entries, most serious first. Kept in the product on purpose.", ""]
    out += [table(["Id", "Severity", "What it means", "Source"], [[e["id"], e["severity"], e["text"].replace("|", "/"), e["source"]] for e in lim]), ""]
    return "\n".join(out)
