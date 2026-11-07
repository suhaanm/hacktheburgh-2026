"""The evidence packet: closed schema, no free text, builders from the v1 shapes, the ML-V2 adapter, drift against the packs."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

from understudy_engine.evidence import packet as P
from understudy_engine.evidence import vocab as V
from understudy_engine.privacy.payload import SafePayload, UnsafeFieldError

PACKS = Path(__file__).resolve().parents[4] / "packages" / "packs"


def _allowed_strings() -> set[str]:
    s: set[str] = set()
    s |= set(V.ORIGINS) | {"people", "cases", "episodes", "households", "personas", "descriptive_nearest_expert", "leave_one_person_out", "none"}
    s |= set(V.HABITS) | set(V.COG_IDS) | set(V.ROUTINE_KINDS) | set(V.REASON_CODES) | set(V.LIMIT_IDS) | set(V.STATUS_PHRASE)
    s |= {"model", "rule", "silent", "nudge", "annotate", "takeover_offer", "expert_policy", "stuck", "ask", "L1", "L2", "L3", "L4",
          "A0", "A1", "A2", "A3", "RECONCILE", "CHECK_CLIFF", "calibrated", "overconfident", "underconfident", "untested",
          "ok", "absent", "stale", "v1", "v2", "fixture"} | set(V.BLOCK_IDS)
    return s


def _strings(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield f"{path}.{k}", k, True
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(o, str):
        yield path, o, False


def test_the_wire_form_holds_only_ids_from_the_closed_sets(packets):
    ok = _allowed_strings()
    fields = set()
    for cls in (P.EvidencePacket, P.Meta, P.Gap, P.Habit, P.Cog, P.Consequence, P.Hazard, P.Progress, P.Coach, P.Routine, P.BlockInfo):
        fields |= set(cls.model_fields)
    for pk in packets:
        for path, s, is_key in _strings(pk.to_wire()):
            assert s in ok or (is_key and s in fields), f"{path}: {s!r} is not a closed-set id"


def test_a_free_string_field_cannot_be_declared():
    with pytest.raises(UnsafeFieldError):
        class Bad(SafePayload):                          # noqa: F841
            note: str


def test_unknown_fields_and_free_text_are_refused():
    base = {"meta": {"origin": "synthetic", "n": 4, "n_unit": "people", "split": "none"}}
    P.EvidencePacket.model_validate(base)
    with pytest.raises(Exception):
        P.EvidencePacket.model_validate({**base, "note": "Ada Lovelace"})
    with pytest.raises(Exception):
        P.EvidencePacket.model_validate({**base, "habits": {"tab_switching": {"seconds": 3.0}}})
    with pytest.raises(Exception):
        P.EvidencePacket.model_validate({**base, "limitations": ["a made up limitation"]})
    with pytest.raises(Exception):
        P.EvidencePacket.model_validate({"meta": {**base["meta"], "origin": "somewhere"}})


def test_genome_builder_matches_the_alignment_and_rounds_to_one_decimal(cohort):
    for person, case, pk in cohort[:8]:
        g = pk.gap
        assert g and g.case_s and g.reference_s and g.gap_s is not None
        assert abs((g.case_s - g.reference_s) - g.gap_s) <= 0.15            # dwell sums reconcile with the alignment's own total
        assert g.cohort_lo <= g.cohort_gap_s <= g.cohort_hi and g.cohort_n == 16
        assert pk.meta.origin == "synthetic" and pk.meta.n == 24 and pk.meta.n_unit == "people"
        for h in pk.habits.values():
            assert round(h.seconds, 1) == h.seconds
        assert "synthetic_data" in pk.limitations and "association_only" in pk.limitations and "single_case" in pk.limitations
        assert all(c.seconds > 0 for c in pk.cogs.values())                  # only behaviours that account for added time


def test_wire_is_small_enough_to_send(packets):
    assert max(len(json.dumps(pk.to_wire())) for pk in packets) < 4500


def test_json_schema_file_is_closed_and_in_sync():
    path = P.SCHEMA_PATH
    assert path.is_file(), "run: uv run --package understudy-engine python -m understudy_engine.evidence schema"
    on_disk = json.loads(path.read_text())
    fresh = P.json_schema()

    def strip_cogs(o):
        if isinstance(o, dict):
            return {k: ("<cogs>" if k == "enum" and isinstance(v, list) and "READ_RESULT" in v else strip_cogs(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [strip_cogs(v) for v in o]
        return o

    assert strip_cogs(on_disk) == strip_cogs(fresh)                          # cog ids follow the pack files and may grow
    jsonschema.Draft202012Validator.check_schema(on_disk)

    def walk(o):
        if isinstance(o, dict):
            if "properties" in o:
                assert o.get("additionalProperties") is False, "every object in the schema is closed"
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(on_disk)
    habit_enum = on_disk["properties"]["habits"]["propertyNames"]["enum"]
    assert habit_enum == list(V.HABITS)
    assert set(on_disk["$defs"]["Meta"]["properties"]["origin"]["enum"]) == {"synthetic", "simulated_participants", "live"}
    assert set(on_disk["$defs"]["Hazard"]["properties"]["source"]["enum"]) == {"model", "rule"}
    assert set(on_disk["properties"]["limitations"]["items"]["enum"]) == set(V.LIMIT_IDS)


def test_every_packet_validates_against_the_schema_file(packets):
    schema = json.loads(P.SCHEMA_PATH.read_text())
    for pk in packets:
        jsonschema.validate(pk.to_wire(), schema)


# ------------------------------------------------------------------------------------------------ drift
def test_habit_labels_match_the_genome_constants():
    from understudy_engine.genome import labels as L

    expected = {L.PACE: "pace", L.PAUSES: "pauses", L.SEARCH_LOOPS: "search_loops", L.REPEATED_READS: "repeated_reads",
                L.MISSED_CHECK: "missed_check", L.WRONG_COPY: "wrong_copy", L.REWORK: "rework", L.SKIPPED: "step_skips", L.OTHER_EXTRA: "other_extra"}
    assert V.LABEL_TO_HABIT == expected
    assert set(L.LABEL_ORDER) == set(V.LABEL_TO_HABIT)


def test_routine_kinds_match_the_pack_templates():
    ids = set()
    for f in PACKS.glob("*/routines.yaml"):
        ids |= {t["id"] for t in yaml.safe_load(f.read_text())["templates"]}
    assert ids == set(V.ROUTINE_KINDS), "a pack routine template was added or renamed: update vocab.RoutineKind"


def test_cog_ids_follow_the_pack_files_including_new_ones():
    extra = set()
    for f in PACKS.glob("*/pack.yaml"):
        extra |= set((yaml.safe_load(f.read_text()).get("cogs") or {}).get("extra") or [])
    assert extra <= set(V.COG_IDS)
    assert {"PROBE_EDGE", "INSPECT_INPUT", "WRITE_TEST", "CLEAN_DATA", "RECONCILE_CONTROL", "GROUP_AGG"} <= set(V.COG_IDS)
    P.Cog(seconds=1.0)
    pk = P.EvidencePacket.model_validate({"meta": {"origin": "synthetic", "n": 1, "n_unit": "people", "split": "none"},
                                          "cogs": {"PROBE_EDGE": {"seconds": 3.0}}})
    assert "cog.PROBE_EDGE.seconds" in P.facts(pk).facts
    assert all(re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", c) for c in V.COG_IDS)


def test_ids_that_the_privacy_backstop_would_refuse_are_not_in_any_vocabulary():
    from understudy_engine.privacy import patterns

    every = set(V.HABITS) | set(V.COG_IDS) | set(V.ROUTINE_KINDS) | set(V.LIMIT_IDS) | set(V.MENU_IDS) | set(V.REASON_CODES)
    for i in every:
        assert not patterns.scan_text(i), f"{i!r} would be refused as a payload value"
    for long_id in V.LIMIT_ALIASES:
        assert len(long_id) >= 32 and V.LIMIT_ALIASES[long_id] in V.LIMITATIONS


# ------------------------------------------------------------------------------------------------ ML-V2 adapter
def _inputs(accepted=True):
    from understudy_engine.mlv2 import evidence_inputs as E

    hab = E.HabitInput("search_loops", ("SEARCH",), 65.6, 50.1, 80.2, 40.2, 30.0, 55.5, 24, "splice")
    hab2 = E.HabitInput("pauses", ("IDLE",), 38.6, 20.0, 60.0, None, None, None, 24)
    env = E.EnvelopeRow("SEARCH", 120.0, 40.0, 70.0, 65.6, 50.1, 80.2)
    hz = E.HazardInput(0.62, "model", 0.579, 31, 0.015, 0.436, 0.509, 0.509, 1.21, 0.95, 1.48, calibration="calibrated", p_lo=0.5, p_hi=0.7)
    case = E.CaseInput("p_nov01", "t_nov01a", 500.0, 350.0, 150.0, 120.0, 180.0, (hab, hab2), (env,), hz, E.TimeToProgress(1.8, 1.2, 2.6, 0.7),
                       ("timing_reconstructed",))
    return E.EvidenceInputs(
        E.Provenance("synthetic", 24, "people", "leave_one_person_out", "v2", accepted),
        (case,), E.CohortInput(229.6, 193.1, 269.9, 16), None, {"placebo_expert_vs_expert": 7.1},
        ("additive_counterfactual_assumes_rest_unchanged", "held_out_replicates_same_generator", "n_four_personas"))


def test_evidence_inputs_adapter_maps_every_block():
    pk = P.from_evidence_inputs(_inputs(), person="p_nov01", case="t_nov01a")
    assert pk.gap.case_s == 500.0 and pk.gap.gap_lo == 120.0 and pk.gap.cohort_gap_s == 229.6 and pk.gap.placebo_s == 7.1
    h = pk.habits["search_loops"]
    assert (h.seconds, h.lo, h.hi, h.counterfactual_s, h.cf_lo, h.cf_hi, h.n) == (65.6, 50.1, 80.2, 40.2, 30.0, 55.5, 24)
    assert pk.habits["pauses"].counterfactual_s is None
    assert pk.cogs["SEARCH"].expert_hi_s == 70.0
    assert pk.hazard.source == "model" and pk.hazard.calibration == "calibrated" and pk.hazard.fa_hi == 1.48
    assert pk.progress.expected_min == 1.8
    assert "single_case" not in pk.limitations                              # the case has its own interval
    for lid in ("additive_counterfactual", "heldout_same_generator", "n_four_personas", "timing_reconstructed", "counterfactual_model"):
        assert lid in pk.limitations
    json.loads(P.SCHEMA_PATH.read_text())
    jsonschema.validate(pk.to_wire(), json.loads(P.SCHEMA_PATH.read_text()))


def test_a_variant_that_failed_acceptance_is_dropped():
    with pytest.raises(P.InputNotAccepted):
        P.from_evidence_inputs(_inputs(accepted=False))
    P.from_evidence_inputs(_inputs(accepted=None))


def test_evidence_inputs_with_an_unknown_habit_id_never_reach_a_packet():
    from understudy_engine.mlv2 import evidence_inputs as E

    inp = _inputs()
    bad = E.HabitInput("tab_switching", (), 1.0, 0.5, 2.0, None, None, None, 3)
    case = inp.cases[0].__class__(**{**inp.cases[0].__dict__, "habits": (bad,)})
    inp2 = E.EvidenceInputs(inp.provenance, (case,), inp.cohort, inp.hazard, inp.baselines, inp.limitations)
    with pytest.raises(E.EvidenceInputError):
        P.from_evidence_inputs(inp2)


def test_facts_cover_intervals_and_signs(pk0):
    t = P.facts(pk0)
    assert t.intervals and all(lo in t.facts and hi in t.facts for lo, hi, _ in t.intervals)
    neg = [f for f in t.facts.values() if f.signed and f.value < 0]
    assert all(f.unit == "s" for f in neg)
    assert "meta.n" in t.facts and t.facts["meta.level"].unit == "frac"


def test_builders_for_hazard_coach_and_routines():
    hz = P.from_hazard({"series": [{"t": "x", "p": 0.2}, {"t": "y", "p": 0.7}], "model": {"log_loss": 0.4363, "ece": 0.0149},
                        "baselines": {"time_since_progress": {"log_loss": 0.5091}}, "false_alarms_per_hour": 1.2149,
                        "person": {"alarm_rule": {"threshold": 0.5786}}})
    assert (hz.peak_p, hz.p_now, hz.mean_p, hz.alarm_threshold, hz.source, hz.n_bins) == (0.7, 0.7, 0.45, 0.579, "model", 2)
    coach, h2 = P.from_coach({"action": "nudge", "level": "L2", "trigger": "stuck", "reason_codes": ["stuck_signal", "weird_new_code"],
                              "gate": {"consecutive": 2}, "missed": ["a", "b"], "p_stuck": 0.61, "p_source": "heuristic"})
    assert coach.reasons == ["stuck_signal", "other"] and coach.missed_steps == 2 and h2.source == "rule"
    rows = P.from_routines([
        {"id": "calc-entry-3x", "episodes": 14, "minutes_per_week": 96, "value": {"hours_saved": [3.1, 5.2], "horizon_weeks": 4}, "status": "shadow",
         "rung": "A1", "shadow": {"runs": 12, "matches": 12, "wilson_lower": 0.757}},
        {"id": "r_0123abcd", "episodes": 3}])                                  # an unmatched routine has no id a sentence may use
    assert list(rows) == ["calc-entry-3x"]
    r = rows["calc-entry-3x"]
    assert r.next_rung == "A2" and r.runs_to_next is not None and r.runs_to_next > 0 and r.hours_lo == 3.1
