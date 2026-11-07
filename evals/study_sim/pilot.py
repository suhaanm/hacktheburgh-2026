"""The declared feasibility criterion for the exploratory run 5 (PLAN_RUN5.md section 4), as a pure function. Decided by code from pilot data, not by judgement."""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import analysis

BUDGET_USD = 6.0               # pilot + run 5 together, a hard cap (PLAN_RUN5.md amendment 1: US$6, US$1 kept in reserve)
SAFETY_FACTOR = 1.25           # projected cost per participant = pilot mean x 1.25
MIN_SHARE_ABOVE_ZERO = 0.5     # at least half of the pilot post-tests must score above zero
FULL_N = 12
MIN_N = 8                      # fewer than 8 affordable participants: stop (the headline would be on 4 coached)
PILOT_N = 3


def decide(rows: list[dict], pilot_spend_usd: float, budget_usd: float = BUDGET_USD) -> dict:
    """``rows``: the pilot's participants.csv rows (human format). Returns the decision with every number that went into it."""
    ex = set(analysis.excluded_ids(rows))
    people = sorted({r["participant"] for r in rows})
    posts = [r for r in rows if r["participant"] not in ex]
    scores = [analysis.A.skill_score(r) for r in posts]
    above = sum(1 for x in scores if x > 0)
    need = math.ceil(MIN_SHARE_ABOVE_ZERO * len(posts)) if posts else 0
    complete = len(people) == PILOT_N and not ex and len(posts) == 2 * PILOT_N
    off_floor = complete and above >= need
    mean_cost = pilot_spend_usd / PILOT_N
    projected = mean_cost * SAFETY_FACTOR
    afford = int(math.floor(max(budget_usd - pilot_spend_usd, 0.0) / projected)) if projected > 0 else 0
    n_planned = FULL_N if afford >= FULL_N else (MIN_N if afford >= MIN_N else 0)
    proceed = bool(off_floor and n_planned >= MIN_N)
    why = []
    if not complete:
        why.append(f"pilot incomplete or with harness exclusions (participants {len(people)}, excluded {sorted(ex)}, post-tests {len(posts)} of {2 * PILOT_N})")
    elif not off_floor:
        why.append(f"only {above} of {len(posts)} pilot post-tests scored above zero (needed {need})")
    if off_floor and n_planned < MIN_N:
        why.append(f"not affordable: pilot cost US${pilot_spend_usd:.2f} ({mean_cost:.2f} per participant, projected {projected:.2f}); the remaining US${budget_usd - pilot_spend_usd:.2f} pays for {afford} participants, fewer than {MIN_N}")
    return {"pass": proceed, "n_planned": n_planned if proceed else 0, "post_tests": len(posts), "post_tests_above_zero": above, "needed_above_zero": need,
            "pilot_scores": [round(x, 3) for x in scores], "pilot_spend_usd": round(pilot_spend_usd, 3), "mean_cost_per_participant_usd": round(mean_cost, 3),
            "projected_cost_per_participant_usd": round(projected, 3), "affordable_participants": afford, "budget_usd": budget_usd, "reasons_for_stopping": why,
            "criterion": {"min_share_post_tests_above_zero": MIN_SHARE_ABOVE_ZERO, "safety_factor": SAFETY_FACTOR, "full_n": FULL_N, "min_n": MIN_N}}


def decide_from_dir(pilot_dir: Path) -> dict:
    from .analysis_io import write_provenance

    rows = analysis.load_rows(Path(pilot_dir) / "participants.csv")
    cost = json.loads((Path(pilot_dir) / "cost.json").read_text())
    d = decide(rows, float(cost["usd_est"]))
    write_provenance(Path(pilot_dir))
    (Path(pilot_dir) / "PILOT_DECISION.json").write_text(json.dumps(d, indent=1) + "\n")
    (Path(pilot_dir).parent / "PILOT_REPORT.md").write_text(report_md(pilot_dir, d))
    return d


def report_md(pilot_dir: Path, decision: dict) -> str:
    """A short report of the pilot as a pilot (PLAN_RUN5.md section 4): facts only, no coach claim."""
    import glob

    pilot_dir = Path(pilot_dir)
    rows = analysis.load_rows(pilot_dir / "participants.csv")
    L = ["# Run 5 pilot (3 A/A participants, option P2: the fast-tier model at reasoning effort low)", "",
         "**simulated participants (language model), not people.** Exploratory pilot, discarded from every analysis; it only decides whether run 5 proceeds. The coach was silent in every block.", ""]
    L += ["| participant | block | skill | post-test score | post-test actions | post-test ended | calculations in the sandbox | saved draft |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: (x["participant"], x["block"])):
        st = pilot_dir / "raw" / f"{r['participant']}-block{int(r['block'])}-post.json"
        d = __import__("json").loads(st.read_text()) if st.exists() else {}
        L.append(f"| {r['participant']} | {int(r['block'])} | {r['skill']} | {int(r['post_checks_done'])}/{int(r['post_checks_possible'])} | {int(r['post_actions'])} | {r['post_end']} | {len(d.get('calculations', []))} | {'yes' if d.get('notes') else 'no'} |")
    L += ["", f"**Declared criterion** (PLAN_RUN5.md section 4, decided by code): all three complete without harness exclusion, at least {decision['needed_above_zero']} of {decision['post_tests']} post-tests above zero, and the remaining budget pays for at least 8 participants.",
          f"**Result:** {decision['post_tests_above_zero']} of {decision['post_tests']} post-tests scored above zero. Pilot spend US${decision['pilot_spend_usd']} (US${decision['mean_cost_per_participant_usd']} per participant at the assumed 0.75 and 4.50 per million tokens), "
          f"affordable participants for the main stage {decision['affordable_participants']}. **Decision: {'PROCEED, n = ' + str(decision['n_planned']) if decision['pass'] else 'STOP, there is no run 5 proper'}.**"]
    if decision["reasons_for_stopping"]:
        L += ["", "Reasons: " + "; ".join(decision["reasons_for_stopping"]) + "."]
    L += ["", "A pass would not have been evidence about the coach, and a stop is not either: it only says the stronger participant is or is not off the floor. No coach claim is made."]
    return "\n".join(L) + "\n"
