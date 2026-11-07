"""summary.json and REPORT.md of a role study. Everything is labelled LABEL. Nothing here touches the live study's ``study`` section; every write is checked by
``analysis_io.check_output_dir`` and every folder of the results tree gets a PROVENANCE.json."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from evals.study_sim import analysis_io as sim_io

from . import LABEL
from .analysis import analyse_role
from .analysis_rows import load_rows

LIMITATIONS = [
    {"id": "roles-not-people", "severity": "high", "text": "The participants are language-model agents, not people. Nothing here shows that people learn from the coach, and nothing here is a user study."},
    {"id": "roles-memory-is-a-note", "severity": "high",
     "text": "The only 'memory' a participant has is a note of at most 280 characters that it wrote itself after the practice case and sees again at the post-test of the same skill. Every case starts "
             "from a fresh model context. That is a prompt, not learning in any human sense."},
    {"id": "roles-instruction-following", "severity": "high",
     "text": "A model that is shown 'try the edges before you commit' can simply do what it says. A higher post-test score after coaching can be instruction following plus a self-written note, not retention of a skill."},
    {"id": "roles-authored-by-us", "severity": "high", "text": "The coach prompts, the sandboxes, the tasks, the oracles and the personas were all written by us."},
    {"id": "roles-power", "severity": "high",
     "text": "The design is small (at most 12 coached-arm participants per role). A null or small result does not show that the coach has no effect; a result counts as clear only if the interval excludes zero."},
    {"id": "roles-one-model-family", "severity": "medium",
     "text": "One model (id recorded in the CSV), one persona family, the participant tier chosen by a feasibility pilot. The results are about prompts and sandboxes, not about people or other models."},
    {"id": "roles-timing", "severity": "medium", "text": "Timing is not human: each action is followed by a fixed pause and the model's latency varies, so effort is reported as ACTION COUNTS."},
    {"id": "roles-renderer", "severity": "medium",
     "text": "The coach is real but the overlay renderer is simulated: a ring is drawn only when an element carrying the target zone exists on the page (the test editor zone exists only while the test file is open)."},
    {"id": "roles-oracle", "severity": "medium", "text": "Scores are discrete (0, 1, 2 points per case), so ties and ceilings are likely and the t interval is not exact."},
]


def _stats(vals: list[float]) -> dict:
    return {"n": len(vals), "median": round(statistics.median(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2)} if vals else {"n": 0}


def aggregate_checks(checks_dir: Path) -> dict:
    files = sorted(Path(checks_dir).glob("p_*.json")) if Path(checks_dir).is_dir() else []
    docs = [json.loads(f.read_text()) for f in files]
    tot = {"events": 0, "from_extension": 0, "schema_invalid": 0}
    types: dict[str, int] = {}
    zones: dict[str, int] = {}
    coach_rows: list[dict] = []
    polls = nonsilent = 0
    by_mode = {"train": 0, "post_test": 0, "off": 0}
    ns_by_mode = {"train": 0, "post_test": 0, "off": 0}
    violations: list[str] = []
    store_viol: list[str] = []
    eng = {"tracebacks": 0, "error_lines": 0, "events_post_failures": 0}
    consent_start: list[int] = []
    consent_end: list[int] = []
    kill = {"n": 0, "engine_reports_killed": 0, "coach_silent_after_kill": 0}
    excl: list[str] = []
    capped = {"pre": 0, "practice": 0, "post": 0}
    contaminated = harness_errors = weberrors = 0
    task_starts = task_ends = 0
    for d in docs:
        c = d["checks"]
        e = c.get("events", {})
        tot["events"] += e.get("total", 0)
        tot["from_extension"] += e.get("from_extension", 0)
        tot["schema_invalid"] += e.get("schema_invalid", 0)
        task_starts += e.get("task_starts", 0)
        task_ends += e.get("task_ends", 0)
        for k, v in (e.get("types") or {}).items():
            types[k] = types.get(k, 0) + v
        for k, v in (e.get("zones") or {}).items():
            zones[k] = zones.get(k, 0) + v
        co = c.get("coach", {})
        coach_rows += co.get("shown", [])
        polls += co.get("polls", 0)
        nonsilent += co.get("decisions_non_silent", 0)
        for m in by_mode:
            by_mode[m] += (co.get("polls_by_mode") or {}).get(m, 0)
            ns_by_mode[m] += (co.get("non_silent_by_mode") or {}).get(m, 0)
        violations += [f"{d['participant']}: {v}" for v in c.get("study_mode_violations", [])]
        store_viol += [f"{d['participant']}: {v}" for v in c.get("study_mode_enforcement_from_store", [])]
        for k, v in (c.get("engine_log") or {}).items():
            eng[k] = eng.get(k, 0) + v
        weberrors += sum(1 for x in c.get("errors", []) if str(x).startswith("weberror"))
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
        if d.get("exclusion"):
            excl.append(f"{d['participant']}: {d['exclusion']}")
        for case in d.get("cases", []):
            if case.get("capped"):
                capped[case["phase"]] += 1
    annotate = [r for r in coach_rows if r.get("action") in ("annotate", "takeover_offer")]
    return {
        "participants_run": len(docs), "events": {**tot, "by_type": types, "by_zone": zones, "task_starts": task_starts, "task_ends": task_ends},
        "coach": {"decisions_non_silent": nonsilent, "polls": polls, "shown": len(coach_rows), "annotate": len(annotate), "outcomes": {o: sum(1 for r in coach_rows if r.get("outcome") == o) for o in ("followed", "dismissed", "ignored")},
                  "false_nudges": sum(1 for r in coach_rows if r.get("false") == "false"), "lagging": sum(1 for r in coach_rows if r.get("false") == "lag"),
                  "rings_found": sum(1 for r in annotate if r.get("ring_found")), "zones_served": {z: sum(1 for r in annotate if r.get("zone") == z) for z in sorted({str(r.get("zone")) for r in annotate})},
                  "delay_s": _stats([r["delay_s"] for r in coach_rows if r.get("delay_s") is not None]), "polls_by_mode": by_mode, "non_silent_by_mode": ns_by_mode},
        "study_mode_enforcement": {"violations": violations, "store_violations": store_viol, "non_silent_in_post_or_off": ns_by_mode["post_test"] + ns_by_mode["off"]},
        "errors": {"engine": eng, "weberrors": weberrors, "harness_tracebacks": harness_errors, "contaminated_attempts": contaminated, "exclusions": excl, "capped_cases": capped},
        "consent": {"events_with_consent_off_at_start": consent_start, "events_after_switched_off": consent_end}, "kill_flag": kill,
    }


def write_all(role: str, results_dir: Path, *, label: str = LABEL) -> dict:
    results_dir = sim_io.check_output_dir(results_dir)
    csv_path = results_dir / "participants.csv"
    rows = load_rows(csv_path) if csv_path.exists() else []
    a = analyse_role(role, rows) if rows else {"role": role, "headline": {"n": 0}}
    cost = json.loads((results_dir / "cost.json").read_text()) if (results_dir / "cost.json").exists() else {"usd_est": 0.0, "calls": 0, "tokens": {"in": 0, "out": 0}}
    checks = aggregate_checks(results_dir / "checks")
    n = a.get("headline", {}).get("n", 0)
    summary = {"status": "ok" if n >= 8 else ("harness_failure" if rows else "not_run"), "role": role, "label": label, "n": n, "n_aa": (a.get("aa") or {}).get("n", 0), **a, "pipeline_checks": checks, "cost": cost,
               "limitations": LIMITATIONS,
               "meta": {"origin": "simulated_llm", "n": n, "n_unit": "silicon participants", "label": label, "interval_level": 0.95, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "note": "Simulated participants are not people. This never stands in for the live study."}}
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    (results_dir / "REPORT.md").write_text(render_markdown(summary))
    sim_io.write_provenance_tree(results_dir)
    return summary


def _fmt_ci(h: dict) -> str:
    ci = h.get("ci95") or [None, None]
    return f"{h.get('mean_difference')} (95% t interval {ci[0]} to {ci[1]}; exact sign-flip p {h.get('sign_flip_p_two_sided')}; n = {h.get('n')})"


def render_markdown(s: dict) -> str:
    h, aa = s.get("headline", {}), s.get("aa") or {}
    L = [f"# Role study: {s['role']}", "", f"**{s['label']}**", "", f"Status: {s['status']}. Coached-arm participants: {s['n']}; A/A sham participants: {s['n_aa']}. Cost estimate: ${s['cost'].get('usd_est')}.", ""]
    if s["status"] == "harness_failure":
        L += ["Fewer than 8 coached-arm participants survived: no headline claim is made.", ""]
    L += ["## Primary outcome", "", "Post-test oracle points (0 to 2) of the coached skill minus the uncoached skill, per participant, mean over participants:", "", _fmt_ci(h), ""]
    if h.get("ci_degenerate"):
        L += ["The interval has zero width (all differences identical): read the sign-flip p.", ""]
    L += ["## Secondary", "", "Change pre to post, coached minus uncoached skill (fractions of 2 points): " + _fmt_ci(s.get("change_pre_to_post", {})), "", "### Per skill (descriptive)", ""]
    for k, v in (s.get("per_skill") or {}).items():
        L.append(f"- {k}: baseline pre mean {v['baseline_pre_mean_points']} (floor share {v['baseline_share_zero']}, full share {v['baseline_share_full']}); post coached {v['post_mean_coached']} vs uncoached "
                 f"{v['post_mean_uncoached']} (difference {v['difference_points']}, bootstrap {v['ci95_bootstrap_points']}); skill check done pre {v['skill_check_done_pre']}, post coached "
                 f"{v['skill_check_done_post_coached']}, post uncoached {v['skill_check_done_post_uncoached']}.")
    L += ["", "### Outcomes", "", f"pre: {json.dumps(s.get('outcomes', {}).get('pre'))}", "", f"post: {json.dumps(s.get('outcomes', {}).get('post'))}", "", f"false claims: {json.dumps(s.get('false_claims'))}", ""]
    L += ["## A/A sham arm (the coach is silent in every block)", "", f"Mean difference {aa.get('mean_difference')}, interval {aa.get('ci95')}, sign-flip p {aa.get('sign_flip_p_two_sided')}; difference in differences "
          f"{json.dumps(aa.get('difference_in_differences'))}; relabelling false-positive check {json.dumps(aa.get('relabelling'))}.", ""]
    L += ["## Pipeline checks", "", "```json", json.dumps(s.get("pipeline_checks"), indent=1, default=str)[:6000], "```", "", "## Limits (read before quoting any number)", ""]
    L += [f"- {x['text']}" for x in s["limitations"]]
    return "\n".join(L) + "\n"
