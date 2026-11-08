"""The decisions scoreboard: paired contrasts, the adjusted level for the primary family, the share of the gap closed, and each row on a small world."""
from __future__ import annotations

import numpy as np

from understudy_engine.hrt import scoreboard as sb


def test_the_primary_family_is_four_and_its_adjusted_level_is_98_75_percent():
    assert sb.N_PRIMARY == 4 and abs(sb.LEVEL_ADJ - 0.9875) < 1e-12


def test_contrast_pairs_replicates_and_applies_the_right_level():
    rng = np.random.default_rng(0)
    base = rng.normal(10.0, 3.0, 40)                       # replicate worlds differ a lot in level ...
    shipped = base - 1.0 + rng.normal(0, 0.2, 40)           # ... but the shipped rule is about 1 lower in each: a paired contrast sees it
    idx = sb.boot_idx(40, 2000, 1)
    c = sb.contrast(shipped, base, idx, good="lower", primary=True, label="x")
    assert c["est"] < -0.8 and c["ci95"][1] < 0 and c["verdict"] == "win"
    assert c["ci_adjusted"][0] <= c["ci95"][0] and c["ci_adjusted"][1] >= c["ci95"][1]           # the adjusted interval is wider
    assert c["adjusted_level"] == sb.LEVEL_ADJ and c["family_size"] == 4
    # an unpaired view would not see it: the spread of the base level swamps a difference of 1
    assert np.std(base) / np.sqrt(40) * 1.96 * 2 > 1.0
    # higher-is-better flips the direction
    assert sb.contrast(base + 1.0, base, idx, good="higher", primary=False, label="y", n_exploratory=7)["verdict"] == "win"
    assert sb.contrast(base + 1.0, base, idx, good="lower", primary=False, label="y", n_exploratory=7)["verdict"] == "loss"
    flat = sb.contrast(base + rng.normal(0, 3, 40), base, idx, good="lower", primary=False, label="z", n_exploratory=7)
    assert flat["verdict"] == "no clear difference" and flat["exploratory_cells_in_row"] == 7 and "ci_adjusted" not in flat


def test_an_exploratory_cell_is_judged_at_the_nominal_level_and_a_primary_at_the_adjusted_level():
    rng = np.random.default_rng(3)
    base = np.zeros(30)
    shipped = rng.normal(-0.35, 1.0, 30)                    # a borderline effect
    idx = sb.boot_idx(30, 4000, 5)
    prim = sb.contrast(shipped, base, idx, good="lower", primary=True, label="p")
    expl = sb.contrast(shipped, base, idx, good="lower", primary=False, label="e", n_exploratory=3)
    assert prim["ci95"] == expl["ci95"]
    if prim["ci95"][1] < 0 <= prim["ci_adjusted"][1]:
        assert expl["verdict"] == "win" and prim["verdict"] == "no clear difference"       # the correction can take a win away


def test_gap_closed_is_a_share_of_the_naive_to_oracle_gap_and_is_not_defined_without_a_gap():
    rng = np.random.default_rng(1)
    naive = 10 + rng.normal(0, 0.2, 40)
    oracle = 4 + rng.normal(0, 0.2, 40)
    shipped = 7 + rng.normal(0, 0.2, 40)                  # halfway
    idx = sb.boot_idx(40, 2000, 2)
    g = sb.gap_closed(shipped, naive, oracle, idx, good="lower")
    assert abs(g["share"] - 0.5) < 0.05 and g["ci"][0] < 0.5 < g["ci"][1]
    higher = sb.gap_closed(-shipped, -naive, -oracle, idx, good="higher")
    assert abs(higher["share"] - 0.5) < 0.05
    none = sb.gap_closed(shipped, naive, naive + rng.normal(0, 0.05, 40), idx, good="lower")
    assert none["share"] is None and "not clearly different from zero" in none["reason"]


def test_ski_replicate_costs_have_the_oracle_as_a_floor_and_the_known_orderings():
    r = sb.ski_replicate(123456, (4.0, 32.0), n_routines=400)
    for b, row in r.items():
        assert row["oracle_hindsight"] <= min(row[k] for k in row if k != "oracle_hindsight") + 1e-9
        assert row["never_build"] > row["oracle_hindsight"]
    assert r[4.0]["build_now"] < r[4.0]["break_even"]                    # when building is cheap, build at once


def test_routing_replicate_orders_the_reviewers_and_random_is_the_exact_expectation():
    r = sb.routing_replicate(777, (0.3,), n=1200)[0.3]
    assert r["hindsight_oracle"] <= r["model"] <= r["random"] + 1e-9
    assert r["model"] < r["random"] and r["agent_confidence_only"] < r["random"]
    # random review of a share s leaves a (1 - s) share of the errors in expectation
    assert abs(r["random"] - r["error_rate_per_100"] * 0.7) < 0.05


def test_nudge_replicate_has_the_exact_optimum_as_a_ceiling_and_silence_at_zero():
    r = sb.nudge_replicate(5, n=600)
    assert r["never_speak"] == 0.0
    assert r["shipped_bandit_snapshot"] <= r["oracle_optimum"] + 1e-9 and r["rule_baseline"] <= r["oracle_optimum"] + 1e-9 and r["always_nudge"] <= r["oracle_optimum"] + 1e-9


def test_presence_replicate_counts_and_the_oracle_never_collides():
    r = sb.presence_replicate(9_999_001, "nine-to-five", (1.0, 9.0))
    c = r["counts"]
    assert c["oracle_knows_spell_length"][1] == 0                         # an oracle never collides
    # the value at each loss ratio is completed runs minus (L/G) x collisions, per test day
    n = r["n_test_days"]
    for lr in (1.0, 9.0):
        for p, (done, hit) in c.items():
            assert np.isclose(r["value_per_day"][lr][p], (done - lr * hit) / n)
    assert 0.0 <= r["interruption_rate"]["shipped_rule"] <= 1.0


def test_cue_row_reads_the_recorded_file_and_does_not_run_anything():
    row = sb.cue_row()
    assert row["id"] == "D5" and row["recorded"] is True
    assert row["status"] in ("ok", "pending")
    if row["status"] == "ok":
        assert row["naive"]["never speak"] == 0.0 and row["acceptance"]["faster_to_resume_target"] in ("met", "not_met")
    assert sb.ladder_row()["status"] == "not_scored"


def test_build_timing_row_on_a_tiny_world_reports_every_cell_and_marks_exactly_one_primary():
    row = sb.build_timing_row((1, 2), bs=(4.0, 8.0), b_primary=8.0, n_routines=80, seed=3)
    prim = [(b, n) for b, cell in row["cells"].items() for n, c in cell["contrasts"].items() if c["primary"]]
    assert prim == [("8", "shipped_minus_break_even")]
    assert row["primary"]["primary"] is True and row["direction"] == "lower" and row["replicates"] == 2
    for cell in row["cells"].values():
        assert set(cell["policies"]) >= {"shipped_learned_lambda", "break_even", "build_now", "never_build", "oracle_hindsight"}
