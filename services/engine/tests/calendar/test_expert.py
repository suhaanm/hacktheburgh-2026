"""CAL-2: expert templates (one per role pack), the feature gap with intervals, and the week ribbon with its placebo."""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
import yaml

from understudy_engine.calendar import expert as E
from understudy_engine.calendar import service
from understudy_engine.calendar.features import ALL_KEYS, analyse_week, week_blocks_json
from understudy_engine.calendar.model import week_label


def test_every_role_pack_has_a_valid_template():
    assert E.template_roles() == ["benefits-processor", "data-analyst", "programmer"]
    for role in E.template_roles():
        tpl = E.load_template(role)
        assert tpl.role == role and len(tpl.slots) >= 7 and tpl.work.end_min > tpl.work.start_min
        kinds = {s.kind for s in tpl.slots}
        assert {"meeting", "batch", "review", "offscreen"} <= kinds             # batch windows, review slots, a real break, standing meetings
        ref = E.template_reference(role)
        assert E.breaches(ref, tpl.targets) == {}, (role, E.breaches(ref, tpl.targets))      # a template meets its own targets
        assert ref["fragmented_days"] == 0 and ref["back_to_back_runs"] == 0 and ref["outside_hours_h"] == 0
        assert ref["recurring_in_peak_h"] <= tpl.targets["recurring_in_peak_h_max"]
        assert tpl.plugin_refs and all(k in ("source", "skill") for k, _ in tpl.plugin_refs)


def test_templates_differ_by_role():
    a, b, c = (E.load_template(r) for r in E.template_roles())
    assert len({(t.work.start_min, t.work.end_min) for t in (a, b, c)}) == 3
    assert E.template_reference("programmer")["meeting_h"] != E.template_reference("benefits-processor")["meeting_h"]


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["slots"][0].update(kind="party"), "kind"),
    (lambda d: d["targets"].pop("meeting_h_max"), "meeting_h_max"),
    (lambda d: d["work_window"].update(start="9am"), "start"),
    (lambda d: d.update(version=2), "version"),
    (lambda d: d["slots"][0].update(days=["someday"]), "days"),
    (lambda d: d.update(surprise=1), "surprise"),
    (lambda d: d["slots"][1].update(end="08:00"), "ends before"),
])
def test_invalid_templates_are_rejected(mutate, needle):
    d = yaml.safe_load(open(E.packs_dir() / "benefits-processor" / "routine_expert.yaml").read())
    d = copy.deepcopy(d)
    mutate(d)
    with pytest.raises(E.TemplateError) as e:
        E.parse_template(d)
    assert needle in str(e.value)


def test_missing_template_is_a_plain_error():
    with pytest.raises(E.TemplateError) as e:
        E.load_template("nonexistent-role")
    assert "benefits-processor" in str(e.value)


def test_breaches_are_relative_to_the_target():
    t = {"focus_blocks_90_min": 6, "back_to_back_runs_max": 1, "offscreen_h_min": 3.0, "review_slots_min": 3, "meeting_h_max": 8.0}
    b = E.breaches({"focus_blocks_90": 3, "back_to_back_runs": 4, "offscreen_h": 3.0, "review_slots": 3, "meeting_h": 8.0}, t)
    assert set(b) == {"focus_blocks_90", "back_to_back_runs"} and b["focus_blocks_90"]["shortfall"] == 0.5 and b["back_to_back_runs"]["shortfall"] == 3.0


def test_cohort_agrees_with_the_template_it_was_generated_from(store):
    ref = service.reference_for(store, "benefits-processor")
    assert ref.source == "cohort" and ref.n_experts == 8 and len(ref.weeks) == 24
    tpl_ref = E.template_reference("benefits-processor")
    m = ref.features()
    assert abs(m["meeting_h"] - tpl_ref["meeting_h"]) < 2.0 and abs(m["focus_blocks_90"] - tpl_ref["focus_blocks_90"]) < 2.0
    assert abs(m["offscreen_h"] - tpl_ref["offscreen_h"]) < 1.0 and m["recurring_in_peak_h"] == 0 and m["fragmented_days"] == 0
    # by construction, not evidence about real experts: the test documents it
    assert E.breaches(m, E.load_template("benefits-processor").targets) == {}


def test_a_role_without_a_cohort_falls_back_to_the_template(store):
    ref = service.reference_for(store, "programmer")
    assert ref.source == "template" and ref.n_experts == 0 and ref.bootstrap() is None
    rows = E.gap_rows(E.template_reference("programmer"), ref)
    assert all(r["ci"] is None and r["delta"] == 0 for r in rows)


def test_ribbon_distance_basics(store):
    pc = store.get("p_exp01")
    wa = pc.week(pc.weeks[0])
    r = E.ribbon_distance(wa, wa)
    assert r.distance == 0.0 and all(c.op == "match" for c in r.alignment.columns)
    other = store.get("p_nightowl")
    far = E.ribbon_distance(wa, other.week(other.weeks[0]))
    assert far.distance > 0.3
    assert {row["op"] for row in far.rows()} <= {"match", "mismatch", "gap_expert", "gap_novice"}
    assert all(set(row) == {"op", "expert", "learner", "minutes"} for row in far.rows())      # enums and numbers only


def test_placebo_is_near_zero_and_planted_weeks_are_far(store):
    ref = service.reference_for(store, "benefits-processor")
    pl = ref.placebo()
    assert pl["distance"] is not None and pl["distance"] < 0.2 and pl["ci"][0] <= pl["distance"] <= pl["ci"][1] and pl["n_experts"] == 8
    truth = store.truth()["people"]
    planted, clean = [], []
    for p in store.people():
        if store.info(p)["group"] == "expert":
            continue
        pc = store.get(p)
        for m in pc.weeks:
            d = ref.nearest(pc.week(m))[1].distance
            (planted if truth[p]["problems"] else clean).append(d)
    assert sum(planted) / len(planted) > 2 * pl["distance"] and sum(planted) / len(planted) > 0.3
    assert len(clean) == 3 and max(clean) < 0.25                                    # the one clean novice looks like an expert


def test_gap_rows_recover_the_planted_direction(store):
    ref = service.reference_for(store, "benefits-processor")

    def rows(p):
        pc = store.get(p)
        feats = pc.week(pc.weeks[0]).features
        return {r["feature"]: r for r in E.gap_rows(feats, ref)}

    r = rows("p_ninetofive")
    assert r["fragmented_days"]["delta"] > 1.5 and r["fragmented_days"]["significant"] and r["focus_blocks_90"]["delta"] < -3
    r = rows("p_nightowl")
    assert r["meeting_h"]["delta"] > 15 and r["offscreen_h"]["delta"] < -3 and r["focus_blocks_90"]["delta"] < -5 and r["focus_blocks_90"]["significant"]
    r = rows("p_shiftwkr")
    assert r["back_to_back_runs"]["delta"] > 1.5 and r["external_unbuffered_n"]["delta"] > 0.5
    r = rows("p_irregular")
    assert r["recurring_in_peak_h"]["delta"] > 1.5 and r["review_slots"]["delta"] < -2 and r["recurring_in_peak_h"]["significant"]
    for row in rows("p_ninetofive").values():
        assert row["ci"][0] <= row["delta"] <= row["ci"][1] or abs(row["delta"] - sum(row["ci"]) / 2) < 1.0


def test_an_expert_compared_with_the_others_shows_almost_no_gap(store):
    ref = service.reference_for(store, "benefits-processor")
    sig = 0
    n = 0
    for p in store.people("expert"):
        pc = store.get(p)
        f = pc.week(pc.weeks[0]).features
        for r in E.gap_rows(f, ref, exclude=p):
            n += 1
            sig += bool(r["significant"])
            if r["feature"] in ("fragmented_days", "recurring_in_peak_h", "outside_hours_h"):
                assert abs(r["delta"]) < 0.5
    assert sig / n < 0.25                                                                 # outside the range of the other experts' weeks: rare


def test_bootstrap_is_deterministic_and_leave_one_out(store):
    ref = service.reference_for(store, "benefits-processor")
    a = ref.bootstrap("p_exp01", n_boot=50, seed=3)
    b = ref.bootstrap("p_exp01", n_boot=50, seed=3)
    assert a == b and a != ref.bootstrap("p_exp01", n_boot=50, seed=4)
    assert ref.features("p_exp01") != ref.features()


def test_week_report_shape_and_no_text(store):
    rep = service.week_report(store, "p_nov05", "2026-W43", n_boot=100)
    assert rep["week"] == "2026-W43" and rep["weeks_available"] == ["2026-W42", "2026-W43", "2026-W44"] and rep["group"] == "novice"
    assert len(rep["days"]) == 7 and set(rep["expert"]) >= set(ALL_KEYS) | {"days", "person", "week", "source", "n_experts"}
    assert len(rep["expert"]["days"]) == 7 and rep["expert"]["person"].startswith("p_exp") and rep["expert"]["source"] == "cohort"
    mon = rep["days"][0]["blocks"]
    for b in mon:
        assert set(b) >= {"start", "end", "kind", "start_min", "end_min", "usable"} and b["kind"] in ("meeting", "focus", "break", "offscreen", "free")
        assert len(b["start"]) == 5 and b["start"][2] == ":" and len(b["end"]) == 5 and b["end"][2] == ":"
        assert b["start_min"] < b["end_min"] and ("n_attendees_bucket" in b) == (b["kind"] == "meeting")
        assert b.get("n_attendees_bucket", "lt5") in ("lt5", "5to9", "10plus")
    assert [r["feature"] for r in rep["gap"]["rows"]][:8] == list(E.CONTRACT_KEYS)
    assert rep["gap"]["ribbon"]["placebo"]["distance"] < rep["gap"]["ribbon"]["distance"] + 1


def test_an_expert_report_leaves_that_expert_out_of_its_own_reference(store):
    rep = service.week_report(store, "p_exp03", n_boot=50)
    assert rep["expert"]["n_experts"] == 7 and rep["expert"]["person"] != "p_exp03"
