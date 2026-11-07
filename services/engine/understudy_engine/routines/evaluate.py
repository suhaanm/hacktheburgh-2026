"""Evaluation functions for the eval harness (ANA-10, ANA-11): plain dicts with metrics, split, intervals, n, n_unit, origin.

* ``evaluate_finder``: precision and recall of the routine finder against planted routines, on the synthetic personas.
* ``evaluate_ski_rental``: regret against the hindsight best and against break-even, on simulated workdays.
* ``evaluate_forecast``: does the recurrence forecast's interval cover what happened next (planted routines).

Ground truth (``truth.json``) is read only to score. Precision is reported at two levels, because they answer different
questions: **clusters** (the finder's raw output at minimum support 3) and **proposals** (what survives the value gate and
would reach the worker as a card).
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Any

import numpy as np

from ..core import Event
from ..memory.packinfo import load_pack
from ..memory.paths import data_dir
from ..presence.personas import PERSONAS, have_persona, load_persona
from .detect import DetectConfig, detect_routines
from .finder import FinderConfig, find_routines
from .forecast import DAY, backtest_coverage
from .simulate import SimConfig, regret_table
from .skirental import robustness


def persona_episodes(name: str, root: Path | None = None):
    """Episodes (via the cog mapper) and truth labels for one synthetic persona."""
    from ..cogs import segment_episodes

    rows, truth = load_persona(name, root)
    events = [Event.model_validate(r) for r in rows]
    eps = segment_episodes(events)
    labels = {}
    for r in truth["routines"]:
        for i in r["instances"]:
            labels[i["task_id"]] = r["name"]
    return eps, labels, truth


def _wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z / d) * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def _score_clusters(member_task_ids: list[list[str]], labels: dict[str, str], truth_counts: dict[str, int], min_support: int) -> dict[str, Any]:
    """Cluster-level precision (clusters whose majority is one planted routine) and recall (planted routines found)."""
    tp, found, purity = 0, set(), []
    for tids in member_task_ids:
        cnt = collections.Counter(labels.get(t, "adhoc") for t in tids)
        top, n = cnt.most_common(1)[0]
        purity.append(n / len(tids) if top != "adhoc" else 0.0)
        if top != "adhoc" and n / len(tids) >= 0.5:
            tp += 1
            found.add(top)
    detectable = {l for l, n in truth_counts.items() if n >= min_support}
    n_ep = sum(len(t) for t in member_task_ids)
    ep_ok = sum(collections.Counter(labels.get(t, "adhoc") for t in tids).most_common(1)[0][1]
                for tids in member_task_ids if collections.Counter(labels.get(t, "adhoc") for t in tids).most_common(1)[0][0] != "adhoc")
    return {"clusters": len(member_task_ids), "true_clusters": tp, "precision": round(tp / len(member_task_ids), 3) if member_task_ids else None,
            "precision_ci": _wilson(tp, len(member_task_ids)), "planted": sorted(truth_counts), "detectable": sorted(detectable),
            "found": sorted(found & detectable), "missed": sorted(detectable - found), "undetectable_support_below_min": sorted(set(truth_counts) - detectable),
            "recall": round(len(found & detectable) / len(detectable), 3) if detectable else None,
            "recall_ci": _wilson(len(found & detectable), len(detectable)),
            "episode_precision": round(ep_ok / n_ep, 3) if n_ep else None, "mean_purity_of_true_clusters": round(float(np.mean([p for p in purity if p > 0])), 3) if any(p > 0 for p in purity) else None}


def evaluate_finder(root: Path | None = None, *, min_support: int = 3, wage_gbp_h: float = 15.0) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name in PERSONAS:
        if not have_persona(name, root):
            continue
        eps, labels, truth = persona_episodes(name, root)
        pack = load_pack(truth.get("role", "benefits-processor"))
        truth_counts = {r["name"]: len(r["instances"]) for r in truth["routines"]}
        fcfg = FinderConfig(min_support=min_support)
        clusters = find_routines(eps, fcfg)
        raw = _score_clusters([[e.task_id for e in c.episodes] for c in clusters], labels, truth_counts, min_support)
        detected = detect_routines(eps, pack, person=truth.get("person", "p"), cfg=DetectConfig(finder=fcfg, wage_gbp_h=wage_gbp_h))
        shown = [d for d in detected if d["proposable"] or d["value"]["confidence"] >= 0.5]
        # skill gate is not what is measured here: count value-worthy routines whether or not the worker has mastered them
        prop = _score_clusters([d["member_task_ids"] for d in shown], labels, truth_counts, min_support)
        rows.append({"persona": name, "person": truth.get("person"), "n_episodes": len(eps),
                     "planted": len(truth_counts), "found": len(raw["found"]), "precision": prop["precision"], "recall": raw["recall"],
                     "finder": raw, "proposals": prop,
                     "reported": len(detected), "proposed_ids": [d["id"] for d in shown]})
    tot = {"clusters": sum(r["finder"]["clusters"] for r in rows), "true": sum(r["finder"]["true_clusters"] for r in rows),
           "p_clusters": sum(r["proposals"]["clusters"] for r in rows), "p_true": sum(r["proposals"]["true_clusters"] for r in rows),
           "detectable": sum(len(r["finder"]["detectable"]) for r in rows), "found": sum(len(r["finder"]["found"]) for r in rows)}
    overall = {
        "precision": round(tot["p_true"] / tot["p_clusters"], 3) if tot["p_clusters"] else None,
        "precision_ci": _wilson(tot["p_true"], tot["p_clusters"]),
        "recall": round(tot["found"] / tot["detectable"], 3) if tot["detectable"] else None,
        "recall_ci": _wilson(tot["found"], tot["detectable"]),
        "finder_precision": round(tot["true"] / tot["clusters"], 3) if tot["clusters"] else None,
        "finder_precision_ci": _wilson(tot["true"], tot["clusters"]),
    }
    limits = [
        {"id": "routines-synthetic", "severity": "high",
         "text": f"Routine precision and recall are scored on {len(rows)} synthetic personas whose routines were planted by a generator "
                 "that varies steps and timing but not the way real people drift. They show the method recovers planted structure, not that real routines look like this."},
        {"id": "routines-finder-noise", "severity": "medium",
         "text": f"The finder alone (minimum support 3) returns many small clusters of one-off work: precision {overall['finder_precision']:.0%} over "
                 f"{tot['clusters']} clusters. The value gate removes them: precision {overall['precision']:.0%} over {tot['p_clusters']} proposals. "
                 "Short routines of three or four steps are the hardest to tell from chance."},
    ]
    undetect = sorted({f"{r['persona']}/{n}" for r in rows for n in r["finder"]["undetectable_support_below_min"]})
    if undetect:
        limits.append({"id": "routines-rare", "severity": "low",
                       "text": "Planted routines that ran fewer than 3 times cannot be found by design and are excluded from recall: " + ", ".join(undetect) + "."})
    missed = [f"{r['persona']}/{m}" for r in rows for m in r["finder"]["missed"]]
    if missed:
        limits.append({"id": "routines-missed", "severity": "medium", "text": "Detectable planted routines the finder missed: " + ", ".join(missed) + "."})
    return {"name": "routine_finder", "meta": {"origin": "synthetic", "n": len(rows), "n_unit": "personas", "interval_level": 0.95,
                                              "split": "unsupervised finder; truth used only to score", "note": None},
            "origin": "synthetic", "n": len(rows), "n_unit": "personas", "interval_level": 0.95,
            "split": "no fitting: the finder is unsupervised; truth is used only to score", "min_support": min_support,
            "rows": [{"persona": r["persona"], "planted": r["planted"], "found": r["found"], "precision": r["precision"], "recall": r["recall"]} for r in rows],
            "overall": {"precision": overall["precision"], "recall": overall["recall"]},
            "metrics": overall, "personas": rows, "limitations": limits,
            "note": "Precision counts proposals (after the value gate); recall counts planted routines with at least the minimum support."}


def evaluate_forecast(root: Path | None = None) -> dict[str, Any]:
    """Backtest the recurrence forecast on planted routines: fit on the first two weeks, compare with the third."""
    rows = []
    for name in PERSONAS:
        if not have_persona(name, root):
            continue
        _, truth = load_persona(name, root)
        from datetime import datetime

        start = datetime.fromisoformat(truth["start_date"] + "T00:00:00+00:00").timestamp()
        for r in truth["routines"]:
            times = [datetime.fromisoformat(i["t0"].replace("Z", "+00:00")).timestamp() for i in r["instances"]]
            if len(times) < 8:
                continue
            bt = backtest_coverage(times, start, start + 14 * DAY, start + 21 * DAY)
            rows.append({"persona": name, "routine": r["name"], **{k: round(v, 2) for k, v in bt.items()}})
    n = len(rows)
    cov = sum(r["inside"] for r in rows)
    return {"name": "forecast", "origin": "synthetic", "n": n, "n_unit": "routines", "interval_level": 0.95,
            "split": "fit on days 1-14, scored on days 15-21", "rows": rows,
            "metrics": {"interval_coverage": round(cov / n, 3) if n else None, "interval_coverage_ci": _wilson(int(cov), n)},
            "limitations": [{"id": "forecast-small-n", "severity": "medium",
                             "text": (f"The 95% forecast interval covered what happened in {int(cov)} of {n} planted routines ({cov / n:.0%}), "
                                      "which is below nominal and rests on one held-out week; the schedule change on day 15 falls inside it, "
                                      "and the model has no way to know about it.") if n else "No planted routines had enough runs to backtest the forecast."}]}


def routines_report(finder: dict[str, Any]) -> dict[str, Any]:
    """The ``routines`` row of /eval/report from ``evaluate_finder``."""
    return {"rows": finder["rows"], "overall": finder["overall"],
            "meta": {"origin": "synthetic", "n": finder["n"], "n_unit": "personas", "interval_level": 0.95,
                     "split": "planted routines per persona, found by the routine finder",
                     "note": "Precision is over proposals (after the value gate); recall over planted routines with at least 3 runs."}}


def _ratio_rows(x: np.ndarray, y: np.ndarray, b: float, lambdas: tuple[float, ...], seed: int = 9) -> list[dict[str, Any]]:
    from . import skirental as sk

    opt = np.minimum(x, b)
    rng = np.random.default_rng(seed)
    idx = [rng.integers(0, len(x), len(x)) for _ in range(300)]

    def ratio(cost: np.ndarray) -> tuple[float, list[float]]:
        boots = [cost[i].sum() / max(opt[i].sum(), 1e-9) for i in idx]
        return round(float(cost.sum() / max(opt.sum(), 1e-9)), 3), [round(float(q), 3) for q in np.quantile(boots, [0.025, 0.975])]

    rows = []
    specs = [("Build now", "buy-now", None, lambda xi, yi: 1), ("Build at break-even", "break-even", None, lambda xi, yi: sk.break_even_run(b))]
    for l in lambdas:
        specs.append((f"Ski rental with predictions (lambda {l:g})", "predictions", l, (lambda l_: lambda xi, yi: sk.buy_run(yi, b, l_))(l)))
    for label, rule, lam, fn in specs:
        reg, ci = ratio(np.array([sk.cost(xi, fn(xi, yi), b) for xi, yi in zip(x, y)]))
        row = {"rule": rule, "label": label, "b": b, "regret": reg, "ci": ci}
        if lam is not None:
            row["lambda"] = lam
            row["robustness_bound"] = round(sk.robustness(lam), 2)
            row["consistency_bound"] = round(sk.consistency(lam), 2)
        rows.append(row)
    return rows


def evaluate_ski_rental(cfg: SimConfig | None = None, *, b: float = 16.0, sweep: tuple[float, ...] = (4.0, 8.0, 16.0, 32.0),
                        lambdas: tuple[float, ...] = (0.2, 0.5)) -> dict[str, Any]:
    """Regret as a competitive ratio (mean cost / mean hindsight cost; hindsight = 1.0), on simulated workdays.

    ``rows`` are at buy cost ``b`` (in manual runs); ``sweep`` shows every buy cost, because the winner changes with it.
    """
    from .simulate import simulate_routines

    cfg = cfg or SimConfig()
    x, y = simulate_routines(cfg)
    sweep_rows = {f"{bb:g}": _ratio_rows(x, y, bb, lambdas) for bb in sweep}
    rows = sweep_rows.get(f"{b:g}") or _ratio_rows(x, y, b, lambdas)
    wins = []
    for bb, rr in sweep_rows.items():
        best = min(rr, key=lambda r: r["regret"])
        wins.append(f"b={bb}: {best['label']} ({best['regret']:.2f})")
    cheap = sweep_rows[f"{min(sweep):g}"]
    nowr = next(r for r in cheap if r["rule"] == "buy-now")["regret"]
    ski = min((r for r in cheap if r["rule"] == "predictions"), key=lambda r: r["regret"])["regret"]
    be_ = next(r for r in cheap if r["rule"] == "break-even")["regret"]
    limits = [
        {"id": "ski-simulated", "severity": "high",
         "text": "Ski-rental regret is measured on simulated routines (lognormal run rates, 45% retiring after an exponential life, the forecast sees 10 workdays), "
                 "not on real build decisions. It shows the rule's behaviour against break-even under a stated mechanism."},
        {"id": "ski-not-uniformly-best", "severity": "medium",
         "text": "The rule is not the best everywhere. Lowest regret by build cost: " + "; ".join(wins) + ". "
                 f"When building is cheap (b = {min(sweep):g} manual runs) building at once ({nowr:.2f}) is "
                 + ("level with" if abs(nowr - ski) < 0.01 else "ahead of" if nowr < ski else "behind")
                 + f" the rule ({ski:.2f}) and both are ahead of break-even ({be_:.2f}); "
                 "the prediction earns its keep when building costs more. The pack's own build costs are 4 to 9 runs."},
        {"id": "ski-lambda-heuristic", "severity": "low",
         "text": "The trust parameter lambda is fixed by us (or set from past forecast error by a heuristic that is not in the paper). It was not tuned on this simulation."},
    ]
    return {
        "name": "ski_rental", "rows": rows, "hindsight_regret": 1.0, "hindsight": 1, "sweep": sweep_rows, "b_manual_runs": b,
        "robustness_bounds": {f"{l:g}": round(__import__("understudy_engine.routines.skirental", fromlist=["robustness"]).robustness(l), 2) for l in lambdas},
        "origin": "synthetic", "n": cfg.n_routines, "n_unit": "routines", "interval_level": 0.95,
        "split": f"simulated workdays; the forecast sees {cfg.history_workdays} workdays of history, the cost is over the {cfg.horizon_workdays - cfg.history_workdays} after",
        "meta": {"origin": "synthetic", "n": cfg.n_routines, "n_unit": "routines", "interval_level": 0.95,
                 "split": f"simulated workdays; buy cost b = {b:g} manual runs; forecast sees {cfg.history_workdays} workdays, cost over the next {cfg.horizon_workdays - cfg.history_workdays}",
                 "note": "Regret = cost divided by the hindsight-best cost (1.0 is perfect). Simulated mechanism; not real build decisions."},
        "metrics": {"b": b}, "limitations": limits,
    }


def ski_rental_report(cfg: SimConfig | None = None, **kw) -> dict[str, Any]:
    """The ``ski_rental`` row of /eval/report."""
    r = evaluate_ski_rental(cfg, **kw)
    return {"rows": r["rows"], "hindsight_regret": 1.0, "hindsight": 1, "sweep": r["sweep"], "meta": r["meta"]}
