#!/usr/bin/env python
"""Pre-specified analysis of the live study (EVL-2, EVL-3, EVL-5). Written and tested BEFORE any data exists.

    uv run python evals/study/analyze.py evals/study/results/participants.csv

Reads one CSV (columns in ANALYSIS_PLAN.md), writes evals/study/results/summary.json next to it and prints a
short text summary. The headline (unassisted skill score on the later matched case) and the assisted speed
are computed and reported SEPARATELY and never combined. n is stated everywhere. No significance claim is
made: with four participants the exact two-sided sign-flip p cannot go below 0.125.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from scipy import stats

HERE = Path(__file__).resolve().parent
LEVEL = 0.95
POSSIBLE = {"cliff": 2, "reconcile": 1}  # check opportunities in an unassisted post-test case (two calculators)
COLUMNS = ["participant", "sequence", "block", "skill", "condition", "practice_case", "post_case",
           "practice_seconds", "practice_capped", "post_seconds", "post_capped",
           "post_checks_done", "post_checks_possible", "nudges_shown", "nudges_followed", "nudges_dismissed",
           "exclusion", "notes"]


def load(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("block", "practice_seconds", "post_seconds", "post_checks_done", "post_checks_possible",
                  "nudges_shown", "nudges_followed", "nudges_dismissed"):
            r[k] = float(r[k]) if r.get(k, "") != "" else math.nan
        for k in ("practice_capped", "post_capped"):
            r[k] = str(r.get(k, "")).strip().lower() in ("1", "true", "yes")
    return rows


def design_problems(rows: list[dict], assignments: dict | None = None) -> list[str]:
    """Structural checks, run before any number is computed."""
    out: list[str] = []
    missing = [c for c in COLUMNS if rows and c not in rows[0]]
    if missing:
        return [f"missing columns: {missing}"]
    by_p: dict[str, list[dict]] = {}
    for r in rows:
        by_p.setdefault(r["participant"], []).append(r)
    for p, rs in by_p.items():
        blocks = sorted(int(r["block"]) for r in rs)
        if blocks != [1, 2]:
            out.append(f"{p}: needs exactly blocks 1 and 2, has {blocks}")
        skills = {r["skill"] for r in rs}
        if skills != {"cliff", "reconcile"}:
            out.append(f"{p}: each participant must do both skills, has {sorted(skills)}")
        conds = sorted(r["condition"] for r in rs)
        if conds != ["coached", "uncoached"]:
            out.append(f"{p}: needs one coached and one uncoached block, has {conds}")
        for r in rs:
            if r["post_checks_possible"] != POSSIBLE.get(r["skill"]):
                out.append(f"{p} block {int(r['block'])}: post_checks_possible must be {POSSIBLE.get(r['skill'])} for {r['skill']}")
            if not (0 <= r["post_checks_done"] <= r["post_checks_possible"]):
                out.append(f"{p} block {int(r['block'])}: post_checks_done outside 0..possible")
    if assignments:
        for p, rs in by_p.items():
            plan = assignments["participants"].get(p)
            if not plan:
                out.append(f"{p}: not in assignments.json")
                continue
            for r in rs:
                b = next((x for x in plan["blocks"] if x["block"] == int(r["block"])), None)
                if not b or (b["skill"], b["condition"], b["practice_case"], b["post_case"]) != (r["skill"], r["condition"], r["practice_case"], r["post_case"]):
                    out.append(f"{p} block {int(r['block'])}: differs from the fixed assignment (a protocol deviation: record it in notes)")
    return out


def score_post_test(skill: str, state: dict) -> tuple[int, int]:
    """Objective post-test scoring from the sandbox state saved right after the block (GET /__state).
    cliff: distinct calculators (a, b) whose cliff panel was opened during the block; reconcile: 1 if a saved
    note has reconciliation 'discrepancy' (the form's default is 'agree'). The state is reset before each case."""
    if skill == "cliff":
        return len({o.get("site") for o in state.get("cliff_opens", []) if o.get("site") in ("a", "b")}), POSSIBLE["cliff"]
    if skill == "reconcile":
        notes = (state.get("notes") or {}).values()
        return int(any(n.get("reconciliation") == "discrepancy" for n in notes)), POSSIBLE["reconcile"]
    raise ValueError(f"unknown skill {skill!r}")


def skill_score(r: dict) -> float:
    return r["post_checks_done"] / r["post_checks_possible"]


def sign_flip_p(d: list[float]) -> float:
    """Exact two-sided randomisation p for the mean paired difference (all 2^n sign patterns)."""
    n = len(d)
    obs = abs(sum(d))
    total = 0
    hits = 0
    for signs in itertools.product((1, -1), repeat=n):
        total += 1
        if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12:
            hits += 1
    return hits / total


def t_interval(d: list[float], level: float = LEVEL) -> tuple[float, float, float]:
    n = len(d)
    mean = sum(d) / n
    if n < 2:
        return mean, math.nan, math.nan
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
    half = stats.t.ppf(1 - (1 - level) / 2, n - 1) * sd / math.sqrt(n)
    return mean, mean - half, mean + half


def paired(rows: list[dict], value) -> dict[str, float]:
    """participant -> value(coached block) - value(uncoached block)."""
    out: dict[str, float] = {}
    by_p: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_p.setdefault(r["participant"], {})[r["condition"]] = r
    for p, d in by_p.items():
        if "coached" in d and "uncoached" in d:
            out[p] = value(d["coached"]) - value(d["uncoached"])
    return out


def analyse(rows: list[dict], assignments: dict | None = None) -> dict:
    problems = design_problems(rows, assignments)
    included = [r for r in rows if not str(r.get("exclusion", "")).strip()]
    excluded = sorted({r["participant"] for r in rows if str(r.get("exclusion", "")).strip()})
    # a participant with any excluded block is excluded entirely (the plan's rule)
    included = [r for r in included if r["participant"] not in excluded]
    people = sorted({r["participant"] for r in included})

    head = paired(included, skill_score)
    d = [head[p] for p in sorted(head)]
    mean, lo, hi = t_interval(d)
    assisted = paired(included, lambda r: r["practice_seconds"])
    ad = [assisted[p] for p in sorted(assisted)]
    am, alo, ahi = t_interval(ad)
    post_t = paired(included, lambda r: r["post_seconds"])
    pd_ = [post_t[p] for p in sorted(post_t)]
    pm, plo, phi = t_interval(pd_)

    def block_view(r: dict) -> dict:
        return {"participant": r["participant"], "block": int(r["block"]), "skill": r["skill"], "condition": r["condition"],
                "post_score": round(skill_score(r), 3), "post_checks": f"{int(r['post_checks_done'])}/{int(r['post_checks_possible'])}",
                "practice_seconds": r["practice_seconds"], "practice_capped": r["practice_capped"],
                "post_seconds": r["post_seconds"], "post_capped": r["post_capped"]}

    n = len(people)
    meta = {"origin": "real", "n": n, "n_unit": "people", "split": "within-subject, counterbalanced (2 skills x 2 orders)",
            "interval_level": LEVEL, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": (f"n = {n} teammates, not target workers; synthetic households on sandbox sites. Estimation only: with "
                     f"{n} participants the exact sign-flip p cannot go below {2 / 2 ** max(n, 1):.3f}. Not evidence that novices become experts.")}
    return {
        "meta": meta,
        "design_problems": problems,
        "excluded_participants": excluded,
        "headline_unassisted": {
            "label": "Unassisted skill score on a later matched case (coached skill minus uncoached skill), per participant",
            "per_participant_difference": {p: round(head[p], 3) for p in sorted(head)},
            "mean_difference": round(mean, 3), "ci95": [None if math.isnan(lo) else round(lo, 3), None if math.isnan(hi) else round(hi, 3)],
            "ci_method": f"t interval, df = {max(n - 1, 0)}, on the per-participant differences (assumes roughly normal differences, which four points cannot check)",
            "sign_flip_p_two_sided": round(sign_flip_p(d), 4) if d else None,
            "smallest_possible_p": round(2 / 2 ** n, 4) if n else None,
            "blocks": [block_view(r) for r in sorted(included, key=lambda r: (r["participant"], r["block"]))],
        },
        "assisted_speed": {
            "label": "ASSISTED practice time in seconds (coached minus uncoached), reported separately from the headline",
            "per_participant_difference_s": {p: round(assisted[p], 1) for p in sorted(assisted)},
            "mean_difference_s": round(am, 1), "ci95": [None if math.isnan(alo) else round(alo, 1), None if math.isnan(ahi) else round(ahi, 1)],
            "capped_blocks": sum(1 for r in included if r["practice_capped"]),
        },
        "unassisted_speed": {
            "label": "UNASSISTED post-test time in seconds (coached minus uncoached)",
            "per_participant_difference_s": {p: round(post_t[p], 1) for p in sorted(post_t)},
            "mean_difference_s": round(pm, 1), "ci95": [None if math.isnan(plo) else round(plo, 1), None if math.isnan(phi) else round(phi, 1)],
            "capped_blocks": sum(1 for r in included if r["post_capped"]),
        },
        "coach_use": {
            "nudges_shown": int(sum(r["nudges_shown"] for r in included if r["condition"] == "coached" and not math.isnan(r["nudges_shown"]))),
            "nudges_followed": int(sum(r["nudges_followed"] for r in included if r["condition"] == "coached" and not math.isnan(r["nudges_followed"]))),
            "nudges_dismissed": int(sum(r["nudges_dismissed"] for r in included if r["condition"] == "coached" and not math.isnan(r["nudges_dismissed"]))),
        },
        "not_claimed": ["an effect on real benefits work", "that novices become experts", "generalisation beyond these four people",
                        "statistical significance", "an effect on speed (assisted speed is descriptive only)"],
    }


def main(argv: list[str]) -> int:
    if argv and argv[0] == "score":  # analyze.py score <skill> <state.json>: print post_checks_done and _possible
        done, possible = score_post_test(argv[1], json.loads(Path(argv[2]).read_text()))
        print(json.dumps({"post_checks_done": done, "post_checks_possible": possible}))
        return 0
    path = Path(argv[0]) if argv else HERE / "results" / "participants.csv"
    if not path.is_file():
        print(f"no results file at {path}: nothing to analyse (no data yet)")
        return 1
    assignments_path = HERE / "assignments.json"
    assignments = json.loads(assignments_path.read_text()) if assignments_path.is_file() else None
    result = analyse(load(path), assignments)
    out = path.with_name("summary.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    h = result["headline_unassisted"]
    print(f"n = {result['meta']['n']} (excluded: {result['excluded_participants'] or 'none'})")
    print(f"HEADLINE (unassisted, later matched case): mean difference {h['mean_difference']} (95% CI {h['ci95']}), per participant {h['per_participant_difference']}")
    a = result["assisted_speed"]
    print(f"ASSISTED speed (separate): mean difference {a['mean_difference_s']} s (95% CI {a['ci95']})")
    if result["design_problems"]:
        print("DESIGN PROBLEMS:", *result["design_problems"], sep="\n  ")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
