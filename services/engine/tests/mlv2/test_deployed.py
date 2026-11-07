import numpy as np

from understudy_engine.hazard.model import HazardModel
from understudy_engine.mlv2.deployed import HazardModelV2, make_hazard_model


def test_make_hazard_model_defaults_to_v1_and_v2_is_explicit():
    assert isinstance(make_hazard_model(), HazardModel)
    assert isinstance(make_hazard_model("v2"), HazardModelV2)
    try:
        make_hazard_model("v3")
        assert False
    except ValueError:
        pass


def test_v2_fit_predict_is_leakage_free_and_matches_the_protocol_shape(sim_tab):
    tab = sim_tab
    people = tab.people
    tr, te = tab.rows_of(people[1:]), tab.rows_of(people[:1])
    for spec in ("A1", "A6", "A7_A1"):
        m = HazardModelV2(spec, inner_folds=3).fit(tab, tr)
        p = m.predict(tab, te)
        assert p.shape == te.shape and np.all((p > 0) & (p < 1))
        assert m.alarm_config is not None and "threshold" in m.alarm_config
    # prediction for one person must not depend on the labels of that person's later episodes
    import dataclasses
    m = HazardModelV2("A6", inner_folds=3).fit(tab, tr)
    p1 = m.predict(tab, te)
    y2 = tab.y.copy()
    last = te[tab.episode[te] == tab.episode[te][-1]]
    y2[last] = 1 - y2[last]
    p2 = m.predict(dataclasses.replace(tab, y=y2), te)
    n_before = te.size - last.size
    assert np.allclose(p1[:n_before], p2[:n_before])
