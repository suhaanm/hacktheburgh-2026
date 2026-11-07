"""The guards: strict schema, no verbatim span, PII backstop, fail closed."""
from __future__ import annotations

import pytest

from understudy_engine.localmodel.guards import (
    GuardError,
    audit_text_for_leaks,
    guard_digest,
    guard_model_reply,
    scan_pii,
    validate_digest,
    verbatim_overlap,
)

GOOD_COMMIT = {"category": "fix", "size_bucket": "small", "touches_tests": True, "risk": "low", "message_quality": "ok"}
GOOD_EVENT = {"category": "review", "recurring": False, "duration_bucket": "60to89", "attendee_bucket": "lt5", "needs_prep": True}


def test_valid_digests_pass():
    assert guard_digest("commit_digest", dict(GOOD_COMMIT), "Fix the exporter") == GOOD_COMMIT
    assert guard_digest("event_digest", dict(GOOD_EVENT), "Design review") == GOOD_EVENT


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(extra="x"), "bad_keys"),
    (lambda d: d.pop("risk"), "bad_keys"),
    (lambda d: d.update(category="banana"), "not_in_vocabulary"),
    (lambda d: d.update(touches_tests=1), "bad_bool"),
    (lambda d: d.update(touches_tests="yes"), "bad_bool"),
    (lambda d: d.update(size_bucket=3), "bad_type"),
])
def test_schema_violations_are_rejected(mutate, code):
    d = dict(GOOD_COMMIT)
    mutate(d)
    with pytest.raises(GuardError) as e:
        validate_digest("commit_digest", d)
    assert e.value.code == code


def test_non_dict_rejected():
    with pytest.raises(GuardError):
        validate_digest("commit_digest", ["fix"])


def test_verbatim_span_is_classified_as_a_leak_not_just_invalid():
    source = "Fix invoice export for Zorblax Holdings"
    bad = dict(GOOD_COMMIT, category="invoice export for zorblax")
    with pytest.raises(GuardError) as e:
        validate_digest("commit_digest", bad, source=source)
    assert e.value.code == "verbatim_span"
    with pytest.raises(GuardError) as e2:
        validate_digest("commit_digest", dict(GOOD_COMMIT, category="banana"), source=source)
    assert e2.value.code == "not_in_vocabulary"


def test_overlap_ignores_case_and_punctuation_and_counts_zero_for_disjoint():
    assert verbatim_overlap("Zorblax-Holdings!", "we paid zorblax holdings") > 0
    assert verbatim_overlap("feature", "wholly unrelated words") == 0
    assert verbatim_overlap("abc", "abc") == 0          # shorter than one 8-gram


def test_model_reply_guard_takes_only_the_model_fields():
    assert guard_model_reply("commit_digest", {"category": "fix", "risk": "low", "message_quality": "ok"}, "x") == \
        {"category": "fix", "risk": "low", "message_quality": "ok"}
    with pytest.raises(GuardError):
        guard_model_reply("commit_digest", dict(GOOD_COMMIT), "x")           # the code-computed fields are not the model's to send
    with pytest.raises(GuardError):
        guard_model_reply("event_digest", {"category": "review", "needs_prep": "true"}, "x")


@pytest.mark.parametrize("text,kind", [
    ("mail me at jane.doe@example.com", "email"),
    ("see https://intranet.example.org/x", "url"),
    ("file /Users/jane/projects/secret/a.py", "unix_path"),
    (r"C:\Users\jane\Desktop\x.txt", "windows_path"),
    ("server 10.20.30.40 is down", "ipv4"),
    ("key sk-abcdefghijklmnopqrstuvwx", "secret_token"),
    ("token ghp_abcdefghijklmnopqrstuv", "secret_token"),
    ("NI number AB123456C", "uk_nino"),
    ("call +44 7700 900123 now", "phone"),
    ("sha deadbeefdeadbeefdeadbeefdeadbeef", "long_hex"),
])
def test_pii_backstop_finds_planted_patterns(text, kind):
    assert kind in scan_pii(text)


def test_pii_backstop_is_quiet_on_plain_enums():
    for w in ("feature", "one_to_one", "60to89", "10plus", "team_meeting"):
        assert scan_pii(w) == []


def test_audit_text_for_leaks():
    assert audit_text_for_leaks('{"a": "Zorblax"}', ["zorblax", "other"]) == ["zorblax"]
