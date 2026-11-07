"""The findings the Evidence page leads with, generated from the sections that carry their numbers (nothing typed in):

1. REALISM matrix (hazard, benefits-processor): the v1 stuck model's advantage over time-since-progress depends on the generator.
2. The simulated study (run 4, with the run 5 pilot): the outcome sits at the floor, so a null shows nothing.
3. ML v2 transfer (M5): neither v1 nor v2 transfers to the simulated participants' floor-bound behaviour.
4. REALISM genome (benefits-processor): deficit detection precision and recall fall on the harder generator families, and false attribution rises.
5. REALISM routines (benefits-processor, with the two thin roles): the repeat finder's raw precision and recall depend on the generator; the gate is what keeps proposals precise.
6. ML v2 genome families: E4 and Q1, the pre-registered primary candidates, are rejected on the held-out cohort (harmful: more error than v1's attribution).
7. ML v2 under generator mismatch: the plain time-since-progress baseline beats v1, and by more than the accepted v2 (A4) does.

Each finding has an origin badge, the sections it comes from, a plain sentence block, and its numbers. A finding whose source has no numbers yet is
returned with ``status: "pending"`` and says why, so it is never silently absent.
"""
from __future__ import annotations

from typing import Any

SIM = "simulated participants (language model), not people"


def _pct(x: Any, nd: int = 0) -> str:
    return "n/a" if x is None else f"{100 * float(x):.{nd}f}%"


def _ce(x: Any, nd: int = 2) -> str:
    return "n/a" if not x or x[0] is None else f"{x[0]:.{nd}f} to {x[1]:.{nd}f}"


def _v(est: Any, nd: int = 2) -> str:
    if not isinstance(est, dict) or est.get("value") is None:
        return "n/a"
    return f"{est['value']:.{nd}f} [{_ce(est.get('interval'), nd)}]"


def _ok(sections: dict[str, Any], name: str) -> dict[str, Any] | None:
    s = sections.get(name)
    return s if isinstance(s, dict) and "status" not in s else None


def m5_text(tr: dict[str, Any]) -> str:
    """The M5 sentence block, from the recorded transfer result."""
    m = tr["models"]
    v1, v2, base = m.get("v1") or {}, m.get("v2") or {}, m.get("base_rate") or {}
    d21 = ((tr.get("paired_log_loss") or {}).get("v2_minus_v1") or {})
    delta = d21.get("delta")
    return (
        f"M5, out-of-generator transfer ({SIM}; test only, no decision rule; n = {tr.get('n')} participants, {tr.get('n_bins')} scored 30 s bins): neither v1 nor v2 "
        f"transfers to the floor-bound behaviour of those traces. Log loss is {_v(v1.get('log_loss'))} for v1 and {_v(v2.get('log_loss'))} for v2 against "
        f"{_v(base.get('log_loss'))} for the base rate, and calibration is destroyed (expected calibration error {_v(v1.get('ece'))} and {_v(v2.get('ece'))}). The label shifts: "
        f"{_pct(tr.get('label_rate'))} of the test bins are 'stuck' against {_pct(tr.get('train_label_rate'))} in training, because progress is sparse in these traces. "
        f"v2 minus v1 log loss is {'n/a' if delta is None else f'{delta:+.3f}'} with an interval of {_ce(d21.get('interval'), 3)}: no improvement. "
        "Reported as is; the models and alarm rules were fixed before these traces existed.")


def _signed(x: Any, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:+.{nd}f}"


def realism_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "realism-generator-dependence", "title": "The stuck model's advantage depends on the generator", "origin": "synthetic",
            "badge": "synthetic (generators we wrote)", "sections": ["realism", "hazard"], "severity": "high"}
    rz = _ok(sections, "realism")
    hz = ((rz or {}).get("blocks") or {}).get("hazard") or {}
    role = "benefits-processor"
    b = hz.get(role)
    if not b:
        return {**base, "status": "pending", "text": "The realism hazard matrix for the benefits-processor role has not been recorded yet, so this finding has no numbers.",
                "reason": "no data/eval/realism_blocks/hazard_benefits-processor.json" if rz is not None else "realism section has no numbers"}
    own = b["v1_own"]["h1"]
    diag = b["v2_diagonals"]
    dvals = [c["est"] for c in diag.values() if c.get("est") is not None]
    wors = [c["est"] for c in b["v1_trained_on_v2"].values() if c.get("est") is not None]
    fa = b["false_alarm_over_budget"]
    hh = _ok(sections, "hazard") or {}
    m, tsp = hh.get("model") or {}, (hh.get("baselines") or {}).get("time_since_progress") or {}
    headline = ""
    if all(isinstance(x.get("log_loss"), (int, float)) for x in (m, tsp)):
        headline = (f" The v1 headline (log loss {m['log_loss']:.3f} against {tsp['log_loss']:.3f} for time since progress, leave one person out, on the four v1 personas) "
                    "therefore largely reflects the generator's emission table; it stays labelled synthetic.")
    no_skill = ", ".join(b["no_skill_cells"]) or "none"
    text = (
        f"Hazard, {role}, synthetic generators we wrote ({b.get('n_people_v2_cell')} synthetic people per v2 cell; the v1 generator has {b.get('n_people_v1_cell')} personas): the v1 stuck model beats time-since-progress by {own['est']:.3f} nats per bin "
        f"on its own generator, and the advantage falls to {min(dvals):.3f} to {max(dvals):.3f} on three harder generator families. A v1-trained model is "
        f"{abs(max(wors)):.2f} to {abs(min(wors)):.2f} nats worse than the baseline on their data (H1 {max(wors):+.2f} to {min(wors):+.2f}). False alarms: the interval is entirely above the 1.0 per hour budget in "
        f"{fa['v2_off_diagonal']['over']} of {fa['v2_off_diagonal']['n']} v2-to-v2 off-diagonal cells, {fa['v2_diagonal']['over']} of {fa['v2_diagonal']['n']} v2 diagonals, "
        f"{fa['v1_to_v2']['over']} of {fa['v1_to_v2']['n']} v1-to-v2 cells and {fa['v2_to_v1']['over']} of {fa['v2_to_v1']['n']} v2-to-v1 cells. "
        f"Cells with no skill (the H1 interval includes zero or lies below it): {no_skill}.{headline}")
    return {**base, "status": "ok", "text": text,
            "numbers": {"role": role, "v1_own_generator_h1": own, "v2_diagonal_h1": diag, "v1_trained_on_v2_h1": b["v1_trained_on_v2"], "false_alarm_over_budget": fa,
                        "no_skill_cells": b["no_skill_cells"], "partial": b.get("partial"), "source": "data/eval/realism_blocks/hazard_benefits-processor.json"}}


def _rng(vals: list[Any], pct: bool = True, nd: int = 0) -> str:
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return "n/a"
    lo, hi = min(vals), max(vals)
    k = 100 if pct else 1
    u = "%" if pct else ""
    a, b = f"{lo * k:.{nd}f}", f"{hi * k:.{nd}f}"
    return f"{a}{u}" if a == b else f"{a} to {b}{u}"


def _ests(group: dict[str, Any] | None, metric: str) -> list[Any]:
    return [(c.get(metric) or {}).get("est") for c in (group or {}).values() if isinstance(c, dict)]


def _people(group: dict[str, Any] | None) -> str:
    ns = sorted({c.get("n_people") for c in (group or {}).values() if isinstance(c, dict) and c.get("n_people")})
    return "n/a" if not ns else (str(ns[0]) if len(ns) == 1 else f"{ns[0]} to {ns[-1]}")


def genome_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "realism-genome-generator-dependence", "title": "Deficit detection does not hold up on harder generators", "origin": "synthetic",
            "badge": "synthetic (generators we wrote)", "sections": ["realism"], "severity": "high"}
    rz = _ok(sections, "realism")
    role = "benefits-processor"
    b = (((rz or {}).get("blocks") or {}).get("genome") or {}).get(role)
    if not b or not b.get("v1_own"):
        return {**base, "status": "pending", "text": "The realism genome block for the benefits-processor role has not been recorded yet, so this finding has no numbers.",
                "reason": "no data/eval/realism_blocks/genome_benefits-processor.json" if rz is not None else "realism section has no numbers"}
    v1, diag, fit_v1, to_v1 = b["v1_own"], b["v2_diagonals"], b["v1_trained_on_v2"], b["v2_trained_on_v1"]
    fa1 = (v1.get("false_attr_s") or {}).get("est")
    text = (
        f"Genome (deficit detection), {role}, synthetic generators we wrote ({b.get('n_people_v1_cell')} personas on the v1 generator, {_people(diag)} synthetic people per v2 cell): "
        f"precision {_rng([v1['precision']['est']])} and recall {_rng([v1['recall']['est']])} on the v1 generator fall to {_rng(_ests(diag, 'precision'))} precision and "
        f"{_rng(_ests(diag, 'recall'))} recall on three harder generator families (thresholds fitted and tested on the same family). Thresholds fitted on v1 keep recall "
        f"({_rng(_ests(fit_v1, 'recall'))}) but lose precision ({_rng(_ests(fit_v1, 'precision'))}); thresholds fitted on a v2 family give v1 high precision "
        f"({_rng(_ests(to_v1, 'precision'))}) but recall of only {_rng(_ests(to_v1, 'recall'))}. False attribution to deficits that are absent is "
        f"{_rng(_ests(diag, 'false_attr_s'), pct=False)} s on the v2 families against {'n/a' if fa1 is None else f'{fa1:.1f}'} s on v1. "
        "The v1 figures describe the v1 generator, not workers.")
    return {**base, "status": "ok", "text": text,
            "numbers": {"role": role, "v1_own": {k: v1.get(k) for k in ("precision", "recall", "false_attr_s")},
                        "v2_diagonals": {f: {k: c.get(k) for k in ("precision", "recall", "false_attr_s")} for f, c in diag.items()},
                        "v1_trained_on_v2": {f: {k: c.get(k) for k in ("precision", "recall")} for f, c in fit_v1.items()},
                        "v2_trained_on_v1": {f: {k: c.get(k) for k in ("precision", "recall")} for f, c in to_v1.items()},
                        "partial": b.get("partial"), "source": "data/eval/realism_blocks/genome_benefits-processor.json"}}


def routines_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "realism-routines-generator-dependence", "title": "The repeat finder's precision depends on the generator; the gate carries the proposals", "origin": "synthetic",
            "badge": "synthetic (generators we wrote)", "sections": ["realism"], "severity": "high"}
    rz = _ok(sections, "realism")
    role = "benefits-processor"
    rb = ((rz or {}).get("blocks") or {}).get("routines") or {}
    b = rb.get(role)
    if not b or not b.get("shipped_by_test_family"):
        return {**base, "status": "pending", "text": "The realism routines block for the benefits-processor role has not been recorded yet, so this finding has no numbers.",
                "reason": "no data/eval/realism_blocks/routines_benefits-processor.json" if rz is not None else "realism section has no numbers"}
    sh = b["shipped_by_test_family"]
    v1 = sh.get("v1") or {}
    v2 = {k: c for k, c in sh.items() if k != "v1"}
    fitted = b.get("fitted") or {}
    off = {p: c for p, c in fitted.items() if p.split("->")[0] != p.split("->")[1]}
    thin = {r: x for r, x in rb.items() if r != role and x.get("shipped_by_test_family")}
    thin_text = ""
    if thin:
        pool = {f"{r}:{f}": c for r, x in thin.items() for f, c in x["shipped_by_test_family"].items()}
        thin_text = (f" The two thin roles ({', '.join(sorted(thin))}; v2 families only, shipped thresholds) give raw precision {_rng(_ests(pool, 'r1_precision'))}, recall "
                     f"{_rng(_ests(pool, 'r2_recall'))} and proposal precision {_rng(_ests(pool, 'r3_proposal_precision'))}, so the figures differ by role as well as by family.")
    fixed = b.get("shipped_identical_across_fit_family")
    v1p = (v1.get("r1_precision") or {}).get("est")
    text = (
        f"Routines (repeat finder, then the proposal gate), {role}, synthetic generators we wrote ({_people({'v1': v1})} personas on the v1 generator, {_people(v2)} synthetic people per v2 cell; shipped thresholds"
        f"{', which do not depend on the fit family' if fixed else ''}): raw cluster precision is {_rng([v1p])} on the v1 generator (the published figure) and "
        f"{_rng(_ests(v2, 'r1_precision'))} on the three v2 families, with recall {_rng(_ests(v2, 'r2_recall'))} ({_rng([(v1.get('r2_recall') or {}).get('est')])} on v1). "
        f"Proposal precision after the gate is {_rng(_ests(v2, 'r3_proposal_precision'))} ({_rng([(v1.get('r3_proposal_precision') or {}).get('est')])} on v1). "
        f"Thresholds fitted per family transfer unevenly: across the fitted off-diagonal cells raw precision ranges from {_rng(_ests(off, 'r1_precision'))} and recall from "
        f"{_rng(_ests(off, 'r2_recall'))}.{thin_text} These numbers say how many of the clusters found are real routines in a "
        "generator we wrote, not in real workers.")
    return {**base, "status": "ok", "text": text,
            "numbers": {"role": role, "shipped_v1": {k: v1.get(k) for k in ("r1_precision", "r2_recall", "r3_proposal_precision")},
                        "shipped_v2": {f: {k: c.get(k) for k in ("r1_precision", "r2_recall", "r3_proposal_precision")} for f, c in v2.items()},
                        "shipped_identical_across_fit_family": fixed,
                        "thin_roles": {r: {f: {k: c.get(k) for k in ("r1_precision", "r2_recall", "r3_proposal_precision")} for f, c in x["shipped_by_test_family"].items()} for r, x in thin.items()},
                        "partial": b.get("partial"), "source": "data/eval/realism_blocks/routines_<role>.json"}}


def study_sim_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "study-sim-floor-null", "title": "The simulated study cannot show an effect: the outcome sits at the floor", "origin": "synthetic", "badge": SIM,
            "sections": ["study_sim", "study_power"], "severity": "high"}
    ss = _ok(sections, "study_sim")
    if not ss or not ss.get("headline"):
        return {**base, "status": "pending", "text": f"{SIM}: the simulated study has no analysed result yet, so this finding has no numbers.",
                "reason": (sections.get("study_sim") or {}).get("reason") or "no analysed run"}
    h, fl, nd = ss["headline"], ss.get("floor") or {}, ss.get("nudges") or {}
    co, aa = fl.get("coached") or {}, fl.get("aa") or {}
    enf = ((ss.get("pipeline_checks") or {}).get("study_mode_enforcement") or {}).get("non_silent_polls_by_mode") or {}
    held = enf and enf.get("post_test") == 0 and enf.get("off") == 0
    power = next((x["text"] for x in ss.get("limitations") or [] if x.get("id") == "sim-power"), None)
    if power and power.lower().startswith(SIM + ":"):
        power = power[len(SIM) + 1:].strip()                          # already labelled once at the head of this finding
    pilot = ss.get("run5_pilot") or {}
    lo, hi = (h.get("ci95") or [None, None])
    parts = [
        f"{SIM[0].upper() + SIM[1:]}. Run 4 (n = {(ss.get('n') or 0) + (ss.get('n_aa') or 0)}: {ss.get('n')} coached-arm and {ss.get('n_aa')} A/A participants): "
        f"{co.get('score_zero')} of {co.get('post_tests')} coached post-tests scored 0 (the floor) and {aa.get('score_zero')} of {aa.get('post_tests')} A/A post-tests; "
        f"the action cap was hit in {co.get('hit_the_action_cap')} of {co.get('post_tests')} coached post-tests. The headline difference is {_signed(h.get('mean_difference'))} "
        f"[{_signed(lo)}, {_signed(hi)}], sign-flip p = {h.get('sign_flip_p_two_sided')}. An outcome at the floor means a null shows nothing: it does not show the coach has no effect."]
    if power:
        parts.append(power)
    if pilot:
        parts.append(f"Run 5 pilot: {pilot.get('post_tests_above_zero')} of {pilot.get('post_tests')} post-tests scored above zero (needed {pilot.get('needed_above_zero')}); "
                     f"{'it passed' if pilot.get('pass') else 'stopped, so there is no run 5 proper'}"
                     + (f" (reason recorded: {'; '.join(pilot.get('reasons_for_stopping') or [])})." if pilot.get("reasons_for_stopping") else "."))
    if enf:
        parts.append(f"Study-mode enforcement {'held' if held else 'DID NOT HOLD'}: {enf.get('post_test')} non-silent coach polls in post-test blocks and {enf.get('off')} in blocks with the coach off "
                     f"(including A/A); {nd.get('shown')} nudges were shown, all in train blocks.")
    return {**base, "status": "ok", "text": " ".join(parts),
            "numbers": {"n": ss.get("n"), "n_aa": ss.get("n_aa"), "floor": fl, "headline": {k: h.get(k) for k in ("mean_difference", "ci95", "sign_flip_p_two_sided")},
                        "run5_pilot": pilot or None, "study_mode_enforcement_non_silent_polls": enf or None, "enforcement_held": bool(held)}}


def m5_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "mlv2-m5-transfer-failure", "title": "ML v2 does not transfer to the simulated participants", "origin": "synthetic", "badge": SIM, "sections": ["mlv2"], "severity": "high"}
    ml = _ok(sections, "mlv2")
    tr = (ml or {}).get("transfer_simulated_participants")
    if not (isinstance(tr, dict) and isinstance(tr.get("models"), dict)):
        return {**base, "status": "pending", "text": f"{SIM}: the M5 transfer result is not recorded yet, so this finding has no numbers.",
                "reason": "no evals/mlv2/results/transfer_sim.json" if ml is not None else "mlv2 section has no numbers"}
    m = tr["models"]
    return {**base, "status": "ok", "text": m5_text(tr),
            "numbers": {"n": tr.get("n"), "n_bins": tr.get("n_bins"), "label_rate": tr.get("label_rate"), "train_label_rate": tr.get("train_label_rate"),
                        "log_loss": {k: (m.get(k) or {}).get("log_loss") for k in ("v1", "v2", "base_rate")}, "ece": {k: (m.get(k) or {}).get("ece") for k in ("v1", "v2")},
                        "source": "evals/mlv2/results/transfer_sim.json"}}


def _sg(x: Any, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:+.{nd}f}"


def _iv(c: Any, nd: int = 2) -> str:
    return "n/a" if not c or c[0] is None else f"{c[0]:+.{nd}f}, {c[1]:+.{nd}f}"


def mlv2_e4_q1_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "mlv2-e4-q1-rejected", "title": "ML v2 expert-envelope and counterfactual candidates (E4, Q1) are rejected", "origin": "synthetic",
            "badge": "synthetic (generators we wrote)", "sections": ["mlv2"], "severity": "high"}
    ml = _ok(sections, "mlv2")
    rows = {r.get("id"): r for r in (ml or {}).get("verdicts") or [] if isinstance(r, dict) and r.get("family") in ("E", "Q")}
    if not (rows.get("E4") and rows.get("Q1")):
        return {**base, "status": "pending", "text": "The held-out genome result for the E and Q families is not recorded yet, so this finding has no numbers.",
                "reason": "no evals/mlv2/results/heldout_genome.json" if ml is not None else "mlv2 section has no numbers"}
    gen = (((ml.get("heldout") or {}).get("genome") or {}).get("result") or {})
    e4, q1, e1 = rows["E4"], rows["Q1"], rows.get("E1")
    others = ", ".join(f"{k} {r['verdict']} ({_sg(r.get('delta'))} [{_iv(r.get('interval'))}] s)" for k, r in sorted(rows.items()) if k in ("E1", "E2", "E3") and r.get("delta") is not None)
    text = (f"ML v2 genome families on the held-out apprentice cohort ({gen.get('n_cohorts')} cohorts, {gen.get('n_novices')} novices; synthetic): the pre-registered primary candidates E4 "
            f"(expert envelope) and Q1 (counterfactual price) are both {e4['verdict']} and so rejected. The primary metric is the mean absolute error, in seconds, of the recovered price of a "
            f"deficit, paired against v1's attribution, so a positive difference is worse: E4 {_sg(e4['delta'])} [{_iv(e4['interval'])}] s, Q1 {_sg(q1['delta'])} [{_iv(q1['interval'])}] s. "
            f"Other E variants: {others}. v1's attribution stays the default for these families. Reported as is: the candidates were frozen before the held-out run.")
    return {**base, "status": "ok", "text": text,
            "numbers": {"E4": {k: e4.get(k) for k in ("verdict", "delta", "interval", "level")}, "Q1": {k: q1.get(k) for k in ("verdict", "delta", "interval", "level")},
                        "E1": {k: e1.get(k) for k in ("verdict", "delta", "interval", "level")} if e1 else None, "n_cohorts": gen.get("n_cohorts"), "n_novices": gen.get("n_novices"),
                        "source": "evals/mlv2/results/heldout_genome.json"}}


def mlv2_mismatch_finding(sections: dict[str, Any]) -> dict[str, Any]:
    base = {"id": "mlv2-tsp-beats-v1-under-mismatch", "title": "Under generator mismatch the time-since-progress baseline beats v1", "origin": "synthetic",
            "badge": "synthetic (generators we wrote)", "sections": ["mlv2"], "severity": "high"}
    ml = _ok(sections, "mlv2")
    roles = ((((ml or {}).get("heldout") or {}).get("mismatch") or {}).get("result") or {}).get("roles") or {}
    got = {r: (v.get("pooled_off_diagonal") or {}) for r, v in roles.items()}
    got = {r: p for r, p in got.items() if isinstance(p.get("TSP"), dict) and p["TSP"].get("delta_log_loss") is not None}
    if not got:
        return {**base, "status": "pending", "text": "The held-out generator-mismatch result is not recorded yet, so this finding has no numbers.",
                "reason": "no evals/mlv2/results/heldout_mismatch.json" if ml is not None else "mlv2 section has no numbers"}
    chosen = ((ml.get("final_decisions") or {}).get("default_v2") or {})
    per = "; ".join(f"{r} {_sg(p['TSP']['delta_log_loss'], 3)} [{_iv(p['TSP'].get('interval'), 3)}]" for r, p in got.items())
    deep = got.get("benefits-processor") or {}
    v2 = chosen.get("benefits-processor")
    vs = ""
    if v2 and isinstance(deep.get(v2), dict):
        vs = (f" The accepted v2 ({v2}) improves on v1 by {_sg(deep[v2]['delta_log_loss'], 3)} [{_iv(deep[v2].get('interval'), 3)}] for benefits-processor under the same test, "
              "a smaller improvement than the baseline's, so on this test a rule that only counts time since progress does better than the accepted v2 when the generator changes.")
    text = (f"ML v2 under generator mismatch (fit on one synthetic generator family, test on another; pooled off-diagonal cells; synthetic): the plain time-since-progress baseline beats v1 on log "
            f"loss, paired against v1 (negative is better; adjusted intervals as recorded): {per}.{vs} The held-out result is reported as is; it is about our generators, not about workers.")
    return {**base, "status": "ok", "text": text,
            "numbers": {"time_since_progress_vs_v1_by_role": {r: {"delta_log_loss": p["TSP"]["delta_log_loss"], "interval": p["TSP"].get("interval")} for r, p in got.items()},
                        "accepted_v2": v2, "accepted_v2_vs_v1_benefits_processor": ({"delta_log_loss": deep[v2]["delta_log_loss"], "interval": deep[v2].get("interval")}
                                                                                      if v2 and isinstance(deep.get(v2), dict) else None),
                        "source": "evals/mlv2/results/heldout_mismatch.json"}}


def build_findings(sections: dict[str, Any]) -> list[dict[str, Any]]:
    return [realism_finding(sections), study_sim_finding(sections), m5_finding(sections), genome_finding(sections), routines_finding(sections),
            mlv2_e4_q1_finding(sections), mlv2_mismatch_finding(sections)]
