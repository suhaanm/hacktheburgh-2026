"""Evaluation entry points for the intervention policy (ANA-6, ANA-7, COA-4). Plain-dict outputs.

evaluate_ope()   simulator with known truth: do IPS / SNIPS / DM / DR recover the true value of target policies
                 from epsilon-greedy logs, and how biased are the naive averages? One detailed run with
                 bootstrap intervals, plus R independent replications for bias, RMSE and interval coverage.
evaluate_gate()  false nudges per hour with and without the dignity gate, on held-out hazard predictions.
"""
from __future__ import annotations

import numpy as np

from understudy_engine.core import Episode
from understudy_engine.hazard.evaluate import oof_predictions
from understudy_engine.hazard.events import (
    EpisodeEvents, alarms_for, pool, score_alarms, stuck_events,
)
from understudy_engine.policy import ope, rules, sim
from understudy_engine.policy.context import K, NUDGE
from understudy_engine.policy.gate import GateParams, gate_alarms

ESTIMATORS = ("ips", "snips", "dm", "dr", "naive_on_policy", "naive_matched")


def _targets(snapshot) -> dict:
    return {
        "rule_baseline": lambda X: rules.rule_probs(X),
        "bandit_greedy_snapshot": lambda X: snapshot.policy_probs(X),
        "always_nudge": lambda X: np.tile(np.eye(K)[NUDGE], (X.shape[0], 1)),
    }


def _one_run(n: int, seed: int, n_boot: int, truth_cache: dict | None = None) -> tuple[dict, dict]:
    X, a, r, p, _g, _bandit, snap = sim.simulate_log(n, seed=seed)
    half = n // 2
    Xs, as_, rs, ps = X[half:], a[half:], r[half:], p[half:]
    out = {}
    for name, fn in _targets(snap).items():
        # the "snapshot" policy differs per run, so its truth is recomputed; fixed policies are cached
        if name == "bandit_greedy_snapshot" or truth_cache is None or name not in truth_cache:
            tv = sim.true_value(fn)
            if truth_cache is not None and name != "bandit_greedy_snapshot":
                truth_cache[name] = tv
        else:
            tv = truth_cache[name]
        res = ope.evaluate_policy_value(Xs, as_, rs, ps, fn(Xs), n_boot=n_boot, seed=seed)
        out[name] = {"true_value": tv, **res}
    meta = {"n_logged": n, "n_evaluated": n - half, "action_share": (np.bincount(a, minlength=K) / n).tolist(),
            "mean_logged_reward": float(r.mean())}
    return out, meta


def evaluate_ope(n: int = 6000, seed: int = 0, n_boot: int = 500, replications: int = 24,
                 rep_n: int = 2400, rep_boot: int = 150) -> dict:
    """One detailed run (seed) and `replications` independent small runs (seeds seed+1000...)."""
    detail, meta = _one_run(n, seed, n_boot)
    targets = {}
    for name, d in detail.items():
        tv = d["true_value"]
        est = {k: {"estimate": d["estimates"][k], "ci": d["intervals"][k], "error": d["estimates"][k] - tv,
                   "ci_covers_truth": bool(d["intervals"][k][0] <= tv <= d["intervals"][k][1])}
               for k in ESTIMATORS}
        targets[name] = {"true_value": tv, "estimators": est, "diagnostics": d["diagnostics"]}
    out = {
        "origin": "synthetic", "n": int(n), "n_unit": "decisions",
        "split": "logs from the second half of an online epsilon-greedy run (eps 0.2); the bandit-greedy target "
                 "is a snapshot taken at the halfway point so it never saw the evaluated rows",
        "interval_level": 0.95,
        "logging": {**meta, "epsilon": 0.2},
        "optimal_value": sim.optimal_value(),
        "targets": targets,
    }
    if replications > 0:
        cache: dict = {}
        errs = {t: {k: [] for k in ESTIMATORS} for t in ("rule_baseline", "bandit_greedy_snapshot", "always_nudge")}
        cover = {t: {k: [] for k in ESTIMATORS} for t in errs}
        for i in range(replications):
            res, _ = _one_run(rep_n, seed + 1000 + i, rep_boot, cache)
            for name, d in res.items():
                tv = d["true_value"]
                for k in ESTIMATORS:
                    errs[name][k].append(d["estimates"][k] - tv)
                    lo, hi = d["intervals"][k]
                    cover[name][k].append(lo <= tv <= hi)
        out["replications"] = {
            "n_replications": replications, "n_logged_each": rep_n,
            "by_target": {
                name: {k: {"mean_error": float(np.mean(errs[name][k])),
                           "rmse": float(np.sqrt(np.mean(np.square(errs[name][k])))),
                           "ci_coverage": float(np.mean(cover[name][k]))} for k in ESTIMATORS}
                for name in errs},
        }
    out["caveats"] = [
        "Synthetic simulator: the reward structure is invented by us. It shows the estimators recover a known truth, "
        "not that the real reward looks like this.",
        "Implicit labels (followed, dismissed, repeated, undone) are noisy proxies for 'did it help'; the reward model "
        "weights them by assumption.",
        "Intervals hold the cross-fitted reward model fixed and resample decisions; they do not include the "
        "variance of re-fitting it.",
        "Doubly robust needs correct logged propensities. The simulator logs them exactly; in a live system a "
        "logging bug would break every estimate here.",
        "Weights reach 20 (propensity floor 0.05); effective sample size is reported with each target.",
    ]
    return out


def evaluate_gate(episodes: list[Episode], *, params: GateParams = GateParams(), raw_threshold: float | None = None,
                  seed: int = 0) -> dict:
    """False nudges per hour of held-out hazard predictions: a bare threshold on every 30 s bin versus the dignity
    gate (2 consecutive signals, cooldown, silent when below threshold)."""
    tab, p = oof_predictions(episodes)
    thr = params.p_signal if raw_threshold is None else raw_threshold
    raw: dict[int, EpisodeEvents] = {}
    gated: dict[int, EpisodeEvents] = {}
    for e in range(len(tab.ep_person)):
        a0, a1 = int(tab.ep_offsets[e]), int(tab.ep_offsets[e + 1])
        t, y, pe = tab.t[a0:a1], tab.y[a0:a1], p[a0:a1]
        raw_alarms = t[pe >= thr]  # a nudge on every bin above threshold: no confirmation, no cooldown
        raw[e] = score_alarms(t, y, raw_alarms, bin_s=tab.bin_s)
        gated[e] = score_alarms(t, y, gate_alarms(t, pe, params), bin_s=tab.bin_s)
    r, g = pool(raw.values()), pool(gated.values())

    def pack(res) -> dict:
        d = res.as_dict()
        d["nudges_total"] = res.false_alarms + res.true_alarms
        d["nudges_per_stuck_event"] = None if not res.n_events else d["nudges_total"] / res.n_events
        return d

    return {
        "origin": episodes[0].origin if len({e.origin for e in episodes}) == 1 else "mixed",
        "n": len(tab.people), "n_unit": "people", "split": "leave-one-person-out",
        "interval_level": 0.95,
        "gate_params": {"need": params.need, "cooldown_s": params.cooldown_s, "p_signal": params.p_signal},
        "raw_threshold": thr,
        "bare_threshold": pack(r), "dignity_gate": pack(g),
        "false_nudges_per_hour_reduction": (None if not r.fa_per_hour or not np.isfinite(r.fa_per_hour)
                                            else 1.0 - g.fa_per_hour / r.fa_per_hour),
        "caveats": [
            "A 'false nudge' is a nudge outside any stuck event (stuck = no progress for about two minutes), so "
            "it measures annoyance, not harm. Nudges per stuck event shows the repeated-nudge burden the gate removes.",
            "The gate trades latency for fewer interruptions; the detection and latency numbers show that trade.",
            "Held-out hazard predictions come from synthetic personas unless the data origin says otherwise.",
        ],
    }
