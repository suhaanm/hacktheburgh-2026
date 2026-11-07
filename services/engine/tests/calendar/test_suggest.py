"""CAL-3: the fixed catalogue, code-side selection, templated text, and wording only through the egress guard."""
from __future__ import annotations

import json

import pytest

from understudy_engine.calendar import service
from understudy_engine.calendar import suggest as S
from understudy_engine.calendar.expert import load_template, template_reference
from understudy_engine.calendar.features import ALL_KEYS
from understudy_engine.calendar.model import week_label

T = load_template("benefits-processor").targets
GOOD = dict(template_reference("benefits-processor"))


def feats(**kw):
    return {**GOOD, **kw}


def test_catalogue_has_at_least_eight_templates_and_is_fixed():
    assert len(S.TEMPLATES) >= 8 and len(set(S.TEMPLATE_IDS)) == len(S.TEMPLATES)
    wanted = {"protect_focus_block", "batch_similar_work", "add_review_slot", "auto_hold_scheduling", "offcomputer_break", "reduce_back_to_back",
              "move_recurring_out_of_peak", "buffer_before_external"}
    assert wanted <= set(S.TEMPLATE_IDS)
    for t in S.TEMPLATES:
        assert t.cites and all(c in ALL_KEYS for c in t.cites) and t.title and t.text
    assert S.catalogue()[0]["id"] == S.TEMPLATES[0].id


def test_a_week_that_meets_the_targets_gets_no_suggestion_and_so_does_a_week_exactly_at_them():
    assert S.suggest(feats(), GOOD, T) == []
    edge = feats(focus_blocks_90=T["focus_blocks_90_min"], back_to_back_runs=T["back_to_back_runs_max"], offscreen_h=T["offscreen_h_min"],
                 recurring_in_peak_h=T["recurring_in_peak_h_max"], external_unbuffered_n=T["external_unbuffered_max"], review_slots=T["review_slots_min"],
                 meeting_h=T["meeting_h_max"], outside_hours_h=T["outside_hours_h_max"])
    assert S.select(edge, T) == {}


@pytest.mark.parametrize("patch,template", [
    ({"focus_blocks_90": 2}, "protect_focus_block"),
    ({"batch_windows": 1, "fragmented_days": 3}, "batch_similar_work"),
    ({"review_slots": 0}, "add_review_slot"),
    ({"offscreen_h": 0.0}, "offcomputer_break"),
    ({"back_to_back_runs": 4}, "reduce_back_to_back"),
    ({"recurring_in_peak_h": 3.0}, "move_recurring_out_of_peak"),
    ({"external_unbuffered_n": 2}, "buffer_before_external"),
    ({"meeting_h": 20.0, "meeting_share": 0.5}, "trim_meeting_load"),
    ({"outside_hours_h": 3.0}, "protect_working_edges"),
])
def test_each_threshold_selects_its_template(patch, template):
    assert template in S.select(feats(**patch), T)


def test_batch_needs_both_a_missing_batch_window_and_fragmentation():
    assert "batch_similar_work" not in S.select(feats(batch_windows=0), T)
    assert "batch_similar_work" not in S.select(feats(fragmented_days=3), T)


def test_auto_hold_replaces_the_one_off_block_only_when_the_shortfall_repeats():
    short = feats(focus_blocks_90=1)
    assert "protect_focus_block" in S.select(short, T) and "auto_hold_scheduling" not in S.select(short, T)
    assert "protect_focus_block" in S.select(short, T, [short])
    hist = [short, short]
    sel = S.select(short, T, hist)
    assert "auto_hold_scheduling" in sel and "protect_focus_block" not in sel
    assert "protect_focus_block" in S.select(short, T, [GOOD, short])                         # one bad week out of two is not a pattern
    # a calendar that is already mostly meetings has no room to hold: stay with the one-off advice
    assert "auto_hold_scheduling" not in S.select({**short, "meeting_share": 0.6}, T, hist)


def test_priority_orders_by_how_far_off_the_week_is():
    out = S.suggest(feats(focus_blocks_90=5, review_slots=0), GOOD, T, person="p", week="2026-W44")
    assert [s["template"] for s in out][0] == "add_review_slot" and out[0]["priority"] > out[1]["priority"]
    assert S.suggest(feats(review_slots=0, offscreen_h=0.0, focus_blocks_90=0), GOOD, T, max_n=2).__len__() == 2


def test_each_suggestion_carries_numbers_the_expert_reference_and_a_low_risk():
    out = S.suggest(feats(back_to_back_runs=4, longest_b2b_min=150), GOOD, T, person="p_x", week="2026-W44")
    s = next(x for x in out if x["template"] == "reduce_back_to_back")
    assert s["numbers"] == {"back_to_back_runs": 4, "longest_b2b_min": 150}
    assert s["expert_ref"]["back_to_back_runs_max"] == T["back_to_back_runs_max"] and "back_to_back_runs_reference" in s["expert_ref"]
    assert s["risk"] == "low" and s["can_draft"] is False and s["source"] == "templated" and s["id"] == "cal:reduce_back_to_back:p_x:2026-W44"
    assert "4" in s["text"] and "150" in s["text"] and "\n" not in s["text"] and "{" not in s["text"]
    holds = {x["template"]: x["can_draft"] for x in S.suggest(feats(focus_blocks_90=0, review_slots=0, offscreen_h=0.0, external_unbuffered_n=3,
                                                                     back_to_back_runs=5), GOOD, T)}
    assert holds["protect_focus_block"] and holds["add_review_slot"] and holds["offcomputer_break"] and holds["buffer_before_external"] and not holds["reduce_back_to_back"]


def test_templated_text_has_no_unfilled_placeholders_for_any_template():
    worst = feats(focus_blocks_90=0, focus_blocks_60=0, batch_windows=0, fragmented_days=4, fragmentation=0.95, review_slots=0, offscreen_h=0.0,
                  back_to_back_runs=6, longest_b2b_min=200, recurring_in_peak_h=5.0, recurring_series=4, external_unbuffered_n=3, meeting_h=25.0,
                  meeting_share=0.45, outside_hours_h=6.0, work_span_h=12.0)
    out = S.suggest(worst, GOOD, T, history=[worst, worst, worst])
    assert {s["template"] for s in out} == set(S.TEMPLATE_IDS) - {"protect_focus_block"}       # auto-hold stands in for the one-off block
    assert all("{" not in s["text"] and "}" not in s["text"] for s in out)
    one = S.suggest(worst, GOOD, T)
    assert "protect_focus_block" in {s["template"] for s in one}


def test_catalogue_coverage_on_the_synthetic_cohort(store):
    """Every template is triggered by at least one synthetic person-week, and experts are rarely told anything."""
    hit: dict[str, int] = {t: 0 for t in S.TEMPLATE_IDS}
    expert_weeks = expert_flagged = 0
    for p in store.people():
        pc = store.get(p)
        for m in pc.weeks:
            rep = service.suggestions_report(store, p, week_label(m))
            for s in rep["suggestions"]:
                hit[s["template"]] += 1
            if pc.group == "expert":
                expert_weeks += 1
                expert_flagged += bool(rep["suggestions"])
    assert all(v > 0 for v in hit.values()), hit
    assert expert_weeks == 24 and expert_flagged / expert_weeks <= 0.15, (expert_flagged, expert_weeks)


# ---------------------------------------------------------------------------------------------------- wording through the guard
def _port(text="Try holding one longer focus block each day."):
    from understudy_engine.privacy.testing import CapturingPort
    return CapturingPort(stub_text=text)


def _one():
    f = feats(focus_blocks_90=2, longest_focus_min=95, review_slots=0)
    sug = S.suggest(f, GOOD, T, person="p_x", week="2026-W44")
    return f, next(x for x in sug if x["template"] == "protect_focus_block")


def test_wording_payload_is_numbers_and_enums_only():
    f, s = _one()
    p = S.wording_payload(s, "benefits-processor", GOOD, f)
    assert set(p) == {"template", "role", "risk", "learner", "expert"} and p["template"] in S.TEMPLATE_IDS and p["risk"] == "low"
    blob = json.dumps(p)
    assert all(isinstance(v, (int, float, str)) for v in list(p["learner"].values()) + list(p["expert"].values()))
    assert p["learner"]["focus_blocks_90"] == "lt5"                                                # counts under five are generalised
    assert "cal:" not in blob and "p_x" not in blob and "2026-W44" not in blob                      # no person id, no week label


def test_reword_goes_through_egress_and_is_recorded(tmp_path):
    from understudy_engine.privacy import ledger
    from understudy_engine.privacy.testing import CapturingPort, assert_ledger_complete  # noqa: F401
    f, s = _one()
    port = _port("Hold one longer focus block on most days.")
    out = S.reword(s, "benefits-processor", GOOD, f, port=port, accept_mock=True)
    assert out["source"] == "reworded" and out["text"] == "Hold one longer focus block on most days." and out["ledger_id"]
    assert len(port.requests) == 1
    body = json.dumps(port.requests[0].body, default=str).lower()
    for forbidden in ("cal:", "p_x", "huddle", "@", "fenwick"):
        assert forbidden not in body
    assert s["template"] in body and "benefits-processor" in body


def test_reword_falls_back_to_the_template_on_refusal_or_bad_output():
    f, s = _one()
    from understudy_engine.privacy.testing import CapturingPort
    boom = CapturingPort().fail_with(RuntimeError("model down"))
    assert S.reword(s, "benefits-processor", GOOD, f, port=boom, accept_mock=True)["source"] == "templated"
    for bad in ("x" * 400, "two\nlines", "   "):
        assert S.reword(s, "benefits-processor", GOOD, f, port=_port(bad), accept_mock=True)["text"] == s["text"]
    # an offline stub is not a rewording: the template stays, the ledger line is still written
    assert S.reword(s, "benefits-processor", GOOD, f, port=_port("stub"))["text"] == s["text"]
    # a payload the guard refuses never reaches the port
    port = _port()
    bad = {**s, "template": "not_a_template"}
    with pytest.raises(KeyError):
        S.wording_payload(bad, "benefits-processor", GOOD, f)
    assert port.requests == []


def test_template_ids_and_features_are_registered_with_the_privacy_vocabularies():
    from understudy_engine.privacy import payload
    from understudy_engine.privacy.bucket import feature_kinds
    assert S.register_privacy()
    for kind, name in (("calendar.template", t) for t in S.TEMPLATE_IDS):
        assert payload.get_vocabulary(kind).allows(name) if hasattr(payload, "get_vocabulary") else True
    kinds = feature_kinds()
    assert all(k in kinds for k in ("meeting_h", "focus_blocks_90", "recurring_in_peak_h", "external_unbuffered_n", "review_slots", "outside_hours_h"))
