"""The analysis exists and is tested before any data (EVL-3). The numbers here are made up for the tests only."""
from __future__ import annotations

import csv
import itertools
import json
import math
import sys
from pathlib import Path

import pytest
from scipy import stats

EVALS = Path(__file__).resolve().parents[1]
STUDY = EVALS / "study"
sys.path.insert(0, str(STUDY))
import analyze as A  # noqa: E402
import make_assignments as M  # noqa: E402

ASSIGN = json.loads((STUDY / "assignments.json").read_text())


def fake_rows(done: dict[tuple[str, str], int], practice: dict | None = None, post: dict | None = None) -> list[dict]:
    """rows for the four planned participants; done[(participant, condition)] = checks done."""
    rows = []
    for p, plan in ASSIGN["participants"].items():
        for b in plan["blocks"]:
            key = (p, b["condition"])
            rows.append({
                "participant": p, "sequence": plan["sequence"], "block": float(b["block"]), "skill": b["skill"], "condition": b["condition"],
                "practice_case": b["practice_case"], "post_case": b["post_case"],
                "practice_seconds": float((practice or {}).get(key, 300)), "practice_capped": False,
                "post_seconds": float((post or {}).get(key, 200)), "post_capped": False,
                "post_checks_done": float(min(done.get(key, 0), A.POSSIBLE[b["skill"]])), "post_checks_possible": float(A.POSSIBLE[b["skill"]]),
                "nudges_shown": 6.0 if b["condition"] == "coached" else 0.0, "nudges_followed": 4.0 if b["condition"] == "coached" else 0.0,
                "nudges_dismissed": 1.0 if b["condition"] == "coached" else 0.0, "exclusion": "", "notes": "",
            })
    return rows


def test_design_is_balanced_and_fixed_before_data():
    seqs = ASSIGN["sequences"]
    assert len(seqs) == 4 and len(ASSIGN["participants"]) == 4
    coached = [(b["skill"]) for s in seqs.values() for b in s if b["condition"] == "coached"]
    assert sorted(coached) == ["cliff", "cliff", "reconcile", "reconcile"]
    coached_first = [s[0]["condition"] == "coached" for s in seqs.values()]
    assert sum(coached_first) == 2
    first_skill = [s[0]["skill"] for s in seqs.values()]
    assert first_skill.count("cliff") == 2
    for plan in ASSIGN["participants"].values():
        assert {b["skill"] for b in plan["blocks"]} == {"cliff", "reconcile"}
        assert sorted(b["condition"] for b in plan["blocks"]) == ["coached", "uncoached"]


def test_matched_pairs_are_usable_and_regeneration_is_deterministic():
    assert M.build() == ASSIGN
    for skill, rows in ASSIGN["pairs"].items():
        assert len(rows) == 2
        x, y = rows
        assert x["archetype"] == y["archetype"] and x["cliff_flags"] == y["cliff_flags"]
        assert abs(x["a"] - x["b"]) > 1 and abs(y["a"] - y["b"]) > 1      # reconciliation_expected is "discrepancy"
        assert x["id"] != y["id"]
    ids = [r["id"] for rows in ASSIGN["pairs"].values() for r in rows]
    assert len(set(ids)) == 4
    # practice and post cases alternate between participants so case version is not confounded with condition
    p1 = ASSIGN["participants"]["P1"]["blocks"][0]
    p2 = ASSIGN["participants"]["P2"]["blocks"][0]
    pair1 = ASSIGN["pairs"][p1["skill"]]
    assert p1["practice_case"] == pair1[0]["id"]
    assert ASSIGN["participants"]["P3"]["blocks"][0]["practice_case"] == ASSIGN["pairs"][ASSIGN["participants"]["P3"]["blocks"][0]["skill"]][0]["id"]
    assert p2["practice_case"] != ASSIGN["pairs"][p2["skill"]][0]["id"]


def test_sign_flip_p_and_its_floor():
    assert A.sign_flip_p([0.5, 0.5, 0.5, 0.5]) == pytest.approx(2 / 16)     # best possible with n = 4
    assert A.sign_flip_p([0.5, -0.5, 0.5, -0.5]) == 1.0
    assert A.sign_flip_p([1.0, 0.5, 0.0, 0.5]) == pytest.approx(4 / 16)     # a zero difference cannot change sign: the floor rises
    d = [0.4, 0.1, -0.2, 0.3]
    brute = sum(abs(sum(s * x for s, x in zip(sg, d))) >= abs(sum(d)) - 1e-12 for sg in itertools.product((1, -1), repeat=4)) / 16
    assert A.sign_flip_p(d) == pytest.approx(brute)


def test_t_interval_matches_scipy():
    d = [0.5, 0.0, 0.25, 0.75]
    mean, lo, hi = A.t_interval(d)
    ref = stats.t.interval(0.95, 3, loc=sum(d) / 4, scale=stats.sem(d))
    assert (lo, hi) == pytest.approx(ref)
    assert A.t_interval([0.3])[1] != A.t_interval([0.3])[1]  # one point: no interval (nan)


def test_headline_and_assisted_speed_are_separate_and_per_participant():
    # coached skills score higher (2/2, 1/1) than uncoached (1/2, 0/1) for everyone
    done = {}
    for p, plan in ASSIGN["participants"].items():
        for b in plan["blocks"]:
            done[(p, b["condition"])] = A.POSSIBLE[b["skill"]] if b["condition"] == "coached" else (1 if b["skill"] == "cliff" else 0)
    practice = {(p, "coached"): 420 for p in ASSIGN["participants"]} | {(p, "uncoached"): 300 for p in ASSIGN["participants"]}
    res = A.analyse(fake_rows(done, practice), ASSIGN)
    h = res["headline_unassisted"]
    assert res["meta"]["n"] == 4 and res["meta"]["origin"] == "real" and res["meta"]["interval_level"] == 0.95
    # coached block scores 1.0; the uncoached block scores 0.5 (cliff) or 0.0 (reconcile)
    expected = {p: 1.0 - (0.5 if next(b for b in plan["blocks"] if b["condition"] == "uncoached")["skill"] == "cliff" else 0.0)
                for p, plan in ASSIGN["participants"].items()}
    assert h["per_participant_difference"] == pytest.approx(expected)
    assert h["mean_difference"] == pytest.approx(sum(expected.values()) / 4)
    assert h["smallest_possible_p"] == 0.125
    assert "ASSISTED" in res["assisted_speed"]["label"] and "UNASSISTED" in res["unassisted_speed"]["label"]
    assert res["assisted_speed"]["mean_difference_s"] == 120.0                 # coached practice was slower: reported, not hidden
    assert "skill" not in json.dumps(res["assisted_speed"]).lower()          # no headline numbers leak into the speed block
    assert "statistical significance" in res["not_claimed"] and "that novices become experts" in res["not_claimed"]
    assert "n = 4" in res["meta"]["note"] and "not target workers" in res["meta"]["note"]
    assert res["design_problems"] == []


def test_headline_difference_values():
    done = {("P1", "coached"): 2, ("P1", "uncoached"): 0, ("P2", "coached"): 1, ("P2", "uncoached"): 1}
    rows = fake_rows(done)
    d = A.paired([r for r in rows if r["participant"] in ("P1", "P2")], A.skill_score)
    # P1: coached skill is whichever block is coached; recompute by hand from the rows
    for p in ("P1", "P2"):
        c = next(r for r in rows if r["participant"] == p and r["condition"] == "coached")
        u = next(r for r in rows if r["participant"] == p and r["condition"] == "uncoached")
        assert d[p] == pytest.approx(A.skill_score(c) - A.skill_score(u))


def test_exclusions_remove_the_whole_participant_and_are_listed():
    rows = fake_rows({})
    for r in rows:
        if r["participant"] == "P3" and r["block"] == 2.0:
            r["exclusion"] = "site crashed twice during the post-test"
    res = A.analyse(rows, ASSIGN)
    assert res["excluded_participants"] == ["P3"]
    assert res["meta"]["n"] == 3
    assert "P3" not in res["headline_unassisted"]["per_participant_difference"]
    assert res["headline_unassisted"]["smallest_possible_p"] == 0.25


def test_design_problems_are_reported_not_hidden():
    rows = fake_rows({})
    rows = [r for r in rows if not (r["participant"] == "P2" and r["block"] == 2.0)]
    rows[0]["post_checks_done"] = 5.0
    probs = A.design_problems(rows, ASSIGN)
    assert any("P2" in p and "blocks 1 and 2" in p for p in probs)
    assert any("outside 0..possible" in p for p in probs)
    rows2 = fake_rows({})
    rows2[0]["post_case"] = "hh_9999"
    assert any("differs from the fixed assignment" in p for p in A.design_problems(rows2, ASSIGN))


def test_results_csv_round_trip(tmp_path):
    rows = fake_rows({("P1", "coached"): 2})
    path = tmp_path / "participants.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=A.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "block": int(r["block"]), "practice_capped": "no", "post_capped": "no"})
    loaded = A.load(path)
    assert len(loaded) == 8 and loaded[0]["block"] in (1.0, 2.0)
    assert A.analyse(loaded, ASSIGN)["meta"]["n"] == 4
    assert A.main([str(path)]) == 0 and (tmp_path / "summary.json").is_file()


def test_main_without_data_says_so(capsys):
    assert A.main([str(STUDY / "results" / "does-not-exist.csv")]) == 1
    assert "no data yet" in capsys.readouterr().out


def test_no_results_data_is_committed_with_the_plan():
    left = [p.name for p in (STUDY / "results").iterdir() if p.name != ".gitkeep"]
    assert left == [], f"results/ must be empty until the first session: {left}"


def test_power_statement_in_the_plan_matches_the_numbers():
    text = (STUDY / "ANALYSIS_PLAN.md").read_text()
    from scipy import optimize
    import numpy as np
    tcrit = stats.t.ppf(0.975, 3)
    power = lambda dz: 1 - stats.nct.cdf(tcrit, 3, dz * 2) + stats.nct.cdf(-tcrit, 3, dz * 2)
    dz = optimize.brentq(lambda d: power(d) - 0.8, 0.1, 10)
    assert f"{dz:.1f}" in text and "0.125" in text and "1.59" in text


def test_post_test_scoring_comes_from_the_saved_state():
    assert A.score_post_test("cliff", {"cliff_opens": []}) == (0, 2)
    assert A.score_post_test("cliff", {"cliff_opens": [{"site": "a"}, {"site": "a"}]}) == (1, 2)       # same calculator twice counts once
    assert A.score_post_test("cliff", {"cliff_opens": [{"site": "a"}, {"site": "b"}, {"site": "c"}]}) == (2, 2)  # site c is not part of the study
    assert A.score_post_test("reconcile", {"notes": {}}) == (0, 1)
    assert A.score_post_test("reconcile", {"notes": {"CN-1": {"reconciliation": "agree"}}}) == (0, 1)     # the default earns nothing
    assert A.score_post_test("reconcile", {"notes": {"CN-1": {"reconciliation": "discrepancy"}}}) == (1, 1)
    with pytest.raises(ValueError):
        A.score_post_test("typing", {})


def test_score_command_prints_json(tmp_path, capsys):
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"cliff_opens": [{"site": "a"}, {"site": "b"}]}))
    assert A.main(["score", "cliff", str(f)]) == 0
    assert json.loads(capsys.readouterr().out) == {"post_checks_done": 2, "post_checks_possible": 2}


def test_sandbox_state_has_the_fields_the_scoring_reads():
    sites = pytest.importorskip("understudy_agent.sandbox_sites.sites")
    snap = sites.SandboxState().snapshot()
    assert {"notes", "cliff_opens", "calculations", "submissions"} <= set(snap)
