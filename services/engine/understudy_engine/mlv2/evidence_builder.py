"""Builders that fill ``EvidenceInputs`` (the explainer's numbers) from the engine's own computations. No text, no names, no paths.

``build_evidence_inputs(cohort, person, model_version=...)`` takes an apprentice-style cohort (a ``genome.Cohort``) and one person in it and returns the
per-case habit seconds with intervals, the counterfactual seconds with intervals, the envelope rows (the person's seconds on a cog against the interval the
nearest experts take), the gap, and, if supplied, the hazard reading with its calibration figures. ``model_version`` is "v1" (nearest single expert,
alignment seconds only, no counterfactual) or "v2" (the pre-registered primary candidates: E4 ensemble for the seconds, Q1 for the counterfactual).
``accepted`` is read from the held-out verdict table when a verdict is passed in; v1 carries ``None`` (not applicable).
"""
from __future__ import annotations

import numpy as np

from understudy_engine.genome.cohort import Cohort
from understudy_engine.genome.labels import DEFICIT_OF_LABEL, LABEL_ORDER, label_columns
from understudy_engine.mlv2 import evidence_inputs as EI
from understudy_engine.mlv2.counterfactual import q1_functional
from understudy_engine.mlv2.envelope import VARIANTS, EnvelopeModel

LABEL_COGS = {   # which pack cogs each waterfall bar touches (for cog_ids); the bar's own columns decide per case, this is the fallback
    "Repeated reads": ("READ_RESULT",), "Search loops": ("SEARCH", "REFORMULATE", "READ"), "Long pauses": ("IDLE",),
    "Missed check, redone": ("CHECK_CLIFF", "REVERT", "ENTER_HOUSEHOLD"), "Wrong figure, copied again": ("RECONCILE", "REVERT", "COPY_TO_NOTE"),
}


def hazard_input_from_summary(p: float, source: str, summary: dict | None, alarm_threshold: float | None = None) -> EI.HazardInput:
    """A hazard reading with the calibration figures of a held-out or dev summary (``family_a`` row dict of a part result)."""
    s = summary or {}
    m = s.get("metrics") or {}
    ev = s.get("events") or {}
    ece = (m.get("ece") or {}).get("value")
    fa = ev.get("false_alarms_per_hour") or {}
    calib = "untested" if ece is None else ("calibrated" if ece <= 0.03 else "overconfident")
    iv = fa.get("interval") or [None, None]
    return EI.HazardInput(
        p=float(p), source=source, threshold=alarm_threshold, n_bins=int(s.get("n_bins", 0) or 0), ece=ece,
        log_loss=(m.get("log_loss") or {}).get("value"), base_rate_log_loss=s.get("base_rate_log_loss"), tsp_log_loss=s.get("tsp_log_loss"),
        false_alarms_per_hour=fa.get("value"), fa_lo=iv[0], fa_hi=iv[1], calibration=calib)


def _dwell_by_cog(ep) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in ep.cogs:
        out[c.id] = out.get(c.id, 0.0) + c.dwell
    return out


def build_evidence_inputs(cohort: Cohort, person: str, *, model_version: str = "v1", accepted: bool | None = None, split: str = "descriptive_nearest_expert",
                          pool: str = "none", hazard: EI.HazardInput | None = None, origin: str = "synthetic", seed: int = 0, n_boot: int = 120,
                          limitations: tuple[str, ...] = ("synthetic_people_only", "generator_planted_structure", "shared_steps_mispriced",
                                                           "additive_counterfactual_assumes_rest_unchanged")) -> EI.EvidenceInputs:
    if model_version not in ("v1", "v2"):
        raise ValueError(model_version)
    model = EnvelopeModel(cohort.experts, seed=seed, n_boot=n_boot)
    att_variant = VARIANTS["E4" if model_version == "v2" else "E0"]
    cases = []
    for ep in [e for e in cohort.episodes if e.person == person]:
        att = model.attribute(ep, att_variant, with_interval=True)
        cf = model.attribute(ep, VARIANTS["E4"], with_interval=True, fn=q1_functional) if model_version == "v2" else None
        ranked = model._ranked(ep, model.cost_for(att_variant))
        ref_ep = ranked[0][0]
        top = [r for r, _ in ranked[: max(1, att_variant.m_experts)]]
        habits = []
        for lab in LABEL_ORDER:
            hid = EI.HABIT_OF_LABEL[lab]
            sec, lo, hi = att.point[lab], att.lo[lab], att.hi[lab]
            if abs(sec) < 0.5 and abs(hi) < 0.5 and abs(lo) < 0.5:
                continue
            kw = dict(counterfactual_s=None, counterfactual_lo=None, counterfactual_hi=None, method="alignment")
            if cf is not None:
                kw = dict(counterfactual_s=cf.point[lab], counterfactual_lo=cf.lo[lab], counterfactual_hi=cf.hi[lab], method="splice")
            habits.append(EI.HabitInput(habit_id=hid, cog_ids=LABEL_COGS.get(lab, ()), seconds=float(sec), seconds_lo=float(min(lo, sec)),
                                        seconds_hi=float(max(hi, sec)), n=1, **kw))
        nov = _dwell_by_cog(ep)
        refs = [_dwell_by_cog(r) for r in top]
        envelope = []
        for cog, s in sorted(nov.items()):
            vals = [r.get(cog, 0.0) for r in refs]
            envelope.append(EI.EnvelopeRow(cog_id=cog, novice_s=float(s), expert_lo_s=float(min(vals)), expert_hi_s=float(max(vals)),
                                           attributed_s=float(s - np.median(vals)), attributed_lo=float(s - max(vals)), attributed_hi=float(s - min(vals))))
        gap = sum(att.point.values())
        draws = att.draws.sum(axis=1) if att.draws is not None else None
        glo, ghi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))) if draws is not None else (float(gap), float(gap))
        cases.append(EI.CaseInput(person_id=person, task_id=ep.task_id, case_s=float(sum(c.dwell for c in ep.cogs)),
                                  reference_s=float(sum(c.dwell for c in ref_ep.cogs)), gap_s=float(gap), gap_lo=min(glo, float(gap)), gap_hi=max(ghi, float(gap)),
                                  habits=EI.sorted_habits(habits), envelope=tuple(envelope), hazard=hazard, limitations=()))
    pv = EI.Provenance(origin=origin, n=len({e.person for e in cohort.novices}), n_unit="people", split=split, model_version=model_version,
                       accepted=accepted, pool=pool)
    return EI.EvidenceInputs(provenance=pv, cases=tuple(cases), cohort=None, hazard=hazard, baselines={}, limitations=tuple(limitations)).validate()
