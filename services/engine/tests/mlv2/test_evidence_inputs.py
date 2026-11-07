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


def test_builder_fills_validated_inputs_for_v1_and_v2_without_any_free_text(apprentice_d0):
    from understudy_engine.mlv2.evidence_builder import build_evidence_inputs, hazard_input_from_summary

    co = apprentice_d0.cohort
    person = co.novices[0].person
    haz = hazard_input_from_summary(0.31, "model", {"metrics": {"ece": {"value": 0.015}, "log_loss": {"value": 0.436}}, "n_bins": 7376,
                                                    "events": {"false_alarms_per_hour": {"value": 1.2, "interval": [0.9, 1.5]}}}, 0.43)
    v1 = build_evidence_inputs(co, person, model_version="v1", hazard=haz, n_boot=30)
    v2 = build_evidence_inputs(co, person, model_version="v2", accepted=False, n_boot=30)
    for x in (v1, v2):
        x.validate()
        assert x.cases and all(h.habit_id in EI.HABIT_IDS for c in x.cases for h in c.habits)
        assert all(c.person_id == person for c in x.cases)
        json.dumps(x.to_dict())
    assert v1.accepted is None and v1.usable() and v2.accepted is False and not v2.usable()
    assert all(h.counterfactual_s is None for c in v1.cases for h in c.habits)
    assert all(h.counterfactual_s is None for c in v2.cases for h in c.habits)
    assert v1.cases[0].hazard.calibration == "calibrated" and v1.cases[0].hazard.source == "model"
    c = v1.cases[0]
    assert abs(c.gap_s - sum(h.seconds for h in c.habits)) < 5.0 or c.habits      # the habits (bars above half a second) account for the gap
    assert all(e.expert_lo_s <= e.expert_hi_s for e in c.envelope)


def test_build_for_person_and_case_from_a_store(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path / "evals"))               # no held-out file here: v2 must be unaccepted
    from understudy_engine.mlv2 import evidence_builder as EB
    from understudy_engine.personas import apprentices

    apprentices.generate(tmp_path)
    x = EI.build("p_nov01", root=tmp_path, n_boot=20)
    assert x.model_version == "v1" and x.accepted is None and len(x.cases) == 2
    one = EB.build_for("p_nov01", x.cases[0].task_id, root=tmp_path, n_boot=20)
    assert len(one.cases) == 1 and one.cases[0].task_id == x.cases[0].task_id
    v2 = EB.build_for("p_nov01", root=tmp_path, model_version="v2", n_boot=20)
    assert v2.model_version == "v2" and v2.accepted is False and not v2.usable()        # no held-out acceptance: never reaches the explainer
    assert all(h.counterfactual_s is None for c in v2.cases for h in c.habits)         # Q1 was rejected: no counterfactual attached
    from understudy_engine.mlv2 import freeze

    freeze.write_json(freeze.out_dir() / "results" / "heldout_genome.json", {"family_e": {"rows": {"E1": {"verdict": "accepted"}}}})
    v2b = EB.build_for("p_nov01", root=tmp_path, model_version="v2", n_boot=20)
    assert v2b.accepted is True and v2b.usable() and v2b.provenance.pool == "heldout"
    with pytest.raises(ValueError):
        EB.build_for("p_nobody", root=tmp_path)
    with pytest.raises(ValueError):
        EB.build_for("p_nov01", "t_other", root=tmp_path, n_boot=20)
