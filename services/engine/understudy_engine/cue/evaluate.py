"""Cue evaluation (CUE-3, CUE-9 and the evidence for CUE-1, CUE-7): ``evaluate_cue(fast=False)`` returns an eval-harness section.

SIMULATED. Everything here runs on simulated workers and learners and says so (``meta.origin == "synthetic"``). The design, the metrics, the
dev/held-out split, the tuning grid and the acceptance rules are in ``evals/cue/PLAN.md``, committed before any held-out replicate was run.

* ``evaluate_cue(fast=True)`` (under 60 s): small populations, the tuned parameters as they stand, no tuning, the held-out run is NEVER part
  of it (``held_out`` is reported ``not_run``) unless ``held_out=True`` is passed, which only the frozen command in ``evals/cue/README`` does.
* ``tune_on_dev()`` runs the pre-registered grid on the dev population and replicates and returns the table and the selection.
* Intervals are percentile bootstraps over WORKERS (the cluster); decisions on the two primary outcomes use 97.5% intervals (Bonferroni for
  two), everything else is exploratory at 95%.
"""
from __future__ import annotations

import hashlib
import itertools
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from ..trust.meta import analytic_meta
from . import evaluate_candidates as EC
from . import evaluate_score as ES
from . import paths as P
from . import params as PRM
from .params import CueParams
from .simulate import ASSUME, DT, Simulator, WorkerResult, make_population

DEV = {"pop_seed": 11, "reps": (0, 1, 2, 3, 4)}
HELD = {"pop_seed": 77, "reps": (1000, 1001, 1002, 1003, 1004)}
GRID = {"p_signal": (0.30, 0.40, 0.50, 0.60, 0.70), "margin_thr": (0.10, 0.20, 0.30)}
DESIGN_TARGET_FALSE_PER_H = 1.0
GROUND_SWEEP = (0.6, 0.7, 0.8, 0.9, 1.0)
LEVEL = 0.95
PRIMARY_LEVEL = 0.975        # two primary outcomes, Bonferroni


# ------------------------------------------------------------------------------------------------ aggregation per worker
def _worker_record(rs: list[WorkerResult]) -> dict[str, Any]:
    """One worker's pooled replicates."""
    iv = [i for r in rs for i in r.interventions]
    eps = [e for r in rs for e in r.episodes]
    cued = [e for e in eps if e.first_cue_tau is not None]
    saved = sum(e.stall_s - e.realised_s for e in eps)
    costs = sum(i.cost_s for i in iv if (not i.stuck_now) or (i.kind == "ask" and i.stuck_now))
    return {
        "hours": sum(r.seconds for r in rs) / 3600.0,
        "shown": len(iv), "false": sum(1 for i in iv if not i.stuck_now), "wrong_target": sum(1 for i in iv if i.wrong_target),
        "accepted": sum(1 for i in iv if i.outcome == "accepted"), "dismissed": sum(1 for i in iv if i.outcome == "dismissed"),
        "ignored": sum(1 for i in iv if i.outcome == "ignored"), "asks": sum(1 for i in iv if i.kind == "ask"), "offers": sum(1 for i in iv if i.kind == "offer"),
        "cue_tier": {t: sum(1 for i in iv if i.kind == "cue" and i.tier == t) for t in (1, 2, 3, 4)},
        "stuck_eps": len(eps), "with_cue": len(cued), "correct": sum(1 for e in eps if e.correct_appeared), "accepted_eps": sum(1 for e in eps if e.accepted),
        "after_cue": np.array([e.realised_s - e.first_cue_tau for e in cued], float),           # type: ignore[operator]
        "no_cue_remaining": np.array([e.stall_s - e.first_cue_tau for e in cued], float),       # type: ignore[operator]
        "diff": np.array([e.realised_s - e.stall_s for e in cued], float),
        "diff_sum": float(sum(e.realised_s - e.stall_s for e in cued)), "cued_n": len(cued), "shortened": sum(1 for e in cued if e.realised_s < e.stall_s - 1.0),
        "saved_s": saved, "interruption_s": costs, "net_s": saved - costs,
        "ticks": sum(r.ticks for r in rs), "stuck_ticks": sum(r.stuck_ticks for r in rs), "silent_ticks": sum(r.silent_ticks for r in rs),
        "silent_stuck_ticks": sum(r.silent_stuck_ticks for r in rs), "silent_not_stuck": sum(r.silent_ticks - r.silent_stuck_ticks for r in rs),
        "gate_episodes": sum(r.gate_episodes for r in rs), "questions": sum(sum(r.questions_by_episode.values()) for r in rs),
        "violations": sum(len(r.violations) for r in rs), "violation_kinds": sorted({v for r in rs for v in r.violations}),
        "stall_no_cue": np.array([e.stall_s for e in eps], float), "stall_with_cue": np.array([e.realised_s for e in eps], float), "cases": sum(r.cases for r in rs),
    }


def run_condition(params: CueParams, *, ground_accuracy: float = 0.9, pop_seed: int, reps: tuple[int, ...], n_workers: int = 40, sessions: int = 3,
                  cases_per_session: int = 4, signal: str = "rule", sim: Simulator | None = None, ledger: bool = False) -> list[dict[str, Any]]:
    """Run the cue arm over the population and replicates; one pooled record per worker."""
    pop = make_population(pop_seed, n_workers)
    sim = sim or Simulator(params=params, ground_accuracy=ground_accuracy, signal=signal, ledger=ledger)
    sim.params, sim.ground_accuracy, sim.signal = params, ground_accuracy, signal
    by_worker: dict[str, list[WorkerResult]] = {w.id: [] for w in pop}
    for rep in reps:
        for r in sim.run(pop, rep, arm="cue", sessions=sessions, cases_per_session=cases_per_session):
            by_worker[r.worker].append(r)
    return [_worker_record(by_worker[w.id]) for w in pop]


# ------------------------------------------------------------------------------------------------ intervals over workers
def _ratio(recs: list[dict[str, Any]], num: str, den: str, B: int, seed: int, level: float = LEVEL, scale: float = 1.0) -> dict[str, Any]:
    n = np.array([r[num] for r in recs], float)
    d = np.array([r[den] for r in recs], float)
    point = float(n.sum() / d.sum()) * scale if d.sum() > 0 else None
    if len(recs) < 2 or d.sum() <= 0:
        return {"value": None if point is None else round(point, 4), "ci": [None, None], "n": int(n.sum()), "n_workers": len(recs)}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(recs), (B, len(recs)))
    dd = d[idx].sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(dd > 0, n[idx].sum(1) / dd, np.nan) * scale
    tail = (1 - level) / 2
    return {"value": round(point, 4), "ci": [round(float(x), 4) for x in np.nanquantile(v, [tail, 1 - tail])], "n": int(n.sum()), "n_workers": len(recs)}


def _median(recs: list[dict[str, Any]], key: str, B: int, seed: int, level: float = LEVEL) -> dict[str, Any]:
    arrs = [r[key] for r in recs]
    pooled = np.concatenate(arrs) if arrs else np.array([])
    if pooled.size == 0:
        return {"value": None, "ci": [None, None], "n": 0}
    rng = np.random.default_rng(seed)
    meds = []
    for _ in range(B):
        idx = rng.integers(0, len(arrs), len(arrs))
        a = np.concatenate([arrs[i] for i in idx])
        if a.size:
            meds.append(np.median(a))
    tail = (1 - level) / 2
    return {"value": round(float(np.median(pooled)), 2), "ci": [round(float(x), 2) for x in np.quantile(meds, [tail, 1 - tail])], "n": int(pooled.size)}


def metrics(recs: list[dict[str, Any]], B: int = 400, seed: int = 0) -> dict[str, Any]:
    """Every metric of the plan for one condition, each with n, an interval over workers and (where one exists) its baseline."""
    R = lambda num, den, **kw: _ratio(recs, num, den, B, seed, **kw)                                      # noqa: E731
    hours = sum(r["hours"] for r in recs)
    base_rate = 1.0 - sum(r["stuck_ticks"] for r in recs) / max(1, sum(r["ticks"] for r in recs))
    return {
        "n_workers": len(recs), "hours": round(hours, 1), "cases": sum(r["cases"] for r in recs), "stuck_episodes": sum(r["stuck_eps"] for r in recs),
        "p1_false_nudges_per_hour": {"all": R("false", "hours"), "primary_975": R("false", "hours", level=PRIMARY_LEVEL),
                                      "design_target": DESIGN_TARGET_FALSE_PER_H, "baseline_no_cue": 0.0, "note": "A design target (at most 1.0 an hour), not a measured tolerance."},
        "p2_seconds_to_resume_paired_diff": {"median": _median(recs, "diff", B, seed, PRIMARY_LEVEL), "baseline": 0.0,
                                             "note": "Seconds from the first cue to resuming, with Cue minus the no-cue remaining stall, per cued stall; negative is faster."},
        "p2_exploratory_mean_diff_s": R("diff_sum", "cued_n"), "cued_stalls_shortened_share": R("shortened", "cued_n"),
        "seconds_from_first_cue_to_resume": {"with_cue": _median(recs, "after_cue", B, seed), "no_cue_counterfactual": _median(recs, "no_cue_remaining", B, seed)},
        "stuck_episodes_with_a_correct_cue_share": R("correct", "stuck_eps"),
        "stuck_episodes_with_any_cue_share": R("with_cue", "stuck_eps"),
        "stuck_episodes_accepted_share": R("accepted_eps", "stuck_eps"),
        "acceptance_rate": R("accepted", "shown"), "dismissal_rate": R("dismissed", "shown"), "ignored_rate": R("ignored", "shown"),
        "silence_precision": {**R("silent_not_stuck", "silent_ticks"), "baseline_always_silent": round(base_rate, 4),
                              "note": "Share of silent moments that were genuinely not stuck; always staying silent scores the baseline."},
        "stuck_seconds_that_stayed_silent_share": R("silent_stuck_ticks", "stuck_ticks"),
        "questions_per_episode": R("questions", "gate_episodes"), "cues_per_hour": R("shown", "hours"),
        "asks_per_hour": R("asks", "hours"), "offers_per_hour": R("offers", "hours"),
        "wrong_target_cues_per_hour": R("wrong_target", "hours"),
        "net_seconds_saved_per_hour": {**R("net_s", "hours"), "baseline_no_cue": 0.0, "note": "Stall seconds saved minus seconds lost to interruptions, per hour of work."},
        "median_stall_s": {"no_cue": _median(recs, "stall_no_cue", B, seed), "with_cue": _median(recs, "stall_with_cue", B, seed)},
        "violations": {"count": int(sum(r["violations"] for r in recs)), "kinds": sorted({k for r in recs for k in r["violation_kinds"]})},
    }


def decide_acceptance(m: dict[str, Any]) -> dict[str, Any]:
    p1 = m["p1_false_nudges_per_hour"]["primary_975"]
    p2 = m["p2_seconds_to_resume_paired_diff"]["median"]
    a1 = "met" if p1["ci"][1] is not None and p1["ci"][1] <= DESIGN_TARGET_FALSE_PER_H else ("point_only" if p1["value"] is not None and p1["value"] <= DESIGN_TARGET_FALSE_PER_H else "not_met")
    a2 = "met" if p2["ci"][1] is not None and p2["ci"][1] < 0 else "not_met"
    a3 = "met" if m["violations"]["count"] == 0 else "not_met"
    return {"P1_false_nudges": a1, "P2_faster_to_resume": a2, "invariants": a3, "intervals": "97.5% (Bonferroni, two primary outcomes)"}


# ------------------------------------------------------------------------------------------------ tuning (dev only)
def tune_on_dev(*, n_workers: int = 40, reps: tuple[int, ...] = DEV["reps"], grid: dict[str, tuple] | None = None, B: int = 300,
                base: CueParams = PRM.DEFAULT, log=None) -> dict[str, Any]:
    grid = grid or GRID
    sim = Simulator(params=base)
    rows = []
    keys = list(grid)
    for combo in itertools.product(*(grid[k] for k in keys)):
        p = base.with_(**dict(zip(keys, combo)))
        recs = run_condition(p, pop_seed=DEV["pop_seed"], reps=reps, n_workers=n_workers, sim=sim)
        m = metrics(recs, B=B, seed=1)
        row = {**dict(zip(keys, combo)), "false_per_h": m["p1_false_nudges_per_hour"]["all"]["value"], "false_per_h_975_upper": m["p1_false_nudges_per_hour"]["primary_975"]["ci"][1],
               "net_s_per_h": m["net_seconds_saved_per_hour"]["value"], "net_ci": m["net_seconds_saved_per_hour"]["ci"],
               "correct_cue_share": m["stuck_episodes_with_a_correct_cue_share"]["value"], "p2_median_diff": m["p2_seconds_to_resume_paired_diff"]["median"]["value"],
               "cues_per_h": m["cues_per_hour"]["value"], "violations": m["violations"]["count"]}
        rows.append(row)
        if log:
            log(row)
    ok = [r for r in rows if r["false_per_h_975_upper"] is not None and r["false_per_h_975_upper"] <= DESIGN_TARGET_FALSE_PER_H and r["violations"] == 0]
    if ok:
        best = sorted(ok, key=lambda r: (-r["net_s_per_h"], r["p_signal"]))[0]
        rule = "highest net seconds saved per hour among configurations whose dev false-nudge 97.5% upper bound is at most 1.0"
    else:
        top = max(r["net_s_per_h"] for r in rows)
        near = [r for r in rows if r["net_s_per_h"] >= 0.5 * top] or rows
        best = sorted(near, key=lambda r: (r["false_per_h"], r["p_signal"]))[0]
        rule = "no configuration met the target: lowest false-nudge rate among those within 50% of the best net saving"
    return {"grid": {k: list(v) for k, v in grid.items()}, "rows": rows, "selected": {k: best[k] for k in keys}, "rule": rule, "selected_row": best,
            "n_workers": n_workers, "reps": list(reps), "pop_seed": DEV["pop_seed"]}


# ------------------------------------------------------------------------------------------------ the section
def code_hashes() -> dict[str, str]:
    here = Path(__file__).resolve().parent
    out = {}
    for f in ("gate.py", "params.py", "candidates.py", "question.py", "score.py", "simulate.py", "simlearn.py", "evaluate.py", "evaluate_score.py", "evaluate_candidates.py"):
        out[f] = hashlib.sha1((here / f).read_bytes()).hexdigest()[:12]
    plan = P.repo_root() / "evals" / "cue" / "PLAN.md"
    out["evals/cue/PLAN.md"] = hashlib.sha1(plan.read_bytes()).hexdigest()[:12] if plan.is_file() else "absent"
    return out


READINGS = [
    "Candidates: the pack's order rules do most of the work (the same n-gram without them is clearly worse); family A is 8 people with two orderings, so its interval is wide; family B is written from the pack's rules, so it cannot make them lose.",
    "Score: the independence interval and the trend are the headline. The composite overstates for learners who do not improve and rises falsely in about a third of them, so it is shown as experimental only. 'Steady' means cannot tell yet.",
    "Cue: these numbers say how the policy behaves in a simulated world whose assumptions are in PLAN.md and cue/simulate.py. They do not say Cue works on people.",
]
LIMITATIONS = [
    {"id": "cue-sim-world", "severity": "high", "text": "Every Cue result comes from a simulator written by the same team that wrote the policy: stalls, pauses, reaction times and interruption costs are assumptions. It shows the policy keeps its caps and trades help against nuisance as designed; it is not evidence about people."},
    {"id": "cue-signal-rule", "severity": "medium", "text": "The headline stuck signal is the coach's rule fallback (time since progress). The real hazard model would change when help arrives; an emulated model signal is a secondary sweep and is labelled as an emulation."},
    {"id": "cue-grounding-fake", "severity": "medium", "text": "Grounding is a fake port right at a chosen rate. Real accuracy on real screens is not measured here; the 60 to 100% sweep is a what-if."},
    {"id": "cue-score-composite", "severity": "high", "text": "The composite overstates mastery for learners who do not improve and rises 10 points or more in about a third of them. It is experimental and in no headline; independence and the trend are the evidence, and the trend has low power."},
    {"id": "cue-score-leak", "severity": "medium", "text": "A learner who dismisses a cue and then grinds through alone looks independent in the ledger; the guards remove dismiss-and-walk-away and implicit follows within 10 s but cannot remove that leak."},
    {"id": "cue-candidates-families", "severity": "medium", "text": "Candidate accuracy is measured on 8 scripted apprentice experts and on experts sampled from the pack's own rules; real experts will do things neither contains."},
]


def evaluate_cue(fast: bool = False, *, held_out: bool = False, root: Path | str | None = None) -> dict[str, Any]:
    """The eval-harness section. ``fast`` stays under 60 s: small populations, tuned parameters as they stand, no tuning, no held-out run."""
    t0 = time.time()
    tuned = PRM.TUNED
    nw, reps = (12, DEV["reps"][:2]) if fast else (40, DEV["reps"])
    sess, cps = (2, 2) if fast else (3, 4)
    B = 150 if fast else 400
    out: dict[str, Any] = {}
    out["candidates"] = EC.evaluate_candidates(fast=fast, root=root)
    out["score_validation"] = ES.validate_all(fast=fast)
    sim = Simulator(params=tuned)
    recs = run_condition(tuned, pop_seed=DEV["pop_seed"], reps=reps, n_workers=nw, sessions=sess, cases_per_session=cps, sim=sim)
    dev_m = metrics(recs, B=B, seed=3)
    out["dev"] = {"split": f"dev population seed {DEV['pop_seed']} ({nw} workers), replicate seeds {list(reps)}", "params": tuned.to_dict(), "metrics": dev_m,
                  "acceptance_on_dev": decide_acceptance(dev_m)}
    sweep = {}
    for acc in (GROUND_SWEEP if not fast else (0.6, 1.0)):
        r = run_condition(tuned, ground_accuracy=acc, pop_seed=DEV["pop_seed"], reps=reps[:2], n_workers=nw, sessions=sess, cases_per_session=cps, sim=sim)
        m = metrics(r, B=B, seed=4)
        sweep[str(acc)] = {k: m[k] for k in ("p1_false_nudges_per_hour", "stuck_episodes_with_a_correct_cue_share", "wrong_target_cues_per_hour",
                                             "net_seconds_saved_per_hour", "acceptance_rate", "dismissal_rate")}
    out["grounding_sweep"] = {"accuracies": list(sweep), "rows": sweep, "split": "dev", "note": "A what-if: the fake port is right at this rate; wrong means not found or confidently another step."}
    amb = {}
    for name, beta, margin in (("confident_prior", (1.2, 4.0), tuned.margin_thr), ("split_prior_tuned_margin", (30.0, 30.0), tuned.margin_thr),
                               ("split_prior_wide_margin", (30.0, 30.0), 0.30)):
        p = tuned.with_(margin_thr=margin)
        r = run_condition(p, pop_seed=DEV["pop_seed"], reps=reps[:2], n_workers=nw, sessions=sess, cases_per_session=cps, sim=Simulator(params=p, expert_batch_beta=beta))
        m = metrics(r, B=B, seed=7)
        amb[name] = {"expert_batch_beta": list(beta), "margin_thr": margin, **{k: m[k] for k in ("questions_per_episode", "asks_per_hour", "stuck_episodes_with_a_correct_cue_share",
                                                                                                "p1_false_nudges_per_hour", "net_seconds_saved_per_hour", "violations")}}
    out["ambiguity_sweep"] = {"rows": amb, "split": "dev", "note": "A prior fitted on experts who split evenly between batching the cliff checks and not makes the top two candidates close; with the tuned margin of 0.10 that is still a clear call (0.63 against 0.37), with a margin of 0.30 it is a close call, which exercises the one-question rule."}
    if not fast:
        r = run_condition(tuned, pop_seed=DEV["pop_seed"], reps=reps[:2], n_workers=nw, signal="emulated", sim=sim)
        m = metrics(r, B=B, seed=5)
        out["signal_sweep"] = {"emulated_model_signal": {k: m[k] for k in ("p1_false_nudges_per_hour", "stuck_episodes_with_a_correct_cue_share",
                                                                           "net_seconds_saved_per_hour", "p2_seconds_to_resume_paired_diff")},
                               "note": "An emulation with stated discriminability (d-prime 1.5), not the real hazard model.", "split": "dev"}
    if held_out:
        hr = run_condition(tuned, pop_seed=HELD["pop_seed"], reps=HELD["reps"], n_workers=40, sim=Simulator(params=tuned))
        hm = metrics(hr, B=400, seed=6)
        out["held_out"] = {"split": f"held-out population seed {HELD['pop_seed']} (40 workers), replicate seeds {list(HELD['reps'])}", "params": tuned.to_dict(),
                           "metrics": hm, "acceptance": decide_acceptance(hm)}
    else:
        out["held_out"] = {"status": "not_run", "reason": "the held-out run is a separate frozen command (evals/cue/PLAN.md); evaluate_cue(fast) never looks at it"}
    from . import tierbandit as TB

    out["bandit_offline"] = TB.evaluate_bandit(fast=True if fast else False)
    out["readings"] = READINGS
    out["limitations"] = LIMITATIONS
    out["code_hashes"] = code_hashes()
    out["meta"] = analytic_meta("synthetic", nw, "personas", f"dev population seed {DEV['pop_seed']}; held-out seed {HELD['pop_seed']} (separate command)",
                                note="Simulated workers and learners; nothing here is evidence about people. Design targets are design choices.")
    out["design"] = {"assumptions": {k: (v if not isinstance(v, dict) else {str(a): b for a, b in v.items()}) for k, v in ASSUME.items()}, "dt_s": DT,
                     "voice_ok": False, "seconds": round(time.time() - t0, 1), "fast": fast}
    return out


# ------------------------------------------------------------------------------------------------ frozen commands
def held_out_run(*, seed0: int = ES.HELD_SEED0) -> dict[str, Any]:
    """The held-out look, run once per the plan: the Cue simulation on the held-out population and replicates with the tuned parameters, and
    the score validation on the held-out learner seeds for EVERY mastery variant (including the ones not adopted). Logs the code hashes."""
    t0 = time.time()
    tuned = PRM.TUNED
    hr = run_condition(tuned, pop_seed=HELD["pop_seed"], reps=HELD["reps"], n_workers=40, sim=Simulator(params=tuned))
    hm = metrics(hr, B=600, seed=6)
    return {"code_hashes": code_hashes(), "params": tuned.to_dict(),
            "cue": {"split": f"held-out population seed {HELD['pop_seed']} (40 workers), replicate seeds {list(HELD['reps'])}", "metrics": hm, "acceptance": decide_acceptance(hm)},
            "score_validation": {"split": f"held-out learner seeds {seed0}..{seed0 + 59} per kind", "variants": ES.validate_score(seed0=seed0, n_rep=60, n_boot_trend=200),
                                 "gaming": ES.gaming_sweep(seed0=seed0, n_rep=40)},
            "meta": analytic_meta("synthetic", 40, "personas", "held-out", note="Simulated; run once after evals/cue/PLAN.md was committed."), "seconds": round(time.time() - t0, 1)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="python -m understudy_engine.cue.evaluate")
    ap.add_argument("command", choices=("tune", "dev", "heldout"))
    ap.add_argument("--out", default=None, help="write JSON here (default evals/cue/<command>.json)")
    a = ap.parse_args(argv)
    out_dir = P.repo_root() / "evals" / "cue"
    res = tune_on_dev() if a.command == "tune" else (evaluate_cue(fast=False) if a.command == "dev" else held_out_run())
    path = Path(a.out) if a.out else out_dir / ({"tune": "tune_dev", "dev": "dev", "heldout": "held_out"}[a.command] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=1, sort_keys=True, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
