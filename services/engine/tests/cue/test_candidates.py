from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.cue import expert_data as XD
from understudy_engine.cue.candidates import NextStepModel, enabled_cogs, margin_of
from understudy_engine.cue.question import QuestionError, ambiguity_type, build_question, can_ask, valid_answer
from understudy_engine.cue.types import OTHER, Grounding

from .helpers import cand

READ = ["READ"]
CALC = ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"]


def test_pack_order_rules_mask_what_can_come_next(benefits_vocab):
    em = enabled_cogs(benefits_vocab, [])
    assert set(em) == {"READ"} and em["READ"] == ("read_case", False)
    em = enabled_cogs(benefits_vocab, READ)
    assert em == {"OPEN_CALCULATOR": ("calc_a", False)}                       # nothing else is ready before the record is read
    em = enabled_cogs(benefits_vocab, READ + CALC)                              # calculator A done
    assert em["CHECK_CLIFF"][0] == "cliff_a" and em["OPEN_CALCULATOR"][0] == "calc_b"
    assert "RECONCILE" not in em                                                # reconcile needs all three results and cliffs


def test_a_step_in_progress_claims_its_next_cog(benefits_vocab):
    em = enabled_cogs(benefits_vocab, READ + ["OPEN_CALCULATOR"])
    assert em["ENTER_HOUSEHOLD"] == ("calc_a", True)
    em2 = enabled_cogs(benefits_vocab, READ + ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD"])
    assert em2["READ_RESULT"] == ("calc_a", True)


def test_interchangeable_calculators_are_one_candidate_with_the_first_unstarted_id(benefits_vocab):
    h = READ + CALC + ["CHECK_CLIFF"]
    em = enabled_cogs(benefits_vocab, h)
    assert em["OPEN_CALCULATOR"][0] == "calc_b"
    em = enabled_cogs(benefits_vocab, h + CALC + ["CHECK_CLIFF"])
    assert em["OPEN_CALCULATOR"][0] == "calc_c"
    assert benefits_vocab.group("calc_c") == "calc_a" == benefits_vocab.group("calc_b")


def test_reconcile_waits_for_every_critical_prerequisite(benefits_vocab):
    h = READ + CALC * 3                                                         # three results, no cliff checks
    em = enabled_cogs(benefits_vocab, h)
    assert "RECONCILE" not in em and em["CHECK_CLIFF"][0] == "cliff_a"
    em = enabled_cogs(benefits_vocab, READ + (CALC + ["CHECK_CLIFF"]) * 3)
    assert em["RECONCILE"][0] == "reconcile"


@pytest.fixture(scope="module")
def model(benefits_vocab):
    paths = XD.sample_paths(benefits_vocab, n_people=30, cases=3, seed=5)
    return NextStepModel(benefits_vocab).fit(s for cs in paths.values() for s in cs)


def test_probabilities_sum_to_one_and_candidates_are_pack_vocabulary_only(model, benefits_vocab):
    p = model.p_cog(READ + CALC)
    assert sum(p.values()) == pytest.approx(1.0)
    cands, mass = model.candidates(READ + CALC)
    assert 1 <= len(cands) <= 3 and sum(c.p for c in cands) == pytest.approx(1.0) and 0 < mass <= 1.0
    for c in cands:
        assert c.id in benefits_vocab.policy.steps and c.group in benefits_vocab.policy.steps and c.label == benefits_vocab.label(c.id)
        assert c.reason_id in benefits_vocab.reasons.values()
    assert cands == sorted(cands, key=lambda c: -c.p)
    assert margin_of(cands) == pytest.approx(cands[0].p - cands[1].p)


def test_an_unseen_context_backs_off_instead_of_giving_zero(model):
    weird = ["READ", "REVERT", "REVERT", "IDLE"]
    p = model.p_cog(weird)
    assert min(p.values()) > 0 and sum(p.values()) == pytest.approx(1.0)
    assert model.candidates(weird)[0]                                          # the pack's rules still say what may come next


def test_fit_is_deterministic(benefits_vocab):
    paths = XD.sample_paths(benefits_vocab, n_people=8, cases=2, seed=2)
    seqs = [s for cs in paths.values() for s in cs]
    a = NextStepModel(benefits_vocab).fit(seqs).candidates(READ + CALC)[0]
    b = NextStepModel(benefits_vocab).fit(seqs).candidates(READ + CALC)[0]
    assert [(c.id, c.p) for c in a] == [(c.id, c.p) for c in b]


def test_an_answer_is_a_strong_label_that_moves_the_prior_and_only_the_clone(model, benefits_vocab):
    h = tuple(READ + CALC)
    before = {c.id: c.p for c in model.candidates(h)[0]}
    clone = model.clone()
    assert clone.observe_intent(h, "calc_b")
    after = {c.id: c.p for c in clone.candidates(h)[0]}
    assert after["calc_b"] > before["calc_b"]
    assert {c.id: c.p for c in model.candidates(h)[0]} == before                # the shared model is untouched
    assert not clone.observe_intent(h, "reconcile")                              # not allowed there: nothing recorded


def test_evaluation_runs_and_the_rules_beat_the_bigram_baseline(benefits_vocab):
    from understudy_engine.cue import evaluate_candidates as EC

    paths = XD.sample_paths(benefits_vocab, n_people=14, cases=3, seed=11)
    r = EC.evaluate_family(benefits_vocab, paths, n_boot=100, seed=0)
    b = r["boundary"]
    assert r["n_people"] == 14 and r["n_boundary_positions"] > 100
    assert b["cue"]["value"]["top1"] > b["bigram"]["value"]["top1"] > b["unigram"]["value"]["top1"]
    assert r["paired_boundary"]["top1_minus_bigram"]["ci"][0] > 0
    assert b["cue"]["ci"]["top1"][0] <= b["cue"]["value"]["top1"] <= b["cue"]["ci"]["top1"][1]
    assert all(x["p_mean"] is not None for x in r["calibration_boundary"])


# ------------------------------------------------------------------------------------------------ the question
def test_question_has_two_to_four_pack_options_and_the_fixed_other(benefits_vocab):
    cands = [cand("cliff_a", 0.5, label="Check cliff edges (A)"), cand("calc_b", 0.3, group="calc_a"), cand("reconcile", 0.2)]
    q, options = build_question(cands, "close_call")
    assert q == {"type": "close_call", "text": "Which of these is next?"}
    assert [o["id"] for o in options] == ["cliff_a", "calc_b", "reconcile", OTHER] and options[-1]["label"] == "Something else"
    assert 2 <= len(options) - 1 <= 4


def test_options_are_deduplicated_by_group_and_capped_at_four():
    cands = [cand(f"s{i}", 0.2, group=f"g{i % 3}") for i in range(8)]
    _, options = build_question(cands, "unclear")
    assert len(options) - 1 == 3
    many = [cand(f"s{i}", 0.1) for i in range(9)]
    assert len(build_question(many, "unclear")[1]) - 1 == 4


def test_a_question_needs_two_distinct_steps_and_a_known_template():
    with pytest.raises(QuestionError):
        build_question([cand("a", 1.0)], "close_call")
    with pytest.raises(QuestionError):
        build_question([cand("a", 0.5), cand("b", 0.5)], "free_text")
    assert not can_ask([cand("a", 1.0)]) and can_ask([cand("a", 0.5), cand("b", 0.5)])


def test_options_visible_on_screen_come_first():
    g = Grounding(found=True, chosen="b", available=("b",), box_2d=(1, 2, 30, 40), confidence=0.9, source="vision")
    _, options = build_question([cand("a", 0.6), cand("b", 0.4)], "screen_disagrees", g)
    assert [o["id"] for o in options][:2] == ["b", "a"]


def test_ambiguity_types():
    kw = dict(margin_thr=0.15, min_path_p=0.3, confident_p=0.5, ground_conf_thr=0.7)
    assert ambiguity_type([cand("a", 0.52), cand("b", 0.48)], None, grounded=False, **kw) == "close_call"
    assert ambiguity_type([cand("a", 0.8), cand("b", 0.2)], None, grounded=True, **kw) is None
    g = Grounding(found=True, chosen="b", available=("b",), box_2d=(1, 2, 30, 40), confidence=0.9, source="vision")
    assert ambiguity_type([cand("a", 0.8), cand("b", 0.2)], g, grounded=False, **kw) == "screen_disagrees"
    assert ambiguity_type([cand("a", 0.4), cand("b", 0.1), cand("c", 0.1)], None, grounded=False, **kw) == "unclear"       # ungrounded and not confident
    assert ambiguity_type([], None, grounded=False, **kw) is None


def test_answers_must_be_an_offered_option():
    assert valid_answer(["a", "b", OTHER], "a") and valid_answer(["a", "b", OTHER], OTHER) and not valid_answer(["a", "b", OTHER], "c")
