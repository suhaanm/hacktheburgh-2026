"""AGT-4: code, not a model, decides success; a false 'done' is caught."""
from __future__ import annotations

import pytest

from understudy_agent.completion import (
    ClaimLedger, ResultFields, check_completion, parse_money, parse_status, validate_result_fields,
)


def rf(site, amt, status, ref):
    r, problems = validate_result_fields(site, {"amount_text": amt, "status_text": status, "ref": ref})
    assert r is not None, problems
    return r


RESULTS = {
    "a": rf("a", "£781", "You are likely to be eligible", "GOV-1A2B3C"),
    "b": rf("b", "£955.00 per month", "Likely to qualify", "T2U-4D5E6F"),
    "c": rf("c", "0.00 GBP / month", "NOT ELIGIBLE", "ET-7A8B9C"),
}
NOTE = ("Case CASE-1004. GovCalc: £781 You are likely to be eligible GOV-1A2B3C. Quick Estimator: £955.00 per "
        "month Likely to qualify T2U-4D5E6F. EntitledTo: 0.00 GBP / month NOT ELIGIBLE ET-7A8B9C. Case note CN-2041")


@pytest.mark.parametrize("text,want", [("£1,234", 1234.0), ("£955.00 per month", 955.0), ("313.14 GBP / month", 313.14),
                                      ("£ 1,234.56 per month", 1234.56), ("nothing", None), ("", None)])
def test_parse_money(text, want):
    assert parse_money(text) == want


def test_parse_status():
    assert parse_status("You are likely to be eligible") is True
    assert parse_status("You are unlikely to be eligible") is False
    assert parse_status("NOT ELIGIBLE") is False
    assert parse_status("Likely to qualify") is True
    assert parse_status("hello") is None


def test_complete_when_everything_is_on_the_final_page():
    r = check_completion(NOTE, RESULTS, "CN-2041")
    assert r.ok and r.missing == ()


def test_each_missing_piece_is_named():
    r = check_completion(NOTE.replace("T2U-4D5E6F", ""), RESULTS, "CN-2041")
    assert not r.ok and "calculator b: reference" in r.missing
    r = check_completion(NOTE.replace("£781", "£780"), RESULTS, "CN-2041")
    assert not r.ok and any("calculator a: amount" in m for m in r.missing)
    r = check_completion(NOTE, RESULTS, None)
    assert not r.ok and "case note id" in r.missing
    r = check_completion(NOTE.replace("CN-2041", ""), RESULTS, "CN-2041")
    assert not r.ok and "case note id not on page" in r.missing
    partial = {k: v for k, v in RESULTS.items() if k != "c"}
    r = check_completion(NOTE, partial, "CN-2041")
    assert not r.ok and "calculator c: no result" in r.missing


def test_bad_fields_are_rejected():
    r, problems = validate_result_fields("a", {"amount_text": "lots", "status_text": "", "ref": "x"})
    assert r is None and len(problems) == 3
    r, problems = validate_result_fields("a", {"amount_text": "£5", "status_text": "eligible", "ref": "GOV-1A2B3C extra"})
    assert r is None and problems == ["reference is not a quote reference"]


def test_false_claim_is_counted_only_when_claimed_and_unverified():
    led = ClaimLedger()
    assert led.record("model", claimed_success=True, verified=False) is True
    assert led.record("model", claimed_success=True, verified=True) is False
    assert led.record("tier2", claimed_success=False, verified=False) is False
    assert led.false_claims == 1 and len(led.claims) == 3
