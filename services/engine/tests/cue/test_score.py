from __future__ import annotations

import copy

import numpy as np
import pytest

from understudy_engine.cue import ledger as L
from understudy_engine.cue import score as S
from understudy_engine.cue import simlearn as SL

T0 = 1_790_000_000.0
H = 3600.0


def row(i, outcome="clean", *, skill="check-the-cliff", t=None, accepted=None, stream="assist", tier=0, taught=False, lost_s=None, person="p_t", **kw):
    acc = (outcome == "assisted") if accepted is None else accepted
    return L.make_row(person=person, role="benefits-processor", skill=skill, step="cliff_a", t=(T0 + i * 6 * H) if t is None else t, outcome=outcome,
                      accepted=acc, tier=tier, taught=taught, lost_s=lost_s, stream=stream, serial=i, trigger="auto" if tier else "none",
                      p_stuck=0.8 if tier else None, **kw)


def seq(outcomes, **kw):
    return [row(i, o, **kw) for i, o in enumerate(outcomes)]


# ------------------------------------------------------------------------------------------------ independence
def test_independence_is_clean_share_of_the_last_twenty_with_wilson_bounds():
    rows = seq(["assisted"] * 10 + ["clean"] * 20)
    ind = S.independence(S.assist_only(rows))
    assert (ind["k"], ind["n"]) == (20, 20) and ind["share"] == 1.0
    assert ind["lower"] == pytest.approx(0.8389, abs=1e-3)       # 20 of 20 gives about 0.839 (trust.stats)
    ind2 = S.independence(S.assist_only(seq(["clean"] * 10 + ["assisted"] * 10)))
    assert ind2["share"] == 0.5 and ind2["wilson"][0] < 0.5 < ind2["wilson"][1]


def test_guards_errors_abandoned_and_dismissal_without_completion_are_not_independence():
    ok = S.independence(S.assist_only(seq(["clean"] * 20)))["share"]
    assert ok == 1.0
    for bad in ("error", "abandoned", "assisted"):
        rows = seq(["clean"] * 19 + [bad])
        assert S.independence(S.assist_only(rows))["share"] == 0.95
    dismissed_walked_away = [row(i, "abandoned", tier=1, dismissed=True) for i in range(20)]
    assert S.independence(S.assist_only(dismissed_walked_away))["share"] == 0.0


def test_a_step_that_did_not_occur_has_no_row_and_is_not_counted():
    assert S.independence([])["n"] == 0 and S.independence([])["share"] is None
    g = S.growth([], person="p_t", now=T0)
    assert g["readiness"] == {"occurrences": 0, "needed": 10, "ready": False, "trend_needed": 30} and g["score"]["composite_experimental"] is None


def test_clean_with_an_accepted_flag_is_never_independent():
    r = row(0, "clean", accepted=True)
    assert not S.is_independent(r)


# ------------------------------------------------------------------------------------------------ streams
def test_automation_and_delegated_rows_never_change_any_number():
    base = seq(["clean", "assisted", "clean", "error", "clean"] * 8, lost_s=20.0)
    extra = []
    for i in range(30):
        for stream in ("delegated", "automation"):
            extra.append(L.make_row(person="p_t", role="benefits-processor", skill="check-the-cliff", t=T0 + i * H, outcome="clean", stream=stream, routine="calc-entry-3x",
                                    minutes=12.0, offload_outcome="done", serial=1000 + i))
    now = T0 + 41 * 6 * H
    a = S.growth(base, person="p_t", now=now, n_boot=100)
    b = S.growth(base + extra, person="p_t", now=now, n_boot=100)
    strip = lambda g: {k: v for k, v in g.items() if k not in ("offloaded", "counts")}          # noqa: E731
    assert strip(a) == strip(b)
    assert b["offloaded"]["delegated"] == 30 and b["offloaded"]["automation"] == 30 and a["offloaded"]["delegated"] == 0
    assert b["offloaded"]["minutes"]["delegated"] == 360.0
    # also the building blocks, one by one
    assert S.compute(base, now, n_boot=50, seed=1) == S.compute(base + extra, now, n_boot=50, seed=1)


def test_assist_only_filters_other_streams():
    rows = seq(["clean"] * 3) + [L.make_row(person="p_t", role="benefits-processor", skill=None, t=T0, outcome="clean", stream="automation", serial=99)]
    assert len(S.assist_only(rows)) == 3


# ------------------------------------------------------------------------------------------------ trend
def test_theil_sen_is_robust_to_an_outlier():
    assert S.theil_sen([0.8, 0.6, 0.4, 0.2, 0.0]) == pytest.approx(-0.2)
    assert S.theil_sen([0.8, 0.6, 5.0, 0.2, 0.0]) < -0.1
    assert S.theil_sen([1.0]) is None


def test_trend_direction_and_too_early():
    assert S.trend(S.assist_only(seq(["assisted"] * 5 + ["clean"] * 20)))["direction"] == "too_early"          # fewer than three blocks
    falling = S.assist_only(seq((["assisted"] * 8 + ["clean"] * 2) + (["assisted"] * 5 + ["clean"] * 5) + (["assisted"] * 2 + ["clean"] * 8) + ["clean"] * 10))
    tr = S.trend(falling, n_boot=300)
    assert tr["slope_per_10"] < 0 and tr["direction"] == "less_help" and tr["ci"][1] < 0 and tr["windows"] >= 3
    rising = S.assist_only(seq(["clean"] * 10 + ["assisted"] * 5 + ["clean"] * 5 + ["assisted"] * 10 + ["assisted"] * 10))
    assert S.trend(rising, n_boot=300)["direction"] == "more_help"
    flat = S.assist_only(seq((["assisted", "clean"] * 5) * 5))
    assert S.trend(flat, n_boot=300)["direction"] == "steady"


# ------------------------------------------------------------------------------------------------ gap and retention
def test_gap_closure_first_five_against_latest_five():
    rows = S.assist_only([row(i, "clean", lost_s=40.0 if i < 5 else (10.0 if i >= 15 else 25.0)) for i in range(20)])
    g = S.gap_closure(rows, n_boot=200)
    assert g["value"] == pytest.approx(0.75) and g["first5_lost_s"] == 40.0 and g["last5_lost_s"] == 10.0 and g["ci"][0] <= 0.75 <= g["ci"][1]
    assert S.gap_closure(rows[:8])["value"] is None
    nogap = S.assist_only([row(i, "clean", lost_s=-5.0) for i in range(12)])
    assert S.gap_closure(nogap)["value"] is None            # nothing to close


def test_retention_is_the_first_occurrence_three_days_after_teaching():
    day = 24 * H
    rows = [row(0, "assisted", t=T0, taught=True), row(1, "clean", t=T0 + 1 * day),          # inside 3 days: not a probe
            row(2, "clean", t=T0 + 4 * day),                                                  # the probe: unaided success
            row(3, "assisted", t=T0 + 5 * day, taught=True), row(4, "assisted", t=T0 + 9 * day)]   # a second probe: failed
    r = S.retention(S.assist_only(rows))
    assert (r["k"], r["n"]) == (1, 2) and r["value"] == 0.5
    assert S.retention(S.assist_only(rows[:2]))["value"] is None


def test_retention_pools_by_skill():
    day = 24 * H
    rows = [row(0, "assisted", t=T0, taught=True, skill="a-skill"), row(1, "assisted", t=T0, taught=True, skill="b-skill"),
            row(2, "clean", t=T0 + 4 * day, skill="a-skill"), row(3, "error", t=T0 + 4 * day, skill="b-skill")]
    r = S.retention(S.assist_only(rows))
    assert (r["k"], r["n"]) == (1, 2)


# ------------------------------------------------------------------------------------------------ composite
def test_composite_uses_the_stated_weights_and_renormalises_when_a_component_is_missing():
    c = S.composite(0.5, 0.5, 0.5, 0.5)
    assert c["value"] == 50.0 and not c["partial"] and c["used_weights"] == S.WEIGHTS
    full = S.composite(1.0, 0.0, 0.0, 0.0)
    assert full["value"] == 40.0
    part = S.composite(0.5, 0.5, None, None)
    assert part["partial"] and part["available_weight"] == pytest.approx(0.7) and part["value"] == 50.0
    assert sum(part["used_weights"].values()) == pytest.approx(1.0)
    assert S.composite(None, 0.5, 0.5, 0.5)["value"] is None


def test_components_are_always_returned_beside_the_composite_and_unready_data_has_no_composite():
    rows = seq(["clean", "assisted"] * 4)                   # 8 occurrences: below the needed 10
    g = S.growth(rows, person="p_t", now=T0 + 10 * 6 * H, n_boot=50)
    assert g["score"]["composite_experimental"] is None and g["curve"] == [] and g["trend"]["direction"] == "too_early"
    assert g["readiness"] == {"occurrences": 8, "needed": 10, "ready": False, "trend_needed": 30}
    assert g["trend"]["needed_more"] == 22 and "30 occurrences" in g["trend"]["power_note"]
    assert set(g["components"]) == {"independence", "mastery", "gap_closure", "retention"}
    big = seq(["clean", "assisted", "clean", "clean"] * 10, lost_s=15.0)
    g2 = S.growth(big, person="p_t", now=T0 + 41 * 6 * H, n_boot=60)
    sc = g2["score"]
    assert sc["composite_experimental"] is not None and sc["composite_experimental_ci"][0] <= sc["composite_experimental"] <= sc["composite_experimental_ci"][1] + 5
    assert "composite" not in sc and "composite_ci" not in sc
    assert sc["composite_caveat"].startswith("Experimental.") and "Read the trend and the independence interval instead." in sc["composite_caveat"]
    assert sc["composite_caveat"] == S.caveat_text(sc["composite_caveat_figures"])
    assert g2["trend"]["power_note"] and g2["components"]["mastery"]["note"]
    assert g2["score"]["weights_note"] == "stated assumptions, not fitted"
    assert g2["claim"].endswith("This is not a measure of expertise.")


def test_growth_payload_has_the_agreed_fields_and_no_text_beyond_ids_and_enums():
    rows = SL.simulate_learner(SL.preset("improving"), np.random.default_rng(2), person="p_sim", n_per_skill=14)[0]
    g = S.growth(rows, person="p_sim", n_boot=60)
    for k in ("person", "role", "skill", "window", "as_of", "origin_detail", "readiness", "score", "baseline", "components", "trend", "curve",
              "occurrences", "time_to_progress", "by_skill", "offloaded", "counts", "claim"):
        assert k in g, k
    for k in ("composite_experimental", "composite_experimental_ci", "composite_partial", "available_weight", "weights", "used_weights", "weights_note",
              "composite_caveat", "composite_caveat_figures"):
        assert k in g["score"]
    assert "trend_needed" in g["readiness"] and {"needed_more", "power_note"} <= set(g["trend"])
    pt = g["curve"][-1]
    assert set(pt) == {"i", "t_hour", "independence", "lo", "hi", "n", "level", "tiers"} and len(pt["tiers"]) == 5
    sk = g["by_skill"][0]
    for k in ("skill", "label", "name", "n", "independent", "assisted", "independence_lower", "mastery", "level", "direction", "first10", "last10", "time_to_progress",
              "retention", "retrieval_due"):
        assert k in sk, k
    assert g["origin_detail"] == "synthetic_learner" and g["_origin"] == "synthetic"
    assert g["by_skill"][0]["name"] and g["by_skill"][0]["label"]


def test_growth_for_one_skill_reads_only_that_skill():
    rows = SL.simulate_learner(SL.preset("improving"), np.random.default_rng(4), person="p_sim", n_per_skill=20)[0]
    g = S.growth(rows, person="p_sim", skill="check-the-cliff", n_boot=40)
    assert g["skill"] == "check-the-cliff" and g["readiness"]["occurrences"] == 20
    assert len(g["by_skill"]) == 3                               # the skill list is always all skills


def test_growth_is_deterministic_and_does_not_mutate_its_input():
    rows = SL.simulate_learner(SL.preset("improving"), np.random.default_rng(5), person="p_sim", n_per_skill=12)[0]
    before = copy.deepcopy(rows)
    a = S.growth(rows, person="p_sim", n_boot=60, now=T0 + 90 * 86400)
    b = S.growth(rows, person="p_sim", n_boot=60, now=T0 + 90 * 86400)
    assert a == b and rows == before


def test_summary_line_is_counts_only_and_cannot_be_read_as_a_skill_line():
    from understudy_engine.memory.doc import parse_skill_line

    rows = seq(["clean", "assisted"] * 6)
    line = S.summary_line(rows)
    assert parse_skill_line(line) is None
    assert "6 of the last 12" in line and all(not ch.isalpha() or True for ch in line)
    assert S.summary_line([dict(r, origin="synthetic") for r in rows]).startswith("Cue assist ledger: help was needed") and "generated" not in S.summary_line([dict(r, origin="synthetic") for r in rows])


def test_simulated_learners_are_labelled_synthetic_and_rows_validate():
    rows, truth = SL.simulate_learner(SL.preset("forgetting"), np.random.default_rng(1), person="p_sim", n_per_skill=10)
    assert len(rows) == len(truth.q) == 30
    assert {r["origin"] for r in rows} == {"synthetic"} and {r["origin_detail"] for r in rows} == {"synthetic_learner"}
    for r in rows:
        L.validate_row(r)
