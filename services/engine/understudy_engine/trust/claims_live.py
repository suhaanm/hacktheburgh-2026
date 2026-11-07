"""Agent-claim calibration on REAL traces (ANA-14): agent-core's live-model grid, `data/eval/agent_live_runs.json`.

Real planner, tier 1 disabled, through the SafetyPipeline, on 20 synthetic households under several conditions
(clean, layout_v2, injected, glitch). Rows are one run each; only runs in which the agent CLAIMED success are scored, and the
label is 1 when the deterministic code check disagreed (a false claim).

Honest context, computed from the file rather than asserted: the false claims are ONE family of failures. They are the glitch
runs in which a calculator served a one-off 503 and the model, without page state in its prompt, claimed it was done on the error
page. A classifier can mostly learn 'a page was an error page', and a one-line rule ('a 5xx was seen') may do as well. The
evaluation therefore reports, beside the model: the base rate, the rule 'any 5xx seen', the rule 'any retry or escalation', and
the 'a confidence was stated' indicator (which is degenerate here, see below), on all claims and on the v1 runs only.

Features: the run-trace summaries in the file, except `stated_confidence`. The model only states a confidence when it makes a
finish claim itself, which in this data happened only in the glitch runs that went wrong, so its presence is a copy of the label,
not a signal; it is shown as a baseline and kept out of the classifier.

Protocol: leave one household out; Platt scaling is not applicable to the stated-confidence baseline (no variation in the label
among the rows that have one), so that baseline is the 'confidence present' indicator with training-fold frequencies.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust.calibration import brier, cluster_bootstrap_scores, ece, log_loss, reliability_bins
from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta
from understudy_engine.trust.stats import wilson_interval

LIVE_FEATURES = ("n_steps", "n_retries", "n_escalations", "n_precondition_failures", "time_ratio", "navigators_disagree",
                 "n_recoveries")
LABEL = "real model, tiny n, one family of failures"
N_BINS = 5


def default_path() -> Path:
    from understudy_engine.store import data_dir
    return data_dir() / "eval" / "agent_live_runs.json"


def load_live(path: Path | str | None = None) -> dict:
    p = Path(path) if path else default_path()
    if not p.is_file():
        raise FileNotFoundError(f"live agent runs not found: {p}")
    raw = json.loads(p.read_text())
    runs = {r["run_id"]: r for r in raw["runs"]}
    rows = []
    for row in raw["claim_calibration_rows"]:
        run = runs.get(row["run_id"], {})
        sw = run.get("switches") or {}
        f = row["features"]
        rows.append({
            "group": row["group"], "run_id": row["run_id"], "claimed": bool(row["claimed_success"]),
            "y": int(row["label_false_claim"]),
            "x": [float(f[k]) for k in LIVE_FEATURES],
            "stated_confidence": f.get("stated_confidence"),
            "condition": run.get("condition", "?"), "variant": run.get("variant", "?"),
            "any_5xx": float(any("glitch" in str(v) for v in sw.values())),    # a one-off 503 was served in this run
            "any_trouble": float(f["n_retries"] > 0 or f["n_escalations"] > 0),
            "conf_present": float(f.get("stated_confidence") is not None),
        })
    return {"rows": rows, "meta": raw.get("meta", {}), "n_runs": len(raw["runs"])}


def _folds_loho(groups: np.ndarray) -> list[np.ndarray]:
    return [np.where(groups == g)[0] for g in np.unique(groups)]


def _two_level(flag: np.ndarray, y: np.ndarray, tr: np.ndarray, te: np.ndarray) -> np.ndarray:
    """P(false claim | flag) estimated on the training rows with a 0.5 pseudo-count; a calibrated version of a yes/no rule."""
    out = np.empty(te.size)
    for v in (0.0, 1.0):
        m = flag[tr] == v
        out[flag[te] == v] = (y[tr][m].sum() + 0.5) / (m.sum() + 1.0)
    return out


def _recall_at_share(y: np.ndarray, score: np.ndarray, share: float) -> tuple[float, int]:
    """Expected number of false claims caught when the top `share` of rows by score are flagged; a cutoff that falls inside a tie
    group is resolved by random tie-breaking (expected value), so a yes/no rule is not credited with lucky ordering."""
    n = y.size
    k = max(1, int(round(share * n)))
    caught = 0.0
    left = k
    for s in sorted(set(score.tolist()), reverse=True):
        grp = score == s
        gsize = int(grp.sum())
        take = min(left, gsize)
        caught += float(y[grp].sum()) * take / gsize
        left -= take
        if left <= 0:
            break
    return caught, k


def _share_to_catch_all(y: np.ndarray, score: np.ndarray) -> float:
    """Smallest flagged share that is guaranteed to catch every false claim (whole tie groups are flagged)."""
    pos = score[y == 1]
    if pos.size == 0:
        return 0.0
    return float((score >= pos.min()).mean())


def _paired(y, p_a, p_b, groups, n_boot, seed) -> dict:
    """a minus b for log loss and Brier with a household-cluster bootstrap (negative = a is better)."""
    uniq, inv = np.unique(groups, return_inverse=True)
    c = uniq.size
    n_c = np.bincount(inv, minlength=c).astype(float)
    out = {}
    for name, fn in (("log_loss", lambda p: -(y * np.log(np.clip(p, 1e-12, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-12, 1)))),
                     ("brier", lambda p: (p - y) ** 2)):
        d = np.bincount(inv, weights=fn(p_a) - fn(p_b), minlength=c)
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(n_boot):
            pick = rng.integers(0, c, size=c)
            draws.append(d[pick].sum() / n_c[pick].sum())
        out[name] = {"value": float(d.sum() / n_c.sum()), "ci": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))]}
    return out


def _evaluate_subset(rows: list[dict], *, l2: float, n_boot: int, seed: int, review_budget: float) -> dict:
    X = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])
    g = np.array([r["group"] for r in rows])
    flags = {k: np.array([r[k] for r in rows]) for k in ("any_5xx", "any_trouble", "conf_present")}
    n = y.size
    preds = {k: np.full(n, np.nan) for k in ("model", "base_rate", "rule_any_5xx", "rule_any_retry_or_escalation",
                                              "confidence_present_indicator")}
    for te in _folds_loho(g):
        tr = np.setdiff1d(np.arange(n), te)
        preds["model"][te] = LogisticModel(l2=l2).fit(X[tr], y[tr]).predict_proba(X[te])
        preds["base_rate"][te] = (y[tr].sum() + 0.5) / (tr.size + 1.0)
        preds["rule_any_5xx"][te] = _two_level(flags["any_5xx"], y, tr, te)
        preds["rule_any_retry_or_escalation"][te] = _two_level(flags["any_trouble"], y, tr, te)
        preds["confidence_present_indicator"][te] = _two_level(flags["conf_present"], y, tr, te)

    def pack(p: np.ndarray) -> dict:
        ci = cluster_bootstrap_scores(y.astype(float), p, g, n_bins=N_BINS, n_boot=n_boot, seed=seed)
        caught, k = _recall_at_share(y, p, review_budget)
        total = int(y.sum())
        lo, hi = wilson_interval(int(round(caught)), total) if total else (0.0, 1.0)
        return {
            "brier": brier(y, p), "log_loss": log_loss(y, p), "ece": ece(y, p, N_BINS),
            "ci_brier": list(ci["brier"]), "ci_log_loss": list(ci["log_loss"]), "ci_ece": list(ci["ece"]),
            "flag_top_share": {"share": review_budget, "flagged": k, "false_claims_caught": caught, "false_claims_total": total,
                               "recall": caught / total if total else None, "recall_ci": [lo, hi],
                               "precision": caught / k},
            "share_needed_to_catch_every_false_claim": _share_to_catch_all(y, p),
        }

    full_fit = LogisticModel(l2=l2).fit(X, y)
    coef = {k: float(c) for k, c in zip(LIVE_FEATURES, full_fit.coef_)}      # per standard deviation of each feature
    out = {"n_claims": int(n), "n_false_claims": int(y.sum()), "n_households": int(len(np.unique(g))),
           "standardized_coefficients_full_fit": dict(sorted(coef.items(), key=lambda kv: -abs(kv[1]))),
           "base_failure_rate": float(y.mean()),
           "model": pack(preds["model"]),
           "baselines": {k: pack(v) for k, v in preds.items() if k != "model"},
           "reliability": reliability_bins(y, preds["model"], N_BINS),
           "model_minus_rule_any_5xx": _paired(y, preds["model"], preds["rule_any_5xx"], g, n_boot, seed),
           "model_minus_base_rate": _paired(y, preds["model"], preds["base_rate"], g, n_boot, seed)}
    f5 = flags["any_5xx"] == 1
    tp, fp, fn = int(((y == 1) & f5).sum()), int(((y == 0) & f5).sum()), int(((y == 1) & ~f5).sum())
    out["rule_any_5xx_confusion"] = {"flagged_false": tp, "flagged_but_ok": fp, "missed_false": fn,
                                     "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}
    return out


def evaluate_claims_live(path: Path | str | None = None, *, l2: float = 3.0, n_boot: int = 300, seed: int = 0,
                         review_budget: float = 0.2, fast: bool = False) -> dict:
    """Claim calibration on the live runs. Raises FileNotFoundError if the file is absent."""
    if fast:
        n_boot = min(n_boot, 60)
    data = load_live(path)
    claimed = [r for r in data["rows"] if r["claimed"]]
    if not claimed:
        raise ValueError("no run in the file claimed success")
    allc = _evaluate_subset(claimed, l2=l2, n_boot=n_boot, seed=seed, review_budget=review_budget)
    v1 = [r for r in claimed if r["variant"] != "v2_page_state"]
    v1res = _evaluate_subset(v1, l2=l2, n_boot=n_boot, seed=seed, review_budget=review_budget)

    by_cond: dict[str, dict] = {}
    for r in data["rows"]:
        key = f"{r['condition']}/{r['variant']}"
        d = by_cond.setdefault(key, {"runs": 0, "claimed": 0, "false_claims": 0})
        d["runs"] += 1
        d["claimed"] += int(r["claimed"])
        d["false_claims"] += int(r["claimed"] and r["y"] == 1)
    total_false = sum(v["false_claims"] for v in by_cond.values())
    conf_rows = [r for r in claimed if r["conf_present"] == 1]
    conf_false = sum(r["y"] for r in conf_rows)

    m, rule = allc["model"], allc["baselines"]["rule_any_5xx"]
    m1, rule1 = v1res["model"], v1res["baselines"]["rule_any_5xx"]
    d_all, d_v1 = allc["model_minus_rule_any_5xx"], v1res["model_minus_rule_any_5xx"]

    def excl(ci):
        return "excludes 0" if ci[0] > 0 or ci[1] < 0 else "includes 0"

    conf = allc["rule_any_5xx_confusion"]
    finding = (
        f"All {total_false} false claims are one family: glitch runs (a one-off 503 on one calculator) where the model claimed done on the error page; "
        f"the code check caught every one. On all {allc['n_claims']} claims the classifier's Brier is {m['brier']:.3f} against {rule['brier']:.3f} for the rule "
        f"'a 5xx was seen' (paired difference {d_all['brier']['value']:+.3f}, interval {excl(d_all['brier']['ci'])}), but only because the rule also flags "
        f"the {conf['flagged_but_ok']} glitch runs that the later fix handled correctly (precision {conf['precision']:.2f}, recall {conf['recall']:.2f}); the classifier "
        f"tells those runs apart through run length, retries and escalations, which differ partly because they had page state in the prompt and a larger action cap "
        f"(a code version, not a general failure signal). On the {v1res['n_claims']} runs without that fix the rule is perfect (Brier {rule1['brier']:.3f}) and the "
        f"classifier is no better ({m1['brier']:.3f}; difference {d_v1['brier']['value']:+.3f}, interval {excl(d_v1['brier']['ci'])}). "
        f"So it beats the rule only by learning the version; it has not been shown to know anything the rule does not.")
    out = {
        "label": LABEL,
        "origin": "synthetic", "n": allc["n_claims"], "n_unit": "runs", "n_groups": allc["n_households"],
        "split": f"leave-one-household-out ({allc['n_households']} households); scored on the {allc['n_claims']} runs where the agent claimed success",
        "interval_level": 0.95,
        "meta": analytic_meta("synthetic", allc["n_claims"], "runs", "leave-one-household-out; real model on sandbox sites",
                              note=f"{LABEL}. Sandbox households, real planner; false claims are one family (error pages)."),
        "source": {"file": "data/eval/agent_live_runs.json", "runs_in_file": data["n_runs"], "claims": allc["n_claims"],
                   "models": data["meta"].get("models"), "generated_at": data["meta"].get("generated_at")},
        "features_used": list(LIVE_FEATURES),
        "base_failure_rate": allc["base_failure_rate"],
        # keys the Evidence page reads
        "reliability": allc["reliability"], "brier": m["brier"], "base_rate": allc["base_failure_rate"],
        "all_claims": allc, "v1_runs_only": v1res,
        "by_condition": by_cond,
        "stated_confidence": {
            "rows_with_a_stated_confidence": len(conf_rows), "of_which_false_claims": int(conf_false),
            "excluded_from_model": True,
            "reason": "A confidence is stated only when the model itself makes a finish claim; here that happened only in the glitch runs that "
                      "went wrong, so its presence copies the label. Platt scaling cannot be fitted (no variation in the label among rows that have one). "
                      "The 'confidence_present_indicator' baseline shows the artifact.",
        },
        "finding": finding,
        "limitations": limitations_for("agent_claims_live"),
        "caveats": [
            f"{LABEL}: {allc['n_claims']} claims from {allc['n_households']} households; one cached live sample per repeated page situation, so runs are "
            "less independent than the count suggests.",
            "The glitch runs also differ in code version: v1 had no page state in the prompt and a 20-action cap, v2 had page state and a larger cap. Run length and time "
            "ratio therefore separate v1 from v2 for reasons other than the claim being false.",
            "'Any 5xx seen' is read from the experiment's glitch switch, a stand-in for an HTTP status a navigator would observe.",
            "Code still decides success. A low predicted risk never replaces the completion check.",
        ],
    }
    return out
