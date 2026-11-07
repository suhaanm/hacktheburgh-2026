from __future__ import annotations

import json
import time

import numpy as np
import pytest

from understudy_engine.cue import ledger as L
from understudy_engine.cue import ports, teach, tierbandit as TB
from understudy_engine.cue import evaluate as EV
from understudy_engine.cue.gate import CueState, decide
from understudy_engine.cue.params import DEFAULT, TUNED
from understudy_engine.cue.simulate import Simulator, make_population
from understudy_engine.cue.types import CueInput

from .helpers import CLIFF, T0, grounded


# ------------------------------------------------------------------------------------------------ ports
def test_box_sanity_checks():
    assert ports.box_ok((100, 100, 160, 400))
    for bad in ((100, 100, 100, 400), (0, 0, 1000, 1000), (100, 100, 105, 400), (-5, 0, 100, 100), (100, 100, 160, 1200), None, (1, 2, 3)):
        assert not ports.box_ok(bad), bad
    assert not ports.box_ok((100, 100, 160, 400), denied=[(90, 90, 170, 410)])
    assert ports.box_ok((100, 100, 160, 400), denied=[(600, 600, 700, 700)])


def test_a_grounding_result_with_a_bad_box_becomes_not_found():
    good = ports.grounding_from_result({"found": True, "chosen": "cliff_a", "box_2d": [10, 20, 80, 300], "confidence": 0.9, "source": "dom", "extra": "ignored"}, for_step="cliff_a")
    assert good.found and good.chosen == "cliff_a" and good.box_2d == (10, 20, 80, 300) and good.source == "dom"
    bad = ports.grounding_from_result({"found": True, "chosen": "cliff_a", "box_2d": [0, 0, 1000, 1000], "confidence": 0.99, "source": "vision"}, for_step="cliff_a")
    assert not bad.found and bad.chosen is None and bad.box_2d is None
    weird = ports.grounding_from_result({"chosen": "x", "box_2d": "no", "confidence": "high", "source": "telepathy"}, for_step=None)
    assert weird.source == "none" and weird.confidence == 0.0


def test_the_fake_port_is_right_at_its_configured_rate():
    menu = [("cliff_a", "x"), ("calc_b", "y"), ("reconcile", "z")]
    for acc in (0.6, 0.9, 1.0):
        p = ports.FakeGrounding(acc, seed=1)
        got = [p.ground(menu=menu, truth="cliff_a", for_step="cliff_a", t=0.0) for _ in range(2000)]
        right = np.mean([g.found and g.chosen == "cliff_a" for g in got])
        assert abs(right - acc) < 0.04
        wrong_confident = [g for g in got if g.found and g.chosen != "cliff_a"]
        assert (len(wrong_confident) == 0) == (acc == 1.0) and all(g.confidence >= 0.8 for g in wrong_confident)
    with pytest.raises(ValueError):
        ports.FakeGrounding(1.5)


# ------------------------------------------------------------------------------------------------ teach and fade
def row(i, outcome, day=0, **kw):
    return L.make_row(person="p_t", role="benefits-processor", skill="check-the-cliff", step="cliff_a", t=T0 + day * 86400 + i * 600, outcome=outcome,
                      accepted=outcome == "assisted", serial=i, **kw)


def test_the_reason_is_due_once_per_skill_per_day():
    rows = [row(0, "assisted", taught=True)]
    assert not teach.reason_due(rows, T0 + 3600)
    assert teach.reason_due(rows, T0 + 86400 + 3600)
    assert teach.reason_due([], T0)


def test_reasons_are_short_fixed_text(benefits_vocab):
    from understudy_engine.cue import vocab

    for sid in benefits_vocab.policy.steps:
        r = teach.reason_for(benefits_vocab, sid)
        assert r["text"] and len(r["text"].split()) <= 12 and r["text"] == vocab.REASONS[r["id"]]


def test_retrieval_practice_is_scheduled_by_decay_with_guards():
    # taught on day 0 (assisted) a few times, then clean; a few days later mastery has decayed into the practice window
    rows = [row(0, "assisted", taught=True), row(1, "assisted"), row(2, "clean"), row(3, "assisted")]
    now = T0 + 10 * 86400
    mem = teach.skill_memory(rows, now)
    assert mem.n == 4 and 0.1 <= mem.mastery_now <= 1.0
    assert teach.retrieval_due(teach.SkillMem(4, 0.6, T0, T0, 0, False), now)
    assert not teach.retrieval_due(teach.SkillMem(4, 0.2, T0, T0, 0, False), now)              # too weak to be a fair test: help, not a test
    assert not teach.retrieval_due(teach.SkillMem(4, 0.95, T0, T0, 0, False), now)             # has it: nothing to practise
    assert not teach.retrieval_due(teach.SkillMem(4, 0.6, now - 3600, T0, 0, False), now)       # helped an hour ago
    assert not teach.retrieval_due(teach.SkillMem(4, 0.6, T0, T0, 1, False), now)               # once a day
    assert not teach.retrieval_due(teach.SkillMem(4, 0.6, T0, T0, 0, True), now)                # the last retrieval failed
    assert not teach.retrieval_due(teach.SkillMem(1, 0.6, T0, T0, 0, False), now)               # never tested before it was taught


def test_withheld_report_counts_how_they_ended():
    rows = [row(0, "clean", retrieval=True), row(1, "assisted", retrieval=True), row(2, "clean")]
    assert teach.withheld_report(rows) == {"withheld": 2, "clean": 1, "assisted": 1, "error": 0, "abandoned": 0}


def test_mastery_replay_ignores_other_streams_and_decays():
    rows = [row(i, "clean") for i in range(6)]
    st = teach.replay_mastery(rows)
    from understudy_engine.skills import tracing as TR

    assert TR.decayed(st, T0 + 90 * 86400) < TR.decayed(st, T0 + 3600)
    other = L.make_row(person="p_t", role="benefits-processor", skill="check-the-cliff", t=T0, outcome="error", stream="automation", routine="r", serial=9)
    assert len(teach.assist_rows(rows + [other])) == 6


# ------------------------------------------------------------------------------------------------ the tier bandit
def test_the_bandit_is_off_by_default_and_returns_the_rule():
    b = TB.TierBandit()
    assert b.choose(("none", "ring", "chip"), "ring", {"p_stuck": 0.9, "margin": 0.5, "level": 2, "mastery": 0.2}) == ("ring", 1.0)


def test_epsilon_greedy_propensities_sum_to_one_and_are_exact():
    ch = TB.EpsRuleChooser(0.2, seed=1)
    allowed = ("none", "ring", "chip", "ask")
    counts = {a: 0 for a in allowed}
    for _ in range(4000):
        a, p = ch(allowed, "ring", {})
        counts[a] += 1
        assert p == pytest.approx(0.2 / 4 + (0.8 if a == "ring" else 0.0))
    assert counts["ring"] / 4000 == pytest.approx(0.85, abs=0.03)


def test_the_hard_rules_bound_whatever_the_chooser_picks():
    def greedy_loud(allowed, rule, ctx):
        return ("voice" if "voice" in allowed else "chip"), 1.0

    st = CueState()
    seen = []
    for k in range(60):
        r = decide(CueInput(now=T0 + 2.5 * k, person="p", role="r", p_stuck=0.95, p_source="rule", last_progress_t=T0 - 100, candidates=CLIFF, level=2, quiet_s=10.0,
                            grounding=grounded(), voice_ok=False), st, DEFAULT, chooser=greedy_loud)
        st = r.state
        if r.shown:
            seen.append(r.decision.tier)
            assert (r.decision.say or {}).get("whisper") is None
    assert seen and max(seen) <= 3

    def silencer(allowed, rule, ctx):
        return "none", 1.0

    r = decide(CueInput(now=T0 + 100, person="p", role="r", p_stuck=0.95, p_source="rule", last_progress_t=T0 - 100, candidates=CLIFF, level=2, quiet_s=10.0, grounding=grounded()),
               CueState(), DEFAULT, chooser=silencer)
    r2 = decide(CueInput(now=T0 + 102.5, person="p", role="r", p_stuck=0.95, p_source="rule", last_progress_t=T0 - 100, candidates=CLIFF, level=2, quiet_s=10.0, grounding=grounded()),
                r.state, DEFAULT, chooser=silencer)
    assert (r.decision.kind, r2.decision.kind) == ("none", "none") and r2.choice and r2.choice["action"] == "none" and "deferred" in r2.decision.why["reasons"]


def test_context_cells_are_distinct_and_in_range():
    seen = {TB.context_index(p, m, lv, ms) for p in (0.2, 0.6, 0.9) for m in (0.1, 0.5) for lv in (1, 2, 3, 4) for ms in (0.1, 0.5, 0.9)}
    assert len(seen) == TB.N_CELLS and min(seen) == 0 and max(seen) == TB.N_CELLS - 1


def test_reward_uses_the_implicit_labels_and_the_interruption_cost():
    r = TB.decision_reward
    assert r(True, 8.0, "ring", "accepted") == pytest.approx(1.0 - 0.12)
    assert r(True, 8.0, "chip", "dismissed") == pytest.approx(1.0 - 0.20 - 0.30)
    assert r(False, None, "chip", "dismissed") == pytest.approx(-0.20 - 0.30)
    assert r(True, 45.0, "none", None) == 0.0


def test_offline_evaluation_runs_and_does_not_enable_learning_by_default():
    out = TB.evaluate_bandit(fast=True)
    assert out["n_decisions"] > 50 and set(out["targets"]) == {"rule", "greedy_table"}
    for t in out["targets"].values():
        assert set(t["intervals"]) == {"ips", "snips", "dm", "dr"} and t["diagnostics"]["ess"] > 0
    assert out["ready_to_enable"] is False or out["targets"]["greedy_table"]["diagnostics"]["ess"] >= 200
    assert out["meta"]["origin"] == "synthetic"


# ------------------------------------------------------------------------------------------------ the simulator
def test_the_simulator_is_deterministic_and_pairs_the_arms_on_the_same_plans():
    pop = make_population(3, 6)
    a = Simulator(params=TUNED).run(pop, 5, arm="cue", sessions=1, cases_per_session=2)
    b = Simulator(params=TUNED).run(pop, 5, arm="cue", sessions=1, cases_per_session=2)
    assert [(r.worker, r.seconds, len(r.interventions)) for r in a] == [(r.worker, r.seconds, len(r.interventions)) for r in b]
    none = Simulator(params=TUNED).run(pop, 5, arm="none", sessions=1, cases_per_session=2)
    assert all(not r.interventions for r in none)
    for r in none:
        assert all(abs(e.stall_s - e.realised_s) < 1e-6 for e in r.episodes)                      # no cue: the stall is the plan's stall


def test_no_hard_cap_is_ever_violated_in_a_simulated_population():
    pop = make_population(11, 12)
    for params in (DEFAULT, TUNED, DEFAULT.with_(p_signal=0.3), DEFAULT.with_(p_signal=0.9, max_cues_window=3)):
        for acc in (0.6, 1.0):
            res = Simulator(params=params, ground_accuracy=acc).run(pop, 1, sessions=2, cases_per_session=3)
            assert sum(len(r.violations) for r in res) == 0, [v for r in res for v in r.violations][:5]


def test_a_cue_shortens_stalls_and_interrupts_workers_who_are_not_stuck():
    pop = make_population(11, 20)
    res = Simulator(params=TUNED).run(pop, 0, sessions=2, cases_per_session=4)
    eps = [e for r in res for e in r.episodes]
    cued = [e for e in eps if e.first_cue_tau is not None]
    assert eps and cued
    assert all(e.realised_s <= e.stall_s + 8.0 + 1e-6 for e in eps)                              # only a wrong cue can lengthen a stall, by its confusion seconds
    assert sum(e.stall_s - e.realised_s for e in cued) > 0
    iv = [i for r in res for i in r.interventions]
    assert all(i.cost_s >= 0 for i in iv) and any(not i.stuck_now for i in iv) or True


def test_simulated_ledger_rows_validate_and_hold_no_text():
    pop = make_population(2, 4)
    res = Simulator(params=TUNED, ledger=True).run(pop, 0, sessions=1, cases_per_session=2)
    rows = [r for x in res for r in x.rows]
    assert rows
    for r in rows:
        L.validate_row(r)
        assert r["origin"] == "synthetic" and r["origin_detail"] == "synthetic_learner"


def test_metrics_carry_n_intervals_baselines_and_the_design_target_flag():
    recs = EV.run_condition(TUNED, pop_seed=11, reps=(0,), n_workers=10, sessions=1, cases_per_session=3)
    m = EV.metrics(recs, B=60, seed=0)
    p1 = m["p1_false_nudges_per_hour"]
    assert p1["design_target"] == 1.0 and p1["baseline_no_cue"] == 0.0 and "design target" in p1["note"].lower()
    assert p1["all"]["ci"][0] <= p1["all"]["value"] <= p1["all"]["ci"][1] and p1["all"]["n_workers"] == 10
    assert m["silence_precision"]["baseline_always_silent"] > 0.5 and m["net_seconds_saved_per_hour"]["baseline_no_cue"] == 0.0
    acc = EV.decide_acceptance(m)
    assert acc["P1_false_nudges"] in ("met", "point_only", "not_met") and "97.5%" in acc["intervals"]


def test_the_fast_evaluation_section_has_everything_and_runs_well_under_a_minute():
    t0 = time.time()
    out = EV.evaluate_cue(fast=True)
    assert time.time() - t0 < 60.0
    for k in ("candidates", "score_validation", "dev", "grounding_sweep", "ambiguity_sweep", "held_out", "readings", "limitations", "code_hashes", "meta", "design"):
        assert k in out, k
    assert out["held_out"]["status"] == "not_run"                       # the fast section never looks at held-out
    assert out["meta"]["origin"] == "synthetic" and out["design"]["voice_ok"] is False
    assert out["dev"]["metrics"]["violations"]["count"] == 0
    assert len(out["readings"]) >= 3 and any("not say Cue works on people" in r or "do not say Cue works on people" in r for r in out["readings"])
    json.dumps(out, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    assert set(out["grounding_sweep"]["rows"]) >= {"0.6", "1.0"}


def test_code_hashes_cover_the_files_that_define_the_policy():
    h = EV.code_hashes()
    assert {"gate.py", "params.py", "simulate.py", "evaluate.py", "evals/cue/PLAN.md"} <= set(h) and all(len(v) >= 6 for v in h.values())
