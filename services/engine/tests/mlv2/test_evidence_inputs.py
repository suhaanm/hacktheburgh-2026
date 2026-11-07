import dataclasses
import json

import pytest

from understudy_engine.mlv2 import evidence_inputs as EI


def _habit(**kw):
    d = dict(habit_id="repeated_reads", cog_ids=("READ_RESULT",), seconds=12.0, seconds_lo=8.0, seconds_hi=16.0,
             counterfactual_s=11.0, counterfactual_lo=7.0, counterfactual_hi=15.0, n=14, method="splice", shapley_share=0.3)
    d.update(kw)
    return EI.HabitInput(**d)


def _inputs(**kw):
    case = EI.CaseInput("p_nov03", "t_nov03a", 310.0, 240.0, 70.0, 40.0, 100.0, habits=(_habit(),),
                        envelope=(EI.EnvelopeRow("READ_RESULT", 20.0, 6.0, 12.0, 8.0, 4.0, 11.0),),
                        hazard=EI.HazardInput(0.31, "model", 0.43, 800, 0.015, 0.436, 0.509, 0.509, 0.95, 0.8, 1.1),
                        time_to_progress=EI.TimeToProgress(1.7, 1.2, 2.4, 0.64), limitations=("shared_steps_mispriced",))
    base = dict(provenance=EI.Provenance("synthetic", 16, "people", "leave_one_person_out", "v2", accepted=False, pool="heldout"),
                cases=(case,), cohort=EI.CohortInput(229.6, 192.7, 272.6, 16), hazard=None,
                baselines={"base_rate": 0.509}, limitations=("synthetic_people_only", "generator_planted_structure"))
    base.update(kw)
    return EI.EvidenceInputs(**base)


def test_valid_inputs_pass_and_expose_the_accept_fields():
    x = _inputs().validate()
    assert x.model_version == "v2" and x.accepted is False and not x.usable()
    assert _inputs(provenance=EI.Provenance("synthetic", 4, "people", "none", "v1")).usable()
    json.dumps(x.to_dict())


def test_closed_sets_are_enforced():
    with pytest.raises(EI.EvidenceInputError):
        _inputs(cases=(dataclasses.replace(_inputs().cases[0], habits=(_habit(habit_id="skipped_steps"),)),)).validate()
    with pytest.raises(EI.EvidenceInputError):
        _inputs(limitations=("this is free text",)).validate()
    with pytest.raises(EI.EvidenceInputError):
        _inputs(provenance=EI.Provenance("real", 4, "people", "none", "v1")).validate()
    with pytest.raises(EI.EvidenceInputError):
        _inputs(cases=(dataclasses.replace(_inputs().cases[0], person_id="Alice Smith"),)).validate()


def test_numbers_must_be_finite_and_intervals_ordered():
    with pytest.raises(EI.EvidenceInputError):
        _inputs(cases=(dataclasses.replace(_inputs().cases[0], habits=(_habit(seconds=float("nan")),)),)).validate()
    with pytest.raises(EI.EvidenceInputError):
        _inputs(cases=(dataclasses.replace(_inputs().cases[0], habits=(_habit(seconds_lo=20.0, seconds_hi=10.0),)),)).validate()


def test_habit_label_maps_cover_every_waterfall_bar_without_the_forbidden_word():
    from understudy_engine.genome.labels import LABEL_ORDER

    assert set(EI.HABIT_OF_LABEL) == set(LABEL_ORDER)
    assert set(EI.HABIT_OF_LABEL.values()) <= set(EI.HABIT_IDS)
    assert "skipped_steps" not in EI.HABIT_IDS
    assert set(EI.HABIT_OF_DEFICIT.values()) <= set(EI.HABIT_IDS)
