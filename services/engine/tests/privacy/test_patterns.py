from __future__ import annotations

import json
import random

import pytest

from understudy_engine.privacy import patterns as PT


def rules(text, **kw):
    return set(PT.scan_text(text, **kw))


@pytest.mark.parametrize("text,rule", [
    ("ada.lovelace@example.com", "email"),
    ("mail ADA@Corp.CO.UK now", "email"),
    ("https://example.org/plan", "url"),
    ("see www.example.net/x", "url"),
    ("visit corp.internal", "url"),
    ("/Users/ada/Projects/x/notes.txt", "path"),
    ("~/Documents/plan", "path"),
    ("C:\\Users\\ada\\notes.docx", "path"),
    ("src/payroll/rounding.py", "path"),
    ("secrets.env", "path"),
    ("+44 7700 900123", "phone"),
    ("07700 900123", "phone"),
    ("(415) 555-0132", "phone"),
    ("AB 12 34 56 C", "ni_number"),
    ("ab123456c", "ni_number"),
    ("account 12345678", "long_digits"),
    ("4111 1111 1111 1111", "long_digits"),
    ("192.168.0.12", "ip_address"),
    ("sk-abcdefghijklmnop1234", "secret_like"),
    ("ghp_abcdefghijklmnopqrstuv", "secret_like"),
    ("AKIAABCDEFGHIJKLMNOP", "secret_like"),
])
def test_pii_shapes_are_caught(text, rule):
    assert rule in rules(text, names=False), (text, rules(text, names=False))


@pytest.mark.parametrize("text", [
    "lt5", "5to9", "10plus", "protect_focus_block", "benefits-processor", "READ", "meeting_h", "focus_blocks_60", "0.3",
    "calendar.suggestion_wording", "a plain sentence about focus time", "huge_commits", "h:0123abcd", "d:deadbeef0123",
])
def test_vocabulary_like_values_are_clean(text):
    assert rules(text, names=False) == set(), rules(text, names=False)


def test_hashed_ids_are_never_refused_for_their_digits():
    rng = random.Random(7)
    for _ in range(5000):
        h = "".join(rng.choice("0123456789abcdef") for _ in range(rng.randint(4, 16)))
        assert PT.scan_text(f"h:{h}", names=False) == [] and PT.scan_text(f"d:{h}", names=False) == []
    assert "long_digits" in rules("x:1234567", names=False)       # but a bare number with another prefix is


@pytest.mark.parametrize("name,hit", [
    ("password_hint", True), ("api_key", True), ("token_count", True), ("national_insurance", True), ("card_number", True),
    ("meeting_h", False), ("focus_blocks_60", False), ("learner_ratio", False), ("template", False), ("n_commits", False),
])
def test_sensitive_field_names_are_matched_case_insensitively(name, hit):
    assert bool(rules(name.upper(), pii=False)) is hit


def test_the_embedded_copy_covers_every_pattern_in_the_schema_file():
    from understudy_engine.privacy._paths import schema_dir

    data = json.loads((schema_dir() / "sensitive_fields.json").read_text())
    missing = [p for p in data["patterns"] if p not in PT.SENSITIVE_FALLBACK]
    assert missing == [], f"sensitive_fields.json has patterns the embedded copy lacks: {missing}. Add them to SENSITIVE_FALLBACK."
    assert set(PT.sensitive_patterns()) >= set(PT.SENSITIVE_FALLBACK)


def test_scan_value_walks_keys_values_lists_and_numbers_and_reports_paths_not_text():
    secret = "ada@example.com"
    hits = PT.scan_value({"a": [1, {"b": secret}], "password": 3, "n": 5_000_000, "f": float("nan")})
    got = {(h.path, h.rule) for h in hits}
    assert ("a[1].b", "email") in got and ("n", "large_number") in got and ("f", "non_finite_number") in got
    assert any(p == "password{key}" for p, _ in got)
    assert all(secret not in str(h) for h in hits)


def test_scan_value_ignores_bools_none_and_small_numbers():
    assert PT.scan_value({"a": True, "b": None, "c": 999_999, "d": 0.123456789012}) == []


def test_non_string_keys_and_foreign_types_are_flagged():
    assert PT.scan_value({1: "x"}) and PT.scan_value(object())
