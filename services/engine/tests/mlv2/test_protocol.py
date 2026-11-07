import numpy as np

from understudy_engine.hazard.evaluate import evaluate_hazard
from understudy_engine.mlv2 import protocol as P
from understudy_engine.mlv2.alarms import build_layout
from understudy_engine.mlv2.family_a import choose_a7, choose_primary, compare_family_a, run_family_a
from understudy_engine.mlv2.models import FAMILY_A, LEARNERS


def test_inner_assignments_are_leave_one_out_for_small_training_sets_and_grouped_otherwise():
    g = P.inner_assignments(["b", "a", "c"], 5)
    assert g == [["a"], ["b"], ["c"]]
    people = [f"p{i:02d}" for i in range(20)]
    g = P.inner_assignments(people, 5)
    assert len(g) == 5 and sorted(sum(g, [])) == people and all(len(x) == 4 for x in g)
    assert P.inner_assignments(people, None) == [[q] for q in people]


def test_a0_reproduces_v1_exactly(sim_episodes, sim_tab):
    tab = sim_tab
    v1 = evaluate_hazard(sim_episodes, n_boot=10, include_series=False)
    folds = P.make_folds(tab)
    base = P.fit_base_oof(tab, LEARNERS["L"], folds=folds)
    out = P.apply_variant(tab, base, FAMILY_A["A0"], layout=build_layout(tab), folds=folds)
    r = P.reproduces_v1(tab, v1, out)
    assert r["ok"], r


def test_family_a_runs_and_comparison_has_the_registered_structure(sim_tab):
    variants = {k: FAMILY_A[k] for k in ("A0", "A1", "A3", "A6")}
    run = run_family_a(sim_tab, variants=variants, include_baselines=True, inner_folds=3)
    cmp = compare_family_a(run, primary="A3", n_boot=200, candidates=["A1", "A3", "A6"])
    assert cmp["rows"]["A0"]["verdict"] == "reference"
    assert cmp["rows"]["A3"]["level"] == 0.95 and cmp["rows"]["A1"]["level"] < 0.99 and cmp["rows"]["A1"]["level"] > 0.97
    assert cmp["m_candidates"] == 3
    for vid in ("A1", "A3", "A6", "TSP", "BASE"):
        row = cmp["rows"][vid]
        assert set(row["guards"]) >= {"brier", "ece", "auc", "detection"}
        assert row["verdict"] in ("accepted", "null", "harmful")
    # the base-rate baseline is worse than the model with an interval that excludes zero (sanity for the harness)
    assert cmp["rows"]["BASE"]["paired_vs_ref"]["log_loss"]["interval"][0] > 0
    assert choose_primary(cmp, ["A1", "A3", "A6"]) in (None, "A1", "A3", "A6")


def test_shuffled_label_control_no_model_beats_base_rate(sim_tab):
    from understudy_engine.mlv2.controls import LL_TOL, shuffle_labels
    from understudy_engine.trust.calibration import log_loss

    tab = shuffle_labels(sim_tab, 5)
    variants = {k: FAMILY_A[k] for k in ("A0", "A1", "A3", "A6")}
    run = run_family_a(tab, variants=variants, include_baselines=True, inner_folds=3)
    y = tab.y.astype(float)
    base = log_loss(y, run.outputs["BASE"].p)
    for vid in ("A0", "A1", "A3", "A6"):
        assert base - log_loss(y, run.outputs[vid].p) < LL_TOL, vid
