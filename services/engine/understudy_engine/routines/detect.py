"""From episodes to routine objects: finder, score, template, forecast, value, build timing, skill gate, proposal copy."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core import Episode
from ..memory.packinfo import PackView
from . import skirental as sk
from .finder import FinderConfig, find_routines
from .forecast import DAY, backtest_coverage, fit_forecast
from .gate import SkillSource, routine_skill_gate
from .proposal import build_proposal
from .scoring import auto_id, auto_title, match_template, score_cluster
from .value import ValueParams, value_model


@dataclass(frozen=True)
class DetectConfig:
    finder: FinderConfig = FinderConfig()
    horizon_weeks: int = 4
    report_min_confidence: float = 0.2    # show a routine when P(net > 0) reaches this, or a pack template matched
    propose_min_confidence: float = 0.5   # raise a card when P(net > 0) reaches this
    max_judgement_share: float = 0.5      # more judgement than this: reported, never proposed
    default_build_cost_runs: float = 6.0
    wage_gbp_h: float | None = None       # None: the pack's own illustration (15)
    forecast_draws: int = 4000            # Monte Carlo draws per routine (fewer for a fast evaluation)


def _irreversible_classes(never: Sequence[str], patterns: Sequence[str]) -> list[str]:
    out = []
    for n in never:
        for p in patterns:
            try:
                hit = re.search(p, n, re.I) or re.search(re.escape(n), p, re.I)
            except re.error:
                hit = p.lower() in n.lower()
            if hit:
                out.append(n)
                break
    return list(dict.fromkeys(out))


def detect_routines(episodes: Sequence[Episode], pack: PackView, *, person: str, now: float | None = None,
                    skills: SkillSource | None = None, cfg: DetectConfig | None = None) -> list[dict[str, Any]]:
    """Return routine dicts (measured fields only; consent state is the store's business), best value first."""
    cfg = cfg or DetectConfig()
    episodes = list(episodes)
    if not episodes:
        return []
    fcfg = cfg.finder
    mp = pack.template_defaults.get("min_support")
    if mp and mp != fcfg.min_support:
        fcfg = FinderConfig(fcfg.threshold, int(mp), fcfg.min_len, fcfg.max_episodes, fcfg.drop)
    clusters = find_routines(episodes, fcfg)
    w0 = min(e.t0 for e in episodes)
    w1 = max(e.t1 for e in episodes)
    start = (int(w0 // DAY)) * DAY
    end = (int(w1 // DAY) + 1) * DAY
    span_days = max(7.0, (end - start) / DAY)
    t_now = now if now is not None else w1
    judgement = pack.judgement_cogs()
    wage = cfg.wage_gbp_h if cfg.wage_gbp_h is not None else float(pack.template_defaults.get("wage_gbp_per_h", 15.0))

    # forecast errors seen on this person's routines (fit on the first two thirds, score on the last third): feeds lambda
    split = start + (end - start) * 2 / 3
    rel_errors = []
    for cl in clusters:
        times = [e.t0 for e in cl.episodes]
        if sum(1 for t in times if t < split) >= 3:
            bt = backtest_coverage(times, start, split, end)
            rel_errors.append(float(np.log((bt["predicted"] + 1) / (bt["actual"] + 1))))
    lam = sk.choose_lambda(rel_errors) if len(rel_errors) >= 2 else 0.5

    out: list[dict[str, Any]] = []
    for cl in clusters:
        tmpl, tmpl_d = match_template(cl.medoid, pack.templates)
        sc = score_cluster(cl, span_days, judgement)
        times = [e.t0 for e in cl.episodes]
        fc = fit_forecast(times, (start, end), cfg.horizon_weeks * 7, seed=17, draws=cfg.forecast_draws)
        vd = (tmpl or {}).get("value_defaults", {}) or {}
        vp = ValueParams(wage_gbp_h=wage, build_cost_runs=float(vd.get("build_cost_runs", cfg.default_build_cost_runs)),
                         maintenance_risk_gbp=float(vd.get("maintenance_risk_gbp", 5.0)),
                         error_cost_gbp=float(vd.get("error_cost_gbp", 5.0)), horizon_weeks=cfg.horizon_weeks)
        val = value_model(fc.draws, [e.duration for e in cl.episodes], sc.judgement_share, vp)
        timing = sk.plan_build(fc.mean_runs, vp.build_cost_runs, lam, fc.draws, runs_done=sc.count)
        rid = tmpl["id"] if tmpl else auto_id(cl.medoid)
        title = tmpl["title"] if tmpl else auto_title(cl.medoid)
        learning = bool((tmpl or {}).get("learning_relevant", True))
        skill_cogs = list((tmpl or {}).get("skill_cogs") or dict.fromkeys(cl.medoid))
        gate = routine_skill_gate(skills, skill_cogs, t_now, learning_relevant=learning)
        automatable = bool((tmpl or {}).get("automatable", True))
        reasons = []
        if not automatable:
            reasons.append("needs your judgement, so it stays manual")
        if sc.judgement_share > cfg.max_judgement_share:
            reasons.append(f"{sc.judgement_share:.0%} of the steps are judgement")
        if val["confidence"] < cfg.propose_min_confidence:
            reasons.append("not enough time saved to be worth building yet")
        if not gate["eligible"]:
            reasons.append(gate["reason"])
        if tmpl is None and val["confidence"] < cfg.report_min_confidence:
            continue  # one-off work that happens to repeat a few times; not worth a row
        proposal = build_proposal(title=title, template=tmpl, medoid=list(cl.medoid), count=sc.count, span_days=span_days,
                                  hours=val["hours_saved"], horizon_weeks=cfg.horizon_weeks, risk_irreversible=pack.risk_irreversible)
        never = proposal["never"]
        out.append({
            "id": rid, "role": pack.id, "title": title, "person": person, "template_id": tmpl["id"] if tmpl else None,
            "template_distance": round(tmpl_d, 3) if tmpl else None,
            "episodes": sc.count, "minutes_per_week": round(sc.minutes_per_week, 1), "cv": round(sc.cv, 3),
            "judgement_share": round(sc.judgement_share, 3), "n_days": sc.n_days, "mean_duration_s": round(sc.mean_duration_s, 1),
            "value": {"hours_saved": val["hours_saved"], "net_gbp": val["net_gbp"], "confidence": val["confidence"],
                      "horizon_weeks": val["horizon_weeks"], "assumptions": val["assumptions"]},
            "forecast": {"runs": round(fc.mean_runs, 1), "interval": fc.interval(), "runs_per_week": round(fc.runs_per_week, 2),
                         "dispersion": round(fc.dispersion, 2), "horizon_weeks": cfg.horizon_weeks},
            "touches": proposal["touches"], "never": never,
            "irreversible_classes": _irreversible_classes(never, pack.risk_irreversible),
            "build_timing": timing.contract(),
            "skill_gate": gate, "automatable": automatable, "learning_relevant": learning, "skill_cogs": skill_cogs,
            "other_reasons": [r for r in reasons if r != gate["reason"]],
            "proposable": not reasons, "not_proposable_because": reasons,
            "proposal": {k: proposal[k] for k in ("what", "how_often", "touches", "never")} | {"hours_saved_text": proposal["hours_saved_text"]},
            "signature": list(cl.medoid), "last_seen": max(e.t1 for e in cl.episodes), "first_seen": min(e.t0 for e in cl.episodes),
            "member_task_ids": [e.task_id for e in cl.episodes], "member_t0": [round(e.t0, 1) for e in cl.episodes],
        })
    out.sort(key=lambda r: (-r["value"]["hours_saved"][1], r["id"]))
    # one pack template may match several clusters (a variant split off); keep the larger, rename the others
    seen: dict[str, int] = {}
    for r in out:
        n = seen.get(r["id"], 0)
        seen[r["id"]] = n + 1
        if n:
            r["id"] = f"{r['id']}-v{n + 1}"
    return out
