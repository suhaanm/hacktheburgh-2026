"""summary.json and REPORT.md for the simulated study. Everything is labelled LABEL. Nothing here touches the live study's ``study`` section."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from . import LABEL, analysis
from .analysis_io import RESULTS
from .design import N_AA, N_COACHED

from .coach import EXPECTED_ZONES

LIMITATIONS = [
    {"id": "sim-not-people", "severity": "high",
     "text": "The participants are language-model agents, not people. Nothing here shows that people learn from the coach, and nothing here is a user study."},
    {"id": "sim-memory-is-a-note", "severity": "high",
     "text": "The only 'memory' a participant has is a note of at most 280 characters that it wrote itself after the practice case and sees again at the post-test of the same skill. Every case starts from a fresh model context. That is a prompt, not learning in any human sense."},
    {"id": "sim-instruction-following", "severity": "high",
     "text": "A model that is shown 'check cliff edges before you copy this result' can do what it says. A higher score after coaching can therefore be instruction following plus a self-written note, not retention of a skill."},
    {"id": "sim-authored-by-us", "severity": "high",
     "text": "The coach prompts, the sandbox sites, the households, the scoring rule and the personas were all written by us."},
    {"id": "sim-power", "severity": "high",
     "text": "With 16 coached-arm participants the analysis has about 6% false positives and 12%, 29% and 76% power for a small, medium and large true effect (engine-analytics Monte Carlo, interval excludes zero); sign-flip p below 0.05 has less. A null or small result does not show that the coach has no effect; a result counts as clear only if the interval excludes zero."},
    {"id": "sim-spillover", "severity": "medium",
     "text": "The counterbalanced design cancels a fixed block-2 shift and generic carry-over, not spill-over of the coached gain to the other skill in block 2, which dilutes the contrast. Because each block starts from a fresh model context, order and fatigue effects are absent by construction."},
    {"id": "sim-timing", "severity": "medium",
     "text": "Timing is not human. Each action is followed by a fixed 2 s pause and the model's own latency varies, so effort is reported as ACTION COUNTS and the coach's poll-to-prompt delay is a property of the pipeline, not of people. A fast participant can finish the note page before a prompt arrives."},
    {"id": "sim-renderer", "severity": "medium",
     "text": "The coach is real but the overlay renderer is simulated: a ring is drawn only when an element carrying the target zone exists on the page the participant is on. The cliff button exists only on a calculator result tab, not on the case note page where the prompt usually arrives. The reconcile target was `results_tabs` (no page element) when the plan was written; the pipeline snapshot used targets `reconcile_control` (the case note's dropdown), which exists. The by-zone table shows which was served."},
    {"id": "sim-model-frame", "severity": "medium",
     "text": "Participants are reached through the shared model port's fast-tier check call, whose fixed instructions tell the model to treat quoted material as data. That may make it less responsive to on-page text in both arms."},
    {"id": "sim-machine-load", "severity": "medium",
     "text": "The build machine was heavily loaded by other agents' tests while the participants ran (1-minute load average above 100 on 12 CPUs, sampled and reported), so wall-clock times, the coach's 3 s polls, the extension's event flush and the prompt delays are slower and noisier than on an idle machine. Action counts are not affected; timings are."},
    {"id": "sim-one-model", "severity": "medium",
     "text": "One model (id read from the environment and recorded in the CSV) and one family of personas written by us. Results say nothing about other models."},
    {"id": "sim-scoring", "severity": "medium",
     "text": "Scores come from the sandbox state exactly as analyze.py scores them (cliff 0, 1 or 2 of 2; reconcile 0 or 1), so ties and ceilings are likely and the t interval is not exact for such discrete scores."},
]


def _stats(vals: list[float]) -> dict:
    v = sorted(vals)
    if not v:
        return {"n": 0}
    q = lambda p: v[min(len(v) - 1, int(round(p * (len(v) - 1))))]  # noqa: E731
    return {"n": len(v), "median": round(statistics.median(v), 2), "min": round(v[0], 2), "max": round(v[-1], 2), "q25": round(q(0.25), 2), "q75": round(q(0.75), 2)}


def load_table(results_dir: Path) -> dict:
    """Machine load while the participants ran. Run 4 recorded it with a separate sampler (results/load_samples.jsonl, every 15 s): a participant's start is its
    checks file's modification time minus its wall time, its end the modification time; the load is the nearest sample. Later runs also carry load1_start and
    load1_end columns in participants.csv. Load is the 1-minute load average; the machine has the stated number of CPUs."""
    results_dir = Path(results_dir)
    samples = []
    sf = results_dir / "load_samples.jsonl"
    if sf.exists():
        samples = [json.loads(x) for x in sf.read_text().splitlines() if x.strip()]
    if not samples:
        return {"available": False}
    def nearest(t: float):
        x = min(samples, key=lambda y: abs(y["t"] - t))
        return x["load1"] if abs(x["t"] - t) <= 60 else None            # no sample near this time (the sampler started after the first participants)
    rows = []
    for f in sorted((results_dir / "checks").glob("p_sim*.json")) if (results_dir / "checks").is_dir() else []:
        d = json.loads(f.read_text())
        end = f.stat().st_mtime
        start = end - float(d.get("wall_s", 0))
        rows.append({"participant": d["participant"], "load1_start": nearest(start), "load1_end": nearest(end), "wall_s": d.get("wall_s")})
    vals = [v for r in rows for v in (r["load1_start"], r["load1_end"]) if v is not None]
    if rows:
        (results_dir / "load_by_participant.csv").write_text("participant,load1_start,load1_end,wall_s\n" + "".join(f"{r['participant']},{'' if r['load1_start'] is None else r['load1_start']},{'' if r['load1_end'] is None else r['load1_end']},{r['wall_s']}\n" for r in rows))
    cpus = samples[0].get("cpus")
    return {"available": True, "cpus": cpus, "samples": len(samples), "load1_min": min(x["load1"] for x in samples), "load1_max": max(x["load1"] for x in samples),
            "load1_median_at_participant_start_or_end": round(statistics.median(vals), 1) if vals else None, "participants": len(rows), "participants_with_a_sample_at_start_or_end": sum(1 for r in rows if r["load1_start"] is not None or r["load1_end"] is not None)}


def floor_check(results_dir: Path, rows: list[dict]) -> dict:
    """Floor and ceiling descriptives of the unassisted post-tests, by arm (not part of the pre-registered estimates): how many scored zero, how many hit the action
    cap, how many ended without a saved draft, and how many sandbox states hold any calculation at all."""
    results_dir = Path(results_dir)
    out = {}
    for arm in ("coached", "aa"):
        rs = [r for r in rows if r.get("arm") == arm and not str(r.get("exclusion", "")).strip()]
        n = len(rs)
        zero = sum(1 for r in rs if analysis.A.skill_score(r) == 0)
        full = sum(1 for r in rs if analysis.A.skill_score(r) == 1)
        capped = sum(1 for r in rs if r["post_capped"])
        no_calc = saved = 0
        for r in rs:
            f = results_dir / "raw" / f"{r['participant']}-block{int(r['block'])}-post.json"
            if f.exists():
                st = json.loads(f.read_text())
                no_calc += len(st.get("calculations", [])) == 0
                saved += len(st.get("notes", {})) > 0
        out[arm] = {"post_tests": n, "score_zero": zero, "score_full": full, "hit_the_action_cap": capped, "sandbox_state_with_no_calculation": no_calc,
                    "ended_with_a_saved_draft": saved, "share_zero": round(zero / n, 3) if n else None}
    return out


def aggregate_checks(checks_dir: Path) -> dict:
    files = sorted(Path(checks_dir).glob("p_sim*.json")) if Path(checks_dir).is_dir() else []
    docs = [json.loads(f.read_text()) for f in files]
    ev_total = ev_ext = ev_invalid = 0
    types: dict[str, int] = {}
    coach_rows: list[dict] = []
    p_source: dict[str, int] = {}
    polls = nonsilent = 0
    by_mode = {"train": 0, "post_test": 0, "off": 0}
    ns_by_mode = {"train": 0, "post_test": 0, "off": 0}
    violations: list[str] = []
    store_viol: list[str] = []
    eng = {"tracebacks": 0, "error_lines": 0, "events_post_failures": 0}
    weberrors = harness_errors = poll_errors = contaminated = 0
    consent_start = []
    consent_end = []
    kill = {"engine_reports_killed": 0, "coach_silent_after_kill": 0, "n": 0}
    excl: list[str] = []
    capped = {"practice": 0, "post": 0}
    typed = {"fills_and_selects": 0, "cleaned": 0}
    export = {"participants_exported": 0, "events": 0, "stripped_values": 0, "errors": 0}
    shown_by_block: dict[str, int] = {}
    workers: dict[str, list[float]] = {}
    for d in docs:
        c = d["checks"]
        e = c.get("events", {})
        ev_total += e.get("total", 0)
        ev_ext += e.get("from_extension", 0)
        ev_invalid += e.get("schema_invalid", 0)
        for k, v in (e.get("types") or {}).items():
            types[k] = types.get(k, 0) + v
        co = c.get("coach", {})
        coach_rows += co.get("shown", [])
        polls += co.get("polls", 0)
        nonsilent += co.get("decisions_non_silent", 0)
        for k, v in (co.get("p_source") or {}).items():
            p_source[str(k)] = p_source.get(str(k), 0) + v
        for m in by_mode:
            by_mode[m] += (co.get("polls_by_mode") or {}).get(m, 0)
            ns_by_mode[m] += (co.get("non_silent_by_mode") or {}).get(m, 0)
        violations += [f"{d['participant']}: {v}" for v in c.get("study_mode_violations", [])]
        store_viol += [f"{d['participant']}: {v}" for v in c.get("study_mode_enforcement_from_store", [])]
        for k, v in (c.get("engine_log") or {}).items():
            eng[k] = eng.get(k, 0) + v
        weberrors += sum(1 for x in c.get("errors", []) if str(x).startswith("weberror"))
        poll_errors += sum(1 for x in c.get("errors", []) if "coach/" in str(x))
        harness_errors += sum(1 for x in c.get("errors", []) if "Traceback" in str(x))
        contaminated += len(c.get("contaminated_attempts", []))
        if c.get("consent_probe_events") is not None:
            consent_start.append(c["consent_probe_events"])
        if c.get("consent_off_events_after") is not None:
            consent_end.append(c["consent_off_events_after"])
        k = c.get("kill") or {}
        if k:
            kill["n"] += 1
            kill["engine_reports_killed"] += bool(k.get("engine_reports_killed"))
            kill["coach_silent_after_kill"] += k.get("coach_action_after_kill") == "silent"
        for kk, v in ((c.get("coach_events") or {}).get("by_block_skill") or {}).items():
            shown_by_block[kk] = shown_by_block.get(kk, 0) + v
        for k in typed:
            typed[k] += (c.get("typed_values_cleaned") or {}).get(k, 0)
        xe = c.get("engine_events_export") or {}
        if "events" in xe:
            export["participants_exported"] += 1
            export["events"] += xe["events"]
            export["stripped_values"] += xe.get("stripped_values", 0)
        elif xe:
            export["errors"] += 1
        if d.get("exclusion"):
            excl.append(f"{d['participant']}: {d['exclusion']}")
        for case in d.get("cases", []):
            if case.get("capped"):
                capped[case["phase"]] += 1
    annotate = [r for r in coach_rows if r.get("action") in ("annotate", "takeover_offer")]
    zone_ok = sum(1 for r in annotate if r.get("zone") in EXPECTED_ZONES.get(r.get("skill") or "", set()))
    delays = [r["delay_s"] for r in coach_rows if r.get("delay_s") is not None]
    outcome = {o: sum(1 for r in coach_rows if r.get("outcome") == o) for o in ("followed", "dismissed", "ignored")}
    return {
        "participants_run": len(docs),
        "events": {"total": ev_total, "from_extension": ev_ext, "schema_invalid": ev_invalid, "by_type": types,
                   "schema_valid_share": round(1 - ev_invalid / ev_total, 4) if ev_total else None},
        "coach": {"polls": polls, "decisions_shown": len(coach_rows), "decisions_non_silent_polls": nonsilent, "outcomes": outcome, "p_source": p_source,
                  "by_kind": {k: sum(1 for r in coach_rows if r.get("action") == k) for k in ("annotate", "nudge", "takeover_offer")}},
        "ring_target": {"annotate_decisions": len(annotate), "zone_equals_missing_step_zone": zone_ok,
                        "ring_drawn_on_arrival": sum(1 for r in annotate if r.get("ring_on_arrival")), "ring_drawn_at_some_point": sum(1 for r in annotate if r.get("ring_found")),
                        "message_only": sum(1 for r in annotate if not r.get("ring_found")), "by_zone": {z: sum(1 for r in annotate if r.get("zone") == z) for z in {r.get("zone") for r in annotate}}},
        "delay_from_first_note_page_action_to_prompt_s": _stats(delays),
        "false_nudges": {"prompts_for_a_step_already_done_more_than_6s_earlier": sum(1 for r in coach_rows if r.get("false") == "false"),
                         "prompts_lagging_a_step_done_within_6s": sum(1 for r in coach_rows if r.get("false") == "lag"), "of": len(coach_rows)},
        "study_mode_enforcement": {"polls_by_mode": by_mode, "non_silent_polls_by_mode": ns_by_mode, "violations_seen_by_poller": violations,
                                   "violations_in_event_store": store_viol, "coach_shown_events_by_block_and_skill": shown_by_block,
                                   "verdict": "VIOLATION: report as a bug" if (violations or store_viol or ns_by_mode["post_test"] or ns_by_mode["off"]) else "zero nudges outside the trained skill's train block"},
        "errors": {"engine": eng, "extension_weberrors": weberrors, "coach_poll_errors": poll_errors, "harness_tracebacks": harness_errors,
                   "contaminated_attempts_retried": contaminated, "exclusions": excl},
        "consent": {"events_while_capture_off_at_start": consent_start, "events_after_capture_switched_off": consent_end,
                    "respected": all(x == 0 for x in consent_start + consent_end) if (consent_start or consent_end) else None},
        "kill_flag": {**kill, "note": "the KILL file was written in each participant's isolated data dir (never POST /kill, which would call the agent service); the engine reports it and the coach stays silent. The extension's capture is governed by its own consent toggle, not by this flag."},
        "capped_cases": capped,
        "engine_events_export": {**export, "statement": "Each participant's engine events (results/raw/<participant>/engine_events.jsonl) are schema-valid L0 events: timestamps, types, zones, hashed ids, coach step and outcome ids. They contain no participant text, no typed values and no page text; the schema forbids it, and any string that was not enum-like would have been replaced and counted in stripped_values."},
        "typed_values_cleaned": {**typed, "share": round(typed["cleaned"] / typed["fills_and_selects"], 4) if typed["fills_and_selects"] else None,
                                 "note": "values the participant typed with JSON artifacts from its structured reply removed before typing (PLAN amendment 1); identical for every arm"},
    }


def findings(pc: dict) -> list[dict]:
    """Pipeline findings (facts about the system under test, not study results), with the numbers from this run."""
    dl = pc["delay_from_first_note_page_action_to_prompt_s"]
    rt = pc["ring_target"]
    ev = pc["events"]["by_type"]
    return [
        {"id": "latency", "text": f"A prompt arrives about {dl.get('median', 'n/a')} s (median of n = {dl.get('n', 0)}; min {dl.get('min', 'n/a')}, max {dl.get('max', 'n/a')}) after the participant's first action on the case note page: "
                                  "the extension batches events every 2 s and the coach needs two consecutive signals at 3 s polls. A participant who finishes the note page faster never sees it."},
        {"id": "zones", "text": f"Prompt targets served, by zone: {rt['by_zone']}. The cliff ring can only be drawn on a calculator result tab (the Check cliff edges button lives there), not on the case note page where the "
                                  f"prompt usually arrives (ring drawn on arrival {rt['ring_drawn_on_arrival']} of {rt['annotate_decisions']}, at some point {rt['ring_drawn_at_some_point']}). The reconcile target was results_tabs (no page element) when "
                                  "the plan was written; the frozen pipeline serves reconcile_control, the case note's dropdown, which exists."},
        {"id": "reconcile-signal", "text": f"The engine's RECONCILE signal was a browser tab switch (results_tabs) and is now also a click or focus on the dropdown (reconcile_control); tab events recorded in this run: {ev.get('tab', 0)}. "
                                            "Comparing calculators within one tab never satisfied the older signal."},
    ]


def build_section(results_dir: Path = RESULTS, expected: tuple[int, int] = (N_COACHED, N_AA), specs=None, run_label: str = "",
                  extra_limitations: list | None = None) -> dict:
    results_dir = Path(results_dir)
    limitations = LIMITATIONS + (extra_limitations or [])
    csv_path = results_dir / "participants.csv"
    meta = {"origin": "simulated_llm", "n_unit": "silicon participants", "label": LABEL, "interval_level": 0.95, "run_label": run_label,
            "split": "within-participant, counterbalanced S1-S4, plus an A/A sham arm in which the coach is silent in every block",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not csv_path.exists():
        return {"status": "not_run", "label": LABEL, "n": 0, "n_aa": 0, "limitations": limitations, "meta": {**meta, "n": 0,
                "note": "The simulated study has not been run. It never stands in for the live study with people."}}
    rows = analysis.load_rows(csv_path)
    a = analysis.analyse_all(rows, specs)
    coached, aa = analysis.split_arms(rows)
    ex = set(a["excluded_participants"])
    n = len({r["participant"] for r in coached} - ex)
    n_aa = len({r["participant"] for r in aa} - ex)
    status = "complete" if (n >= expected[0] and n_aa >= expected[1]) else ("harness_failure" if n < min(8, expected[0]) else "partial")
    cost = {}
    if (results_dir / "cost.json").exists():
        c = json.loads((results_dir / "cost.json").read_text())
        ref = c.get("usd_at_fast_tier_reference_rates")
        if ref is None and c.get("tokens"):
            ref = round((c["tokens"]["in"] * 0.75 + c["tokens"]["out"] * 4.50) / 1e6, 3)
        carried = round(sum(json.loads(x.read_text()).get("usd_est", 0) for x in results_dir.parent.glob("aborted_run*/cost.json")), 3)
        cost = {"usd_est": c.get("usd_est"), "of_which_from_aborted_runs": carried, "cap_usd": c.get("cap_usd"), "calls": c.get("calls"), "cache_hits": c.get("cache_hits"), "tokens": c.get("tokens"),
                "prices_from_env": c.get("prices_from_env"), "usd_at_fast_tier_reference_rates": ref, "price_in_per_mtok": c.get("price_in_per_mtok"), "price_out_per_mtok": c.get("price_out_per_mtok")}
    models = sorted({r.get("model", "") for r in rows})
    aborted = []
    for nf in sorted(results_dir.parent.glob("aborted_run*/NOTE.json")):
        try:
            aborted.append(json.loads(nf.read_text()))
        except (OSError, ValueError):
            pass
    h = a["headline"]
    eff = a["effort"]
    section = {
        "status": status, "label": LABEL, "n": n, "n_aa": n_aa,
        "headline": {"mean_difference": h.get("mean_difference"), "ci95": h.get("ci95"), "ci_degenerate": h.get("ci_degenerate"),
                     "per_participant_difference": h.get("per_participant_difference"), "sign_flip_p_two_sided": h.get("sign_flip_p_two_sided"),
                     "smallest_possible_p": h.get("smallest_possible_p"), "ci_method": h.get("ci_method")},
        "per_skill": a["per_skill"],
        "aa": a["aa"],
        "effort": {"unit": eff["unit"], "actions_coached": eff["actions_coached"]["mean"], "actions_uncoached": eff["actions_uncoached"]["mean"], "detail": eff,
                   "detail_aa": a["effort_aa"]},
        "nudges": {"shown": a["nudges"]["shown"], "followed": a["nudges"]["followed"], "dismissed": a["nudges"]["dismissed"], "detail": a["nudges"]},
        "pipeline_checks": {**aggregate_checks(results_dir / "checks"), "machine_load": load_table(results_dir)},
        "cost": cost,
        "limitations": limitations,
        "meta": {**meta, "expected_n": {"coached": expected[0], "aa": expected[1]}, "n": n, "models": models, "excluded_participants": a["excluded_participants"], "design_problems": a["design_problems"], "aborted_runs": aborted,
                 "note": "Simulated participants (language model), not people. Never the live study. n counts silicon participants."},
    }
    section["analyze_py"] = a["analyze_py"]
    section["floor"] = floor_check(results_dir, rows)
    section["findings"] = findings(section["pipeline_checks"])
    snap = results_dir / "snapshot.json"
    if snap.exists():
        section["meta"]["pipeline_snapshot"] = json.loads(snap.read_text())
    return section


def _fmt(x, nd=3):
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def render_md(s: dict) -> str:
    L: list[str] = []
    w = L.append
    w("# Simulated study: language-model participants, not people" + (f" ({s['meta']['run_label']})" if s.get("meta", {}).get("run_label") else ""))
    w("")
    w(f"**{LABEL}.** This is an end-to-end test of the pipeline under realistic use, a probe of whether the coach's prompts change a language-model "
      "novice's later unassisted behaviour, and an A/A control of the measurement chain. It is **not** the live study, it never fills the `study` "
      "section of the report, and it cannot show that people learn. Pre-registered in `evals/study_sim/PLAN.md` before any model-driven run.")
    w("")
    if s["status"] == "not_run":
        w("**Status: not run.** There is no data.")
        return "\n".join(L) + "\n"
    h, aa = s["headline"], s["aa"]
    w(f"**Status: {s['status']}.** n = {s['n']} coached-arm silicon participants and n = {s['n_aa']} in the A/A sham arm (planned {s['meta'].get('expected_n', {}).get('coached', N_COACHED)} and {s['meta'].get('expected_n', {}).get('aa', N_AA)}). Models: {', '.join(s['meta'].get('models', [])) or 'n/a'}.")
    if s["meta"]["excluded_participants"]:
        w(f"Excluded (harness errors, decided before looking at scores): {', '.join(s['meta']['excluded_participants'])}.")
    w("")
    if s["status"] != "complete":
        w(f"> **Status {s['status']}: fewer participants than planned ({s['meta'].get('expected_n', {}).get('coached', N_COACHED)} coached, {s['meta'].get('expected_n', {}).get('aa', N_AA)} sham). Read the numbers below as a harness or partial-run report; no headline claim is made.**")
        w("")
    for ab in s["meta"].get("aborted_runs", []):
        w(f"> **An earlier run ({ab['id']}) was aborted after GO and is not analysed:** {ab['reason']}. Its spend (US${ab.get('usd_est')}, {ab.get('calls')} calls) counts against the cap. See the amendment log in PLAN.md."
          + (f" {ab['honesty']}" if ab.get("honesty") else ""))
        w("")
    w("## 1. Headline: unassisted skill score, coached skill minus uncoached skill")
    w("")
    w(f"Mean difference **{_fmt(h['mean_difference'])}** (95% t interval {h['ci95']}, n = {s['n']}); exact two-sided sign-flip p = {_fmt(h['sign_flip_p_two_sided'], 6)} "
      f"(smallest possible {h['smallest_possible_p']:.2e}). Scores run from 0 to 1 on the post-test, read from the sandbox state exactly as `analyze.py score` does.")
    if h.get("ci_degenerate"):
        w("The interval has zero width because all differences are identical: read the sign-flip p beside it, and treat the interval with care.")
    w("")
    ci = h.get("ci95") or [None, None]
    if ci[0] is not None and ci[0] > 0:
        w("**Reading:** the interval excludes zero: coached skills scored higher than uncoached ones on the unassisted post-test for these model participants. "
          "This is instruction following plus a self-written note, in a sandbox we built; it says nothing about people.")
    elif ci[1] is not None and ci[1] < 0:
        w("**Reading:** the interval is below zero: coached skills scored LOWER. Reported as found.")
    else:
        w("**Reading:** the interval includes zero. This is consistent with no effect and with a moderate one; with 16 participants a null is not evidence of no effect (see power below).")
    w("")
    fl = s.get("floor") or {}
    if fl.get("coached"):
        c_, a_ = fl["coached"], fl.get("aa") or {}
        w(f"**Floor check (descriptive, not a pre-registered estimate).** Of the {c_['post_tests']} unassisted post-tests in the coached arm, {c_['score_zero']} ({c_['share_zero']:.0%}) scored 0, {c_['hit_the_action_cap']} hit the action cap, "
          f"{c_['sandbox_state_with_no_calculation']} ended with no calculation at all in the sandbox and only {c_['ended_with_a_saved_draft']} with a saved draft; in the A/A arm {a_.get('score_zero')} of {a_.get('post_tests')} scored 0 and {a_.get('hit_the_action_cap')} hit the cap. "
          "**The measurement is at the floor: the headline and the A/A comparison say very little about the coach**, whatever their sign.")
        w("")
    w("| per-participant difference | value |")
    w("|---|---|")
    for p, v in (h.get("per_participant_difference") or {}).items():
        w(f"| {p} | {v} |")
    w("")
    w("## 2. Per skill (different people, same skill; descriptive, no p-value)")
    w("")
    w("| skill | n coached | mean score coached | n uncoached | mean score uncoached | difference | 95% bootstrap interval |")
    w("|---|---|---|---|---|---|---|")
    for k, v in s["per_skill"].items():
        w(f"| {k} | {v['n_coached']} | {_fmt(v['mean_coached'])} | {v['n_uncoached']} | {_fmt(v['mean_uncoached'])} | {_fmt(v['difference'])} | {v['ci95_bootstrap']} |")
    w("")
    w("## 3. A/A sham arm: how biased is the measurement chain?")
    w("")
    rl = aa.get("relabelling") or {}
    w(f"No coaching at all (study mode off in every block), same sequences, n = {aa['n']}. Mean difference {_fmt(aa['mean_difference'])} (95% t interval {aa['ci95']}), "
      f"sign-flip p = {_fmt(aa['sign_flip_p_two_sided'], 6)}. The true effect is zero by construction, so anything away from zero is bias or chance.")
    if rl.get("relabellings"):
        w(f"Over all {rl['relabellings']} balanced relabellings of the A/A participants, the share with sign-flip p < 0.05 was {rl['share_sign_flip_p_below_05']} "
          f"and the share whose interval excluded zero was {rl['share_ci_excludes_zero']} (nominal 0.05).")
    dd = aa["difference_in_differences"]
    w(f"Coached-arm difference minus A/A difference: {_fmt(dd.get('estimate'))} (95% bootstrap interval {dd.get('ci95_bootstrap')}).")
    w("")
    w("## 4. Assisted effort (action counts, not seconds) and nudges")
    w("")
    e = s["effort"]["detail"]
    w(f"Practice actions per case: coached mean {_fmt(e['actions_coached']['mean'], 1)} (n = {e['actions_coached']['n']}), uncoached mean {_fmt(e['actions_uncoached']['mean'], 1)} "
      f"(n = {e['actions_uncoached']['n']}). Model latency is not human speed, so no seconds are reported. Capped cases: practice {e['capped_practice']}, post-test {e['capped_post']}.")
    nd = s["nudges"]["detail"]
    w(f"Coach prompts in the coached blocks: shown {nd['shown']}, followed {nd['followed']}, dismissed (explicit or ignored at case end) {nd['dismissed']} "
      f"(ignored {nd['ignored_at_case_end']}); drawn with a ring {nd['rings_drawn']}; false {nd['false_nudges']}, lagging {nd['lag_prompts']}; coached blocks {nd['coached_blocks']}.")
    w("")
    pc = s["pipeline_checks"]
    w("## 5. Pipeline checks (counts)")
    w("")
    w(f"- Participants run: {pc['participants_run']}. Events landed: {pc['events']['total']} ({pc['events']['from_extension']} from the extension), schema-valid share {_fmt(pc['events']['schema_valid_share'], 4)}; by type {pc['events']['by_type']}.")
    c = pc["coach"]
    w(f"- Coach: {c['polls']} polls, {c['decisions_shown']} prompts shown {c['by_kind']}, outcomes {c['outcomes']}, stuck-signal source {c['p_source']}.")
    r = pc["ring_target"]
    w(f"- Ring target: {r['zone_equals_missing_step_zone']} of {r['annotate_decisions']} annotate decisions carried the zone of the missing step; ring drawn on arrival {r['ring_drawn_on_arrival']}, at some point {r['ring_drawn_at_some_point']}, message only {r['message_only']}; by zone {r['by_zone']}.")
    dl = pc["delay_from_first_note_page_action_to_prompt_s"]
    w(f"- Delay from the participant's first action on the case note page to the prompt: {dl}.")
    fn = pc["false_nudges"]
    w(f"- False nudges (prompt for a step already done more than 6 s earlier): {fn['prompts_for_a_step_already_done_more_than_6s_earlier']} of {fn['of']}; lagging prompts (step done within 6 s): {fn['prompts_lagging_a_step_done_within_6s']}.")
    sm = pc["study_mode_enforcement"]
    w(f"- **Study mode enforcement: {sm['verdict']}.** Polls by mode {sm['polls_by_mode']}; non-silent polls by mode {sm['non_silent_polls_by_mode']}; coach_shown events by block and skill {sm['coach_shown_events_by_block_and_skill']}; violations seen {sm['violations_seen_by_poller'] + sm['violations_in_event_store'] or 'none'}.")
    er = pc["errors"]
    w(f"- Errors: engine {er['engine']}, extension web errors {er['extension_weberrors']}, coach poll errors {er['coach_poll_errors']}, harness tracebacks {er['harness_tracebacks']}, contaminated attempts retried {er['contaminated_attempts_retried']}; exclusions {er['exclusions'] or 'none'}.")
    tv = pc["typed_values_cleaned"]
    w(f"- Typed values cleaned of structured-reply artifacts (PLAN amendment 1, same for every arm): {tv['cleaned']} of {tv['fills_and_selects']} fills and selects ({tv['share']}).")
    ex = pc["engine_events_export"]
    w(f"- **Transcript-free statement:** the engine event files kept for each participant (`results/raw/<participant>/engine_events.jsonl`, {ex['events']} events from {ex['participants_exported']} participants) contain no participant text: they are schema-valid L0 events (timestamps, types, zones, hashed ids, coach step and outcome ids). Strings that were not enum-like and had to be removed: {ex['stripped_values']} (expected 0); export errors: {ex['errors']}. The only model text kept anywhere is each participant's own 280-character note in `actions.jsonl`.")
    ml = pc.get("machine_load") or {}
    if ml.get("available"):
        w(f"- Machine load while the participants ran (1-minute load average on {ml['cpus']} CPUs): min {ml['load1_min']}, max {ml['load1_max']} over {ml['samples']} samples; median at participant start or end {ml['load1_median_at_participant_start_or_end']} (the sampler started after the first participants; {ml.get('participants_with_a_sample_at_start_or_end')} of {ml['participants']} have a sample within a minute of their start or end). Per participant in `load_by_participant.csv`. Timings and the coach's prompt delays are affected (see limitations).")
    sn = s["meta"].get("pipeline_snapshot")
    if sn:
        w(f"- Code under test: a frozen snapshot of git {str(sn.get('git_head', ''))[:8]} plus {sn.get('uncommitted_files_in_snapshot_dirs')} uncommitted files in services/ and packages/ (fingerprint {sn.get('fingerprint')}, taken {sn.get('taken_at')}); engines and sandbox sites ran from that copy for the whole run, the extension from one build per worker.")
    co = pc["consent"]
    w(f"- Consent toggle respected: {co['respected']} (events while off at start {co['events_while_capture_off_at_start']}, after switching off {co['events_after_capture_switched_off']}).")
    k = pc["kill_flag"]
    w(f"- Kill flag: engine reported it in {k['engine_reports_killed']} of {k['n']} participants, coach silent after it in {k['coach_silent_after_kill']}. {k['note']}")
    w("")
    w("### Pipeline findings (about the system, not results)")
    w("")
    for f in s.get("findings", []):
        w(f"- {f['text']}")
    w("")
    w("## 6. Cost")
    w("")
    cs = s.get("cost") or {}
    w(f"Estimated spend US${_fmt(cs.get('usd_est'), 2)} of the US$8 cap (of which US${_fmt(cs.get('of_which_from_aborted_runs'), 2)} was spent by the aborted runs); {cs.get('calls')} model calls ({cs.get('cache_hits')} cache hits); tokens {cs.get('tokens')}. "
      f"Prices {'were set from the environment and are an ASSUMPTION (supplied by the lead, not verified against a bill)' if cs.get('prices_from_env') else 'were conservative defaults (the estimate is an upper bound if the model is cheaper)'}: "
      f"in {cs.get('price_in_per_mtok')}, out {cs.get('price_out_per_mtok')} per million tokens. For reference, the same tokens at the fast-tier rates of 0.75 and 4.50 would cost US${_fmt(cs.get('usd_at_fast_tier_reference_rates'), 2)}.")
    w("")
    w("## 7. What this does not show")
    w("")
    for x in s["limitations"]:
        w(f"- ({x['severity']}) {x['text']}")
    w("")
    w("We do not claim that people learn from the coach, that the coach works on real benefits work, that a model's note is memory, any effect on speed, or statistical "
      "significance beyond what the exact sign-flip test gives. After GO nothing about the prompts, personas, cases, caps, pace, scoring or analysis was changed except the harness repairs and reporting additions in the amendment log of PLAN.md, each dated, the repairs made before any run's participants were analysed by arm.")
    return "\n".join(L) + "\n"


def write_all(results_dir: Path = RESULTS, expected: tuple[int, int] = (N_COACHED, N_AA), specs=None, run_label: str = "", extra_limitations: list | None = None,
              report_path: Path | None = None) -> dict:
    from .analysis_io import check_output_dir, write_provenance_tree

    results_dir = check_output_dir(Path(results_dir))
    report_path = check_output_dir(Path(report_path)) if report_path else check_output_dir(results_dir.parent / "REPORT.md")
    s = build_section(results_dir, expected, specs, run_label, extra_limitations)
    (results_dir / "summary.json").write_text(json.dumps(s, indent=2, default=str) + "\n")
    report_path.write_text(render_md(s))
    write_provenance_tree(results_dir)
    print(f"wrote {results_dir / 'summary.json'} and {report_path} (status {s['status']})")
    return s
