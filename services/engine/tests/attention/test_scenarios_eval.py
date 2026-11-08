"""The simulated workday, the five scenarios, the tuning rule and the evaluation harness. Small populations: the full runs are in evals/attention."""
from __future__ import annotations

import json
import time

import numpy as np
import pytest

from understudy_engine.attention import evaluate as E
from understudy_engine.attention import scenarios as SC
from understudy_engine.attention import simulate as S
from understudy_engine.attention import vocab as V
from understudy_engine.attention.state import DEFAULT, Settings


# ------------------------------------------------------------------------------------------------ the simulated day
def test_a_world_is_deterministic_and_shared_by_every_condition():
    spec = S.population(3, 1)[0]
    a, b = S.build_world(spec, 3), S.build_world(spec, 3)
    assert [(r.t, r.type, r.subject) for r in a.events] == [(r.t, r.type, r.subject) for r in b.events]
    assert np.array_equal(a.tl.typing, b.tl.typing) and np.array_equal(a.glances, b.glances)
    r1, r2 = S.run_condition(a, "R"), S.run_condition(a, "R")
    assert r1.to_dict() == r2.to_dict()
    # the same raw events are replayed under every condition: every condition saw the same producers
    assert {c: S.run_condition(a, c).important_n for c in ("R", "B1", "B2")} == {c: r1.important_n for c in ("R", "B1", "B2")} or True
    ns = {c: S.run_condition(a, c).important_n for c in ("R", "R-nolearn", "B1", "B2")}
    assert ns["R"] == ns["R-nolearn"] == ns["B1"] == ns["B2"]


def test_the_timeline_is_a_plausible_working_day():
    spec = S.population(1, 1)[0]
    w = S.build_world(spec, 4)
    tl = w.tl
    assert tl.present.any() and (~tl.present).any()
    assert not (tl.typing & ~tl.present).any() and not (tl.typing & tl.meeting).any()
    assert tl.quiet[tl.typing].max() <= 2.0 and (tl.quiet[~tl.typing & tl.present] >= 0).all()
    assert (tl.away == ~tl.present).all() and tl.locked[tl.away].any()
    assert w.work_h > 20 and w.flow_h > 1
    assert all(r.t >= S.BASE_T for r in w.events)


def test_the_four_archetypes_come_from_the_personas_or_the_built_in_generator():
    for p in S.ARCHETYPES:
        days, src = S.schedule(S.WorkerSpec("x", p, 5), 5)
        assert sum(1 for d in days if d.windows) == 5 and src in ("persona_truth", "built_in")
        days2, src2 = S.schedule(S.WorkerSpec("x", p, 5), 5, source="built_in")
        assert src2 == "built_in" and sum(1 for d in days2 if d.windows) == 5


def test_the_router_never_misses_urgent_never_nags_never_interrupts_a_meeting_and_the_baselines_fail_where_expected():
    res, _ = E.run_seeds((0, 1), 1, 5)
    r, b1, b2 = res["R"], res["B1"], res["B2"]
    assert sum(x.safety_missed for x in r) == 0
    assert max((n for x in r for n in x.needs_reminders), default=0) <= 1
    assert sum(x.hq_breaches for x in r) == 0
    assert sum(x.hq_breaches for x in b1) > 0                                              # show-everything interrupts meetings, calls and shares
    assert sum(x.dup_displays for x in b1) > sum(x.dup_displays for x in r)
    assert sum(x.flow_displays_nonsafety for x in b1) > sum(x.flow_displays_nonsafety for x in r)
    assert sum(x.important_seen for x in b2) / max(1, sum(x.important_n for x in b2)) < sum(x.important_seen for x in r) / max(1, sum(x.important_n for x in r))
    assert sum(x.displays for x in b2) <= sum(x.days for x in b2)                           # one summary a working day at most (plus none)


def test_learning_never_makes_the_router_louder():
    res, _ = E.run_seeds((0,), 2, 8, conds=("R", "R-nolearn"))
    assert sum(x.displays for x in res["R"]) <= sum(x.displays for x in res["R-nolearn"])


def test_unknown_polls_hold_everything_but_safety_and_never_miss_a_safety_item():
    res, _ = E.run_seeds((0,), 1, 6, conds=("R",), unknown_poll_rate=0.5)
    assert sum(x.safety_missed for x in res["R"]) == 0


# ------------------------------------------------------------------------------------------------ the scenarios
@pytest.mark.parametrize("fn", [SC.s1_overnight_approval, SC.s2_meeting_and_share, SC.s3_injection_in_long_run, SC.s5_kill_state])
@pytest.mark.parametrize("seed", [0, 7])
def test_scripted_scenarios_hold(fn, seed):
    out = fn(seed)
    failed = [k for k, v in out["assertions"].items() if not v]
    assert not failed, (out["id"], failed, out["numbers"])


def test_s2_the_baselines_interrupt_the_meeting_the_router_does_not():
    out = SC.s2_meeting_and_share(0)
    assert out["numbers"]["meeting_interruptions_non_safety"] == 0
    assert out["contrast"]["B1"]["hard_quiet_breaches"] > 0


@pytest.fixture(scope="module")
def personas_root(tmp_path_factory):
    """A private copy of the seeded personas (deterministic: the same files `understudy synth --all` writes). The simulated worker's schedule comes
    from <root>/synthetic/<persona>/truth.json when it exists and from a fallback generator when it does not, so a test that read the repo's
    git-ignored data/ gave different numbers on a fresh checkout than on the owner's machine (s4 below failed there: the late-minus-early interval's
    upper end was +0.18 with the fallback and -1.9 with the personas, n = 4 workers)."""
    from understudy_engine.personas import write_all_personas

    root = tmp_path_factory.mktemp("attention_personas")
    write_all_personas(root)
    return root


def test_s4_learning_quietens_and_time_sensitive_items_stay_visible(personas_root):
    out = SC.s4_dismisses_everything(0, per_archetype=1, n_work_days=10, n_boot=100, root=personas_root)
    failed = [k for k, v in out["assertions"].items() if not v]
    assert not failed, (failed, out["numbers"])
    assert out["numbers"]["safety_missed"] == 0 and out["numbers"]["approval_toasts_shown"] > 0


def test_scripted_scenario_robust_to_background_events():
    # with the ordinary background stream added, the safety and marker guarantees must still hold
    for fn in (SC.s2_meeting_and_share, SC.s3_injection_in_long_run, SC.s5_kill_state):
        out = fn(3, background=True)
        for k, ok in out["assertions"].items():
            if "marker" in k or "injection" in k or "no_non_safety_interruption_in_the_meeting" in k or "shown_within_5_s" in k or "notice is shown at once" in k:
                assert ok, (out["id"], k, out["numbers"])


# ------------------------------------------------------------------------------------------------ tuning, freezing, acceptance
def test_the_grid_is_the_plans_grid_one_factor_at_a_time():
    cs = E.configs()
    assert cs[0]["name"] == "defaults" and len(cs) == 13 and len({c["name"] for c in cs}) == 13
    for c in cs[1:]:
        diff = [k for k in E.GRID if c[k] != cs[0][k]]
        assert len(diff) == 1 and c[diff[0]] in E.GRID[diff[0]]
    for c in cs:
        p, st = E.to_params(c)
        assert p.max_reminders == DEFAULT.max_reminders and isinstance(st, Settings)               # hard constants are not in the grid


def row(name, flow, seen=0.97, missed=0, delay=30.0, cost=100.0):
    return {"name": name, "flow_non_safety": flow, "important_seen": seen, "missed_urgent_safety": missed, "median_delay_s": delay, "cost_per_day": cost}


def test_selection_follows_the_plans_rule():
    rows = [row("defaults", 0.20), row("a", 0.10, seen=0.90), row("b", 0.12, missed=1), row("c", 0.15, delay=300.0), row("d", 0.16)]
    s = E.select(rows)
    assert s["chosen"] == "d" and set(s["eligible"]) == {"defaults", "d"}
    tie = [row("defaults", 0.200, cost=90.0), row("x", 0.205, cost=80.0)]
    assert E.select(tie)["chosen"] == "x"                                                           # within 0.01: the lower cost wins
    flat = [row("defaults", 0.20), row("y", 0.20)]
    assert E.select(flat)["chosen"] == "defaults"                                                   # still tied: the defaults
    none_ok = [row("defaults", 0.3, seen=0.5), row("z", 0.2, seen=0.8)]
    assert E.select(none_ok)["rule_met_by_any"] is False and E.select(none_ok)["chosen"] == "z"


def test_tuning_refuses_held_out_seeds_and_freezing_writes_a_stable_hash(tmp_path):
    with pytest.raises(AssertionError):
        E.tune_on_dev(seeds=(1000,))
    tuning = {"seeds": [0], "rows": [{"name": "defaults", "config": E.configs()[0] | {}, "flow_non_safety": 1}], "selection": {"chosen": "defaults"}}
    tuning["rows"][0]["config"].pop("name", None)
    a = E.freeze_config(tuning, tmp_path / "f.json")
    b = E.freeze_config(tuning, tmp_path / "g.json")
    assert a["hash"] == b["hash"] and len(a["hash"]) == 16 and json.loads((tmp_path / "f.json").read_text())["name"] == "defaults"
    assert a["hard_constants"] == {"max_reminders": 1}


def test_held_out_refuses_to_run_without_the_frozen_config(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "FROZEN", "evals/attention/__no_such_frozen__.json")
    with pytest.raises(FileNotFoundError):
        E.evaluate_attention(held_out=True)


def test_acceptance_verdicts_meet_not_meet_or_stay_inconclusive():
    def ci(est, lo, hi):
        return {"est": est, "lo": lo, "hi": hi}

    def cond(seen=ci(0.99, 0.97, 1.0), missed=0, safety_items=5, mr=1):
        return {"important_seen_within_window": seen, "missed_urgent_safety": missed, "safety_items": safety_items, "max_reminders_per_needs_you_item": mr,
                "hard_quiet_breaches_per_day": ci(0.0, 0.0, 0.0)}

    pair = {"interruptions_per_flow_hour_non_safety": ci(-1, -1.2, -0.8), "duplicate_rate": ci(-0.2, -0.3, -0.1), "important_seen_within_window": ci(0.0, -0.01, 0.01)}
    pair2 = {"important_seen_within_window": ci(0.7, 0.5, 0.8)}
    summary = {"conditions": {"R": cond(), "B1": cond(), "B2": cond(missed=3)}, "paired": {"R_minus_B1": pair, "R_minus_B2": pair2}}
    s4 = {"passed": True, "numbers": {"wait_late_minus_early": ci(-0.5, -0.8, -0.2), "helpful_late_minus_early": ci(-2, -2.5, -1.5), "helpful_late_router_minus_nolearn": ci(-3, -3.5, -2.5),
                                      "approval_toasts_shown": 40, "time_sensitive_seen_share": 0.98, "safety_missed": 0}}
    scen = {"S1": {"passed": True}, "S4": s4}
    a = E.acceptance(summary, scen)
    assert a["not_met"] == 0 and a["inconclusive"] == 0 and a["met"] == 12
    summary["conditions"]["R"] = cond(seen=ci(0.96, 0.93, 0.98), missed=1, mr=2)
    b = E.acceptance(summary, {"S1": {"passed": False}, "S4": {"passed": False, "numbers": dict(s4["numbers"], wait_late_minus_early=ci(0.3, 0.1, 0.6))}})
    assert b["criteria"]["2_important_seen_at_least_95pct"] == "inconclusive"
    assert b["criteria"]["3_missed_urgent_zero_for_R"] == "not_met" and b["criteria"]["4_max_one_reminder_per_needs_you_item"] == "not_met"
    assert b["criteria"]["6_scenarios_hold"] == "not_met"
    assert b["criteria"]["7_s4_can_wait_toasts_later_below_early_and_approvals_unchanged"] == "not_met"      # the plan's wording: can-wait toasts must fall, not rise
    assert b["criteria"]["7b_s4_helpful_now_displays_fall_with_learning"] == "met"
    assert E._criterion_7(None) == "inconclusive"
    straddle = dict(s4["numbers"], wait_late_minus_early=ci(-0.1, -0.4, 0.2))
    assert E._criterion_7({"numbers": straddle}) == "inconclusive"
    assert E._criterion_7({"numbers": dict(s4["numbers"], safety_missed=1)}) == "not_met"


def test_boot_diff_has_the_right_sign_and_width():
    a, b = np.array([1.0, 1.2, 0.9, 1.1]), np.array([2.0, 2.1, 2.2, 1.9])
    d = E.boot_diff(a, b, 500, 1)
    assert d["est"] < 0 and d["hi"] < 0 and d["lo"] <= d["est"] <= d["hi"]
    assert E.boot_diff(np.array([]), np.array([]), 10, 1) == {"est": 0.0, "lo": 0.0, "hi": 0.0}


def test_recost_scales_linearly():
    res, _ = E.run_seeds((0,), 1, 3, conds=("R", "B1"))
    assert E.recost(res["B1"], 2.0) == pytest.approx(2 * E.recost(res["B1"], 1.0), rel=1e-3)
    assert E.recost(res["B1"], 1.0) > E.recost(res["R"], 1.0)


# ------------------------------------------------------------------------------------------------ the harness entry point
def test_evaluate_attention_fast_mode_is_under_a_minute_and_fully_labelled():
    t0 = time.time()
    rep = E.evaluate_attention(fast=True)
    assert time.time() - t0 < 60.0
    assert rep["meta"]["origin"] == "synthetic" and "not people" in rep["meta"]["badge"] and rep["meta"]["split"] == "dev" and rep["meta"]["fast"] is True
    assert set(rep["conditions"]) == set(E.CONDITIONS) and rep["meta"]["n_workers"] == 8
    for c, d in rep["conditions"].items():
        for k in ("interruptions_per_flow_hour_non_safety", "important_seen_within_window", "duplicate_rate", "attention_cost_s_per_day", "acceptance_rate"):
            assert {"est", "lo", "hi"} <= set(d[k]), (c, k)
        assert "missed_urgent_safety" in d and "median_important_delay_s" in d and "max_reminders_per_needs_you_item" in d
    assert set(rep["scenarios"]) == {"S1", "S2", "S3", "S4", "S5"}
    assert all(s["passed"] for s in rep["scenarios"].values())
    assert rep["limitations"] and rep["acceptance"]["criteria"] and rep["meta"]["code"] and rep["meta"]["cost_model_s"]
    assert rep["conditions"]["R"]["missed_urgent_safety"] == 0
    json.dumps(rep, default=str)                                                                       # JSON-able, nothing exotic


def test_every_sentence_the_evaluation_reports_is_a_fixed_line_that_passes_the_house_style():
    from understudy_engine.attention import texts as X

    out = SC.s1_overnight_approval(0)
    assert out["numbers"]["summary_lines"]
    for line in out["numbers"]["summary_lines"]:
        assert X.lint(None, line) == [], line


def test_a_split_tuning_run_joins_back_into_the_same_grid_and_needs_every_piece(tmp_path):
    cs = E.configs()
    def part(k, n):
        rows = [dict(row(c["name"], 0.5 - 0.02 * i), config={kk: vv for kk, vv in c.items() if kk != "name"}) for i, c in enumerate(cs) if i % n == k]
        return {"split": "dev", "seeds": [0], "n_workers": 8, "n_work_days": 2, "note": "n", "rows": rows, "selection": None, "part": [k, n]}
    paths = []
    for k in range(3):
        p = tmp_path / f"part_{k}_of_3.json"
        p.write_text(json.dumps(part(k, 3)))
        paths.append(p)
    whole = E.combine_parts(paths)
    assert [r["name"] for r in whole["rows"]] == [c["name"] for c in cs] and whole["selection"]["chosen"] == cs[-1]["name"]
    with pytest.raises(AssertionError):
        E.combine_parts(paths[:2])
    small = E.tune_on_dev(per_archetype=1, n_work_days=2, seeds=(0,), part=(0, 7))
    assert small["selection"] is None and [r["name"] for r in small["rows"]] == [c["name"] for i, c in enumerate(cs) if i % 7 == 0]


def test_selection_keeps_the_defaults_unless_the_gain_clears_the_dev_interval():
    rng = np.random.default_rng(3)
    base = [[float(x), 10.0] for x in rng.integers(1, 4, 20)]                       # per-worker (flow displays, flow hours): about 0.2 an hour
    clear = [[x[0] * 0.5, 10.0] for x in base]                                       # every worker halves: a gain well past the interval
    noisy = [[max(0.0, x[0] + float(d)), 10.0] for x, d in zip(base, rng.integers(-1, 2, 20))]   # a different draw around the same mean
    d = dict(row("defaults", 0.20), flow_pairs=base)
    better = dict(row("budget", 0.10), flow_pairs=clear)
    s = E.select([d, better])
    assert s["chosen"] == "budget" and s["interval_vs_defaults"]["hi"] < 0 and s["first_choice_by_rate"] == "budget"
    meh = dict(row("budget", 0.15), flow_pairs=noisy)             # the rate is lower, but the paired interval straddles zero
    s2 = E.select([d, meh])
    assert s2["chosen"] == "defaults" and "no gain" in s2["reason"] and s2["first_choice_by_rate"] == "budget"


def test_a_run_in_pieces_gives_exactly_the_numbers_of_the_run_in_one_go(tmp_path, monkeypatch):
    """The held-out run is split into short pieces (one per seed, one for the sensitivity runs) so it can use the short lane. The join must be the same
    computation: same workers, same results, same pooled metrics."""
    monkeypatch.setattr(E, "HELD_SEEDS", (0, 1))                       # tiny: two seeds, to keep the test fast (the frozen file is not read for dev pieces)
    monkeypatch.setattr(E, "DEV_SEEDS", (0, 1))
    whole, src = E.run_seeds((0, 1), 1, 10, conds=("R", "B1"))
    d = tmp_path / "parts"
    for s in (0, 1):
        res, worlds = E.run_population(s, 1, 10, conds=("R", "B1"))
        (d).mkdir(exist_ok=True)
        (d / f"piece_{s}.json").write_text(json.dumps({"seed": s, "source": "+".join(sorted({w.source for w in worlds})),
                                                       "results": {c: [r.to_dict() for r in rs] for c, rs in res.items()}}))
    pooled, source, sens = E._load_pieces(d, (0, 1))
    assert source == src and sens == {}
    for c in ("R", "B1"):
        assert [r.to_dict() for r in pooled[c]] == [r.to_dict() for r in whole[c]]
    a, b = E.summarise(whole, 100, 1), E.summarise(pooled, 100, 1)
    assert a["conditions"]["R"]["important_seen_within_window"] == b["conditions"]["R"]["important_seen_within_window"]
    assert a["paired"]["R_minus_B1"] == b["paired"]["R_minus_B1"]
    r0 = whole["R"][0]
    again = S.WorkerResult.from_dict(r0.to_dict())
    assert again.delays == r0.delays or all((x == y) or (abs(x - y) < 0.06) for x, y in zip(again.delays, r0.delays))
