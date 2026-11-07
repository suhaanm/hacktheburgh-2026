import numpy as np

from understudy_engine.mlv2 import conformal as CF
from understudy_engine.mlv2.alarms import build_layout, pooled, score_grid
from understudy_engine.mlv2.family_c import compare_family_c, run_family_c
from understudy_engine.mlv2.models import FAMILY_A, LEARNERS
from understudy_engine.mlv2.protocol import fit_base_oof, make_folds


def test_poisson_upper_values_and_coverage():
    assert abs(CF.poisson_upper(0, 0.05) - 2.995732) < 1e-5            # exact: -ln(0.05)
    assert abs(CF.poisson_upper(5, 0.05) - 10.5130) < 1e-3
    rng = np.random.default_rng(0)
    for lam in (0.5, 3.0, 12.0):
        k = rng.poisson(lam, 4000)
        cover = np.mean([CF.poisson_upper(x, 0.05) >= lam for x in k])
        assert cover >= 0.95 - 0.01                                      # exact one-sided limits are conservative


def test_rate_upper_scales_with_exposure():
    assert CF.rate_upper_poisson(3, 4.0, 0.05) == CF.poisson_upper(3, 0.05) / 4.0
    assert CF.rate_upper_poisson(0, 0.0, 0.05) == float("inf")


def test_ltt_rule_returns_a_validated_threshold_within_budget_on_training(sim_tab):
    tab = sim_tab
    lay = build_layout(tab)
    rng = np.random.default_rng(0)
    p = np.clip(1 / (1 + np.exp(-(tab.dense[:, 3] - 3.5))) * 0.6 + rng.uniform(0, 0.4, tab.n), 0, 1)
    eps = np.arange(len(tab.ep_person))
    rule = CF.make_c1_rule(0.05)
    for budget in (0.3, 1.0, 3.0):
        cfg = rule(lay, p, eps, budget)
        if cfg["budget_met"]:
            gs = score_grid(lay, p, np.array([cfg["threshold"]]), cfg["confirm_bins"], episodes=eps)
            pl = pooled(lay, gs, eps)
            h = float(lay.non_event_h[eps].sum())
            assert CF.rate_upper_poisson(float(pl["fa"][0]), h, 0.025) <= budget + 1e-9      # the stopping rule's own bound
            assert pl["fa_per_hour"][0] <= budget
    # an impossible budget never alarms
    cfg = rule(lay, p, eps, 1e-6)
    assert cfg["threshold"] > 1.0 and not cfg["budget_met"]


def test_c1_never_beats_v1_rule_on_training_detection_and_keeps_training_fa_within_budget(sim_tab):
    tab = sim_tab
    lay = build_layout(tab)
    folds = make_folds(tab)
    base = fit_base_oof(tab, LEARNERS["L"], folds=folds)
    run = run_family_c(tab, base, FAMILY_A["A0"], layout=lay, n_boot_rule=100)
    for person, cfg1 in run.outputs["C1"].configs.items():
        cfg0 = run.outputs["C0"].configs[person]
        if cfg1.get("budget_met"):
            # C1's feasible set is a subset of what C0 may choose from, so on the training people C0 detects at least as much
            assert cfg1["train_fa_per_hour"] <= 1.0 + 1e-9
            assert cfg1["train_detection_rate"] <= cfg0["train_detection_rate"] + 1e-9
    cmp = compare_family_c(run, n_boot=200)
    assert cmp["rows"]["C0"]["verdict"] == "reference"
    assert "exchangeable" in cmp["guarantee"] and len(cmp["breaks"]) >= 3
    assert set(cmp["rows"]) == {"C0", "C1", "C2"}
