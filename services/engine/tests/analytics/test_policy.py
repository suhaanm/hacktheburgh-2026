import datetime as dt
import json

import numpy as np
import pytest

from understudy_engine.core import Event
from understudy_engine.hazard.sim import simulate_people
from understudy_engine.policy import labels as LB
from understudy_engine.policy import ope, rules, sim
from understudy_engine.policy.bandit import EPS, EpsGreedyBandit
from understudy_engine.policy.context import ANNOTATE, K, NUDGE, SILENT, TAKEOVER, make_context
from understudy_engine.policy.evaluate import evaluate_gate, evaluate_ope
from understudy_engine.policy.gate import GateParams, GateState, gate_alarms, gate_step


# ---------------- dignity gate ----------------
def run_gate(ps, dt_s=30.0, params=GateParams(), unsure=None):
    st, acts, reasons = GateState(), [], []
    for i, p in enumerate(ps):
        d = gate_step(st, p, 1000.0 + i * dt_s, unsure=bool(unsure[i]) if unsure else False, params=params)
        st = d.state
        acts.append(d.act)
        reasons.append(d.reason)
    return acts, reasons


def test_gate_needs_two_consecutive_signals():
    acts, reasons = run_gate([0.9, 0.2, 0.9, 0.9])
    assert acts == [False, False, False, True]
    assert reasons == ["wait_signals", "below_threshold", "wait_signals", "act"]


def test_gate_cooldown_then_acts_again_only_if_still_stuck():
    acts, reasons = run_gate([0.9] * 10, dt_s=30.0)  # cooldown 120 s = 4 bins
    assert [i for i, a in enumerate(acts) if a] == [1, 5, 9]
    assert reasons[2:5] == ["cooldown"] * 3
    acts2, _ = run_gate([0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1], dt_s=30.0)
    assert sum(acts2) == 1  # the person recovered during the cooldown: no second prompt


def test_gate_is_silent_when_unsure_and_unsure_breaks_the_chain():
    acts, reasons = run_gate([0.9, 0.9, 0.9], unsure=[False, True, False])
    assert acts == [False, False, False] and reasons[1] == "unsure"
    # low confidence counts as unsure
    d = gate_step(GateState(1, -1e18), 0.95, 0.0, confidence=0.3, params=GateParams(min_confidence=0.5))
    assert not d.act and d.reason == "unsure" and d.state.consecutive == 0


def test_gate_alarms_over_a_series():
    t = 1000.0 + 30.0 * np.arange(8)
    p = np.array([0, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0])
    assert gate_alarms(t, p).tolist() == [t[2], t[6]]


# ---------------- rule baseline ----------------
def ctx(p=0.9, level=1, since=1.0, consec=3, risk=0, mastery=0.2):
    return make_context(p, level, since, consec, risk, mastery)


def test_rule_baseline_by_level_and_gate():
    assert rules.rule_action(ctx(level=1)) == ANNOTATE
    assert rules.rule_action(ctx(level=2)) == ANNOTATE
    assert rules.rule_action(ctx(level=3)) == NUDGE
    assert rules.rule_action(ctx(level=4)) == SILENT
    assert rules.rule_action(ctx(consec=1)) == SILENT       # fewer than two consecutive signals
    assert rules.rule_action(ctx(since=0.4)) == SILENT       # cooldown not over
    assert rules.rule_action(ctx(p=0.4)) == SILENT           # not a clear signal
    P = rules.rule_probs(np.vstack([ctx(level=1), ctx(level=4)]))
    assert P.sum(1).tolist() == [1.0, 1.0] and P[0, ANNOTATE] == 1 and P[1, SILENT] == 1


# ---------------- implicit labels ----------------
BASE = dt.datetime(2026, 11, 7, 12, 0, 0, tzinfo=dt.timezone.utc)


def ev(t_s, typ, person="p_a", **meta):
    return Event.model_validate({
        "schema": 1, "id": f"e{t_s}{typ}", "t": BASE + dt.timedelta(seconds=t_s), "origin": "synthetic",
        "actor": "human", "person": person, "role": "r", "source": "coach", "type": typ, "meta": meta,
    })


def one(events):
    out = LB.label_prompts(events)
    assert len(out) == 1
    return out[0].label


def test_followed_within_ten_seconds_only():
    assert one([ev(0, "coach_shown", action="nudge", issue=1), ev(9.5, "coach_followed")]) == "followed"
    assert one([ev(0, "coach_shown", action="nudge", issue=1), ev(10.5, "coach_followed")]) == "ignored"


def test_dismissed_within_four_seconds_only():
    assert one([ev(0, "coach_shown", issue=1), ev(3.9, "coach_dismissed")]) == "dismissed"
    assert one([ev(0, "coach_shown", issue=1), ev(4.5, "coach_dismissed")]) == "ignored"


def test_repeated_means_same_issue_again_within_ten_seconds():
    assert one([ev(0, "coach_shown", issue=7), ev(8, "stuck", issue=7)]) == "repeated"
    assert one([ev(0, "coach_shown", issue=7), ev(8, "stuck", issue=8)]) == "ignored"
    assert one([ev(0, "coach_shown", issue=7), ev(11, "stuck", issue=7)]) == "ignored"
    two = LB.label_prompts([ev(0, "coach_shown", issue=7), ev(6, "coach_shown", issue=7)])
    assert [x.label for x in two] == ["repeated", "ignored"]


def test_undo_within_ten_seconds_of_the_prompt_or_the_follow():
    assert one([ev(0, "coach_shown", action="takeover", issue=1), ev(8, "undo")]) == "undone"
    assert one([ev(0, "coach_shown", issue=1), ev(2, "coach_followed"), ev(11, "undo")]) == "undone"
    assert one([ev(0, "coach_shown", issue=1), ev(2, "coach_followed"), ev(13, "undo")]) == "followed"


def test_precedence_undone_over_dismissed_over_repeated_over_followed():
    assert one([ev(0, "coach_shown", issue=1), ev(1, "coach_followed"), ev(2, "stuck", issue=1)]) == "repeated"
    assert one([ev(0, "coach_shown", issue=1), ev(1, "coach_followed"), ev(2, "coach_dismissed")]) == "dismissed"
    assert one([ev(0, "coach_shown", issue=1), ev(2, "coach_dismissed"), ev(5, "undo")]) == "undone"


def test_other_people_do_not_label_my_prompt():
    out = LB.label_prompts([ev(0, "coach_shown", person="p_a", issue=1), ev(2, "coach_followed", person="p_b")])
    assert out[0].label == "ignored"


def test_reward_formula():
    assert LB.reward(2, "silent") == 2.0
    assert LB.reward(1, "nudge") == pytest.approx(1 - 0.12)
    assert LB.reward(1, "takeover") == pytest.approx(1 - 0.45 - 0.40)
    assert LB.reward(0, "annotate", "dismissed") == pytest.approx(-0.20 - 0.30)
    assert LB.reward(0, TAKEOVER, "undone") < LB.reward(0, TAKEOVER, "followed")


# ---------------- bandit ----------------
def test_logged_propensity_follows_epsilon_greedy_formula():
    b = EpsGreedyBandit(eps=0.2, seed=3)
    x = ctx()
    for _ in range(50):
        b.update(x, NUDGE, 1.0)
        b.update(x, SILENT, 0.0)
    g = b.greedy(x)
    assert g == NUDGE
    p = b.probs(x)
    assert p.sum() == pytest.approx(1.0) and p[g] == pytest.approx(0.8 + 0.05) and p[0] == pytest.approx(0.05)
    seen = [b.act(x) for _ in range(4000)]
    share_greedy = np.mean([a == g for a, _, _ in seen])
    assert share_greedy == pytest.approx(0.85, abs=0.03)
    assert all(pr == pytest.approx(0.85 if a == g else 0.05) for a, pr, _ in seen)


def test_cold_start_is_silent_and_ties_go_to_lowest_index():
    assert EpsGreedyBandit().greedy(ctx()) == SILENT


def test_bandit_learns_the_better_arm_and_is_deterministic():
    def run(seed):
        b = EpsGreedyBandit(seed=seed)
        rng = np.random.default_rng(seed)
        for _ in range(600):
            x = ctx(p=float(rng.uniform(0.3, 1.0)))
            a, _, _ = b.act(x)
            r = {SILENT: 0.0, NUDGE: 0.5, ANNOTATE: 0.2, TAKEOVER: -0.3}[a] + rng.normal(0, 0.05)
            b.update(x, a, r)
        return b
    b1, b2 = run(0), run(0)
    assert b1.greedy(ctx()) == NUDGE
    assert np.allclose(b1.theta, b2.theta)


# ---------------- OPE estimators on hand-checkable cases ----------------
def tiny():
    # 4 decisions, 2 contexts; target = always action 1
    X = np.zeros((4, 6))
    a = np.array([1, 0, 1, 2])
    r = np.array([1.0, 0.0, 3.0, 5.0])
    p = np.array([0.5, 0.25, 0.5, 0.25])
    target = np.zeros((4, K)); target[:, 1] = 1.0
    return X, a, r, p, target


def test_ips_snips_dr_by_hand():
    X, a, r, p, target = tiny()
    w = np.array([2.0, 0.0, 2.0, 0.0])
    Q0 = np.zeros((4, K))
    est = ope.point_estimates(a, r, p, target, Q0)
    assert est["ips"] == pytest.approx(np.mean(w * r))                      # (2 + 0 + 6 + 0) / 4 = 2
    assert est["snips"] == pytest.approx((2 * 1 + 2 * 3) / 4)               # 8 / 4 = 2
    assert est["dr"] == pytest.approx(est["ips"])                           # q = 0: DR reduces to IPS
    assert est["dm"] == 0.0
    # a PERFECT q: DR = DM = mean q(x, pi(x)), with zero residuals
    Q = np.zeros((4, K)); Q[np.arange(4), a] = r; Q[:, 1] = np.array([1.0, 2.0, 3.0, 2.0])
    Q[0, 1], Q[2, 1] = 1.0, 3.0
    est2 = ope.point_estimates(a, r, p, target, Q)
    assert est2["dr"] == pytest.approx(est2["dm"] + np.mean(w * (r - Q[np.arange(4), a])))
    assert est2["dm"] == pytest.approx(np.mean([1.0, 2.0, 3.0, 2.0]))
    assert est2["naive_on_policy"] == pytest.approx(r.mean())
    assert est2["naive_matched"] == pytest.approx(2.0)                      # rows 0 and 2: (1 + 3) / 2


def test_dr_matches_the_spec_formula_for_a_deterministic_target():
    rng = np.random.default_rng(0)
    n = 50
    a = rng.integers(0, K, n)
    r = rng.normal(size=n)
    p = rng.uniform(0.1, 0.9, n)
    Q = rng.normal(size=(n, K))
    pi = rng.integers(0, K, n)
    target = np.eye(K)[pi]
    spec = np.mean(Q[np.arange(n), pi] + (a == pi) / p * (r - Q[np.arange(n), a]))
    assert ope.point_estimates(a, r, p, target, Q)["dr"] == pytest.approx(spec)


def test_when_logging_equals_target_every_estimator_is_the_plain_mean():
    rng = np.random.default_rng(1)
    n = 400
    target = np.full((n, K), 1 / K)
    a = rng.integers(0, K, n)
    p = np.full(n, 1 / K)
    r = rng.normal(size=n)
    est = ope.point_estimates(a, r, p, target, np.zeros((n, K)))
    assert est["ips"] == pytest.approx(r.mean()) and est["snips"] == pytest.approx(r.mean())


def test_cross_fitted_q_never_sees_its_own_row():
    rng = np.random.default_rng(2)
    X = np.array([sim.sample_contexts(1, rng)[0] for _ in range(300)])
    a = rng.integers(0, K, 300)
    r = rng.normal(size=300)
    Q1 = ope.fit_reward_model(X, a, r, folds=2, seed=0)
    r2 = r.copy(); r2[5] += 100.0   # perturb one row's reward: its own prediction must not move
    Q2 = ope.fit_reward_model(X, a, r2, folds=2, seed=0)
    assert Q1[5, a[5]] == pytest.approx(Q2[5, a[5]])
    assert not np.allclose(Q1, Q2)


# ---------------- simulator with known truth ----------------
def test_true_q_is_the_mean_of_sampled_rewards():
    rng = np.random.default_rng(3)
    x = ctx(p=0.7, level=2, since=0.3, consec=2, risk=0, mastery=0.5)
    q = sim.true_q(x)[0]
    for a in range(K):
        mc = np.mean([sim.sample_reward(x, a, rng) for _ in range(40000)])
        assert mc == pytest.approx(q[a], abs=0.02)
    assert q[SILENT] == 0.0


def test_true_value_of_extreme_policies():
    silent = sim.true_value(lambda X: np.tile(np.eye(K)[SILENT], (X.shape[0], 1)), n_mc=20000)
    assert silent == pytest.approx(0.0)
    opt = sim.optimal_value(20000)
    rule = sim.true_value(lambda X: rules.rule_probs(X), n_mc=20000)
    assert opt > rule > -0.01 and opt > 0.2


def test_logging_propensities_are_valid_and_actions_depend_on_context():
    X, a, r, p, g, _, snap = sim.simulate_log(3000, seed=4)
    assert p.min() >= EPS / K - 1e-12 and p.max() <= 1 - EPS + EPS / K + 1e-12
    assert np.mean(a == g) == pytest.approx(1 - EPS + EPS / K, abs=0.05)
    assert snap is not None
    # context dependence: the action mix differs between contexts with high and low stuck probability
    hi = a[X[:, 0] > 0.6]; lo = a[X[:, 0] < 0.2]
    assert np.mean(hi != 0) > np.mean(lo != 0) + 0.1


def test_dr_recovers_the_true_value_and_naive_on_policy_is_biased():
    rule_fn = lambda X: rules.rule_probs(X)  # noqa: E731
    true_rule = sim.true_value(rule_fn)
    err_dr, err_naive, covered = [], [], []
    for seed in range(10):
        X, a, r, p, _, _, snap = sim.simulate_log(3000, seed=seed)
        Xs, as_, rs, ps = X[1500:], a[1500:], r[1500:], p[1500:]
        res = ope.evaluate_policy_value(Xs, as_, rs, ps, rule_fn(Xs), n_boot=200, seed=seed)
        err_dr.append(res["estimates"]["dr"] - true_rule)
        err_naive.append(res["estimates"]["naive_on_policy"] - true_rule)
        lo, hi = res["intervals"]["dr"]
        covered.append(lo <= true_rule <= hi)
    assert abs(np.mean(err_dr)) < 0.03                      # unbiased on average
    assert np.mean(err_naive) > 0.12                        # logging policy's value is not the rule's value
    assert abs(np.mean(err_naive)) > 6 * abs(np.mean(err_dr))
    assert np.mean(covered) >= 0.7                          # bootstrap interval covers truth most of the time


def test_evaluate_ope_dict_is_json_complete_and_deterministic():
    a = evaluate_ope(n=2000, seed=1, n_boot=100, replications=4, rep_n=1200, rep_boot=60)
    b = evaluate_ope(n=2000, seed=1, n_boot=100, replications=4, rep_n=1200, rep_boot=60)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["origin"] == "synthetic" and a["n_unit"] == "decisions" and a["interval_level"] == 0.95
    assert set(a["targets"]) == {"rule_baseline", "bandit_greedy_snapshot", "always_nudge"}
    t = a["targets"]["rule_baseline"]
    assert set(t["estimators"]) >= {"ips", "snips", "dm", "dr", "naive_on_policy"}
    assert abs(t["estimators"]["naive_on_policy"]["error"]) > abs(t["estimators"]["dr"]["error"])
    assert "by_target" in a["replications"] and a["caveats"]


# ---------------- dignity gate on held-out hazard predictions ----------------
def test_gate_cuts_repeated_nudges_and_reports_the_cost_in_detection():
    eps, _ = simulate_people(4, 25, seed=8)
    r = evaluate_gate(eps)
    bare, gated = r["bare_threshold"], r["dignity_gate"]
    assert gated["nudges_total"] < 0.6 * bare["nudges_total"]
    assert gated["nudges_per_stuck_event"] < bare["nudges_per_stuck_event"]
    assert gated["false_alarms_per_hour"] <= bare["false_alarms_per_hour"] + 1e-9
    assert gated["detection_rate"] <= bare["detection_rate"] + 1e-9   # the price of dignity is said, not hidden
    assert r["split"] == "leave-one-person-out" and r["caveats"]
    json.dumps(r)
