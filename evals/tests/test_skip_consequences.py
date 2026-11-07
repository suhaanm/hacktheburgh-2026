"""skip_consequences.json prices skipped steps in answers; the numbers are recomputed here independently."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
CASES = EVALS / "cases"
sys.path.insert(0, str(CASES))
pytest.importorskip("understudy_agent")
import skip_consequences as SC  # noqa: E402

DOC = json.loads((CASES / "skip_consequences.json").read_text())
H200 = json.loads((CASES / "households_200.json").read_text())["cases"]
H20 = json.loads((CASES / "households_20.json").read_text())["cases"]


def wrong(case: dict, site: str) -> bool:
    return abs(case["sites_expected"][site]["uc_monthly"] - case["oracle"]["uc_monthly"]) > 1.0


@pytest.mark.parametrize("name,cases", [("households_20", H20), ("households_200", H200)])
def test_reconcile_numbers_match_a_recomputation(name, cases):
    r = DOC["sets"][name]["RECONCILE"]
    per_site = {s: sum(wrong(c, s) for c in cases) for s in "abc"}
    assert r["by_calculator"]["site_a"]["wrong_n"] == per_site["a"]
    assert r["by_calculator"]["site_b"]["wrong_n"] == per_site["b"]
    assert r["by_calculator"]["site_c"]["wrong_n"] == per_site["c"]
    assert r["expected_wrong_n"] == pytest.approx(sum(per_site.values()) / 3, abs=0.05)
    assert r["n"] == len(cases) == DOC["sets"][name]["n"]
    lo, hi = r["expected_wrong_share_ci95_bootstrap_by_household"]
    assert lo <= r["expected_wrong_share"] <= hi
    assert f"about {r['expected_wrong_n']:.1f} of {r['n']}" in r["sentence"]


def test_the_first_version_trap_is_documented_and_visible_in_the_numbers():
    """GovCalc (site a) is faithful to the oracle by construction: trusting it is never wrong, which is why it is not the main policy."""
    r = DOC["sets"]["households_200"]["RECONCILE"]
    assert r["by_calculator"]["site_a"]["wrong_n"] == 0
    assert r["main_policy"] == "uniform_single_site"
    assert "GovCalc" in SC.__doc__ and "trivially right" in SC.__doc__


def test_cliff_numbers_match_a_recomputation():
    c = DOC["sets"]["households_200"]["CHECK_CLIFF"]
    near = [x for x in H200 if any(v == "yes" for v in x["cliff_panel_expected"].values())]
    assert c["households_near_an_edge"] == len(near) and c["of"] == 200
    assert c["of_those_sites_disagree"] == sum(1 for x in near if not x["sites_agree"])
    impacts = {x["household"]["id"]: SC.nudge_impact(x) for x in near}
    assert c["material_n"] == sum(v > SC.MATERIAL_GBP for v in impacts.values())
    assert sorted(c["material_cases"]) == sorted(i for i, v in impacts.items() if v > SC.MATERIAL_GBP)
    assert c["reconcile_by_median_is_wrong_on"]["n"] == 0
    assert f"{len(near)} of 200" in c["sentence"]


def test_nudges_are_documented_for_every_oracle_cliff_flag():
    flags = {f for x in H200 for f in x["oracle"]["cliff_flags"]}
    assert flags <= set(SC.NUDGES)


def test_a_nudge_across_the_capital_limit_ends_the_award():
    case = next(x for x in H200 if "capital_limit_16000" in x["oracle"]["cliff_flags"] and x["household"]["savings"] == 15900 and x["oracle"]["uc_monthly"] > 0)
    assert SC.nudge_impact(case) == pytest.approx(case["oracle"]["uc_monthly"], abs=0.01)


def test_archetype_rows_add_up_and_meta_is_honest():
    s = DOC["sets"]["households_200"]
    assert sum(a["n"] for a in s["by_archetype"].values()) == 200
    assert sum(a["near_cliff"] for a in s["by_archetype"].values()) == s["CHECK_CLIFF"]["households_near_an_edge"]
    assert sum(a["reconcile_skipped_expected_wrong"] for a in s["by_archetype"].values()) == pytest.approx(s["RECONCILE"]["expected_wrong_n"], abs=0.2)
    m = DOC["meta"]
    assert m["origin"] == "synthetic" and "not law" in m["oracle_label"] and m["interval_level"] == 0.95
    assert "seconds" in m["note"] and "not seconds" in m["note"]


def test_regeneration_is_deterministic(tmp_path):
    for f in ("households_20.json", "households_200.json"):
        (tmp_path / f).write_text((CASES / f).read_text())
    SC.build(tmp_path)
    assert (tmp_path / "skip_consequences.json").read_text() == (CASES / "skip_consequences.json").read_text()
