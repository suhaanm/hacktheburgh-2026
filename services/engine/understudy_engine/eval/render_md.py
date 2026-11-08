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
    "redteam_live": "Red team with a real model (secondary, cached)",
    "study": "Live study (n = 4)",
    "privacy": "Privacy layer (canary leaks, offline)",
    "git": "Git habits (programmer role)",
    "proactive": "Proactive cards",
    "calendar": "Calendar layer",
    "localmodel": "Local model digests",
    "runtime": "Agent runtime",
    "mlv2": "Models v2",
    "evidence": "Evidence quality",
    "cue": "Cue analysis",
    "realism": "Persona realism",
    "attention": "Attention routing",
    "insights": "Insights for workers and admins",
    "hitlist": "Hit list",
    "modelbench": "Model benchmark",
    "study_roles": "Study across roles",
    "agentic": "Agentic evaluation",
    "study_sim": "Language-model participants, not people",
    "study_power": "Study power: what the design could detect",
}


def f(x: Any, nd: int = 2, signed: bool = False) -> str:
    if x is None or isinstance(x, bool):
        return "n/a" if x is None else str(x)
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"
    return str(x)


def usd(x: Any) -> str:
    """A cost, or plainly that it was not measured (never the word None)."""
    return "not measured" if x is None else f"about {x} USD"


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


#: What a section was measured on, in plain words (owner decision D57, 8 Nov 2026: no "synthetic" tag anywhere a person reads). The data enum itself
#: ("synthetic", "real", "mixed", "unknown") is unchanged in report.json; only the words the markdown prints are these.
ORIGIN_WORDS = {"synthetic": "generators we wrote", "real": "real people", "mixed": "real and generated", "unknown": "not run"}


def origin_words(origin: Any) -> str:
    return ORIGIN_WORDS.get(str(origin), str(origin))


def basis(meta: dict[str, Any]) -> str:
    lvl = int(round(100 * (meta.get("interval_level") or 0.95)))
    return (f"*measured on: **{origin_words(meta.get('origin'))}** · n = {meta.get('n')} {meta.get('n_unit')} · split: {meta.get('split') or 'n/a'} · "
            f"intervals: {lvl}%*")


def _deficit(s: dict[str, Any]) -> str:
    rows = [[r["label"] if "label" in r else r["deficit"], f(r["injected_price_s"], 1), f(r["recovered_price_s"], 1), ci(r["ci"], 1),
             f(r.get("bias_s"), 1, True), f"{pc(r['precision'])} {ci(r.get('precision_ci'), pct=True)}", f"{pc(r['recall'])} {ci(r.get('recall_ci'), pct=True)}",
             f(r.get("threshold_s"), 1)] for r in s["rows"]]
    o = s["overall"]
    return (table(["Deficit", "Injected price (s)", "Recovered price (s)", "95% interval", "Bias (s)", "Precision", "Recall", "X (s)"], rows)
            + f"\n\nOverall (all case-deficit pairs): precision {pc(o['precision'])} {ci(o.get('precision_ci'), pct=True)}, recall {pc(o['recall'])} {ci(o.get('recall_ci'), pct=True)}."
            + f"\n\nDetection rule: {s.get('detection_rule')}.")


def _null(s: dict[str, Any]) -> str:
    rows = [["Real: novice vs nearest expert", f(s["real"]["gap_s"], 1), ci(s["real"]["ci"], 1)],
            ["Placebo: expert vs nearest other expert", f(s["placebo"]["gap_s"], 1), ci(s["placebo"]["ci"], 1)],
            ["Null: labels shuffled across people", f(s["null"]["gap_s"], 1), ci(s["null"]["ci"], 1)]]
    return table(["Comparison", "Gap (s per case)", "95% interval"], rows) + f"\n\nPermutation p-value for the real gap against the null: {s['null'].get('p_value')}."


def _hazard(s: dict[str, Any]) -> str:
    m, b = s["model"], s["baselines"]
    rows = [["Stuck hazard", f(m["log_loss"], 3), ci(m.get("ci_log_loss"), 3), f(m["brier"], 3), f(m["ece"], 3)]]
    for k, lab in (("time_since_progress", "Time since progress"), ("base_rate", "Base rate")):
        if k in b:
            rows.append([lab, f(b[k]["log_loss"], 3), ci(b[k].get("ci_log_loss"), 3), f(b[k]["brier"], 3), f(b[k]["ece"], 3)])
    txt = table(["Model", "Log loss", "95% interval", "Brier", "ECE"], rows)
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
    txt = table(["Estimator", "Value", "95% interval", "Interval holds the true value"], rows) + f"\n\nTrue value (known, the simulator is ours): {f(tv, 3)}."
    rep = ((s.get("replications") or {}).get("by_target") or {}).get(s.get("headline_target"))
    if rep:
        names = {"naive_on_policy": "Naive on-policy average", "ips": "IPS", "snips": "Self-normalised IPS", "dr": "Doubly robust", "dm": "Direct method", "naive_matched": "Naive, matched rows only"}
        rr = [[names.get(k, k), f(v.get("mean_error"), 3, True), f(v.get("rmse"), 3), pc(v.get("ci_coverage"))] for k, v in rep.items()]
        txt += (f"\n\nOver {s['replications'].get('n_replications')} independent replications ({s['replications'].get('n_logged_each')} decisions each):\n\n"
                + table(["Estimator", "Mean error", "RMSE", "Interval covers the truth"], rr))
    return txt


def _routing(s: dict[str, Any]) -> str:
    curve = s.get("curve") or []
    pts = curve[:: max(1, len(curve) // 8)] if curve else []
    txt = (f"Target error rate alpha = {s['alpha']}; chosen coverage {pc(s.get('chosen_coverage'), 1)}; held-out error {pc(s['held_out_error'], 1)} {ci(s['held_out_ci'], pct=True)}; "
           f"bound held: **{s['bound_held']}**; expert time {f(s['expert_minutes_per_case'], 1)} min per case (review time per case is an assumption).")
    if pts:
        txt += "\n\n" + table(["Coverage", "Error rate", "95% interval"], [[pc(p["coverage"], 1), pc(p["risk"], 1), ci(p["ci"], pct=True)] for p in pts])
    return txt


def _ski(s: dict[str, Any]) -> str:
    rows = [[r.get("label", r["rule"]), f(r["regret"], 3), ci(r["ci"], 3)] for r in s["rows"]]
    return table(["Rule", "Regret (hindsight = 1.0)", "95% interval"], rows)


def _presence(s: dict[str, Any]) -> str:
    b = s["baselines"]
    rows = [["Start-or-wait rule", pc(s["interruption_rate"], 1), pc(s["idle_time_used"], 1)],
            ["Fixed overnight window", pc(b["fixed_overnight"]["interruption_rate"], 1), pc(b["fixed_overnight"]["idle_time_used"], 1)],
            ["Run whenever idle 5 min", pc(b["idle_5min"]["interruption_rate"], 1), pc(b["idle_5min"]["idle_time_used"], 1)]]
    txt = (f"Window-forecast Brier score {f(s['brier'], 3)} (mean over personas); interruption cap {pc(s['cap'])}. "
           "The pooled numbers are means of four personas; the per-persona rows carry the intervals.\n\n"
           + table(["Policy (mean over personas)", "Interruption rate", "Idle time used"], rows))
    per = s.get("per_persona") or {}
    if per:
        pr = [[n, f"{f(p.get('window_brier'), 3)} {ci(p.get('window_brier_ci'), 3)}", f"{pc(p.get('interruption_rate'), 1)} {ci(p.get('interruption_ci'), pct=True)}",
               f"{pc(p.get('idle_time_used'), 1)} {ci(p.get('idle_time_used_ci'), pct=True)}"] for n, p in per.items()]
        txt += "\n\n" + table(["Persona", "Window Brier [95%]", "Interruption rate, start-or-wait rule [95%]", "Idle time used [95%]"], pr)
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
    return (table(["Persona", "Planted routines", "Planted routines found", "Raw finder: precision over all clusters returned [95%]", "After value gate: precision over proposals shown [95%]", "Recall"], rows)
            + "\n\nThe headline precision is the proposals' precision after the value gate. The raw finder alone returns many clusters of one-off work; "
              "read the left precision column as the finder's accuracy and the right one as what the worker is shown.")


def _agent_runs(s: dict[str, Any]) -> str:
    def row(label: str, b: dict[str, Any]) -> list[str]:
        th = ", ".join(f"tier {k}: {v}" for k, v in (b.get("tier_households") or {}).items()) or "n/a"
        return [label, str(b["n"]), f"{b['pass']} of {b['n']}", ci(b["wilson"], 2), f(b.get("mean_s"), 1), th, str(b.get("false_claims", "n/a"))]

    rows = [row("Clean path (compiled)", s["clean"])]
    if s.get("robust"):
        rows.append(row("Failure injection", s["robust"]))
    txt = table(["Run (mock model, sandbox)", "Households", "Passed", "95% interval", "Mean seconds", "Households that used each tier", "False claims"], rows)
    rb = s.get("robust") or {}
    if rb.get("injected"):
        txt += "\n\nWhat was injected, and what happened:\n\n" + table(["Injection", "Households", "Passed", "Needed tier 2"], [[x["injection"], str(x["n"]), str(x["pass"]), str(x.get("used_tier2", ""))] for x in rb["injected"]])
    elif rb.get("injected_note"):
        txt += f"\n\nInjection plan not shown: {rb['injected_note']}."
    d = s.get("discrepancies_flagged") or {}
    txt += f"\n\nPlanted calculator discrepancies flagged: {d.get('n')} of {d.get('of')} households."
    live = s.get("live")
    if live:
        txt += "\n\n" + _agent_live(live)
    else:
        txt += "\n\nNo real-model run is in this report."
    return txt + ("\n\nCaveat: the clean path is the compiled path on the sandbox it was written against, so a full pass is expected. "
                  "The discriminating evidence is the failure-injection rows and, with a real model, the glitch and injected conditions.")


def _agent_live(live: dict[str, Any]) -> str:
    cond = live.get("conditions") or {}
    labels = {"clean": "Clean", "layout_v2": "Layout change", "glitch": "One-off error page (glitch)", "injected": "Injected page (prompt injection)"}

    def row(label: str, c: dict[str, Any]) -> list[str]:
        return [label, str(c["n"]), f"{c['pass']} of {c['n']} {ci(c['wilson'], 2)}", f"{c.get('claimed_success')}", f"{c.get('false_claims')}", f"{c.get('paused')}",
                f"{c.get('attack_success')} of {c.get('injected_runs')}" if c.get("injected_runs") else "n/a", f(c.get("mean_steps"), 1), f(c.get("mean_latency_s"), 1),
                ", ".join(str(t) for t in c.get("tiers") or []) or "none"]

    body = [row(labels.get(k, k), c) for k, c in cond.items()]
    fix = live.get("glitch_fix")
    if fix:
        body.append(row("After the fix, glitch only: IN-SAMPLE, made after seeing the glitch result", fix))
    head = ["Condition (REAL MODEL, small n)", "Households", "Passed the code check [95%]", "Claimed finished", "False claims", "Paused by the detector", "Attacks that succeeded", "Mean steps", "Mean seconds", "Tiers used"]
    hc = live.get("condition") or live.get("headline_condition")
    txt = (f"**Real model ({live.get('households')} households per condition, {live.get('runs_total')} runs, tier 1 disabled).** "
           f"Headline condition: **{labels.get(hc, hc)}**: {live.get('pass')} of {live.get('n')} passed the code check, {live.get('false_claims')} false claims "
           f"(these two numbers are for that condition alone; every other condition is in its own row below). {live.get('note')}\n\n" + table(head, body))
    gl = cond.get("glitch") or {}
    if gl:
        txt += (f"\n\nOn the one-off error page the model said it was finished in {gl.get('claimed_success')} of {gl.get('n')} runs and {gl.get('false_claims')} of those claims were false; "
                "the code check caught every one. Injected pages were paused by the detector before the planner acted, so task success there is 0 by design.")
    if fix:
        b = fix.get("same_condition_before") or {}
        txt += (f"\n\nThe fix ({fix.get('description')}) was re-run on the glitch condition: {fix.get('pass')} of {fix.get('n')} succeeded with {fix.get('false_claims')} false claims "
                f"(before: {b.get('pass')} of {b.get('n')}). **This is in-sample** and only {fix.get('n')} runs"
                + (f" ({fix.get('dropped_after_budget_stop')} later rows dropped when the run budget stopped)" if fix.get("dropped_after_budget_stop") else "") + ".")
    t3 = live.get("tier3") or {}
    txt += (f"\n\nTier 3 (computer use) is not demonstrated on the benefits task: {f(t3.get('runs'), 0)} runs with a stand-in actuator made {f(t3.get('pointer_actions'), 0)} pointer actions "
            f"and landed on an interactive element {f(t3.get('landed_on_interactive'), 0)} times.")
    c = live.get("cost") or {}
    pr = c.get("price_assumption_usd_per_million") or {}
    txt += (f"\n\nCost: an estimate at placeholder rates ({pr.get('input')} and {pr.get('output')} USD per million tokens in and out), {usd(c.get('cumulative_usd_at_assumed_rates'))} for these rows"
            + (f" (at smaller-model rates: {', '.join(f'{v} USD' for k, v in (c.get('usd_estimates') or {}).items() if 'placeholder' not in k and 'assumed' not in k)})" if len(c.get("usd_estimates") or {}) > 1 else "")
            + f"; {c.get('live_calls_in_rows')} live calls and {c.get('cache_hits_in_rows')} cache hits across the runs.")
    return txt


def _claims(s: dict[str, Any]) -> str:
    m = s.get("model") or {}
    txt = f"Brier {f(s['brier'], 3)} against {f(((s.get('baselines') or {}).get('base_rate') or {}).get('brier'), 3)} for the base rate; base failure rate {pc(s['base_rate'], 1)}."
    if m.get("ci_brier"):
        txt += f" Brier interval {ci(m['ci_brier'], 3)}."
    if s.get("operating_point"):
        op = s["operating_point"]
        txt += (f" Reviewing the top {pc(op.get('review_share'))} by predicted risk catches {pc(op.get('recall'))} of false claims "
                f"(precision {pc(op.get('precision'))}).")
    lv = s.get("live")
    if isinstance(lv, dict):
        lm = lv.get("meta") or {}
        txt += (f"\n\n**{lv.get('label', 'real model')}**: {lm.get('n', lv.get('n'))} claimed successes from {lv.get('n_groups')} households ({lm.get('split') or lv.get('split')}). "
                f"Brier {f(lv.get('brier'), 3)} against {f(lv.get('base_rate'), 3)} for the base rate (the share of claims that were false). "
                "The false claims are one family of failure (a finish claim on an error page), so a high score here does not show that claim risk can be predicted in general.")
    return txt


def _redteam(s: dict[str, Any]) -> str:
    rows = [[r.get("label", r["ablation"]), f"{pc(r['attack_success'], 1)} {ci(r['attack_ci'], pct=True)}", f"{pc(r['task_success'], 1)} {ci(r['task_ci'], pct=True)}", str(r.get("n", ""))] for r in s["rows"]]
    return (table(["Condition", "Attack succeeds", "Task still succeeds", "n"], rows)
            + f"\n\nFalse-pause rate on clean pages: {pc(s['false_pause_rate'], 1)} {ci(s['false_pause_ci'], pct=True)}.")


def _study(s: dict[str, Any]) -> str:
    rows = [[r["participant"], f(r["unassisted_before_s"], 0), f(r["unassisted_after_s"], 0), f(r["unassisted_after_s"] - r["unassisted_before_s"], 0, True)] for r in s["rows"]]
    return table(["Participant (real)", "Unassisted before (s)", "Unassisted after (s)", "Change (s)"], rows) + f"\n\nMean change {f(s['mean_change_s'], 1, True)} s, 95% interval {ci(s['mean_change_ci'], 1)}."



def _gate(s: dict[str, Any]) -> str:
    rows = []
    for k, lab in (("bare_threshold", "Bare threshold on every 30 s bin"), ("dignity_gate", "Dignity gate (2 signals in a row, then a cooldown)")):
        v = s.get(k) or {}
        rows.append([lab, f(v.get("false_alarms_per_hour"), 2), pc(v.get("detection_rate")), str(v.get("nudges_total", "")), f(v.get("median_latency_s"), 0)])
    return (table(["Rule", "False nudges per hour", "Stuck events reached", "Nudges", "Median latency (s)"], rows)
            + f"\n\nFalse nudges per hour fall by {pc(s.get('false_nudges_per_hour_reduction'))}, at the price of reaching far fewer stuck events.")


def _skills(s: dict[str, Any]) -> str:
    rows = [[p.get("persona", k), str(p.get("n_tasks")), f(p.get("spearman_mastery_vs_planted_skill"), 2), str(p.get("final_level"))] for k, p in (s.get("per_persona") or {}).items()]
    txt = table(["Persona", "Tasks", "Spearman, mastery vs planted skill", "Final level"], rows)
    txt += f"\n\nMean Spearman across personas: {f(s.get('mean_spearman_mastery_vs_planted_skill'), 2)}. Mastery saturates on these high-volume personas; see the register."
    return txt


def _forecast(s: dict[str, Any]) -> str:
    rows = [[r["persona"], r["routine"], f(r["predicted"], 1), f"[{f(r['lo'], 0)}, {f(r['hi'], 0)}]", f(r["actual"], 0), "yes" if r.get("inside") else "no"] for r in s.get("rows", [])]
    m = s.get("metrics") or {}
    return table(["Persona", "Routine", "Predicted runs", "95% interval", "Actual", "Inside"], rows) + f"\n\nInterval coverage: {pc(m.get('interval_coverage'))} {ci(m.get('interval_coverage_ci'), pct=True)}."


def _pooling(s: dict[str, Any]) -> str:
    ds = (s.get("datasets") or {}).get("stuck_rate_personas") or {}
    rows = [[str(r["n_episodes"]), f(r["no_pooling"], 3), f(r["partial_pooling"], 3), ci(r.get("ci_partial_pooling"), 3), f(r["complete_pooling"], 3), str(r.get("best", ""))] for r in ds.get("rows", [])]
    txt = table(["Own episodes seen", "No pooling", "Partial pooling", "95% interval", "Complete pooling", "Best"], rows) if rows else ""
    return (txt + f"\n\n{s.get('note') or ''}").strip()


SIM = "language-model participants, not people"


def _cell(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) or x is None for x in v):
        return ci(v, 3)
    if isinstance(v, dict) and "est" in v and "ci" in v and not isinstance(v["est"], (dict, list)):
        return f"{f(v['est'], 3)} {ci(v['ci'], 3)}"
    if isinstance(v, dict) and "value" in v and "interval" in v and not isinstance(v["value"], (dict, list)):
        return f"{f(v['value'], 3)} {ci(v['interval'], 3)}"
    if isinstance(v, (dict, list)):
        return "(see report.json)"
    return "n/a" if v is None else str(v).replace("|", "/")


def _generic_tables(s: dict[str, Any], skip: tuple[str, ...], caption: str, max_rows: int = 200) -> str:
    """Scalars as bullets, list-of-dicts and dict-of-dicts as tables, every block headed by ``caption`` (the shapes belong to the owner)."""
    out: list[str] = []
    scal = [(k, v) for k, v in s.items() if k not in skip and not isinstance(v, (dict, list)) and v is not None]
    if scal:
        out.append(f"Figures ({caption}):\n" + "\n".join(f"- {k}: {_cell(v)}" for k, v in scal))
    for k, v in s.items():
        if k in skip or v is None:
            continue
        rows = None
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            rows = v
        elif isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            rows = [{"key": kk, **x} for kk, x in v.items()]
        if rows:
            cols = list(dict.fromkeys(c for x in rows for c in x))[:9]
            more = f"\n\n({len(rows) - max_rows} more rows in report.json)" if len(rows) > max_rows else ""
            out.append(f"{k} ({caption}):\n\n" + table(cols, [[_cell(x.get(c)) for c in cols] for x in rows[:max_rows]]) + more)
        elif isinstance(v, dict):
            inner = ", ".join(f"{kk}: {_cell(vv)}" for kk, vv in list(v.items())[:12])
            out.append(f"- {k} ({caption}): {inner}")
    return "\n\n".join(out) or "(see report.json)"


def _study_sim(s: dict[str, Any]) -> str:
    cap = SIM
    head = (f"**{SIM[0].upper() + SIM[1:]}.** This is not the live study and is never combined with it. "
            f"The live study (n = 4 people) is reported above and only there.")
    body = _generic_tables(s, ("meta", "label", "owner_label", "limitations", "caveats"), cap)
    return head + "\n\n" + body


def _study_power(s: dict[str, Any]) -> str:
    hp = s.get("headline_power") or {}
    rows = s.get("rows") or []
    out = ["**What the design could detect under our assumptions. A property of the design, not a result about people and not evidence that an effect exists.**"]
    lines = []
    for n in ("4", "16"):
        h = hp.get(n)
        if not h:
            continue
        mp = h.get("min_sign_flip_p")
        lines.append(f"- n = {n}: the smallest attainable two-sided sign-flip p is {mp:.3g}" + (", so p < 0.05 is impossible." if h.get("p05_impossible") else ".")
                     if mp is not None else f"- n = {n}")
    out.append("\n".join(lines))
    hdr = ["Effect (generated design)", "True effect (points)", "n = 4: chance the 95% t interval excludes 0", "n = 16: chance the 95% t interval excludes 0"]
    h4, h16 = hp.get("4") or {}, hp.get("16") or {}
    if h4 or h16:
        tab = [[e, f(((h4 or h16).get("true_effect_pp") or {}).get(e), 1), pc((h4.get("power_ci") or {}).get(e), 1), pc((h16.get("power_ci") or {}).get(e), 1)]
               for e in ("none", "small", "medium", "large")]
        out.append("No spill-over, no order effect (the 'none' row is the false-positive rate):\n\n" + table(hdr, tab))
    sp4, sp16 = (h4.get("spillover") or {}), (h16.get("spillover") or {})
    spill = ("**Spill-over of the coached gain onto the other skill is not protected by the design.** It dilutes the contrast and the design cannot cancel it."
             " Medium effect with full spill-over: ")
    parts = []
    for n, sp in (("4", sp4), ("16", sp16)):
        if sp:
            parts.append(f"at n = {n} the chance the interval excludes 0 falls from {pc(sp.get('power_ci_without'), 1)} to {pc(sp.get('power_ci_with'), 1)} and the estimate is off by {f(sp.get('bias_pp_with'), 1, True)} points")
    out.append(spill + ("; ".join(parts) + "." if parts else "(see the grid in report.json)."))
    sel = [x for x in rows if x.get("n") in (4, 16) and x.get("effect_label") == "medium"]
    if sel:
        cols = ["n", "spill-over", "order effect", "power: interval excludes 0", "power: p < 0.05", "bias (points)", "interval covers the truth"]
        out.append("Medium effect under each nuisance setting (generated design):\n\n" + table(cols, [[str(x["n"]), f(x["carryover"], 1), f(x["order_effect"], 1), pc(x["power_ci"], 1), pc(x["power_p05"], 1), f(x.get("bias_pp"), 1, True), pc(x.get("coverage"), 1)] for x in sel]))
    nd = s.get("needed_difference_n4") or {}
    if nd.get("reading"):
        out.append(f"At n = 4: {nd['reading']}")
    return "\n\n".join(out)


def _privacy(s: dict[str, Any]) -> str:
    h = s.get("headline") or {}
    out = [f"**{h.get('leaked')} of {h.get('planted')} planted canary tokens reached the model port** across {h.get('runs')} runs of {h.get('flows')} flows "
           f"({h.get('requests')} requests); one-sided 95% upper bound on the leak rate {pc(h.get('leak_rate_upper_95'), 2)}. Logs, audit and queue files: "
           f"{h.get('artifact_leaked')} leaks in {h.get('artifact_files_scanned')} files. Ledger complete for every flow: {h.get('ledger_complete')}."]
    rows = [[k, str(v.get("flows")), str(v.get("runs")), str(v.get("requests")), f"{v.get('leaked')} of {v.get('planted')}", pc(v.get("leak_rate_upper_95"), 2)] for k, v in (s.get("by_kind") or {}).items()]
    if rows:
        out.append(table(["Flows (generated fixtures)", "Flows", "Runs", "Requests", "Planted tokens leaked", "Upper 95% bound on the leak rate"], rows))
    lay = s.get("layers") or {}
    if lay:
        out.append("Layers: " + "; ".join(f"{k} {v.get('status')}" for k, v in lay.items()) + ". A layer with no registered flow is never counted as passed.")
    nc = s.get("negative_controls") or []
    if nc:
        out.append(f"Negative controls (the instrument can fail): {sum(1 for x in nc if x.get('passed'))} of {len(nc)} behaved as required.")
    bk = s.get("backstop") or {}
    out.append(f"Bucketing: {h.get('bucketing_failures')} failures over {h.get('bucketing_cases')} cases. Backstop: {h.get('backstop_must_catch')} must-catch shapes caught, "
               f"{h.get('backstop_false_positives')} false positives on {bk.get('ordinary_values')} ordinary values. Static guard: {h.get('static_guard_violations')} violations in {h.get('static_guard_files')} files.")
    out.append("Everything ran offline on generated fixtures with planted tokens; nothing here validates behaviour on real data and the real provider was never called.")
    return "\n\n".join(out)


def _prop(d: dict[str, Any] | None) -> str:
    d = d or {}
    if d.get("value") is None:
        return "n/a"
    return f"{pc(d['value'])} ({d.get('k')} of {d.get('n')}) {ci(d.get('ci'), pct=True)}"


def _git(s: dict[str, Any]) -> str:
    out = [s.get("statement") or ""]
    hr = s.get("habit_recovery") or {}
    ov = hr.get("overall") or {}
    rows = [["All habits", _prop(ov.get("precision")), _prop(ov.get("recall")), _prop(ov.get("specificity"))]]
    rows += [[h, _prop(v.get("precision")), _prop(v.get("recall")), _prop(v.get("specificity"))] for h, v in (hr.get("by_habit") or {}).items()]
    out.append(table(["Planted habit (generated developers)", "Precision [95%]", "Recall [95%]", "Specificity [95%]"], rows))
    pl = (s.get("placebo") or {}).get("false_flags")
    if pl:
        out.append(f"Placebo (each expert against the other experts): false flags {_prop(pl)}.")
    da = s.get("digest_accuracy") or {}
    if da.get("accuracy"):
        out.append(f"Digest rules against the generator's own labels ({da.get('n_commits')} commits): the labels are known by construction, so message-based fields are flattered; "
                   "see the register.")
    ag = s.get("digest_agreement") or {}
    if ag.get("status"):
        out.append(f"Local-model agreement: {ag['status'].replace('_', ' ')}. {ag.get('reason') or ''}")
    g = s.get("genome") or {}
    if g.get("reading"):
        out.append(f"Alignment on commit sessions: {g['reading']}")
    return "\n\n".join(x for x in out if x)


def _calendar(s: dict[str, Any]) -> str:
    out = [s.get("statement") or ""]
    po = (s.get("pattern_recovery") or {}).get("overall") or {}
    so = (s.get("suggestions") or {}).get("overall") or {}
    out.append(table(["What was scored (generated calendars)", "Precision", "Recall"],
                     [["Planted problems found, eight types, micro-average", pc(po.get("precision"), 1), pc(po.get("recall"), 1)],
                      ["Suggestions against the planted cause", pc(so.get("precision"), 1), pc(so.get("recall"), 1)]]))
    sg = s.get("suggestions") or {}
    if sg.get("expert_weeks") is not None:
        out.append(f"Expert weeks with a suggestion: {sg.get('expert_weeks_with_a_suggestion')} of {sg.get('expert_weeks')} (false-alarm rate {pc(sg.get('expert_false_alarm_rate'), 1)}).")
    lc = s.get("leak_canary") or {}
    if lc:
        out.append(f"Leak canary: {lc.get('leaked')} of {lc.get('planted_tokens')} planted tokens leaked across {lc.get('outbound_requests')} outbound requests.")
    return "\n\n".join(x for x in out if x)


def _proactive(s: dict[str, Any]) -> str:
    w = s.get("worth") or {}
    ov = w.get("overall") or {}
    rows = [["Judge (the shipped rules)", f"{ov.get('tp')} of {ov.get('surfaced')} cards were worth it", f"{pc(ov.get('precision'))} {ci(ov.get('precision_ci'), pct=True)}",
             f"{pc(ov.get('recall'))} {ci(ov.get('recall_ci'), pct=True)}"]]
    for k, v in (w.get("baselines") or {}).items():
        got = f"{f(v.get('tp'), 1)} of {f(v.get('surfaced'), 0)}" if v.get("surfaced") is not None else f"{f(v.get('tp'), 1)} worth it (surfaced: n/a)"
        rows.append([k.replace("_", " "), got, f"{pc(v.get('precision'))} {ci(v.get('precision_wilson'), pct=True)}", f"{pc(v.get('recall'))} {ci(v.get('recall_wilson'), pct=True)}"])
    out = [table(["What surfaces cards (generated personas, learners and git learners)", "Cards worth surfacing", "Precision [95%]", "Recall [95%]"], rows)]
    out.append(f"Interval over {ov.get('n_people')} people (bootstrap), which is the honest one; the Wilson interval on pooled counts is too narrow because points are correlated.")
    st = s.get("structure") or {}
    if st:
        out.append(f"Briefings: {st.get('briefings')}, cap {st.get('cap')} cards, cap violations {st.get('cap_violations')}, mean cards {st.get('mean_cards')}; "
                   f"unprompted fires {st.get('unprompted_fires')}, unprompted agent spawns {st.get('unprompted_agent_spawns')}.")
    ac = s.get("acceptance") or {}
    if ac.get("note"):
        out.append(ac["note"])
    return "\n\n".join(out)


def _localmodel(s: dict[str, Any]) -> str:
    mod = s.get("model") or {}
    rows = [[f"{h.get('task')} / {h.get('field')}", str(h.get("n")), f"{pc(h.get('rules_acc'), 1)} {ci(h.get('rules_ci'), pct=True)}",
             f"{pc(h.get('model_acc'), 1)} {ci(h.get('model_ci'), pct=True)}", str(h.get("verdict", "")).replace("_", " "), str(h.get("shipped_source", ""))]
            for h in s.get("headline") or []]
    out = [f"Model arm source: {mod.get('source')}" + (f" ({mod.get('reason')})" if mod.get("reason") else "") + ". Held-out test split; the dev split was used for tuning."]
    if rows:
        out.append(table(["Task / field (generated items)", "Held-out n", "Rules accuracy [95%]", "Local model accuracy [95%]", "Verdict", "Shipped"], rows))
    fnd = [x for x in (s.get("findings") or []) if isinstance(x, str)]
    if fnd:
        out.append("\n".join(f"- {x}" for x in fnd[:6]))
    return "\n\n".join(out)


def _redteam_live(s: dict[str, Any]) -> str:
    rows = s.get("rows") or []

    def cnt(k: Any, n: Any, ci_: Any = None) -> str:
        return f"{k} of {n}" + (f" {ci(ci_, pct=True)}" if ci_ else "")

    body = []
    for r in rows:
        hn = r.get("false_pause_hard_negatives") or {}
        body.append([r.get("label", r["ablation"]), f"{cnt(r.get('attack_successes'), r.get('attack_runs'))}: {pc(r['attack_success'], 1)} {ci(r['attack_ci'], pct=True)}",
                     f"{pc(r['task_success'])} {ci(r['task_ci'], pct=True)}", pc(r.get("paused_rate")),
                     f"{pc(r.get('false_pause_rate'), 1)} over {r.get('n_clean_runs')} clean runs {ci(r.get('false_pause_ci'), pct=True)}",
                     f"{cnt(hn.get('k'), hn.get('n'))} {ci(hn.get('ci'), pct=True)}"])
    txt = (f"**{s.get('label')}.** " + (s.get("reading") or "") + "\n\n"
           + table(["Condition (real model)", "Attack succeeds, runs [95% over cases]", "Task still succeeds [95%]", "Paused", "False pauses on clean pages", "Hard negatives only"], body))
    return txt + f"\n\nSource: {s.get('source')}. Intervals treat the repeats of one case as a single observation; they overlap, so read this as cost and a null, not a guarantee."


def _agentic(s: dict[str, Any]) -> str:
    ho = s.get("heldout") or {}
    out = [f"Origin: {s.get('origin_text')}. Gate stops are shown apart from model failures; each round's result file is checked against its own plan's frozen gate version "
           f"(the newest round's is {s.get('heldout_expected_gate_version') or 'not recorded'}). Held-out rounds measure different configurations and are never pooled."]
    rows, earlier = [], []
    for cond in ("injected", "clean"):
        h = ho.get(cond) or {}
        if h.get("status") != "recorded":
            out.append(f"**{cond.capitalize()} (held-out): NOT RUN YET.** {h.get('reason')}")
            continue
        out.append(f"**{cond.capitalize()} (held-out, newest round).** {h.get('reading')}")
        gs, mf = h.get("gate_stops") or {}, h.get("model_failures") or {}
        pr = h.get("primary") or {}
        rows.append([h.get("round", ""), cond, str(h.get("provider")), str(h.get("seed")), str(h.get("n")),
                     f"{pr['k']} of {pr['n']} (bar {'met' if pr.get('bar_met') else 'not met'})" if pr else f"{(h.get('passed_code_check') or {}).get('k')} of {h.get('n')} passed the code check",
                     f"{(h.get('paused_by_detector') or {}).get('k')} of {h.get('n')}", str(h.get("false_claims")), str(h.get("submissions")),
                     f"{gs.get('total')} ({gs.get('unexpected')} unexpected)", str(mf.get("total")), str(h.get("gate_version"))])
        earlier += [[e.get("round", ""), cond, str(e.get("provider")), str(e.get("seed")), str(e.get("n")), f"{e.get('k')} of {e.get('n')}", ci(e.get("wilson95"), 2),
                     str(e.get("gate_version")), "yes" if e.get("gate_version_ok") else ("no" if e.get("gate_version_ok") is False else "not checked"), str(e.get("frozen_gate_version"))] for e in h.get("earlier_rounds") or []]
    if rows:
        out.append(table(["Round", "Condition", "Provider", "Seed", "n", "Primary result", "Paused by detector", "False claims", "Submissions", "Gate stops", "Model failures", "Gate version"], rows))
    if earlier:
        out.append("**Earlier rounds, shown apart and not pooled with the headline:**")
        out.append(table(["Round", "Condition", "Provider", "Seed", "n", "Result", "Wilson 95%", "Gate version", "Matches its own plan's frozen hash", "Frozen hash"], earlier))
        for cond in ("injected", "clean"):
            for e in (ho.get(cond) or {}).get("earlier_rounds") or []:
                out.append(f"- {e.get('reading')}")
    lh = s.get("lh_offline") or {}
    if lh.get("suites"):
        out.append(f"Long-horizon suites LH-1 to LH-5 (offline; {lh.get('note')}; {lh.get('model_tokens')} model tokens):")
        out.append(table(["Suite", "OK", "False claims", "Ungated submissions"], [[k, str(v.get("ok")), str(v.get("false_claims")), str(v.get("ungated_submissions"))] for k, v in lh["suites"].items()]))
    sp = s.get("spend") or {}
    if sp.get("cap_usd") is not None:
        out.append(f"Spend: {usd(sp.get('spent_placeholder_usd'))} at list price ({usd(sp.get('spent_lower_usd'))} at the lower bound) of a {float(sp.get('cap_usd')):.2f} US dollar cap, {sp.get('pct_of_cap')}%, {sp.get('entries')} ledger entries.")
    out.append((s.get("real_desktop") or {}).get("text") or "")
    return "\n\n".join(x for x in out if x)


def _pilots(s: dict[str, Any]) -> str:
    pl = s.get("pilots") or {}
    if not pl:
        return ""
    rows = [[k.split("/")[-1].removeprefix("PILOT_"), str(p.get("tier")), "yes" if p.get("usable") else "no", pc(p.get("share_zero"), 1), pc(p.get("share_full"), 1), pc(p.get("share_cap_bound"), 1),
             usd(p.get("mean_cost_per_participant_usd")), "; ".join(p.get("reasons") or []) or "none"] for k, p in pl.items()]
    lim = next(iter(pl.values())).get("limits") or {}
    return (f"Feasibility pilots, {SIM} (limits by code: floor at most {pc(lim.get('max_share_zero'))}, ceiling at most {pc(lim.get('max_share_full'))}, cap-binding at most {pc(lim.get('max_share_cap_bound'))}); "
            "participants are discarded and are not results:\n\n" + table(["Pilot", "Tier", "Usable", "Floor", "Ceiling", "Cap-binding", "Cost per participant", "Reasons"], rows)
            + f"\n\nGo-ahead: {(s.get('go_ahead') or {}).get('where')}; needs {(s.get('go_ahead') or {}).get('needs')}.")


RENDER = {"deficit_recovery": _deficit, "null_placebo": _null, "hazard": _hazard, "ope": _ope, "routing": _routing, "ski_rental": _ski,
          "presence": _presence, "routines": _routines, "policy_gate": _gate, "skills": _skills, "forecast": _forecast, "pooling": _pooling, "agent_claims": _claims, "agent_runs": _agent_runs, "study_sim": _study_sim, "agentic": _agentic, "study_power": _study_power, "redteam_live": _redteam_live, "privacy": _privacy, "git": _git, "calendar": _calendar, "proactive": _proactive, "localmodel": _localmodel, "redteam": _redteam, "study": _study}


def _generic(s: dict[str, Any]) -> str:
    """A section with no dedicated renderer (a newer owner, shape unknown): scalars, small tables and one-line dicts, each captioned with its origin."""
    origin = origin_words((s.get("meta") or {}).get("origin", "synthetic"))
    return _generic_tables(s, ("meta", "limitations", "caveats", "owner_status", "trimmed", "statement"), origin, max_rows=20)


def evidence_map_text(emap: list[dict[str, Any]]) -> str:
    """The one table the owner can show first: every section, where its data comes from, its n, and whether it has numbers."""
    ok = sum(1 for e in emap if e["status"] == "ok")
    rows = []
    for e in emap:
        st = "ok" if e["status"] == "ok" else f"{e['status'].replace('_', ' ')}: {(e.get('reason') or '').split('. ')[0][:110]}"
        n = f"{e['n']} {e.get('n_unit') or ''}".strip() if e.get("n") else "n/a"
        origin = origin_words(e["origin"]) if e["status"] in ("ok", "not_run") else "n/a"
        rows.append([e["title"], origin, n, st, e.get("label") or ""])
    head = (f"{len(emap)} sections: {ok} with numbers, {sum(1 for e in emap if e['status'] == 'pending')} pending, {sum(1 for e in emap if e['status'] == 'not_run')} not run, "
            f"{sum(1 for e in emap if e['status'] == 'failed')} failed. Measured on: \"generators we wrote\" means people and data we generated and planted, \"real people\" means people, \"real and generated\" means both. "
            "A section without numbers says why instead of showing a made-up value.")
    return head + "\n\n" + table(["Section", "Measured on", "n", "Status", "Label"], rows)


def render(report: dict[str, Any]) -> str:
    out = ["# Understudy evaluation report", ""]
    rev = f" · git {report['git_rev']}" if report.get("git_rev") else ""
    out.append(f"Generated {report['generated_at']} · mock mode: {'yes' if report.get('mock') else 'no'}{rev} · fast run: {'yes' if (report.get('run') or {}).get('fast') else 'no'}")
    out += ["", "Written by `python -m understudy_engine.eval` from the owning tracks' code; no number here is typed in by hand. "
            "Results from generators we wrote say so. A section without numbers says why instead of showing a made-up value.", ""]
    secs = report["sections"]
    emap = report.get("evidence_map") or []
    if emap:
        out += ["## Evidence map", "", evidence_map_text(emap), ""]
    findings = report.get("findings") or []
    if findings:
        out += ["## Findings", "", "Results the numbers below support, stated as findings and not as footnotes. Each is generated from the sections it names.", ""]
        for fnd in findings:
            out += [f"### {fnd['title']}", "", f"*measured on: **{fnd.get('badge') or origin_words(fnd['origin'])}** · from: {', '.join(fnd.get('sections') or [])} · severity: {fnd.get('severity', 'n/a')}*", ""]
            out += [fnd["text"] if fnd["status"] == "ok" else f"**PENDING**: {fnd['text']} ({fnd.get('reason', '')})", ""]
    for name, title in TITLES.items():
        if name not in secs:
            continue
        s = secs[name]
        sim = name == "study_sim"
        b = basis(s["meta"])
        if sim:
            b = b.replace("*measured on", f"*{SIM} · measured on", 1)
        out += [f"## {title}", "", b, ""]
        if s["meta"].get("note"):
            out += [s["meta"]["note"], ""]
        if "status" in s and name != "study":
            tail = f" ({SIM}; not the live study)" if sim else ""
            out += [f"**{s['status'].upper().replace('_', ' ')}**: {s['reason']}{tail}", ""]
            if name == "study_roles" and s.get("pilots"):
                out += [_pilots(s), ""]
            continue
        if name == "study" and "status" in s:
            label = "NOT RUN" if s["status"] == "not_run" else s["status"].upper().replace("_", " ")
            out += [f"**{label}**: {s['reason']}. The page says so; no numbers are shown.", ""]
            continue
        if name not in RENDER and isinstance(s.get("statement"), str):
            out += [s["statement"], ""]
        out += [RENDER.get(name, _generic)(s), ""]
        if s.get("caveats"):
            cav = [c if not sim or SIM in c.lower() else f"{SIM[0].upper() + SIM[1:]}: {c}" for c in s["caveats"]]
            out += [f"Caveats ({SIM}):" if sim else "Caveats:", ""] + [f"- {c}" for c in cav] + [""]
    lim = secs.get("limitations") or []
    out += ["## Limitations register", "", f"{len(lim)} entries, most serious first. Kept in the product on purpose.", ""]
    out += [table(["Id", "Severity", "What it means", "Source"], [[e["id"], e["severity"], e["text"].replace("|", "/"), e["source"]] for e in lim]), ""]
    return "\n".join(out)
