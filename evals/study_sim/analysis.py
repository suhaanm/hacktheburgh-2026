"""The pre-registered analysis of the simulated study (PLAN section 7). Reuses ``evals/study/analyze.py`` (imported, never edited) on a CSV in the
human format plus ``arm, persona, model``. Every number carries its n. Plain functions, tested on made-up numbers before any run."""
from __future__ import annotations

import itertools
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

from .design import STUDY, SEED, assignments_for_design_check, build_participants

sys.path.insert(0, str(STUDY))
import analyze as A  # noqa: E402

BOOT = 10000


def load_rows(path: Path) -> list[dict]:
    return A.load(Path(path))


def split_arms(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    return [r for r in rows if r.get("arm") == "coached"], [r for r in rows if r.get("arm") == "aa"]


def excluded_ids(rows: list[dict]) -> list[str]:
    return sorted({r["participant"] for r in rows if str(r.get("exclusion", "")).strip()})


def _included(rows: list[dict]) -> list[dict]:
    ex = set(excluded_ids(rows))
    return [r for r in rows if r["participant"] not in ex]


def diffs(rows: list[dict]) -> dict[str, float]:
    """participant -> score(nominally coached block) - score(nominally uncoached block), on the unassisted post-test."""
    return A.paired(_included(rows), A.skill_score)


def interval(d: list[float]) -> dict:
    n = len(d)
    mean, lo, hi = A.t_interval(d) if n >= 2 else ((sum(d) / n if n else math.nan), math.nan, math.nan)
    degenerate = bool(n >= 2 and not math.isnan(lo) and abs(hi - lo) < 1e-12)
    return {"n": n, "mean_difference": None if math.isnan(mean) else round(mean, 4),
            "ci95": [None if math.isnan(lo) else round(lo, 4), None if math.isnan(hi) else round(hi, 4)],
            "ci_method": f"t interval, df = {max(n - 1, 0)}, on the per-participant differences",
            "ci_degenerate": degenerate,
            "sign_flip_p_two_sided": (round(A.sign_flip_p(d), 6) if 0 < n <= 20 else None),
            "smallest_possible_p": (2 / 2 ** n) if n else None}


def headline(rows: list[dict]) -> dict:
    d = diffs(rows)
    out = interval([d[p] for p in sorted(d)])
    out["per_participant_difference"] = {p: round(d[p], 3) for p in sorted(d)}
    return out


def _boot_mean_diff(a: list[float], b: list[float], seed: int = SEED, reps: int = BOOT) -> list[float | None]:
    if len(a) < 2 or len(b) < 2:
        return [None, None]
    rng = np.random.RandomState(seed)
    xa, xb = np.array(a, float), np.array(b, float)
    ma = xa[rng.randint(0, len(xa), (reps, len(xa)))].mean(axis=1)
    mb = xb[rng.randint(0, len(xb), (reps, len(xb)))].mean(axis=1)
    lo, hi = np.percentile(ma - mb, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def per_skill(rows: list[dict]) -> dict:
    """For each skill: mean post-test score where it was coached vs where it was not (different people, same skill). Descriptive: a
    percentile bootstrap interval on the difference of means, no p-value."""
    inc = _included(rows)
    out = {}
    for skill in ("cliff", "reconcile"):
        c = [A.skill_score(r) for r in inc if r["skill"] == skill and r["condition"] == "coached"]
        u = [A.skill_score(r) for r in inc if r["skill"] == skill and r["condition"] == "uncoached"]
        out[skill] = {"n_coached": len(c), "n_uncoached": len(u),
                      "mean_coached": round(statistics.fmean(c), 4) if c else None, "mean_uncoached": round(statistics.fmean(u), 4) if u else None,
                      "difference": round(statistics.fmean(c) - statistics.fmean(u), 4) if c and u else None,
                      "ci95_bootstrap": _boot_mean_diff(c, u), "ci_method": f"percentile bootstrap, {BOOT} resamples, seed {SEED}, people resampled within group"}
    return out


def diff_in_diff(coached_rows: list[dict], aa_rows: list[dict]) -> dict:
    """Secondary: coached-arm mean difference minus A/A mean difference (the bias-corrected contrast), percentile bootstrap."""
    a = list(diffs(coached_rows).values())
    b = list(diffs(aa_rows).values())
    if len(a) < 2 or len(b) < 2:
        return {"estimate": None, "ci95_bootstrap": [None, None], "n_coached": len(a), "n_aa": len(b)}
    return {"estimate": round(statistics.fmean(a) - statistics.fmean(b), 4), "ci95_bootstrap": _boot_mean_diff(a, b, seed=SEED + 1),
            "n_coached": len(a), "n_aa": len(b), "ci_method": f"percentile bootstrap, {BOOT} resamples, seed {SEED + 1}"}


def aa_relabelling(aa_rows: list[dict]) -> dict:
    """The A/A false-positive rate of the pre-registered analysis, conditional on the A/A scores. Each A/A participant has one cliff score
    and one reconcile score and no coaching at all, so the 'coached skill' label is arbitrary. Enumerate every balanced relabelling (half
    the participants labelled cliff-coached) and run the headline analysis on each: the share with sign-flip p < 0.05 and the share whose
    t interval excludes 0 are the empirical false-positive rates of the analysis on these scores (exact, no sampling)."""
    inc = _included(aa_rows)
    by: dict[str, dict[str, float]] = {}
    for r in inc:
        by.setdefault(r["participant"], {})[r["skill"]] = A.skill_score(r)
    ids = sorted(p for p, v in by.items() if set(v) == {"cliff", "reconcile"})
    n = len(ids)
    if n < 4 or n % 2:
        return {"n": n, "note": "needs an even number of A/A participants (at least 4)"}
    base = {p: by[p]["cliff"] - by[p]["reconcile"] for p in ids}
    fp_p = fp_ci = total = 0
    for chosen in itertools.combinations(ids, n // 2):
        d = [base[p] if p in chosen else -base[p] for p in ids]
        total += 1
        fp_p += A.sign_flip_p(d) < 0.05
        m, lo, hi = A.t_interval(d)
        fp_ci += (not math.isnan(lo)) and (lo > 0 or hi < 0)
    return {"n": n, "relabellings": total, "share_sign_flip_p_below_05": round(fp_p / total, 4), "share_ci_excludes_zero": round(fp_ci / total, 4),
            "note": "conditional on these A/A scores; the nominal rate is 0.05. A rate above that means the analysis would raise false alarms on this measurement chain."}


def aa_section(aa_rows: list[dict], coached_rows: list[dict]) -> dict:
    h = headline(aa_rows) if aa_rows else {"n": 0}
    return {"n": h.get("n", 0), "mean_difference": h.get("mean_difference"), "ci95": h.get("ci95"), "ci_degenerate": h.get("ci_degenerate"),
            "sign_flip_p_two_sided": h.get("sign_flip_p_two_sided"), "per_participant_difference": h.get("per_participant_difference"),
            "relabelling": aa_relabelling(aa_rows) if aa_rows else None, "difference_in_differences": diff_in_diff(coached_rows, aa_rows),
            "false_positive_note": ("The sham arm has no coaching, so its true effect is zero by construction: a mean difference away from zero, "
                                    "or a sign-flip p below 0.05, is bias or chance in the measurement chain, not a coach effect.")}


def effort(rows: list[dict]) -> dict:
    """ACTION COUNTS (never seconds): practice actions by actual condition, and post-test actions by nominal condition. Descriptive only."""
    inc = _included(rows)

    def stat(vals: list[float]) -> dict:
        return {"n": len(vals), "mean": round(statistics.fmean(vals), 2) if vals else None, "median": statistics.median(vals) if vals else None}

    c = [float(r["practice_actions"]) for r in inc if r.get("actual_condition") == "coached"]
    u = [float(r["practice_actions"]) for r in inc if r.get("actual_condition") == "uncoached"]
    pc = [float(r["post_actions"]) for r in inc if r["condition"] == "coached"]
    pu = [float(r["post_actions"]) for r in inc if r["condition"] == "uncoached"]
    return {"unit": "actions (model latency is not human speed, so no seconds)", "actions_coached": stat(c), "actions_uncoached": stat(u),
            "unassisted_post_actions_coached_skill": stat(pc), "unassisted_post_actions_uncoached_skill": stat(pu),
            "capped_practice": sum(1 for r in inc if r["practice_capped"]), "capped_post": sum(1 for r in inc if r["post_capped"])}


def nudges(rows: list[dict]) -> dict:
    inc = [r for r in _included(rows) if r.get("actual_condition") == "coached"]
    f = lambda k: int(sum(float(r.get(k) or 0) for r in inc))  # noqa: E731
    return {"shown": f("nudges_shown"), "followed": f("nudges_followed"), "dismissed": f("nudges_dismissed"), "ignored_at_case_end": f("nudges_ignored"),
            "false_nudges": f("false_nudges"), "lag_prompts": f("lag_prompts"), "rings_drawn": f("rings_drawn"), "coached_blocks": len(inc)}


def analyse_all(rows: list[dict]) -> dict:
    specs = build_participants()
    design = assignments_for_design_check(specs)
    coached, aa = split_arms(rows)
    ha = A.analyse(coached, design) if coached else None
    return {
        "headline": headline(coached) if coached else {"n": 0},
        "design_problems": (ha["design_problems"] if ha else []) + (A.analyse(aa, design)["design_problems"] if aa else []),
        "excluded_participants": excluded_ids(rows),
        "per_skill": per_skill(coached),
        "aa": aa_section(aa, coached),
        "effort": effort(coached),
        "effort_aa": effort(aa) if aa else None,
        "nudges": nudges(coached),
        "analyze_py": {"coached_arm": {k: ha[k] for k in ("headline_unassisted", "coach_use")} if ha else None,
                       "note": "analyze.py's own output for the coached arm. Its 'assisted_speed' and 'unassisted_speed' sections are not reproduced: in this study "
                               "those CSV columns hold ACTION COUNTS, not seconds."},
    }
