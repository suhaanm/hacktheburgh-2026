"""Skill tracing checked against planted skill curves (ANA-13), on engine-data's synthetic personas.

Each persona's `truth.json` holds a skill curve by day and the stuck episodes planted from it
(p_step = p0 (1 - skill)^gamma before each productive cog). Per task we derive the outcome the coach would see:
`error` if a stuck spell was planted inside the task, else `clean`. The tracker never sees the skill curve.
Checks: do mastery and level rise with the planted skill, and does mastery decay over days away?
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from understudy_engine.hazard.data import PERSONA_DIRS, _ts
from understudy_engine.skills import SkillTracker
from understudy_engine.skills import tracing as T
from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta

DAY_S = 86400.0


def _tasks(events_path: Path) -> dict[str, tuple[float, float]]:
    spans: dict[str, list[float]] = {}
    with events_path.open() as f:
        for line in f:
            r = json.loads(line)
            if r["type"] in ("task_start", "task_end") and r.get("task_id"):
                spans.setdefault(r["task_id"], []).append(_ts(r["t"]))
    return {k: (min(v), max(v)) for k, v in spans.items() if len(v) >= 1}


def evaluate_skills(root: Path | str | None = None, dirs: tuple[str, ...] = PERSONA_DIRS, *, fast: bool = False,
                    include_learners: bool = True) -> dict:
    """`fast` is accepted for a uniform interface; this evaluation has no resampling and already runs in a second or two."""
    from understudy_engine.store import data_dir

    base = Path(root) if root else data_dir()
    per = {}
    for d in dirs:
        ev, tr = base / "synthetic" / d / "events.jsonl", base / "synthetic" / d / "truth.json"
        if not ev.exists() or not tr.exists():
            raise FileNotFoundError(f"generated persona data missing: {ev}")
        truth = json.loads(tr.read_text())
        person = truth["person"]
        day0 = _dt.datetime.fromisoformat(truth["start_date"]).replace(tzinfo=_dt.timezone.utc).timestamp()
        skill_by_day = np.array(truth["skill"]["by_day"], float)
        n_days = len(skill_by_day)
        stuck_tasks = {s["task_id"] for s in truth.get("stuck_episodes", [])}
        tasks = sorted(_tasks(ev).items(), key=lambda kv: kv[1][0])
        tracker = SkillTracker()
        day_mastery = [np.nan] * n_days
        day_level = [np.nan] * n_days
        day_n = [0] * n_days
        drops: list[tuple[float, float]] = []   # (days away, mastery lost while away)
        last_t: float | None = None
        for tid, (t0, t1) in tasks:
            day = int((t1 - day0) // DAY_S)
            if not 0 <= day < n_days:
                continue
            if last_t is not None and "TASK" in tracker.cogs and (t1 - last_t) >= 1.5 * DAY_S:
                ms = tracker.cogs["TASK"].mastery
                drops.append(((t1 - last_t) / DAY_S, ms.m - T.decayed(ms, t1)))
            outcome = "error" if tid in stuck_tasks else "clean"
            tracker.observe("TASK", outcome, t1)
            last_t = t1
            snap = tracker.snapshot(t1)["TASK"]
            day_mastery[day], day_level[day] = snap["mastery"], snap["level"]
            day_n[day] += 1
        m = np.array(day_mastery)
        lv = np.array(day_level)
        ok = ~np.isnan(m)
        rho_m = spearmanr(m[ok], skill_by_day[ok]).statistic if ok.sum() > 3 else None
        rho_l = spearmanr(lv[ok], skill_by_day[ok]).statistic if ok.sum() > 3 else None
        per[person] = {
            "persona": d, "n_tasks": len(tasks), "n_days_active": int(ok.sum()), "planted_error_share": float(np.mean([t in stuck_tasks for t, _ in tasks])),
            "spearman_mastery_vs_planted_skill": None if rho_m is None else float(rho_m),
            "spearman_level_vs_planted_skill": None if rho_l is None else float(rho_l),
            "absences": {"n": len(drops), "mean_days_away": float(np.mean([d for d, _ in drops])) if drops else None,
                         "mean_mastery_lost": float(np.mean([x for _, x in drops])) if drops else None},
            "first_day_mastery_ge_099": next((i + 1 for i in range(n_days) if ok[i] and m[i] >= 0.99), None),
            "first_day_level_4": next((i + 1 for i in range(n_days) if ok[i] and lv[i] >= 4), None),
            "final_level": int(lv[ok][-1]) if ok.any() else None, "final_mastery": float(m[ok][-1]) if ok.any() else None,
            "level_by_day": [None if np.isnan(x) else int(x) for x in lv],
        }
    rm = [v["spearman_mastery_vs_planted_skill"] for v in per.values() if v["spearman_mastery_vs_planted_skill"] is not None]
    out = {
        "origin": "synthetic", "n": len(per), "n_unit": "personas", "split": "none (no fitting; tracker parameters are fixed)",
        "interval_level": 0.95, "per_persona": per, "limitations": limitations_for("skills"),
        "meta": analytic_meta("synthetic", len(per), "personas", "none (fixed parameters)",
                              note="Skill tracing saturates on these high-volume personas; see caveats."),
        "mean_spearman_mastery_vs_planted_skill": float(np.mean(rm)) if rm else None,
        "caveats": [
            "Outcome per task is 'a stuck spell was planted in it', a coarse single-skill proxy; per-cog tracing is not exercised by this data.",
            "Four personas, 21 days: a sanity check that mastery follows the planted learning curve, not a validation on real learners.",
            "Tracker parameters are hand-set (not fitted), so this is an out-of-the-box check, not a tuned fit.",
            "Weak result by design of the data: about 35 tasks a day with roughly 6 percent stuck means mastery saturates within a "
            "day or two, so the tracker cannot resolve the slow planted learning curve (see the Spearman values) and absences of "
            "2 to 3 days barely decay a heavily practised skill. Decay with absence is demonstrated in unit tests, not by this data.",
        ],
    }
    if include_learners:
        from understudy_engine.skills.learners import evaluate_learner_skills
        try:
            out["learners"] = evaluate_learner_skills(root, fast=fast)
        except FileNotFoundError:
            pass
    return out
