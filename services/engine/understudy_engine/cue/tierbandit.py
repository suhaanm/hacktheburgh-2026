"""The tier policy as a bandit (CUE-9): epsilon-greedy over {none, ring, chip, ask, voice}, logged propensities, implicit labels, OFF by default.

The hard rules of ``gate.decide`` always bound the choice: the bandit is only offered the actions those rules allow (it may silence, it
may pick a lighter or a different allowed tier; it cannot exceed a cap, bypass quiet or flow, or whisper without ``voice_ok``).

* Context: (stuck-probability bucket, margin bucket, help level, mastery bucket), a table of 3 x 2 x 4 x 3 cells.
* Reward for one decision opportunity: 1 if the stalled worker resumed within 30 s of the decision, minus the interruption cost of the
  action, minus the label penalty of ``policy.labels`` (dismissed 0.30, ...) for how the worker reacted (followed within 10 s, dismissed
  within 4 s: the implicit labels, a noisy proxy for "did it help").
* ``TierBandit.explore`` is False by default: ``choose`` returns the rule's action with propensity 1 and nothing is learned. Turning learning on
  needs an offline evaluation first (``evaluate_bandit``): IPS, SNIPS, direct method and doubly robust from ``policy/ope.py`` on logged
  simulated sessions, against the policy's value obtained by re-running the simulator. The report says whether any estimate is trustworthy;
  the default answer is no.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..policy import ope as OPE
from ..policy.labels import LABEL_PENALTY
from ..trust.meta import analytic_meta
from .gate import ACTIONS

K = len(ACTIONS)
EPS = 0.2
INTERRUPTION_COST = {"none": 0.0, "ring": 0.12, "chip": 0.20, "ask": 0.30, "voice": 0.45}
RESUME_WINDOW_S = 30.0
N_CELLS = 3 * 2 * 4 * 3


def context_index(p_stuck: float, margin: float, level: int, mastery: float) -> int:
    pb = 0 if p_stuck < 0.5 else (1 if p_stuck < 0.8 else 2)
    mb = 0 if margin < 0.3 else 1
    lb = min(max(int(level), 1), 4) - 1
    xb = 0 if mastery < 0.35 else (1 if mastery < 0.65 else 2)
    return ((pb * 2 + mb) * 4 + lb) * 3 + xb


def decision_reward(stuck_now: bool, resumed_in_s: float | None, action: str, outcome: str | None) -> float:
    """``outcome`` is the worker's reaction to what was shown: accepted -> followed, dismissed, ignored; None when nothing was shown."""
    label = {"accepted": "followed", "dismissed": "dismissed", "ignored": "ignored"}.get(outcome or "", "ignored")
    resumed = 1.0 if (stuck_now and resumed_in_s is not None and resumed_in_s <= RESUME_WINDOW_S) else 0.0
    return resumed - INTERRUPTION_COST[action] - (LABEL_PENALTY[label] if outcome is not None else 0.0)


@dataclass
class TierBandit:
    """Online epsilon-greedy over the allowed actions. ``explore=False`` (the default) is the rule policy: no exploration, no learning."""

    eps: float = EPS
    seed: int = 0
    explore: bool = False
    n: np.ndarray = field(default_factory=lambda: np.zeros((N_CELLS, K)))
    s: np.ndarray = field(default_factory=lambda: np.zeros((N_CELLS, K)))

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def q(self, cell: int) -> np.ndarray:
        return np.where(self.n[cell] > 0, self.s[cell] / np.maximum(self.n[cell], 1.0), 0.0)

    def choose(self, allowed: tuple[str, ...], rule: str, ctx: dict) -> tuple[str, float]:
        if not self.explore:
            return rule, 1.0
        cell = context_index(ctx["p_stuck"], ctx["margin"], ctx["level"], ctx["mastery"])
        q = self.q(cell)
        best = max(allowed, key=lambda a: (q[ACTIONS.index(a)] + (1e-9 if a == rule else 0.0)))      # ties go to the rule's action
        probs = {a: self.eps / len(allowed) + ((1.0 - self.eps) if a == best else 0.0) for a in allowed}
        a = list(probs)[int(self._rng.choice(len(probs), p=list(probs.values())))]
        return a, probs[a]

    def update(self, cell: int, action: str, reward: float) -> None:
        i = ACTIONS.index(action)
        self.n[cell, i] += 1
        self.s[cell, i] += reward


class EpsRuleChooser:
    """The LOGGING policy for offline evaluation: the rule's action with probability 1 - eps + eps/|allowed|, any other allowed action
    with eps/|allowed|. No learning, so every logged propensity is exact."""

    def __init__(self, eps: float = EPS, seed: int = 0) -> None:
        self.eps = eps
        self._rng = np.random.default_rng(seed)

    def __call__(self, allowed: tuple[str, ...], rule: str, ctx: dict) -> tuple[str, float]:
        probs = {a: self.eps / len(allowed) + ((1.0 - self.eps) if a == rule else 0.0) for a in allowed}
        a = list(probs)[int(self._rng.choice(len(probs), p=list(probs.values())))]
        return a, probs[a]


class TableChooser:
    """A deterministic target policy: greedy over the allowed actions of a (cell x action) value table, the rule's action on ties."""

    def __init__(self, table: np.ndarray | None = None) -> None:
        self.table = table

    def __call__(self, allowed: tuple[str, ...], rule: str, ctx: dict) -> tuple[str, float]:
        if self.table is None:
            return rule, 1.0
        q = self.table[context_index(ctx["p_stuck"], ctx["margin"], ctx["level"], ctx["mastery"])]
        return max(allowed, key=lambda a: (q[ACTIONS.index(a)] + (1e-9 if a == rule else 0.0))), 1.0


# ------------------------------------------------------------------------------------------------ logs from the simulator
def _logs(results) -> dict[str, np.ndarray]:
    rows = []
    for wi, wr in enumerate(results):
        ivs = wr.interventions
        for ch in wr.choices:
            if "resumed_at" not in ch:
                continue
            c = ch["choice"]
            action = c["action"]
            outcome = None
            if action != "none" and ch["n_before"] < len(ivs):
                outcome = ivs[ch["n_before"]].outcome
            resumed = (ch["resumed_at"] - ch["t"]) if ch["stuck_now"] else None
            rows.append((wi, context_index(ch["p"], ch["margin"], ch["level"], ch["mastery"]), ACTIONS.index(action), ACTIONS.index(c["rule"]),
                         c["propensity"], decision_reward(ch["stuck_now"], resumed, action, outcome), [a in c["allowed"] for a in ACTIONS]))
    if not rows:
        return {k: np.array([]) for k in ("w", "cell", "a", "rule", "p", "r", "allowed")}
    return {"w": np.array([r[0] for r in rows]), "cell": np.array([r[1] for r in rows]), "a": np.array([r[2] for r in rows]), "rule": np.array([r[3] for r in rows]),
            "p": np.array([r[4] for r in rows]), "r": np.array([r[5] for r in rows]), "allowed": np.array([r[6] for r in rows], bool)}


def fit_table(cell: np.ndarray, a: np.ndarray, r: np.ndarray, shrink: float = 2.0) -> np.ndarray:
    """Mean reward per (cell, action), shrunk toward the action's overall mean (cells and actions with no data take that mean)."""
    n = np.zeros((N_CELLS, K))
    s = np.zeros((N_CELLS, K))
    np.add.at(n, (cell, a), 1.0)
    np.add.at(s, (cell, a), r)
    gm = np.array([r[a == k].mean() if (a == k).any() else 0.0 for k in range(K)])
    return (s + shrink * gm[None, :]) / (n + shrink)


def _target_matrix(cell: np.ndarray, rule: np.ndarray, allowed: np.ndarray, table: np.ndarray | None) -> np.ndarray:
    T = np.zeros((cell.size, K))
    for i in range(cell.size):
        if table is None:
            T[i, rule[i]] = 1.0
        else:
            q = table[cell[i]].copy()
            q[rule[i]] += 1e-9
            q[~allowed[i]] = -np.inf
            T[i, int(np.argmax(q))] = 1.0
    return T


def _cluster_ci(logs: dict[str, np.ndarray], target: np.ndarray, Q: np.ndarray, B: int, seed: int) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    workers = np.unique(logs["w"])
    by_w = {w: np.where(logs["w"] == w)[0] for w in workers}
    draws: dict[str, list[float]] = {k: [] for k in ("ips", "snips", "dm", "dr")}
    for _ in range(B):
        pick = rng.choice(workers, size=workers.size, replace=True)
        idx = np.concatenate([by_w[w] for w in pick])
        est = OPE.point_estimates(logs["a"][idx], logs["r"][idx], logs["p"][idx], target[idx], Q[idx])
        for k in draws:
            draws[k].append(est[k])
    return {k: [round(float(x), 4) for x in np.nanquantile(v, [0.025, 0.975])] for k, v in draws.items()}


def evaluate_bandit(*, fast: bool = False, n_workers: int | None = None, reps: tuple[int, ...] = (0, 1, 2), seed: int = 0) -> dict[str, Any]:
    """Offline evaluation of two target policies (the rule, and the greedy table fitted on the logs) on SIMULATED sessions."""
    from .params import TUNED
    from .simulate import Simulator, make_population

    nw = n_workers or (16 if fast else 40)
    pop = make_population(11, nw)
    sess, cps = (2, 3) if fast else (3, 4)
    sim_log = Simulator(params=TUNED, chooser=EpsRuleChooser(EPS, seed))
    results = []
    for rep in (reps[:1] if fast else reps):
        results.extend(sim_log.run(pop, rep, arm="cue", sessions=sess, cases_per_session=cps))
    # cluster = the worker (replicates of one worker share a cluster)
    ids = {w.id: i for i, w in enumerate(pop)}
    logs = _logs(results)
    wid = []
    for r in results:
        wid.extend([ids[r.worker]] * sum(1 for ch in r.choices if "resumed_at" in ch))
    logs["w"] = np.array(wid, int)
    n = logs["r"].size
    out: dict[str, Any] = {"n_decisions": int(n), "n_workers": nw, "split": f"dev population seed 11; replicate seeds {list(reps[:1] if fast else reps)}",
                           "logging_policy": f"the rule's action with probability 1 - {EPS} + {EPS}/|allowed|, others {EPS}/|allowed|; no learning", "actions": list(ACTIONS)}
    if n < 50:
        out["status"] = "too_few_decisions"
        out["ready_to_enable"] = False
        out["reason"] = "fewer than 50 logged decision opportunities"
        out["meta"] = analytic_meta("synthetic", nw, "personas", "dev", note="Generated sessions.")
        return out
    # cross-fit by worker parity: the target's table never sees the rows it is scored on
    fold = (logs["w"] % 2).astype(int)
    target_greedy = np.zeros((n, K))
    for f in (0, 1):
        tr, te = fold != f, fold == f
        tbl = fit_table(logs["cell"][tr], logs["a"][tr], logs["r"][tr])
        target_greedy[te] = _target_matrix(logs["cell"][te], logs["rule"][te], logs["allowed"][te], tbl)
    target_rule = _target_matrix(logs["cell"], logs["rule"], logs["allowed"], None)
    # direct-method model, cross-fitted by worker parity
    Q = np.zeros((n, K))
    for f in (0, 1):
        tr, te = fold != f, fold == f
        Q[te] = fit_table(logs["cell"][tr], logs["a"][tr], logs["r"][tr])[logs["cell"][te]]
    full_table = fit_table(logs["cell"], logs["a"], logs["r"])
    rows = {}
    for name, target, chooser in (("rule", target_rule, TableChooser(None)), ("greedy_table", target_greedy, TableChooser(full_table))):
        est = OPE.point_estimates(logs["a"], logs["r"], logs["p"], target, Q)
        ci = _cluster_ci(logs, target, Q, 150 if fast else 300, seed + 1)
        diag = OPE.diagnostics(logs["a"], logs["p"], target)
        # the target's value by re-running the simulator with it in the loop (same random plans)
        sim_t = Simulator(params=TUNED, chooser=chooser)
        tr_results = []
        for rep in (reps[:1] if fast else reps):
            tr_results.extend(sim_t.run(pop, rep, arm="cue", sessions=sess, cases_per_session=cps))
        # the truth is computed with propensity-free rewards: the policy is deterministic, so rewards are those of its own decisions
        tl = _logs(tr_results)
        truth = float(tl["r"].mean()) if tl["r"].size else None
        rows[name] = {"estimates": {k: round(float(v), 4) for k, v in est.items()}, "intervals": ci, "diagnostics": {k: round(float(v), 4) for k, v in diag.items()},
                      "resimulated_value": None if truth is None else round(truth, 4), "resimulated_n": int(tl["r"].size)}
    out["targets"] = rows
    out["logging_policy_value"] = round(float(logs["r"].mean()), 4)
    g, r_ = rows["greedy_table"], rows["rule"]
    dr_diff = g["estimates"]["dr"] - r_["estimates"]["dr"]
    trustworthy = g["diagnostics"]["ess"] >= 200 and g["diagnostics"]["max_weight"] <= 20 and g["intervals"]["dr"][0] > r_["estimates"]["dr"]
    out["ready_to_enable"] = bool(trustworthy)
    out["reason"] = ("the greedy table's doubly robust interval clears the rule's value and the effective sample size is large enough" if trustworthy else
                     f"the doubly robust difference to the rule is {dr_diff:+.3f} with an interval that does not clear the rule's value, or the effective sample size ({g['diagnostics']['ess']:.0f}) is too small: do not turn learning on")
    out["limitations"] = ["Logged on generated sessions only; the reward is a stated proxy (resumed within 30 s minus interruption cost minus label penalty).",
                          "The replayed value is per decision opportunity under the target's own trajectory, so it is an approximate truth for the estimators, not an exact one.",
                          "A dismissal can mean 'I already knew': the label penalty is a noisy proxy."]
    out["meta"] = analytic_meta("synthetic", nw, "personas", "dev; cross-fitted by worker; cluster bootstrap over workers", note="Generated sessions; learning stays off by default.")
    return out
