import numpy as np

from understudy_engine.mlv2.ablation import ablate, permute_within_person, stub_provider
from understudy_engine.mlv2.models import LogitExtras, V1Logit


def test_logit_without_extras_equals_v1(sim_tab):
    tab = sim_tab
    tr, te = tab.rows_of(tab.people[1:]), tab.rows_of(tab.people[:1])
    a = V1Logit().fit(tab, tr).predict(tab, te)
    b = LogitExtras(None).fit(tab, tr).predict(tab, te)
    assert np.allclose(a, b, atol=1e-6)


def test_permute_within_person_keeps_each_persons_values(sim_tab):
    cols = np.arange(sim_tab.n, dtype=float)[:, None]
    out = permute_within_person(cols, sim_tab, 3)
    for q in sim_tab.people:
        r = sim_tab.rows_of([q])
        assert sorted(out[r, 0]) == sorted(cols[r, 0])
    assert not np.array_equal(out, cols)


def test_harness_finds_the_planted_column_and_not_the_controls(sim_episodes, sim_tab):
    cols = stub_provider(1.5, seed=1)(sim_tab, sim_episodes)
    res = ablate(sim_tab, {"informative": cols["informative"], "noise": cols["noise"]}, n_boot=300, seed=2)
    inf = res["rows"]["with:informative"]
    assert inf["improves_log_loss"] and inf["paired_vs_without"]["log_loss"]["delta"] < 0
    assert inf["paired_vs_without"]["auc"]["delta"] > 0
    # the same signal permuted within person must not help, and pure noise must not help
    assert not res["rows"]["placebo:informative"]["improves_log_loss"]
    assert not res["rows"]["with:noise"]["improves_log_loss"]
    assert not res["rows"]["control:noise"]["improves_log_loss"]
    assert res["controls_ok"] is True
    assert res["rows"]["placebo:informative"]["paired_vs_without"]["log_loss"]["delta"] > -0.002
    assert "planted" in res["note"] or "synthetic" in res["note"]
