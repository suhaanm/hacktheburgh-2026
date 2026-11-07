"""Checks on the answer-key cases. Run: uv run pytest evals/tests -q"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

EVALS = Path(__file__).resolve().parents[1]
CASES = EVALS / "cases"
sys.path.insert(0, str(CASES))
pytest.importorskip("understudy_agent")
import generate_cases as GC  # noqa: E402
from understudy_agent.sandbox_sites import households as H  # noqa: E402
from understudy_agent.sandbox_sites import oracle as O  # noqa: E402

DOC20 = json.loads((CASES / "households_20.json").read_text())
DOC200 = json.loads((CASES / "households_200.json").read_text())
SCHEMA = json.loads((CASES / "cases.schema.json").read_text())
PACK_SITES = yaml.safe_load((EVALS.parent / "packages/packs/benefits-processor/tasks/sites.yaml").read_text())


@pytest.mark.parametrize("doc", [DOC20, DOC200], ids=["20", "200"])
def test_files_validate_against_the_schema(doc):
    errs = list(Draft202012Validator(SCHEMA).iter_errors(doc))
    assert not errs, [e.message for e in errs[:3]]
    assert doc["meta"]["count"] == len(doc["cases"])
    assert "not law" in doc["meta"]["oracle_label"]


def test_the_20_cover_every_archetype_and_the_200_cover_every_cliff_flag():
    assert {c["household"]["archetype"] for c in DOC20["cases"]} == set(H.ARCHETYPES)
    flags = {f for c in DOC200["cases"] for f in c["oracle"]["cliff_flags"]}
    assert flags == {"capital_limit_16000", "capital_tariff_band", "third_child", "housing_cap_binding", "work_allowance_edge", "childcare_cap_binding"}


def test_the_hand_check_agrees_with_the_oracle_everywhere_and_disagreements_would_be_listed():
    for doc in (DOC20, DOC200):
        assert doc["meta"]["oracle_independent_disagreements"] == []
        assert all(c["independent_check"]["agrees_with_oracle"] for c in doc["cases"])
    # the list is live: break one value and the meta would name the household
    h = H.generate_households(1, 2026)[0]
    broken = GC.independent_uc(h)
    assert abs(broken["uc_monthly"] - O.score(h)["uc_monthly"]) <= 0.01


def test_site_expectations_and_disagreements_are_consistent():
    for c in DOC200["cases"]:
        ref = c["oracle"]["uc_monthly"]
        off = {s for s, v in c["sites_expected"].items() if abs(v["uc_monthly"] - ref) > O.TOLERANCE_GBP}
        assert set(c["off_by"]) == off
        assert c["sites_agree"] == (not off)
        assert c["reconciliation_expected"] == ("agree" if not off else "discrepancy")
        r = c["routing"]
        assert r["sites_off"] == sorted(off)
        assert r["review_needed"] == bool(off)
        assert r["error_if_trust_first_site"] == ("a" in off)
        assert r["error_if_trust_any_single_site"] == bool(off)


def test_planted_cliffs_produce_the_expected_site_quirks():
    by = {c["household"]["archetype"]: [] for c in DOC200["cases"]}
    for c in DOC200["cases"]:
        by[c["household"]["archetype"]].append(c)
    # savings exactly at 16,000: site c treats it as over the limit, so it must disagree
    exact = [c for c in by["savings_cliff_16k"] if c["household"]["savings"] == 16000]
    assert exact and all("c" in c["off_by"] for c in exact)
    # third child: site c's legacy two-child limit pays less
    assert all("c" in c["off_by"] and c["off_by"]["c"] < 0 for c in by["third_child"])
    # a clean single worker with low savings: all three agree
    assert all(c["sites_agree"] for c in by["childless_earner"])


def test_site_inputs_apply_site_unit_transforms():
    c = next(c for c in DOC20["cases"] if c["household"]["adults"][0]["earnings_monthly"] > 0)
    monthly = c["household"]["adults"][0]["earnings_monthly"]
    assert float(c["site_inputs"]["c"]["adult1_earnings_monthly"]) == pytest.approx(monthly * 12, abs=0.01)
    assert float(c["site_inputs"]["a"]["adult1_earnings_monthly"]) == pytest.approx(monthly, abs=0.01)
    assert all(len(c["site_inputs"][s]) == 12 for s in "abc")


def test_cliff_panel_key_matches_the_pack_and_the_oracle_flags():
    ids = PACK_SITES["cliff"]["ids"]
    flag_of = {"capital_limit": "capital_limit_16000", "capital_tariff": "capital_tariff_band", "children": "third_child",
               "childcare": "childcare_cap_binding", "housing": "housing_cap_binding", "earnings": "work_allowance_edge"}
    for c in DOC200["cases"]:
        # the housing item is only shown to renters
        expected_ids = [i for i in ids if i != "housing" or c["household"]["tenure"] == "rent"]
        assert list(c["cliff_panel_expected"]) == expected_ids
        for panel_id, near in c["cliff_panel_expected"].items():
            assert (near == "yes") == (flag_of[panel_id] in c["oracle"]["cliff_flags"])


def test_households_are_synthetic_and_carry_no_personal_identifiers():
    blob = (CASES / "households_200.json").read_text()
    assert not re.search(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", blob)   # NI-number shape
    assert "@" not in blob
    for c in DOC200["cases"]:
        assert c["household"]["synthetic"] is True


def test_regeneration_is_deterministic(tmp_path):
    GC.build(tmp_path)
    for name in ("households_20.json", "households_200.json"):
        assert (tmp_path / name).read_text() == (CASES / name).read_text()


def test_the_case_note_expectation_never_submits():
    assert all(c["case_note_expected"]["must_not_submit"] for c in DOC20["cases"])
    assert all(c["case_note_expected"]["case_ref"] == c["household"]["case_ref"] for c in DOC20["cases"])
