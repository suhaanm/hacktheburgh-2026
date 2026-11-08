"""The selection (REQ-9): gate order, family control, guard metrics, score, diversity, caps, determinism, stability."""
from __future__ import annotations

import random
from dataclasses import replace

from understudy_engine.insights import select as SEL
from understudy_engine.insights import stats as S
from understudy_engine.insights import vocab as V
from understudy_engine.insights.params import DAY, DEFAULT
from understudy_engine.insights.types import (
    Guard,
    History,
    HistoryEntry,
    InsightCandidate,
    insight_id,
)

from .helpers import NOW


def cand(kind="time_loss_habit", subject="s1", *, audience="worker", value=30.0, lo=20.0, hi=40.0, p=1e-5, n=12, recency=None, impact=10.0, family="f", floor=10.0, sign=1,
         polarity=None, guards=(), action="open_growth", **kw):
    spec = V.KINDS[kind]
    return InsightCandidate(id=insight_id(audience, "scope", kind, subject), kind=kind, audience=audience, subject=subject, group=kw.pop("group", "g"),
                            polarity=polarity or spec.polarity, value=value, unit="seconds", lo=lo, hi=hi, p=p, n=n, origin="synthetic", badge="made-up firm",
                            recency_t=NOW - DAY if recency is None else recency, action_id=action, impact_raw=impact, family=family, floor=floor, sign=sign,
                            guards=guards, **kw)


def pick(cands, audience="worker", **kw):
    return SEL.select(cands, audience=audience, scope="x", now=NOW, **kw)


def ids(sel):
    return [s.cand.id for s in sel.selected]


def why(sel, c):
    return sel.reason_of(c.id)


# ---------------------------------------------------------------------------------------------------- the gate
def test_each_gate_has_its_own_closed_reason():
    cases = {
        "not_enough_data": cand(n=2),
        "stale": cand(recency=NOW - 90 * DAY),
        "below_effect_floor": cand(value=4.0, lo=1.0, hi=7.0),
        "interval_spans_zero": cand(lo=-3.0, hi=60.0),
        "not_persistent": cand(persist_ok=False),
        "no_expert_reference": cand(reason_pre="no_expert_reference"),
    }
    for want, c in cases.items():
        sel = pick([c])
        assert sel.selected == [] and why(sel, c) == ("suppressed", want), (want, why(sel, c))
        assert want in V.SUPPRESSED


def test_a_direction_the_wrong_way_is_below_the_floor_not_an_insight():
    c = cand(value=-30.0, lo=-40.0, hi=-20.0)
    assert why(pick([c]), c) == ("suppressed", "below_effect_floor")


def test_worker_family_control_is_bonferroni_over_the_admissible_family():
    # one test with p = 0.02 passes alone (alpha 0.05) and fails inside a family of 10 (alpha / 10 = 0.005)
    c = cand(p=0.02)
    assert ids(pick([c])) == [c.id]
    others = [cand(subject=f"o{i}", value=0.0, lo=-5.0, hi=5.0, p=0.9) for i in range(9)]
    sel = pick([c] + others)
    assert sel.family["m"] == 10 and abs(sel.family["per_test_alpha"] - 0.005) < 1e-12
    assert why(sel, c) == ("suppressed", "not_significant_after_family_control")


def test_pre_suppressed_candidates_are_not_part_of_the_family():
    c = cand(p=0.02)
    pre = [cand(subject=f"o{i}", reason_pre="not_enough_data", p=None) for i in range(9)]
    sel = pick([c] + pre)
    assert sel.family["m"] == 1 and ids(sel) == [c.id]


def test_admin_family_control_is_benjamini_hochberg():
    cs = [cand(kind="role_gap", subject=f"r{i}", audience="admin", p=p, group=f"r{i}", action="open_roles", n=20) for i, p in enumerate([0.001, 0.012, 0.03, 0.2, 0.6])]
    sel = pick(cs, audience="admin")
    # BH at q = 0.1, m = 5: thresholds 0.02, 0.04, 0.06, 0.08, 0.10 -> the first three pass
    assert sel.family["method"] == "benjamini_hochberg" and sel.family["n_pass"] == 3
    passed = {s.cand.subject for s in sel.selected}
    assert passed == {"r0", "r1", "r2"}
    assert why(sel, cs[3]) == ("suppressed", "not_significant_after_family_control")


def test_bh_pass_matches_the_step_up_definition():
    items = [("a", 0.001), ("b", 0.012), ("c", 0.03), ("d", 0.2), ("e", 0.6)]
    assert S.bh_pass(items, 0.1) == {"a", "b", "c"}
    assert S.bh_pass([("a", 0.5)], 0.1) == set()
    assert S.bh_pass([], 0.1) == set()


# ---------------------------------------------------------------------------------------------------- guards
def test_an_improvement_with_a_worse_guard_becomes_a_trade_off():
    g = Guard("error_share", 0.1, 0.3, 20, 20, True)
    c = cand(kind="habit_improved", guards=(g,), action=None, polarity="positive", slots={"guard": "error_share", "before": 0.1, "after": 0.3})
    sel = pick([c])
    s = sel.selected[0]
    assert s.cand.kind == "trade_off" and s.cand.polarity == "tradeoff" and s.cand.id == c.id and s.reason == "selected_trade_off"


def test_an_improvement_whose_guards_held_stays_a_celebration():
    g = Guard("error_share", 0.1, 0.1, 20, 20, False)
    c = cand(kind="habit_improved", guards=(g,), action=None, polarity="positive")
    assert pick([c]).selected[0].cand.kind == "habit_improved"


def test_an_admin_improvement_with_a_worse_guard_keeps_its_kind_and_turns_tradeoff():
    g = Guard("false_claims", 0.0, 1.0, 40, 40, True)
    c = cand(kind="automation_value", audience="admin", guards=(g,), family="", p=None, lo=None, hi=None, n=30, polarity="positive", action="open_routines")
    s = pick([c], audience="admin").selected[0]
    assert s.cand.kind == "automation_value" and s.cand.polarity == "tradeoff"


# ---------------------------------------------------------------------------------------------------- score, order, determinism
def test_score_parts_are_impact_actionability_novelty_recency():
    c = cand(impact=15.0)
    s = pick([c]).selected[0]
    assert abs(s.parts["impact"] - (1 - 2.718281828 ** -1)) < 1e-4
    assert s.parts["actionability"] == 1.0 and s.parts["novelty"] == 1.0
    assert abs(s.score - s.parts["impact"] * s.parts["recency"]) < 1e-6
    quiet = cand(subject="s2", impact=15.0, action=None)
    assert pick([quiet]).selected[0].parts["actionability"] == DEFAULT.actionability_none


def test_a_score_does_not_depend_on_the_other_candidates():
    a, b = cand(subject="a", impact=8.0), cand(subject="b", impact=3.0)
    alone = pick([a]).selected[0].score
    both = {s.cand.subject: s.score for s in pick([a, b]).selected}
    assert both["a"] == alone


def test_order_is_by_score_ties_by_id_and_input_order_never_matters():
    cs = [cand(subject=f"s{i}", impact=10.0) for i in range(6)]                    # identical scores
    first = ids(pick(cs))
    for seed in range(8):
        sh = cs[:]
        random.Random(seed).shuffle(sh)
        assert ids(pick(sh)) == first
    assert first == sorted(first)                                                 # ties broken by id ascending


def test_the_same_inputs_give_the_same_selection_byte_for_byte():
    cs = [cand(subject=f"s{i}", impact=1.0 + i, p=1e-6) for i in range(5)]
    a, b = pick(cs), pick(cs)
    assert [(s.cand.id, s.score, s.position, s.reason) for s in a.selected] == [(s.cand.id, s.score, s.position, s.reason) for s in b.selected]
    assert [(x.id, x.reason) for x in a.suppressed] == [(x.id, x.reason) for x in b.suppressed]


# ---------------------------------------------------------------------------------------------------- diversity and caps
def test_one_insight_per_subject_and_kind_and_a_worker_hears_one_of_each_sort_about_a_skill():
    a = cand(kind="time_loss_habit", subject="s1", impact=10.0)
    b = cand(kind="relapse", subject="s1", impact=12.0, action="open_growth")
    c = cand(kind="time_loss_habit", subject="s2", impact=2.0)
    sel = pick([a, b, c])
    subjects = [s.cand.subject for s in sel.selected]
    assert subjects == ["s1", "s2"] and sel.selected[0].cand.kind == "relapse"            # two things that are not going well about s1: one message told twice
    assert why(sel, a) == ("suppressed", "same_subject_lower_score")
    good = cand(kind="habit_improved", subject="s1", impact=4.0, polarity="positive", action=None)
    sel = pick([a, good])
    assert {s.cand.kind for s in sel.selected} == {"time_loss_habit", "habit_improved"}   # faster than a month ago, and still slower than the expert: both are true
    other_good = cand(kind="independence_milestone", subject="s1", impact=3.0, polarity="positive", action=None, p=None, lo=None, hi=None, n=20, extras={"k": 19, "n": 20, "kp": 8, "np": 20})
    sel = pick([good, other_good])
    assert len(sel.selected) == 1 and why(sel, other_good) == ("suppressed", "same_subject_lower_score")


def test_the_worker_cap_is_three_and_the_rest_are_over_cap():
    cs = [cand(subject=f"s{i}", impact=20.0 - i) for i in range(6)]
    sel = pick(cs)
    assert len(sel.selected) == 3 and [x.reason for x in sel.suppressed].count("over_cap") == 3


def test_at_least_one_positive_insight_when_any_passes():
    neg = [cand(subject=f"n{i}", impact=30.0 - i) for i in range(4)]
    pos = cand(kind="habit_improved", subject="p", impact=1.0, polarity="positive", action=None)
    sel = pick(neg + [pos])
    assert any(s.cand.polarity == "positive" for s in sel.selected) and len(sel.selected) == 3
    assert why(sel, pos) == ("selected", "selected_positive_slot")
    # with no positive that passes, the list is simply the top three
    assert len(pick(neg).selected) == 3


def test_the_admin_cap_is_seven_and_a_risk_signal_keeps_a_reserved_slot():
    cs = [cand(kind="role_gap", subject=f"r{i}", audience="admin", impact=500.0 - i, group=f"g{i}", action="open_roles", p=1e-9, n=20) for i in range(9)]
    risk = cand(kind="risk_signal", subject="injection_pauses", audience="admin", family="", p=None, lo=None, hi=None, n=1, impact=0.5, group="firm", action="open_queue")
    sel = pick(cs + [risk], audience="admin")
    assert len(sel.selected) == 7 and why(sel, risk) == ("selected", "selected_reserved_risk")


def test_an_admin_group_has_at_most_three_so_one_role_cannot_fill_the_list():
    cs = [cand(kind=k, subject="benefits", audience="admin", impact=900.0 - i, group="benefits", action="open_roles", p=1e-9, n=20)
          for i, k in enumerate(["role_gap", "cohort_trend", "bottleneck_skill", "onboarding_speed", "unit_attention"])]
    sel = pick(cs, audience="admin")
    assert len(sel.selected) == 3


# ---------------------------------------------------------------------------------------------------- novelty and feedback
def test_novelty_halves_per_repeat_and_suppresses_an_unchanged_insight_after_two_shows():
    c = cand()
    h1 = History(shown=[HistoryEntry(c.id, NOW - 7 * DAY, c.value)])
    s = SEL.select([c], audience="worker", scope="x", now=NOW, history=h1).selected[0]
    assert s.parts["novelty"] == 0.5
    h2 = History(shown=[HistoryEntry(c.id, NOW - 14 * DAY, c.value), HistoryEntry(c.id, NOW - 7 * DAY, c.value)])
    sel = SEL.select([c], audience="worker", scope="x", now=NOW, history=h2)
    assert sel.selected == [] and why(sel, c) == ("suppressed", "repeat_recently")
    old = History(shown=[HistoryEntry(c.id, NOW - 40 * DAY, c.value)])                    # outside the 28-day window
    assert SEL.select([c], audience="worker", scope="x", now=NOW, history=old).selected[0].parts["novelty"] == 1.0


def test_a_material_change_resets_novelty():
    c = cand(value=60.0, lo=50.0, hi=70.0)
    h2 = History(shown=[HistoryEntry(c.id, NOW - 14 * DAY, 30.0), HistoryEntry(c.id, NOW - 7 * DAY, 30.0)])                # it doubled
    assert SEL.select([c], audience="worker", scope="x", now=NOW, history=h2).selected[0].parts["novelty"] == 1.0
    c2 = cand(value=31.0)
    assert SEL.select([c2], audience="worker", scope="x", now=NOW, history=h2).selected == []                              # 3% is not material


def test_a_risk_signal_never_decays_in_novelty():
    r = cand(kind="risk_signal", subject="kill_events", audience="admin", family="", p=None, lo=None, hi=None, n=1, impact=40.0, group="firm", action="open_queue")
    h = History(shown=[HistoryEntry(r.id, NOW - k * 7 * DAY, 1.0) for k in range(1, 4)])
    assert SEL.select([r], audience="admin", scope="x", now=NOW, history=h).selected[0].parts["novelty"] == 1.0


def test_feedback_can_only_quiet_things():
    a, b = cand(subject="a", impact=20.0), cand(subject="b", impact=5.0)
    base = SEL.select([a, b], audience="worker", scope="x", now=NOW)
    quiet = SEL.select([a, b], audience="worker", scope="x", now=NOW, history=History(quiet_ids={a.id: NOW - DAY}))
    assert ids(base) == [a.id, b.id] and ids(quiet) == [b.id] and why(quiet, a) == ("suppressed", "hidden_by_feedback")
    hidden = SEL.select([a, b], audience="worker", scope="x", now=NOW, history=History(hidden_kinds=frozenset({"time_loss_habit"})))
    assert hidden.selected == []
    old = SEL.select([a, b], audience="worker", scope="x", now=NOW, history=History(quiet_ids={a.id: NOW - 40 * DAY}))
    assert ids(old) == [a.id, b.id]                                                    # quieting lasts 28 days


def test_milestone_is_resolved_with_the_family_adjusted_bound():
    c = InsightCandidate(id="i_m", kind="independence_milestone", audience="worker", subject="s", group="g", polarity="positive", value=0.95, unit="share", n=20, origin="synthetic",
                         badge="made-up firm", recency_t=NOW - DAY, family="f", extras={"k": 19, "n": 20, "kp": 10, "np": 20}, slots={"skill": "s", "k": 19, "n": 20})
    sel = pick([c])
    assert ids(sel) == ["i_m"] and sel.selected[0].cand.slots["level"] == 0.65
    nomore = replace(c, extras={"k": 19, "n": 20, "kp": 19, "np": 20})                      # the same level as before: not a new crossing
    assert pick([nomore]).selected == []
    weak = replace(c, extras={"k": 13, "n": 20, "kp": None, "np": 0})
    assert pick([weak]).selected == []
