from __future__ import annotations

import json
import statistics
import warnings

import numpy as np
import pytest

from understudy_engine.cogs import segment_episodes
from understudy_engine.core import Cog, Episode
from understudy_engine.genome import (
    DEFAULT_COST, Cohort, CostModel, GenomeError, GenomeService, align, components, consensus, decompose,
    deficit_prices, diff, label_columns, planted_missing_edges, transition_graph,
)
from understudy_engine.genome.decompose import _ob_point
from understudy_engine.personas import apprentices
from understudy_engine.store import EventStore


def seq(*pairs, t0=0.0):
    out, t = [], t0
    for cog, d in pairs:
        out.append(Cog(t, t + d, cog))
        t += d
    return out


def ep(task_id, person, cogs):
    return Episode(task_id, person, "benefits-processor", "synthetic", cogs[0].t0, cogs[-1].t1, cogs)


EXPERT = seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12))


# ------------------------------------------------------------------ alignment
def test_identical_sequences_align_with_zero_gap():
    al = align(EXPERT, EXPERT)
    assert [c.op for c in al.columns] == ["match"] * 7 and al.unit_cost == 0 and al.gap_s == 0
    assert all(c.seconds == 0 for c in al.columns)


def test_slower_novice_is_priced_as_dwell_differences():
    slow = [Cog(c.t0, c.t0 + c.dwell * 1.5, c.id) for c in EXPERT]
    al = align(EXPERT, seq(*[(c.id, c.dwell * 1.5) for c in EXPERT]))
    assert all(c.op == "match" for c in al.columns)
    assert al.gap_s == pytest.approx(sum(c.dwell for c in EXPERT) * 0.5)
    assert sum(c.seconds for c in al.columns) == pytest.approx(al.gap_s)
    del slow


def test_extra_step_is_gap_expert_with_positive_seconds_and_skipped_step_is_gap_novice_negative():
    extra = seq(*[(c.id, c.dwell) for c in EXPERT[:4]], ("READ_RESULT", 9), *[(c.id, c.dwell) for c in EXPERT[4:]])
    al = align(EXPERT, extra)
    gaps = [c for c in al.columns if c.op != "match"]
    assert len(gaps) == 1 and gaps[0].op == "gap_expert" and gaps[0].i is None and gaps[0].j is not None
    assert gaps[0].seconds == pytest.approx(9.0) and al.gap_s == pytest.approx(9.0)
    skipped = seq(*[(c.id, c.dwell) for c in EXPERT if c.id != "CHECK_CLIFF"])
    al = align(EXPERT, skipped)
    gaps = [c for c in al.columns if c.op != "match"]
    assert len(gaps) == 1 and gaps[0].op == "gap_novice" and gaps[0].j is None and gaps[0].cog_expert == "CHECK_CLIFF"
    assert gaps[0].seconds == pytest.approx(-25.0) and al.gap_s == pytest.approx(-25.0)


def test_column_seconds_always_sum_to_total_gap():
    rng = np.random.default_rng(7)
    ids = ["READ", "ENTER", "SEARCH", "CHECK", "COPY", "IDLE", "REVERT", "READ_RESULT"]
    for _ in range(40):
        a = seq(*[(str(rng.choice(ids)), float(rng.uniform(2, 30))) for _ in range(rng.integers(3, 12))])
        b = seq(*[(str(rng.choice(ids)), float(rng.uniform(2, 30))) for _ in range(rng.integers(3, 12))])
        al = align(a, b)
        assert sum(c.seconds for c in al.columns) == pytest.approx(al.gap_s)
        assert [c.i for c in al.columns if c.i is not None] == list(range(len(a)))
        assert [c.j for c in al.columns if c.j is not None] == list(range(len(b)))


def test_cost_model_same_family_cheaper_unrelated_costs_two_gaps():
    cm = DEFAULT_COST
    assert cm.mismatch("READ", "READ") == 0 and cm.mismatch("READ", "READ_RESULT") == 0.5
    assert cm.mismatch("READ", "REVERT") > 2 * cm.gap
    # unrelated cogs are never aligned as a mismatch: one gap each side instead
    al = align(seq(("READ", 5), ("REVERT", 3)), seq(("READ", 5), ("IDLE", 3)))
    assert sorted(c.op for c in al.columns) == ["gap_expert", "gap_novice", "match"]
    custom = CostModel(unrelated=1.0)
    al = align(seq(("READ", 5), ("REVERT", 3)), seq(("READ", 5), ("IDLE", 3)), custom)
    assert sorted(c.op for c in al.columns) == ["match", "mismatch"]


def test_extras_stay_one_contiguous_block():
    nov = seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20),
              ("COPY_TO_NOTE", 12), ("RECONCILE", 20), ("REVERT", 3), ("COPY_TO_NOTE", 12))
    al = align(EXPERT, nov)
    ops = [c.op for c in al.columns]
    first = ops.index("gap_expert")
    assert ops[first:first + 3] == ["gap_expert"] * 3 and ops.count("gap_expert") == 3
    comp = components(al)
    assert comp["Wrong figure, copied again"] == pytest.approx(35.0)


# ------------------------------------------------------------ planted gaps
PLANTS = {
    "idle_before_enter": (lambda: seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("IDLE", 50), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12)), 50.0),
    "search_loop": (lambda: seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("SEARCH", 9), ("READ", 8), ("REFORMULATE", 8), ("READ", 7), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12)), 32.0),
    "repeated_read_result": (lambda: seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("READ_RESULT", 9), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12)), 9.0),
    "copy_error": (lambda: seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("CHECK_CLIFF", 25), ("RECONCILE", 20), ("COPY_TO_NOTE", 12), ("RECONCILE", 16), ("REVERT", 3), ("COPY_TO_NOTE", 12)), 31.0),
    "skipped_check_cliff": (lambda: seq(("READ", 10), ("OPEN_CALCULATOR", 5), ("ENTER_HOUSEHOLD", 40), ("READ_RESULT", 15), ("RECONCILE", 20), ("REVERT", 3), ("ENTER_HOUSEHOLD", 28), ("CHECK_CLIFF", 25), ("READ_RESULT", 14), ("COPY_TO_NOTE", 12)), 3 + 28 + 14),
}


@pytest.mark.parametrize("name", list(PLANTS))
def test_planted_gap_is_recovered_with_its_price(name):
    make, price = PLANTS[name]
    al = align(EXPERT, make())
    rec = deficit_prices(components(al))
    assert set(rec) == {name}, (name, components(al))
    assert rec[name] == pytest.approx(price, abs=0.01)
    assert al.gap_s == pytest.approx(sum(components(al).values()))


def test_labels_cover_every_column():
    al = align(EXPERT, PLANTS["search_loop"][0]())
    labels = label_columns(al)
    assert len(labels) == len(al.columns) and set(labels) == {"Slower on shared steps", "Search loops"}


# -------------------------------------------------- recovery on the apprentices
@pytest.fixture(scope="module")
def cohort_data(tmp_path_factory):
    root = tmp_path_factory.mktemp("genome")
    apprentices.generate(root)
    store = EventStore(root)
    truth = json.loads((root / "synthetic" / "apprentices" / "truth.json").read_text())
    levels = {p["person"]: p["level"] for p in truth["people"]}
    eps = segment_episodes([e for e in store.read("synthetic") if e.person in levels])
    return store, truth, levels, eps


def test_apprentice_deficits_detected_and_priced(cohort_data):
    _, truth, levels, eps = cohort_data
    co = Cohort(eps, levels)
    planted = {t["task_id"]: {d["type"]: d["price_s"] for d in t["deficits"] if d["instances"]} for t in truth["traces"]}
    tp = fp = fn = 0
    errs = []
    for ep_, _, al in co.novice_alignments():
        rec = deficit_prices(components(al))
        for d in ("skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter"):
            pred, act = rec.get(d, 0.0) > 10.0, d in planted[ep_.task_id]
            tp += pred and act
            fp += pred and not act
            fn += (not pred) and act
            if act and pred:
                errs.append(abs(rec[d] - planted[ep_.task_id][d]))
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    assert precision >= 0.85 and recall >= 0.85, (precision, recall)
    assert statistics.median(errs) < 12.0


def test_real_gap_is_large_and_controls_are_near_zero(cohort_data):
    _, truth, levels, eps = cohort_data
    co = Cohort(eps, levels)
    real = co.real_gap()
    placebo = co.placebo()
    null = co.null(B=150, observed=real["gap_s"])
    assert real["gap_s"] > 150 and real["ci"][0] > 100
    # placebo: expert against expert, near zero, interval around zero
    assert abs(placebo["gap_s"]) < 0.1 * real["gap_s"] and placebo["ci"][0] < 5 < placebo["ci"][1] + 20
    assert placebo["ci"][0] <= 0.0 <= placebo["ci"][1] or abs(placebo["gap_s"]) < 15
    # null: shuffled labels, the interval covers zero and excludes the real gap
    assert null["ci"][0] < 0 < null["ci"][1] and real["gap_s"] > null["ci"][1] and null["p_value"] < 0.05
    assert abs(null["gap_s"]) < 0.4 * real["gap_s"]


def test_waterfall_bars_sum_to_the_total_and_carry_intervals(cohort_data):
    _, _, levels, eps = cohort_data
    wf = Cohort(eps, levels).waterfall(B=200)
    assert wf["total_gap_s"] == pytest.approx(sum(r["seconds"] for r in wf["rows"]), abs=0.01)
    for r in wf["rows"]:
        assert r["ci"][0] <= r["seconds"] <= r["ci"][1]
    labels = {r["label"] for r in wf["rows"]}
    assert {"Slower on shared steps", "Long pauses", "Search loops", "Repeated reads", "Missed check, redone"} <= labels


def test_nearest_expert_never_the_same_person_and_consensus_is_sane(cohort_data):
    _, _, levels, eps = cohort_data
    co = Cohort(eps, levels)
    for e in co.experts:
        ref, _ = co.nearest(e)
        assert ref.person != e.person and levels[ref.person] == "expert"
    cons = consensus(co.experts)
    ids = [c.id for c in cons]
    assert ids[0] == "READ" and ids[-2:] == ["RECONCILE", "COPY_TO_NOTE"] and ids.count("OPEN_CALCULATOR") == 3 and ids.count("CHECK_CLIFF") == 3
    assert cons[0].t0 == 0 and all(a.t1 == pytest.approx(b.t0) for a, b in zip(cons, cons[1:]))


def test_transition_graph_flags_edges_broken_by_planted_deficits(cohort_data):
    _, truth, levels, eps = cohort_data
    co = Cohort(eps, levels)
    g = transition_graph(co.experts, co.novices)
    assert {n["cog"] for n in g["nodes"]} >= {"READ_RESULT", "CHECK_CLIFF", "IDLE", "REVERT"}
    missing = {(e["from"], e["to"]) for e in g["edges"] if e["missing_for_novice"]}
    assert missing == set(diff(co.experts, co.novices))
    planted = planted_missing_edges(truth)
    assert missing and missing <= planted                      # every highlight is explained by a planted deficit
    assert ("READ_RESULT", "CHECK_CLIFF") in missing
    extra = {(e["from"], e["to"]) for e in g["edges"] if e["extra_for_novice"]}
    assert ("RECONCILE", "REVERT") in extra and ("IDLE", "ENTER_HOUSEHOLD") in extra


def test_decomposition_matches_statsmodels_on_a_well_conditioned_toy():
    from statsmodels.stats.oaxaca import OaxacaBlinder

    rng = np.random.default_rng(0)
    n = 80
    g = np.r_[np.zeros(40), np.ones(40)]
    X = np.column_stack([rng.normal(size=n) + g, rng.poisson(1 + 2 * g, size=n).astype(float)])
    y = 10 + 3 * X[:, 0] + 5 * X[:, 1] + 4 * g + rng.normal(size=n)
    gap, expl_k, unexpl = _ob_point(y, X, g)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        u, e, gp = OaxacaBlinder(y, np.column_stack([X, g]), 2, hasconst=False).two_fold().params
    assert gap == pytest.approx(gp) and expl_k.sum() == pytest.approx(e, rel=1e-6) and unexpl == pytest.approx(u, rel=1e-6)


def test_decompose_on_apprentices_has_intervals_and_adds_up(cohort_data):
    _, _, levels, eps = cohort_data
    d = decompose(eps, levels, B=150)
    assert d["gap_s"] == pytest.approx(d["explained_s"] + d["unexplained_s"], abs=0.01)
    assert d["gap_ci"][0] < d["gap_s"] < d["gap_ci"][1] and d["unexplained_ci"][0] < d["unexplained_s"] < d["unexplained_ci"][1]
    assert sum(c["seconds"] for c in d["components"]) == pytest.approx(d["explained_s"], abs=0.01)
    assert d["gap_s"] > 150 and d["n_experts"] == 8 and d["n_novices"] == 16


def test_service_genome_shape_and_errors(cohort_data):
    store, truth, levels, _ = cohort_data
    svc = GenomeService(store)
    data, meta = svc.genome("benefits-household-entry", person="p_nov04")
    assert meta.origin == "synthetic" and meta.n == 24 and meta.n_unit == "people" and meta.split
    for key in ("task", "person", "expert_person", "expert", "novice", "alignment", "waterfall", "total_gap_s", "total_gap_ci", "controls"):
        assert key in data
    assert data["person"] == "p_nov04" and data["expert_person"].startswith("p_exp")
    assert set(data["controls"]) == {"placebo", "null"} and {"gap_s", "ci"} <= set(data["controls"]["placebo"])
    for row in data["alignment"]:
        assert row["op"] in ("match", "mismatch", "gap_expert", "gap_novice")
        assert (row["i"] is None) == (row["op"] == "gap_expert") and (row["j"] is None) == (row["op"] == "gap_novice")
    assert data["expert"]["segments"][0] == {"cog": "READ", "t0": 0.0, "t1": pytest.approx(data["expert"]["segments"][0]["t1"])}
    cons, _ = svc.genome("benefits", person="p_nov04", reference="consensus")
    assert cons["expert_person"] is None and cons["reference"] == "consensus"
    default, _ = svc.genome("benefits-household-entry")
    assert default["person"].startswith("p_nov")
    with pytest.raises(GenomeError) as e:
        svc.genome("nope")
    assert e.value.code == "unknown_task"
    with pytest.raises(GenomeError) as e:
        svc.genome("benefits", person="p_exp01")
    assert e.value.code == "not_a_novice"
    g, meta = svc.transitions("benefits")
    assert g["nodes"] and any(x["planted"] for x in g["edges"] if x["missing_for_novice"])


def test_service_without_data_gives_a_clear_error(tmp_path):
    with pytest.raises(GenomeError) as e:
        GenomeService(EventStore(tmp_path)).genome("benefits")
    assert e.value.code == "no_cohort" and "synth" in e.value.message
