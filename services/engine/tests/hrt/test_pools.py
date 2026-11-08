"""Seeds and worlds: every seed is new and distinct (PLAN.md section 2); the routing drift world equals the original generator until it drifts; the
stuck-hazard features are causal (no leakage by construction)."""
from __future__ import annotations


import numpy as np

from understudy_engine.hrt import worlds as w


def test_every_seed_is_disjoint_from_earlier_evaluations_and_from_each_other():
    pools = w.all_seeds()
    flat = [s for v in pools.values() for s in v]
    assert len(flat) == len(set(flat)), "two HRT pools share a seed"
    used = w.known_used_seeds()
    clash = sorted(set(flat) & used)
    assert not clash, f"HRT seeds that an earlier evaluation used: {clash[:10]}"
    # the real mlv2 seed lists, recomputed from its own code, are covered by known_used_seeds
    from understudy_engine.mlv2 import splits

    mlv2 = {splits.replicate_seed(b, kind, r) for b in splits.BASE_SEEDS.values() for kind, rs in (("d", splits.DEV_REPLICATES), ("h", splits.HELD_REPLICATES), ("x", splits.RESERVE_REPLICATES)) for r in rs}
    assert mlv2 <= used and not (mlv2 & set(flat))


def test_pool_shapes_match_the_plan():
    p = w.all_seeds()
    assert len(p["v1_train"]) == 16 and len(p["v1_dev"]) == 8 and len(p["v1_held"]) == 32
    assert len(p["v2_held"]) == 24 and len(p["v2_dev"]) == 6
    assert len(p["route"]) == 11
    assert w.HELD_K == tuple(range(11, 19)) and len(w.HELD_K) == 8


def test_v1_persona_replicate_is_deterministic_and_has_distinct_people():
    a = w.v1_persona_episodes("nine-to-five", 5)
    b = w.v1_persona_episodes("nine-to-five", 5)
    assert [e.task_id for e in a][:20] == [e.task_id for e in b][:20] and len(a) == len(b) > 100
    other = w.v1_persona_episodes("nine-to-five", 6)
    assert {e.person for e in a}.isdisjoint({e.person for e in other})
    assert all(e.person.startswith("p_") for e in a)


def test_routing_drift_world_equals_the_original_generator_until_it_drifts():
    from understudy_engine.routing.cases import simulate_cases

    orig = simulate_cases(600, 7_200_313 + 1)
    same = w.simulate_cases_stream(600, 7_200_313 + 1, drift_at=None)
    assert np.array_equal(orig.X, same.X) and np.array_equal(orig.y, same.y)
    drift = w.simulate_cases_stream(600, 7_200_313 + 1, drift_at=300)
    # before the drift the draws are identical, after it the error probability is higher
    assert np.array_equal(drift.p_true[:300], orig.p_true[:300])
    assert np.all(drift.p_true[300:] > orig.p_true[300:])
    assert drift.p_true[300:].mean() > orig.p_true[300:].mean() + 0.05


def test_stuck_hazard_features_are_causal_truncating_the_future_changes_nothing():
    """For a bin at time b, rebuild the episode from only what had happened by b: the features must be identical."""
    from understudy_engine.core import Episode
    from understudy_engine.hazard.features import HORIZON_S, build_bins
    from understudy_engine.hazard.sim import simulate_people

    eps, _ = simulate_people(3, 20, seed=12)
    checked = 0
    for ep in eps[:30]:
        full = build_bins([ep])
        for k in range(0, full.n, 3):
            b = float(full.t[k])
            cogs = [c for c in ep.cogs if c.t0 <= b]
            if not cogs:
                continue
            cut = Episode(task_id=ep.task_id, person=ep.person, role=ep.role, origin=ep.origin, t0=ep.t0, t1=b + HORIZON_S, cogs=cogs,
                          progress_t=[t for t in ep.progress_t if t <= b])
            part = build_bins([cut])
            j = part.n - 1
            assert np.isclose(part.t[j], b)
            assert np.allclose(part.dense[j], full.dense[k]) and np.array_equal(part.hashed[j], full.hashed[k]) and np.isclose(part.tsp_s[j], full.tsp_s[k])
            checked += 1
    assert checked >= 60
