import numpy as np
import pytest

from understudy_engine.core import Cog, Episode
from understudy_engine.genome.align import DEFAULT_COST, align
from understudy_engine.genome.labels import LABEL_ORDER, components
from understudy_engine.mlv2 import apprentice_pool as AP
from understudy_engine.mlv2 import envelope as EV
from understudy_engine.mlv2 import counterfactual as CF
from understudy_engine.mlv2 import variants as VR


def _ep(seq, person="p_a", tid="t1"):
    t = 0.0
    cogs = []
    for cid, d in seq:
        cogs.append(Cog(t, t + d, cid))
        t += d
    return Episode(task_id=tid, person=person, role="r", origin="synthetic", t0=0.0, t1=t, cogs=cogs, progress_t=[])


def test_registry_counts_match_the_plan():
    c = VR.count_tested()
    assert c == {"A": 7, "C": 2, "E": 4, "Q": 2, "total": 15}
    assert VR.ids("E", "reference") == ["E0"]


def test_learned_cost_lookup_and_fallback():
    lc = EV.LearnedCost(table=(("CHECK_CLIFF", "RECONCILE", 2.0),))
    assert lc.mismatch("RECONCILE", "CHECK_CLIFF") == 2.0 and lc.mismatch("CHECK_CLIFF", "CHECK_CLIFF") == 0.0
    assert lc.mismatch("READ", "READ_RESULT") == 0.5            # not in the table: the hand-set family cost
    assert lc.mismatch("READ", "ENTER") == 2.5
    assert hash(lc) == hash(EV.LearnedCost(table=(("CHECK_CLIFF", "RECONCILE", 2.0),)))     # hashable so v1's alignment cache works


def test_learned_costs_stay_in_range_and_pull_toward_the_hand_set_matrix(apprentice_d0):
    lc, info = EV.learn_costs(apprentice_d0.cohort.experts)
    for a, b, c in lc.table:
        assert EV.COST_MIN <= c <= EV.COST_MAX
        assert a < b
        # regularised: never further from the hand-set cost than the learned value is
        h = info["pairs"][f"{a}|{b}"]
        lo, hi = sorted((h["hand"], h["learned"]))
        assert lo - 1e-3 <= c <= hi + 1e-3
    assert info["n_expert_pairs"] > 50


def test_sampled_alignments_are_valid_and_cover_both_sequences_once():
    ex = _ep([("READ", 5), ("ENTER", 8), ("CHECK", 4)])
    nv = _ep([("READ", 6), ("READ", 5), ("ENTER", 9), ("CHECK", 5)])
    rng = np.random.default_rng(0)
    als = EV.sample_alignments(ex.cogs, nv.cogs, DEFAULT_COST, n=200, tau=EV.TAU, rng=rng)
    for al in als:
        i_seen = [c.i for c in al.columns if c.i is not None]
        j_seen = [c.j for c in al.columns if c.j is not None]
        assert i_seen == list(range(len(ex.cogs))) and j_seen == list(range(len(nv.cogs)))
        assert abs(sum(c.seconds for c in al.columns) - al.gap_s) < 1e-9          # columns account for the whole gap


def test_sampling_splits_a_tie_and_collapses_to_the_optimum_at_low_temperature():
    ex = _ep([("READ", 5), ("ENTER", 8)])
    nv = _ep([("READ", 5), ("READ", 5), ("ENTER", 8)])          # which READ is the extra one is a tie
    rng = np.random.default_rng(1)
    hot = EV.sample_alignments(ex.cogs, nv.cogs, DEFAULT_COST, n=1500, tau=1.0, rng=rng)
    extra_first = np.mean([next(c.j for c in al.columns if c.op == "gap_expert") == 0 for al in hot if sum(c.op == "gap_expert" for c in al.columns) == 1])
    assert 0.3 < extra_first < 0.7                                # a near coin flip: the alignment genuinely cannot tell
    cold = EV.sample_alignments(ex.cogs, nv.cogs, DEFAULT_COST, n=300, tau=0.02, rng=rng)
    assert all(sum(c.op == "gap_expert" for c in al.columns) == 1 for al in cold)


def test_e0_reproduces_v1_recovered_prices_exactly(apprentice_d0):
    from understudy_engine.eval.deficit import compute_from

    co, truth = apprentice_d0.cohort, apprentice_d0.truth
    v1 = {r["deficit"]: r["recovered_price_s"] for r in compute_from(co, truth, fast=True).deficit_recovery["rows"]}
    from understudy_engine.mlv2.genome_stats import run_variant

    r = run_variant([apprentice_d0], "E0", n_boot=20)
    for d, want in v1.items():
        sel = np.array([x == d for x in r.deficit]) & r.present
        assert abs(float(r.point[sel].mean()) - want) < 0.01, d


def test_unscaled_splice_equals_v1_attribution_and_scaling_only_touches_skips_and_substitutions(apprentice_d0):
    co = apprentice_d0.cohort
    ep = co.novices[0]
    ref, al = co.nearest(ep)
    comp = components(al)
    v1 = np.array([comp.get(l, 0.0) for l in LABEL_ORDER])
    assert np.allclose(CF.splice_seconds(al, ref, ep, scaled=False), v1)
    scaled = CF.splice_seconds(al, ref, ep, scaled=True)
    assert scaled.shape == v1.shape and CF.pace_ratio(al, ref, ep) > 0.5
    # the total recovered seconds under unscaled pricing is exactly the novice-minus-expert gap
    assert abs(CF.splice_seconds(al, ref, ep, scaled=False).sum() - al.gap_s) < 1e-6


def test_shapley_is_efficient_and_symmetric_and_additive_games_give_the_parts():
    hab = ["a", "b", "c"]
    add = {"a": 3.0, "b": 5.0, "c": 7.0}
    phi = CF.shapley_values(hab, CF.splice_value_function(add))
    assert all(abs(phi[h] - add[h]) < 1e-9 for h in hab)
    inter = lambda S: sum(add[h] for h in S) + (4.0 if {"a", "b"} <= set(S) else 0.0)
    phi = CF.shapley_values(hab, inter)
    assert abs(sum(phi.values()) - inter(frozenset(hab))) < 1e-9          # efficiency
    assert abs(phi["a"] - 5.0) < 1e-9 and abs(phi["b"] - 7.0) < 1e-9 and abs(phi["c"] - 7.0) < 1e-9
    with pytest.raises(ValueError):
        CF.shapley_values([str(i) for i in range(11)], lambda S: 0.0)


def test_stress_test_shows_double_counting_and_a_fitted_shapley_that_recovers_the_truth():
    st = CF.stress_test_interaction(n_cases=600, seed=1)
    assert st.single_replay_sum > st.total_true + 1.0
    assert abs(sum(st.fitted_shapley.values()) - st.total_true) < 8.0
    for h in st.habits:
        assert abs(st.fitted_shapley[h] - st.true_shapley[h]) < 6.0


def test_apprentice_pools_use_the_registered_seeds_and_lock_the_held_out_pool(monkeypatch):
    assert [s for s, _ in AP.pool_seeds("APP-D0")] == [8808]
    assert [s for s, _ in AP.pool_seeds("APP-DEV")] == [8808, 8818, 8828, 8838]
    assert [s for s, _ in AP.pool_seeds("APP-HELD")] == [8808 + 1000 * r for r in range(1, 7)]
    monkeypatch.delenv("UNDERSTUDY_MLV2_HELDOUT", raising=False)
    from understudy_engine.mlv2.splits import HeldOutLocked
    with pytest.raises(HeldOutLocked):
        AP.load_pool("APP-HELD")
