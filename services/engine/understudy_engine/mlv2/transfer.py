"""M5: out-of-generator transfer test (PLAN.md section 6.7). READ-ONLY: nothing is ever written under ``evals/study_sim``.

Behaviour traces of language-model participants (the simulated study, ``evals/study_sim/results``) are not produced by our persona generator. This
module turns each FINISHED participant's engine events into the same bin tables as the personas and scores stuck models that were trained on
synthetic personas only. Labelled everywhere "simulated participants (language model), not people".

A participant counts as finished only if ``checks/<pid>.json`` exists (written after the participant is completely done and its events are
exported) and its ``exclusion`` is empty; its events are ``raw/<pid>/engine_events.jsonl`` (schema-valid L0 events with measured timestamps, no
text). A partial run is fine: n is reported. NOTHING here is tuned on these traces; they are test-only.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from understudy_engine.core import Episode, Event
from understudy_engine.hazard.features import BinTable, build_bins
from understudy_engine.hazard.model import HazardModel
from understudy_engine.mlv2.alarms import build_layout, person_event_counts
from understudy_engine.mlv2.stats import (
    Clusters, EventCounts, boot_multiplicities, event_draws, event_points, interval, metric_draws, metric_points, score_parts,
)

BADGE = "simulated participants (language model), not people"
ORIGIN = "simulated_participants"


@dataclass
class SimData:
    results_dir: str
    finished: list[str]
    skipped: dict[str, str]
    episodes: list[Episode]
    arm: dict[str, str]
    n_events: int
    n_progress: int
    n_coach_events: int
    timing: str = "measured (engine event timestamps)"


def repo_results_dir() -> Path:
    from understudy_engine.store.paths import evals_dir

    return evals_dir() / "study_sim" / "results"


def _read_arms(results_dir: Path) -> dict[str, str]:
    p = results_dir / "participants.csv"
    arms: dict[str, str] = {}
    if p.exists():
        with p.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                arms.setdefault(row.get("participant", ""), row.get("arm", ""))
    return arms


def finished_participants(results_dir: Path | str) -> tuple[list[str], dict[str, str]]:
    """(finished participant ids, {id: reason skipped}). Read-only."""
    rd = Path(results_dir)
    ok: list[str] = []
    skipped: dict[str, str] = {}
    checks = rd / "checks"
    raw = rd / "raw"
    if not checks.is_dir():
        return [], {}
    for f in sorted(checks.glob("*.json")):
        pid = f.stem
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped[pid] = "unreadable checks file"
            continue
        if doc.get("exclusion"):
            skipped[pid] = "excluded: harness error"
            continue
        ev = raw / pid / "engine_events.jsonl"
        if not ev.exists():
            skipped[pid] = "no engine_events.jsonl"
            continue
        ok.append(pid)
    return ok, skipped


def load_sim(results_dir: Path | str | None = None, *, only: list[str] | None = None) -> SimData:
    """Episodes of every finished participant, built with the engine's own cog mapper and episode segmentation."""
    from understudy_engine.cogs import segment_episodes

    rd = Path(results_dir) if results_dir else repo_results_dir()
    ids, skipped = finished_participants(rd)
    if only is not None:
        ids = [i for i in ids if i in only]
    events: list[Event] = []
    n_progress = n_coach = 0
    for pid in ids:
        with (rd / "raw" / pid / "engine_events.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                e = Event.model_validate(json.loads(line))
                events.append(e)
                n_progress += e.type == "progress"
                n_coach += e.source == "coach"
    eps = segment_episodes(events) if events else []
    arms = _read_arms(rd)
    return SimData(str(rd), ids, skipped, eps, {p: arms.get(p, "") for p in ids}, len(events), n_progress, n_coach)


def evaluate_transfer(train_tab: BinTable, sim: SimData, *, primary_spec_id: str | None = None, n_boot: int = 4000, seed: int = 0,
                      inner_folds: int | None = 5) -> dict:
    """Score v1 and the frozen v2 primary (trained on ``train_tab``, synthetic personas only) on the simulated participants' bins."""
    from understudy_engine.mlv2.deployed import HazardModelV2

    out: dict = {
        "badge": BADGE, "origin": ORIGIN, "test_only": True, "n_participants_finished": len(sim.finished), "participants_skipped": sim.skipped,
        "n_events": sim.n_events, "n_progress_events": sim.n_progress, "n_coach_events": sim.n_coach_events, "timing": sim.timing,
        "arms": {a: sorted(p for p, x in sim.arm.items() if x == a) for a in sorted(set(sim.arm.values()))},
        "genome_comparison": "not applicable: the simulated participants are all novices; there is no expert reference in these data",
        "train": {"pool": "synthetic personas only", "n_people": len(train_tab.people), "n_bins": int(train_tab.n)},
    }
    if not sim.episodes:
        out["status"] = "no_finished_participants"
        return out
    tab = build_bins(sim.episodes)
    if tab.n == 0:
        out["status"] = "no_bins"
        return out
    y = tab.y.astype(float)
    cl = Clusters.from_labels(tab.person)
    out.update({
        "n_unit": "participants", "n": cl.C, "n_cases": len(tab.ep_person), "n_bins": int(tab.n), "label_rate": float(y.mean()),
        "bins_per_participant": {"min": int(cl.counts().min()), "median": float(np.median(cl.counts())), "max": int(cl.counts().max())},
        "interval_level": 0.95, "split": "train on synthetic personas, test on simulated participants (no tuning)",
    })
    rows_tr = np.arange(train_tab.n)
    models = {
        "v1": HazardModel("full", 3.0).fit(train_tab, rows_tr),
        "time_since_progress": HazardModel("tsp", 3.0).fit(train_tab, rows_tr),
        "base_rate": HazardModel("base").fit(train_tab, rows_tr),
    }
    rows = np.arange(tab.n)
    preds = {k: m.predict(tab, rows) for k, m in models.items()}
    v2 = None
    if primary_spec_id:
        v2 = HazardModelV2(primary_spec_id, inner_folds=inner_folds).fit(train_tab, rows_tr)
        preds["v2"] = v2.predict(tab, rows)
    M = boot_multiplicities(cl.C, n_boot, seed)
    parts = {k: score_parts(y, p, cl) for k, p in preds.items()}
    dr = {k: metric_draws(p, M) for k, p in parts.items()}
    pt = {k: metric_points(p) for k, p in parts.items()}
    out["models"] = {k: {m: {"value": pt[k][m], "interval": list(interval(dr[k][m], 0.95))} for m in pt[k]} for k in preds}
    out["paired_log_loss"] = {}
    for a, b in (("v1", "base_rate"), ("v1", "time_since_progress"), ("v2", "v1"), ("v2", "base_rate")):
        if a in preds and b in preds:
            lo, hi = interval(dr[a]["log_loss"] - dr[b]["log_loss"], 0.95)
            out["paired_log_loss"][f"{a}_minus_{b}"] = {"delta": pt[a]["log_loss"] - pt[b]["log_loss"], "interval": [lo, hi]}
    from understudy_engine.trust.calibration import reliability_bins

    out["calibration"] = {k: reliability_bins(y, preds[k]) for k in ("v1",) + (("v2",) if v2 else ())}
    # alarm rules fitted on the TRAINING people's grouped out-of-fold predictions only (inside HazardModelV2.fit), then applied to these bins
    layout = build_layout(tab)
    out["alarm_rules"] = {}
    rules = [("v1_probabilities_v1_rule_C0", "v1", HazardModelV2("A0", inner_folds=inner_folds, alarm="C0").fit(train_tab, rows_tr).alarm_config),
             ("v1_probabilities_risk_controlled_C1", "v1", HazardModelV2("A0", inner_folds=inner_folds, alarm="C1").fit(train_tab, rows_tr).alarm_config)]
    if v2 is not None:
        rules.append(("v2_probabilities_v1_rule_C0", "v2", v2.alarm_config))
    for name, which, cfg in rules:
        cols = {k: [] for k in ("n_events", "detected", "false_alarms", "true_alarms", "non_event_h", "total_h")}
        for q in tab.people:
            eps = np.array([e for e, pp in enumerate(tab.ep_person) if pp == q])
            c = person_event_counts(layout, preds[which], cfg["threshold"], cfg["confirm_bins"], eps)
            for k in cols:
                cols[k].append(c[k])
        ev = EventCounts(**{k: np.array(v) for k, v in cols.items()})
        ed = event_draws(ev, M, 1.0)
        ep = event_points(ev, 1.0)
        out["alarm_rules"][name] = {
            "threshold": cfg["threshold"], "confirm_bins": cfg["confirm_bins"], "n_stuck_events": float(ev.n_events.sum()),
            "false_alarms_per_hour": {"value": ep["false_alarms_per_hour"], "interval": list(interval(ed["false_alarms_per_hour"], 0.95))},
            "detection": {"value": ep["detection"], "interval": list(interval(ed["detection"], 0.95))},
            "non_event_hours": float(ev.non_event_h.sum()),
        }
    out["caveats"] = [
        BADGE + ". Not people, not the live study.",
        "Progress events are sparse in these traces, so the label ('no progress in the next 60 s') is almost always 1: log loss against the base rate "
        "says little, and a model can look good or bad for that reason alone.",
        "Cases are short (about a minute or two), so each participant contributes a handful of 30 s bins.",
        "Nothing was tuned on these traces; the models and alarm rules were fitted on synthetic personas before any of these numbers existed.",
        "Participants are language models acting in a sandbox we built, under a coach we built; this tests transfer to a different behaviour generator, not to real work.",
    ]
    out["status"] = "ok"
    return out
