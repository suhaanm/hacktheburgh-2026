"""deficit_recovery and null_placebo (EVL-1, ANA-2/3) on a private copy of the synthetic apprentices."""
from __future__ import annotations

import json
import math

import pytest
from understudy_engine.eval import deficit
from understudy_engine.eval.schema import errors

ORDER = ["skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter"]


@pytest.fixture(scope="module")
def result(apprentices_root):
    return deficit.compute(apprentices_root, fast=True)


@pytest.fixture(scope="module")
def truth(apprentices_root):
    return json.loads((apprentices_root / "synthetic" / "apprentices" / "truth.json").read_text())


def wrap(result):
    return {"generated_at": "2026-11-07T00:00:00Z", "mock": True,
            "sections": {"deficit_recovery": json.loads(json.dumps(result.deficit_recovery)), "null_placebo": json.loads(json.dumps(result.null_placebo))}}


def test_sections_match_the_contract_shape(result):
    rep = wrap(result)
    for sec in rep["sections"].values():
        sec["meta"]["generated_at"] = "2026-11-07T00:00:00Z"
    assert errors(rep) == []


def test_one_row_per_planted_deficit_in_a_fixed_order(result):
    assert [r["deficit"] for r in result.deficit_recovery["rows"]] == ORDER


def test_injected_price_is_the_planted_mean_from_truth_json(result, truth):
    """The injected side is read from truth.json, not estimated: it must equal the file's own mean price when present."""
    for r in result.deficit_recovery["rows"]:
        t = truth["deficit_totals"][r["deficit"]]
        assert r["injected_price_s"] == pytest.approx(t["mean_price_s_when_present"], abs=0.02)
        assert r["n_present"] == t["traces_with"]
        assert r["n_present"] + r["n_absent"] == 32


def test_recovered_price_tracks_the_planted_price_with_an_interval(result):
    for r in result.deficit_recovery["rows"]:
        lo, hi = r["ci"]
        assert lo <= r["recovered_price_s"] <= hi
        assert hi - lo > 0
        # the method is allowed to be off by tens of seconds for a deficit that shares steps with another, but not to lose the plot
        assert abs(r["bias_s"]) < 0.5 * r["injected_price_s"] + 10, r


def test_precision_and_recall_are_reported_with_intervals_and_are_high_overall(result):
    o = result.deficit_recovery["overall"]
    assert o["precision"] >= 0.8 and o["recall"] >= 0.8
    assert o["precision_ci"][0] <= o["precision"] <= o["precision_ci"][1]
    assert o["recall_ci"][0] <= o["recall"] <= o["recall_ci"][1]
    assert o["tp"] + o["fp"] + o["fn"] <= o["pairs"]
    # the pooled numbers are the sums of the per-deficit counts
    rows = result.deficit_recovery["rows"]
    assert sum(r["tp"] for r in rows) == o["tp"] and sum(r["fp"] for r in rows) == o["fp"] and sum(r["fn"] for r in rows) == o["fn"]
    for r in rows:
        assert r["tp"] + r["fn"] == r["n_present"]
        assert r["fp"] <= r["n_absent"]


def test_threshold_is_stated_and_never_below_one_second(result):
    assert "95th percentile" in result.deficit_recovery["detection_rule"]
    for r in result.deficit_recovery["rows"]:
        assert r["threshold_s"] >= deficit.MIN_X_S


def test_dashboard_aliases_equal_the_contract_keys(result):
    dr = result.deficit_recovery
    assert dr["precision"] == dr["overall"]["precision"] and dr["recall"] == dr["overall"]["recall"]
    for r in dr["rows"]:
        assert r["true_s"] == r["injected_price_s"] and r["est_s"] == r["recovered_price_s"]


def test_real_gap_is_large_and_both_controls_sit_below_it(result):
    n = result.null_placebo
    assert n["real"]["gap_s"] > 100 and n["real"]["ci"][0] > 0
    lo, hi = n["placebo"]["ci"]
    assert lo <= 0 <= hi or abs(n["placebo"]["gap_s"]) < 0.1 * n["real"]["gap_s"]
    # the real gap lies above the whole shuffled-label interval: the comparison that counts
    assert n["real"]["ci"][0] > n["null"]["ci"][1]
    assert n["null"]["p_value"] is not None and n["null"]["p_value"] < 0.05


def test_meta_says_synthetic_with_n_and_split(result):
    for sec in (result.deficit_recovery, result.null_placebo):
        m = sec["meta"]
        assert m["origin"] == "synthetic" and m["n"] > 0 and m["n_unit"] == "people" and "cluster bootstrap by person" in m["split"]
        assert m["interval_level"] == 0.95
    assert result.deficit_recovery["meta"]["n"] == 16 and result.null_placebo["meta"]["n"] == 24


def test_deterministic(apprentices_root, result):
    again = deficit.compute(apprentices_root, fast=True)
    assert json.dumps(again.deficit_recovery, sort_keys=True) == json.dumps(result.deficit_recovery, sort_keys=True)
    assert json.dumps(again.null_placebo, sort_keys=True) == json.dumps(result.null_placebo, sort_keys=True)


def test_full_mode_uses_more_resamples_and_keeps_the_point_estimates(apprentices_root, result):
    full = deficit.compute(apprentices_root, fast=False)
    assert full.deficit_recovery["bootstrap_draws"] > result.deficit_recovery["bootstrap_draws"]
    for a, b in zip(full.deficit_recovery["rows"], result.deficit_recovery["rows"]):
        assert a["recovered_price_s"] == b["recovered_price_s"] and a["precision"] == b["precision"]   # point estimates do not depend on B
    assert full.null_placebo["null"]["draws"] > result.null_placebo["null"]["draws"]


def test_missing_data_is_a_file_not_found_error_so_the_section_becomes_pending(tmp_path):
    with pytest.raises(FileNotFoundError):
        deficit.compute(tmp_path, fast=True)


def test_no_nan_in_output(result):
    s = json.dumps([result.deficit_recovery, result.null_placebo], allow_nan=False)
    assert "NaN" not in s and not math.isnan(result.deficit_recovery["overall"]["precision"])


# ---------------------------------------------------------------------------- the metric logic on a hand-made cohort
def _mini_cohort(extra_unplanted: bool = False, drop_planted: bool = False):
    """Experts all follow one sequence; novices are slower, and some carry one IDLE block of known length before ENTER_HOUSEHOLD."""
    from understudy_engine.core import Cog, Episode
    from understudy_engine.genome import Cohort

    base = [("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12)]

    def episode(tid, person, pairs):
        t, cogs = 0.0, []
        for c, d in pairs:
            cogs.append(Cog(t, t + d, c))
            t += d
        return Episode(tid, person, "benefits-processor", "synthetic", 0.0, t, cogs)

    eps, levels, traces = [], {}, []
    for i in range(4):
        eps.append(episode(f"t_e{i}", f"p_e{i}", [(c, d + i * 0.5) for c, d in base]))
        levels[f"p_e{i}"] = "expert"
    idle_len = {0: 60.0, 1: 45.0, 2: 0.0, 3: 0.0}
    for i in range(4):
        pairs = list(base)
        if idle_len[i]:
            pairs.insert(2, ("IDLE", idle_len[i]))
        planted = idle_len[i] if not (drop_planted and i == 0) else 0.0
        if extra_unplanted and i == 3:
            pairs.insert(2, ("IDLE", 30.0))       # a real extra pause that truth.json does not list: a false positive
        eps.append(episode(f"t_n{i}", f"p_n{i}", pairs))
        levels[f"p_n{i}"] = "novice"
        traces.append({"task_id": f"t_n{i}", "person": f"p_n{i}", "level": "novice",
                       "deficits": [{"type": "idle_before_enter", "instances": 1, "price_s": planted}] if planted else []})
    truth = {"traces": traces, "deficit_types": {"idle_before_enter": {}}}
    return Cohort(eps, levels), truth


def test_metric_logic_recovers_a_known_price_exactly_on_a_hand_made_cohort():
    co, truth = _mini_cohort()
    r = deficit.compute_from(co, truth, fast=True).deficit_recovery
    row = r["rows"][0]
    assert row["deficit"] == "idle_before_enter" and row["n_present"] == 2
    assert row["injected_price_s"] == pytest.approx(52.5) and row["recovered_price_s"] == pytest.approx(52.5)
    assert (row["tp"], row["fp"], row["fn"]) == (2, 0, 0) and row["precision"] == 1.0 and row["recall"] == 1.0


def test_an_unplanted_extra_pause_counts_as_a_false_positive_and_lowers_precision():
    co, truth = _mini_cohort(extra_unplanted=True)
    row = deficit.compute_from(co, truth, fast=True).deficit_recovery["rows"][0]
    assert row["fp"] == 1 and row["tp"] == 2 and row["precision"] == pytest.approx(2 / 3, abs=1e-3)


def test_a_planted_deficit_that_truth_does_not_list_is_not_counted_as_present_and_a_missed_one_is_a_false_negative():
    co, truth = _mini_cohort(drop_planted=True)         # truth says nothing planted on p_n0 although a 60 s pause is there
    row = deficit.compute_from(co, truth, fast=True).deficit_recovery["rows"][0]
    assert row["n_present"] == 1 and row["fp"] == 1
    # and the other direction: truth lists a deficit that the trace does not contain
    co, truth = _mini_cohort()
    truth["traces"][2]["deficits"] = [{"type": "idle_before_enter", "instances": 1, "price_s": 40.0}]
    row = deficit.compute_from(co, truth, fast=True).deficit_recovery["rows"][0]
    assert row["fn"] == 1 and row["recall"] == pytest.approx(2 / 3, abs=1e-3)


def test_placebo_is_zero_when_experts_are_alike_and_the_real_gap_is_positive():
    co, truth = _mini_cohort()
    n = deficit.compute_from(co, truth, fast=True).null_placebo
    assert abs(n["placebo"]["gap_s"]) < 5 and n["real"]["gap_s"] > 20
