import json
import zlib

import numpy as np
import pytest

from understudy_engine.core import Cog, Episode
from understudy_engine.hazard import features as F
from understudy_engine.hazard import events as E
from understudy_engine.hazard.evaluate import evaluate_hazard
from understudy_engine.hazard.model import HazardModel
from understudy_engine.hazard.sim import simulate_people


def make_ep(cogs, progress, t0=1000.0, t1=None, person="p_a"):
    cg = [Cog(a, b, c) for a, b, c in cogs]
    return Episode(task_id="t1", person=person, role="r", origin="synthetic", t0=t0,
                   t1=t1 if t1 is not None else cg[-1].t1, cogs=cg, progress_t=list(progress))


def test_hash_is_stable_across_processes():
    # crc32-based, so it must not depend on PYTHONHASHSEED
    assert F._hash_gram(("READ",), 64) == zlib.crc32(b"1:READ") % 64
    assert F._hash_gram(("A", "B"), 64) == zlib.crc32(b"2:A>B") % 64


def test_labels_and_features_on_a_handmade_trace():
    # 0-30 READ, 30-50 ENTER, 50-70 CHECK (progress at 70), 70-90 SEARCH, 90-110 REFORMULATE,
    # 110-130 REFORMULATE, 130-150 CHECK (progress at 150), 150-300 IDLE (episode ends at 300)
    ep = make_ep(
        [(1000, 1030, "READ"), (1030, 1050, "ENTER"), (1050, 1070, "CHECK"), (1070, 1090, "SEARCH"),
         (1090, 1110, "REFORMULATE"), (1110, 1130, "REFORMULATE"), (1130, 1150, "CHECK"),
         (1150, 1300, "IDLE")],
        progress=[1070, 1150], t1=1300,
    )
    tab = F.build_bins([ep])
    # bins at 1000, 1030, ... while b + 60 <= 1300 -> last bin starts at 1240
    assert tab.t.tolist() == [1000 + 30 * k for k in range(9)]
    # y = 1 iff no progress in (b, b+60]
    expected = []
    for b in tab.t:
        expected.append(0 if any(b < p <= b + 60 for p in (1070, 1150)) else 1)
    assert tab.y.tolist() == expected
    assert expected[0] == 1 and expected[1] == 0 and expected[-1] == 1
    names = list(F.DENSE_NAMES)
    d = {n: tab.dense[:, i] for i, n in enumerate(names)}
    # at b = 1120 (index 4): current cog REFORMULATE (started 1110), 2nd reformulate in a row,
    # 2 reformulations since the progress at 1070, tsp = 50
    i = 4
    assert tab.t[i] == 1120
    assert d["repeat_run"][i] == 2
    assert d["reformulations"][i] == 2
    assert d["log_dwell"][i] == pytest.approx(np.log1p(10))
    assert d["log_tsp"][i] == pytest.approx(np.log1p(50))
    # n-grams: unigram REFORMULATE, bigram REFORMULATE>REFORMULATE, trigram SEARCH>REFORMULATE>REFORMULATE
    row = tab.hashed[i]
    for g in [("REFORMULATE",), ("REFORMULATE", "REFORMULATE"), ("SEARCH", "REFORMULATE", "REFORMULATE")]:
        assert row[F._hash_gram(g, F.N_HASH)] >= 1
    assert row.sum() == 3


def test_features_never_use_the_future():
    rng = np.random.default_rng(0)
    eps, _ = simulate_people(1, 3, seed=11)
    ep = eps[0]
    T = ep.t0 + 300.0
    # Build a variant whose future (after T) is replaced by different cogs/progress.
    keep = [c for c in ep.cogs if c.t1 <= T]
    last_end = keep[-1].t1 if keep else ep.t0
    alt = keep + [Cog(last_end, last_end + 400, "IDLE")]
    alt_ep = Episode(ep.task_id, ep.person, ep.role, ep.origin, ep.t0, last_end + 400, alt,
                     [p for p in ep.progress_t if p <= T] + [last_end + 399])
    a = F.episode_bins(ep)
    b = F.episode_bins(alt_ep)
    # bins up to the cut: all information is in the past, so features are identical
    n_cmp = int((last_end - ep.t0) // F.BIN_S)
    assert n_cmp >= 3
    np.testing.assert_allclose(a["dense"][:n_cmp], b["dense"][:n_cmp])
    np.testing.assert_allclose(a["hashed"][:n_cmp], b["hashed"][:n_cmp])


def test_bins_whose_lookahead_is_unobserved_are_dropped():
    ep = make_ep([(0, 100, "READ")], progress=[100], t0=0.0, t1=100.0)
    tab = F.build_bins([ep])
    assert tab.t.tolist() == [0.0, 30.0]  # 60 and 90 would look past the end


def test_role_prior_is_computed_from_training_rows_only():
    eps, _ = simulate_people(3, 12, seed=5)
    tab = F.build_bins(eps)
    tr = tab.rows_of(["p_sim0", "p_sim1"])
    m = HazardModel("full").fit(tab, tr)
    expect = float(np.log(tab.y[tr].mean() / (1 - tab.y[tr].mean())))
    assert m.role_logit_["benefits-processor"] == pytest.approx(expect)


def test_lopo_never_trains_on_the_held_out_person(monkeypatch):
    seen = []
    orig = HazardModel.fit

    def spy(self, tab, rows):
        seen.append(set(tab.person[rows].tolist()))
        return orig(self, tab, rows)

    monkeypatch.setattr(HazardModel, "fit", spy)
    eps, _ = simulate_people(4, 8, seed=3)
    evaluate_hazard(eps, n_boot=20, include_series=False)
    # every fit (inner and outer) has at most 3 of the 4 people; no fit sees everyone
    assert seen and all(len(s) <= 3 for s in seen)
    # for each outer fold the training set of the final fit is exactly "everyone but one"
    outers = [s for s in seen if len(s) == 3]
    assert {frozenset(set(f"p_sim{i}" for i in range(4)) - s) for s in outers} == {
        frozenset({f"p_sim{i}"}) for i in range(4)}


def test_event_scoring_on_a_handmade_series():
    bin_s = 30.0
    t = 1000.0 + bin_s * np.arange(12)
    y = np.array([0, 1, 1, 1, 0, 0, 0, 1, 0, 0, 1, 1])  # events: bins 1-3 (len 3), 10-11 (len 2); bin 7 is a lone run
    ev = E.stuck_events(y, t, bin_s)
    assert ev == [(1030.0, 1120.0), (1300.0, 1360.0)]
    p = np.zeros(12)
    p[2] = 0.9       # inside event 1 -> detects it
    p[6] = 0.9       # a false alarm (bin 6 is far from every event)
    al = E.alarms_for(t, p, 0.5, confirm_bins=1, cooldown_s=120.0)
    assert al.tolist() == [t[2], t[6]]
    res = E.score_episode(t, y, p, 0.5, bin_s=bin_s)
    assert (res.n_events, res.detected, res.false_alarms, res.true_alarms) == (2, 1, 1, 1)
    assert res.latencies == [30.0]
    # 12 bins * 30 s = 0.1 h, events cover 90 + 60 = 150 s
    assert res.non_event_h == pytest.approx((360 - 150) / 3600)


def test_cooldown_and_confirmation():
    t = 1000.0 + 30.0 * np.arange(10)
    p = np.array([0.9] * 10)
    assert len(E.alarms_for(t, p, 0.5, 1, cooldown_s=120.0)) == 3   # t0, t0+120, t0+240
    p2 = np.array([0.9, 0, 0.9, 0.9, 0, 0, 0, 0, 0, 0])
    assert E.alarms_for(t, p2, 0.5, confirm_bins=2).tolist() == [t[3]]  # needs two in a row


def test_choose_config_respects_the_budget_when_possible():
    eps, _ = simulate_people(3, 20, seed=2)
    tab = F.build_bins(eps)
    m = HazardModel("full").fit(tab, tab.rows_of(["p_sim0", "p_sim1"]))
    rows = tab.rows_of(["p_sim2"])
    p_all = np.full(tab.n, np.nan)
    p_all[rows] = m.predict(tab, rows)
    eps_ids = [e for e, q in enumerate(tab.ep_person) if q == "p_sim2"]
    cfg = E.choose_config(tab, p_all, eps_ids, budget_per_h=0.5)
    res, _ = E.score_rows(tab, p_all, eps_ids, cfg["threshold"], confirm_bins=cfg["confirm_bins"])
    assert cfg["budget_met"] and res.fa_per_hour <= 0.5


def test_full_model_beats_both_baselines_on_held_out_people():
    eps, _ = simulate_people(4, 40, seed=21)
    r = evaluate_hazard(eps, n_boot=100, include_series=False)
    m, tsp, base = r["model"], r["baselines"]["time_since_progress"], r["baselines"]["base_rate"]
    assert m["log_loss"] < tsp["log_loss"] < base["log_loss"] + 0.1
    assert m["log_loss"] < base["log_loss"] - 0.1
    assert m["brier"] < tsp["brier"] and m["brier"] < base["brier"]
    # the paired interval for (model - baseline) log loss excludes zero
    assert r["model_minus_tsp_log_loss_ci"][1] < 0
    assert r["model_minus_base_log_loss_ci"][1] < 0
    # calibration is reasonable on held-out people
    assert m["ece"] < 0.1
    lo, hi = m["ci_log_loss"]
    assert lo <= m["log_loss"] <= hi
    # constant base-rate predictor can never raise an alarm that separates anything
    assert r["baselines"]["base_rate"]["events"]["detected"] == 0


def test_evaluate_output_shape_json_and_determinism():
    eps, _ = simulate_people(3, 10, seed=4)
    a = evaluate_hazard(eps, n_boot=30)
    b = evaluate_hazard(eps, n_boot=30)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["split"] == "leave-one-person-out" and a["n"] == 3 and a["n_unit"] == "people"
    assert a["origin"] == "synthetic" and a["interval_level"] == 0.95
    for k in ("log_loss", "brier", "ece", "ci_log_loss"):
        assert k in a["model"]
    assert set(a["baselines"]) == {"base_rate", "time_since_progress"}
    assert a["calibration"] and set(a["calibration"][0]) >= {"p_mean", "freq", "n"}
    assert set(a["series"]) == {"p_sim0", "p_sim1", "p_sim2"}
    assert {"t", "p"} <= set(a["series"]["p_sim0"][0]) and a["series"]["p_sim0"][0]["t"].endswith("Z")
    assert a["caveats"] and a["false_alarms_per_hour"] is not None


def test_one_person_is_refused():
    eps, _ = simulate_people(1, 5, seed=0)
    with pytest.raises(ValueError):
        evaluate_hazard(eps)
