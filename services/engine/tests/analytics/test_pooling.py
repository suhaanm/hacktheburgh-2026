import json

import numpy as np
import pytest

from understudy_engine.hazard import pooling as P
from understudy_engine.store import data_dir


def test_beta_prior_is_recovered_from_heterogeneous_people():
    rng = np.random.default_rng(0)
    a, b = 2.0, 6.0                                     # mean 0.25, concentration 8
    theta = rng.beta(a, b, 400)
    n = rng.integers(10, 60, 400)
    s = rng.binomial(n, theta)
    ah, bh = P.fit_beta_prior(s, n)
    assert ah / (ah + bh) == pytest.approx(0.25, abs=0.02)
    assert (ah + bh) == pytest.approx(8.0, rel=0.3)


def test_no_between_person_spread_means_complete_pooling():
    rng = np.random.default_rng(1)
    n = rng.integers(40, 80, 30)
    s = rng.binomial(n, 0.3)                            # everyone has the SAME rate
    a, b = P.fit_beta_prior(s, n)
    assert a + b > 500                                  # concentration runs high: shrink hard toward the role rate


def test_a_single_or_empty_group_does_not_blow_up():
    a, b = P.fit_beta_prior(np.array([3.0]), np.array([10.0]))
    assert a > 0 and b > 0 and a + b <= 4.0 + 1e-9
    assert P.fit_beta_prior(np.array([]), np.array([])) == (1.0, 1.0)
    assert P.fit_beta_prior(np.array([0.0, 0.0]), np.array([0.0, 0.0])) == (1.0, 1.0)   # nobody has any trials


def test_estimators_by_hand():
    prior = (3.0, 9.0)                                  # mean 0.25, weight 12
    assert P.estimate("no_pooling", 0, 0, prior, 0.2) == pytest.approx(0.5)
    assert P.estimate("no_pooling", 3, 10, prior, 0.2) == pytest.approx(3.5 / 11)
    assert P.estimate("complete_pooling", 3, 10, prior, 0.2) == pytest.approx(0.2)
    assert P.estimate("partial_pooling", 0, 0, prior, 0.2) == pytest.approx(0.25)           # no data: the role prior
    assert P.estimate("partial_pooling", 6, 12, prior, 0.2) == pytest.approx(9 / 24)         # own weight 12 / (12 + 12)
    assert P.estimate("partial_pooling", 6000, 12000, prior, 0.2) == pytest.approx(0.5, abs=0.001)   # data dominate
    with pytest.raises(ValueError):
        P.estimate("mystery", 1, 2, prior, 0.2)


def make_people(n_people=40, n_eps=14, kappa=8.0, mean=0.25, seed=0):
    rng = np.random.default_rng(seed)
    people = {}
    for i in range(n_people):
        th = rng.beta(mean * kappa, (1 - mean) * kappa)
        people[f"p{i:02d}"] = [P.Unit(np.array([float(rng.binomial(8, th))]), np.array([8.0])) for _ in range(n_eps)]
    return people


def test_partial_pooling_beats_both_extremes_when_people_differ_moderately():
    r = P._pooling_rows(make_people(), (0, 1, 3), n_boot=100, seed=0)
    row = {x["n_episodes"]: x for x in r["rows"]}
    # no data: partial = complete, both far better than a coin flip
    assert row[0]["partial_pooling"] == pytest.approx(row[0]["complete_pooling"], abs=0.01)
    assert row[0]["no_pooling_minus_partial"]["ci"][0] > 0
    # a few episodes: partial pooling beats ignoring the person AND ignoring the role
    for k in (1, 3):
        assert row[k]["partial_pooling"] < row[k]["no_pooling"]
        assert row[k]["partial_pooling"] < row[k]["complete_pooling"]
    assert row[3]["complete_pooling_minus_partial"]["ci"][0] > 0
    assert row[3]["own_weight_partial"] > row[1]["own_weight_partial"] > row[0]["own_weight_partial"] == 0.0
    assert all(x["best"] == "partial_pooling" for x in r["rows"] if x["n_episodes"] >= 1)


def test_role_prior_never_contains_the_held_out_person(monkeypatch):
    people = {f"p{i}": [P.Unit(np.array([float(i)]), np.array([10.0])) for _ in range(4)] for i in range(6)}
    seen = []
    orig = P.fit_beta_prior

    def spy(s, n):
        seen.append(sorted(np.asarray(s).tolist()))
        return orig(s, n)

    monkeypatch.setattr(P, "fit_beta_prior", spy)
    P._pooling_rows(people, (0, 1), n_boot=10, seed=0)
    totals = {float(4 * i) for i in range(6)}            # each person's total successes
    assert len(seen) == 6
    assert all(len(s) == 5 for s in seen)
    # for each fold exactly one person's total is missing from the prior's data
    assert {tuple(sorted(totals - set(s))) for s in seen} == {(t,) for t in totals}


def test_rows_use_one_common_test_set_and_are_deterministic():
    people = make_people(20, 8)
    a = P._pooling_rows(people, (0, 1, 3), n_boot=50, seed=1)
    b = P._pooling_rows(people, (0, 1, 3), n_boot=50, seed=1)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["scored_from_episode_index"] == 3 and a["n_scored_episodes"] == 20 * 5
    with pytest.raises(ValueError):
        P._pooling_rows(make_people(5, 2), (0, 5), n_boot=10, seed=0)


pytestmark_data = pytest.mark.skipif(not (data_dir() / "synthetic" / "learners" / "truth.json").exists(),
                                     reason="synthetic datasets not generated")


@pytestmark_data
def test_evaluate_pooling_on_the_synthetic_data_has_the_agreed_shape():
    r = P.evaluate_pooling(n_boot=60)
    json.dumps(r)
    assert [x["n_episodes"] for x in r["rows"]] == [0, 1, 3, 10]
    for x in r["rows"]:
        assert set(x) >= {"n_episodes", "no_pooling", "partial_pooling", "complete_pooling", "ci"} and len(x["ci"]) == 2
        assert x["ci"][0] <= x["partial_pooling"] <= x["ci"][1]
    assert r["note"] and r["meta"]["origin"] == "synthetic" and r["meta"]["n_unit"] == "personas" and r["limitations"]
    assert set(r["datasets"]) == {"stuck_rate_personas", "stuck_rate_apprentices", "deficit_rates_apprentices",
                                  "deficit_rates_learners"}
    # cold start: with no data, any use of the role beats a coin flip (that is the whole point), with an interval above zero
    k0 = r["rows"][0]
    assert k0["no_pooling_minus_partial"]["ci"][0] > 0
    # person-specific traits (deficits) need the person's own data: complete pooling is clearly worse after one case
    d = {x["n_episodes"]: x for x in r["datasets"]["deficit_rates_apprentices"]["rows"]}
    assert d[1]["complete_pooling_minus_partial"]["ci"][0] > 0
    # partial pooling is never significantly worse than the better of the other two
    for ds in r["datasets"].values():
        for x in ds["rows"]:
            for other in ("no_pooling", "complete_pooling"):
                assert x[f"{other}_minus_partial"]["ci"][1] > -0.03
