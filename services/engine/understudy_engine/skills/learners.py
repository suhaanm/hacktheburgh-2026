"""Skill tracing on the learner-trajectory data (3 novices x 30 cases, three cases a day for ten days; ANA-13, COA-3).

engine-data planted five deficits whose per-case probability falls with practice (faster after a followed coach prompt),
one learner (p_learn02) is absent for three days after case 15, and `truth.json` carries the true curve
skill = 1 - mean_d(p_d / p0_d), exactly 0 at case 1 by construction. The tracker never sees any of it.

What the tracker sees, per case and per deficit-relevant cog:
    error     the deficit showed up in that case (and no followed coach prompt covered it)
    assisted  a coach prompt for it was shown AND followed (the help level engine counts that as neutral)
    clean     the deficit did not show up
Cogs, one per deficit: CHECK_CLIFF, READ_RESULT, SEARCH, COPY_TO_NOTE, IDLE (the deficit's primary cog).

Checks (honest about what they can show with 3 learners): level trajectories, Spearman against the true curve with an
interval, a clock-only control, a cross-sectional rank check that a time trend cannot fake, the absence step, and the
effect of a followed prompt on the next case. `learner_series` / `learner_state` give the Today and work-graph screens the
per-case tracker state.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from understudy_engine.skills import tracing as T
from understudy_engine.skills.tracker import SkillTracker
from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta
from understudy_engine.trust.stats import wilson_interval

DEFICIT_COG = {
    "skipped_check_cliff": "CHECK_CLIFF",
    "repeated_read_result": "READ_RESULT",
    "search_loop": "SEARCH",
    "copy_error": "COPY_TO_NOTE",
    "idle_before_enter": "IDLE",
}
COGS = tuple(DEFICIT_COG.values())
TYPES = tuple(DEFICIT_COG)


def _ts(s: str) -> float:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_learner_truth(root: Path | str | None = None) -> dict:
    from understudy_engine.store import data_dir
    p = (Path(root) if root else data_dir()) / "synthetic" / "learners" / "truth.json"
    if not p.exists():
        raise FileNotFoundError(f"learner data missing: {p} (uv run understudy synth --learners)")
    return json.loads(p.read_text())


def _outcome(trace: dict, deficit: str) -> str:
    present = {d["type"] for d in trace["deficits"]}
    coach = {c["deficit"]: c for c in trace.get("coach", [])}
    c = coach.get(deficit)
    if c and c["shown"] and c["followed"]:
        return "assisted"
    return "error" if deficit in present else "clean"


def learner_series(person: str, root: Path | str | None = None, params: T.TracingParams = T.DEFAULT,
                   truth: dict | None = None) -> list[dict]:
    """Per case: tracker state after that case. Fields: case, t (ISO), level (overall = lowest cog level), chip, mastery by cog,
    level by cog, mean mastery, the planted true skill and p_deficit (for comparison only), outcomes seen."""
    truth = truth or load_learner_truth(root)
    traces = sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])
    if not traces:
        raise KeyError(person)
    tracker = SkillTracker(params)
    out = []
    for tr in traces:
        t_end = _ts(tr["t1"])
        outcomes = {}
        step = {}
        for d in TYPES:
            cog = DEFICIT_COG[d]
            outcomes[cog] = _outcome(tr, d)
            step[cog] = tracker.observe(cog, outcomes[cog], t_end)
        snap = tracker.snapshot(t_end)
        cs = tracker.coach_state(list(COGS), t_end)
        out.append({
            "case": tr["case"], "t": tr["t1"], "level": cs["level"], "chip": cs["chip"],
            "level_by_cog": {c: snap[c]["level"] for c in COGS}, "mastery": {c: snap[c]["mastery"] for c in COGS},
            "mean_mastery": float(np.mean([snap[c]["mastery"] for c in COGS])),
            "outcomes": outcomes, "decay_steps": {c: step[c]["decay_change"] for c in COGS},
            "true_skill": tr["skill"], "true_p_deficit": {DEFICIT_COG[d]: v for d, v in tr["p_deficit"].items()},
            "day": tr.get("day"),
        })
    return out


def learner_state(person: str, case: int, root: Path | str | None = None) -> dict:
    """What the Today screen (`coach_state`) and the work graph need for a learner at a given case index (1-based):
    overall level and chip, mastery by cog, and per cog the level, decay clock and last seen."""
    truth = load_learner_truth(root)
    traces = sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])
    upto = [t for t in traces if t["case"] <= case]
    if not upto:
        raise KeyError(f"{person} has no case <= {case}")
    tracker = SkillTracker()
    t_end = None
    for tr in upto:
        t_end = _ts(tr["t1"])
        for d in TYPES:
            tracker.observe(DEFICIT_COG[d], _outcome(tr, d), t_end)
    state = tracker.coach_state(list(COGS), t_end)
    return {"person": person, "case": upto[-1]["case"], "t": upto[-1]["t1"], **state,
            "cogs": tracker.snapshot(t_end)}


def _fisher_ci(rho: float, n: int) -> list[float]:
    if n < 4 or abs(rho) >= 1:
        return [float(rho), float(rho)]
    z, se = math.atanh(rho), 1.0 / math.sqrt(n - 3)
    return [math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)]


def _sp(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(spearmanr(a, b).statistic)


def evaluate_learner_skills(root: Path | str | None = None, *, fast: bool = False) -> dict:
    truth = load_learner_truth(root)
    people = [p["person"] for p in truth["people"]]
    per: dict[str, dict] = {}
    series_all: dict[str, list[dict]] = {}
    xs_mastery, xs_fade = [], []     # cross-sectional rank check pools
    for person in people:
        s = learner_series(person, root, truth=truth)
        series_all[person] = s
        cases = np.array([x["case"] for x in s])
        mean_m = np.array([x["mean_mastery"] for x in s])
        true_sk = np.array([x["true_skill"] for x in s])
        rho = _sp(mean_m, true_sk)
        rho_clock = _sp(cases, true_sk)
        # per-deficit: mastery vs true fading, over time
        per_def = {}
        for d in TYPES:
            c = DEFICIT_COG[d]
            m = [x["mastery"][c] for x in s]
            fade = [1.0 - x["true_p_deficit"][c] / truth["mechanism"]["deficit_params"][d]["p0"] for x in s]
            per_def[d] = {"spearman_mastery_vs_true_fade": _sp(m, fade), "final_mastery": m[-1],
                          "final_level": s[-1]["level_by_cog"][c]}
        # absence step for the learner who has one
        person_meta = next(p for p in truth["people"] if p["person"] == person)
        ab = person_meta.get("absence")
        absence = None
        if ab:
            k = ab["after_case"]
            before, after = s[k - 1], s[k]
            absence = {
                "after_case": k, "days": ab["days"],
                "mean_mastery_before": before["mean_mastery"], "mean_mastery_after_case": after["mean_mastery"],
                "level_before": before["level"], "level_after": after["level"],
                "decay_steps_at_return": after["decay_steps"],
                "true_skill_before": before["true_skill"], "true_skill_after": after["true_skill"],
                "true_skill_drop": before["true_skill"] - after["true_skill"],
                "level_stepped_down_at_return": any(v < 0 for v in after["decay_steps"].values()),
            }
        per[person] = {
            "cases": len(s), "final_level": s[-1]["level"], "level_by_case": [x["level"] for x in s],
            "first_case_level_ge_L3": next((x["case"] for x in s if int(x["level"][1]) >= 3), None),
            "spearman_mean_mastery_vs_true_skill": rho,
            "spearman_ci_fisher_z": None if rho is None else _fisher_ci(rho, len(s)),
            "spearman_clock_only_vs_true_skill": rho_clock,
            "level_by_cog_final": s[-1]["level_by_cog"], "per_deficit": per_def, "absence": absence,
        }
        # cross-sectional pools at fixed case indices (a clock cannot fake this: it compares deficits and learners)
        for case_idx in (10, 20, 30):
            x = s[min(case_idx, len(s)) - 1]
            for d in TYPES:
                c = DEFICIT_COG[d]
                xs_mastery.append((case_idx, x["mastery"][c]))
                xs_fade.append((case_idx, 1.0 - x["true_p_deficit"][c] / truth["mechanism"]["deficit_params"][d]["p0"]))
    cross = {}
    for case_idx in (10, 20, 30):
        m = [v for ci, v in xs_mastery if ci == case_idx]
        f = [v for ci, v in xs_fade if ci == case_idx]
        cross[f"case_{case_idx}"] = {"n_pairs": len(m), "spearman": _sp(m, f)}
    cvals = [v["spearman"] for v in cross.values() if v["spearman"] is not None]

    # effect of a followed prompt on the NEXT case's deficit (observable from the traces, not from the tracker)
    stats = {"followed": [0, 0], "not_followed": [0, 0]}      # [next case has the deficit, trials]
    for person in people:
        tr = sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])
        for a, b in zip(tr, tr[1:]):
            coach = {c["deficit"]: c for c in a["coach"]}
            nxt = {d["type"] for d in b["deficits"]}
            for d, c in coach.items():                          # deficits present at a
                key = "followed" if (c["shown"] and c["followed"]) else "not_followed"
                stats[key][0] += d in nxt
                stats[key][1] += 1
    eff = {}
    for k, (e, n) in stats.items():
        lo, hi = wilson_interval(int(e), int(n))
        eff[k] = {"next_case_deficit_rate": e / n if n else None, "ci": [lo, hi], "n": int(n)}
    diff = None
    if stats["followed"][1] and stats["not_followed"][1]:
        p1, n1 = stats["followed"][0] / stats["followed"][1], stats["followed"][1]
        p2, n2 = stats["not_followed"][0] / stats["not_followed"][1], stats["not_followed"][1]
        se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        diff = {"followed_minus_not_followed": p1 - p2, "ci_wald": [p1 - p2 - 1.96 * se, p1 - p2 + 1.96 * se]}
    rhos = [v["spearman_mean_mastery_vs_true_skill"] for v in per.values() if v["spearman_mean_mastery_vs_true_skill"] is not None]
    return {
        "origin": "synthetic", "n": len(people), "n_unit": "personas",
        "n_cases_each": 30, "stated": "n = 3 learners x 30 cases; one learner has a 3-day absence",
        "split": "none (tracker parameters fixed, never fitted to this data)", "interval_level": 0.95,
        "per_learner": per,
        "mean_spearman_mean_mastery_vs_true_skill": float(np.mean(rhos)) if rhos else None,
        "cross_sectional_rank_check": cross,
        "cross_sectional_mean_spearman": float(np.mean(cvals)) if cvals else None,
        "coach_effect_on_next_case": {**eff, **(diff or {}),
                                      "reading": "a followed prompt is supposed to speed the decline of that deficit"},
        "series": series_all,
        "meta": analytic_meta("synthetic", len(people), "personas", "none (fixed parameters); 3 learners x 30 cases",
                              note="Skill tracing on learners whose planted deficits fade with practice, beside the saturated persona result."),
        "limitations": limitations_for("skills") + [
            {"id": "ana-skills-learners-n", "severity": "medium",
             "text": "The learner check has three learners with thirty cases each, one of them with a three-day absence, so every interval is wide "
                     "and autocorrelated cases make the Spearman intervals optimistic."}],
        "caveats": [
            "Spearman against the true curve is partly trivial: any rising mastery series correlates with a rising skill curve. The clock-only control "
            "and the cross-sectional check (which compares deficits and learners at a fixed case) are the more informative numbers.",
            "The true curve is exactly 0 at case 1 by construction and mastery is not on that scale; compare shape and rank, not level.",
            "The three-day absence is short against the tracker's memory stability, so a step down at return is not expected unless stability is low.",
            "Tracker parameters were not tuned to this data.",
        ],
    }
