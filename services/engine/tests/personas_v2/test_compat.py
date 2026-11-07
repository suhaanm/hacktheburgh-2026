"""Every existing analytic runs on v2 data unchanged (shapes, not results), and the harness helpers behave."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.personas_v2 import FAMILY_ORDER, generate_cohort, generate_workweeks
from understudy_engine.personas_v2 import eval_genome as EG
from understudy_engine.personas_v2 import eval_routines as ER
from understudy_engine.personas_v2.evalkit import boot_idx, interval, ratio_draws, verdict


@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_genome_entry_point_runs_on_a_v2_cohort(family):
    from understudy_engine.eval import deficit

    c = generate_cohort(family, "benefits-processor", n_people=16, cases_per_person=2, seed=61)
    res = deficit.compute_from(c.genome_cohort(), c.truth, fast=True)
    rows = res.deficit_recovery["rows"]
    assert {r["deficit"] for r in rows} == set(EG.DEFICITS)
    assert res.deficit_recovery["meta"]["origin"] == "synthetic"


@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_hazard_and_finder_run_on_v2_data(family):
    from understudy_engine.hazard import evaluate_hazard
    from understudy_engine.routines.finder import FinderConfig, find_routines

    w = generate_workweeks(family, "benefits-processor", n_people=6, n_days=7, seed=62)
    rep = evaluate_hazard(w.episodes(), n_boot=20, include_series=False, planted=w.planted_spells(), fast=True)
    assert rep["origin"] == "synthetic" and rep["n"] == 6 and rep["n_bins"] > 200
    person = w.people[0].id
    clusters = find_routines(w.episodes_of(person), FinderConfig())
    assert isinstance(clusters, list)


def test_verdict_follows_the_preregistered_rule():
    assert verdict(-0.05, [-0.08, -0.02], 0.01) == "degrades"
    assert verdict(0.003, [-0.01, 0.015], 0.01) == "transfers"
    assert verdict(-0.05, [-0.12, 0.02], 0.01) == "inconclusive"          # wide interval
    assert verdict(0.04, [0.02, 0.06], 0.01) == "inconclusive"            # better than the diagonal is not "transfers"
    assert verdict(0.2, [0.1, 0.3], 0.1, higher_is_better=False) == "degrades"
    assert verdict(float("nan"), [None, None], 0.01) == "inconclusive"


def test_cluster_bootstrap_is_paired_and_seeded():
    idx = boot_idx(10, 200, 5)
    assert (idx == boot_idx(10, 200, 5)).all() and idx.shape == (200, 10)
    num, den = np.arange(10, dtype=float), np.ones(10)
    d = ratio_draws(num, den, idx)
    lo, hi = interval(d)
    assert lo < 4.5 < hi


def test_routine_threshold_choice_prefers_the_shipped_value_on_ties():
    row = {"clusters": 4, "true": 2, "detectable": 2, "found": 1}
    best, f1 = ER.choose_threshold({0.25: [row], 0.35: [dict(row)], 0.45: [dict(row)]})
    assert best == 0.35 and len(set(f1.values())) == 1
    better = {"clusters": 4, "true": 4, "detectable": 2, "found": 2}
    assert ER.choose_threshold({0.25: [row], 0.35: [row], 0.45: [better]})[0] == 0.45


def test_truth_index_marks_material_pairs():
    truth = {"traces": [{"task_id": "t_a", "deficits": [{"type": "search_loop", "instances": 1, "price_s": 40.0, "material": True},
                                                          {"type": "copy_error", "instances": 1, "price_s": 1.0, "material": False}]}]}
    idx = EG.truth_index(truth)
    assert idx["t_a"]["search_loop"]["material"] and not idx["t_a"]["copy_error"]["material"]


def test_evaluate_realism_fast_has_the_section_shape(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_REALISM_WORKERS", "2")
    from understudy_engine.personas_v2.evaluate import evaluate_realism

    sec = evaluate_realism(fast=True)
    assert sec["name"] == "realism" and sec["badge"] == "synthetic, realism-calibrated" and sec["meta"]["origin"] == "synthetic"
    assert sec["meta"]["interval_level"] == 0.95 and "n" in sec["meta"] and sec["limitations"]
    assert set(sec["results"]) >= {"hazard", "genome", "routines", "marginals", "elapsed_s"}
    cells = sec["results"]["hazard"]["benefits-processor"]["cells"]
    assert len(cells) == 9 and "markov->process_trace" in cells
    assert all(set(c["metrics"]["h1"]) == {"est", "ci"} for c in cells.values())
    assert sec["generator"]["params_sha256"] and sec["generator"]["generator_sha256"]
    assert sec["rows"] and sec["caveats"]
