"""The model layer's redactor (understudy_agent/models/redact.py) must cover the key shapes the privacy review named: the Live ephemeral
token resource name ``auth_tokens/<id>``, GitHub ``ghp_`` tokens and ElevenLabs ``sk_`` keys. All values here are made up."""
from __future__ import annotations

import pytest

redact = pytest.importorskip("understudy_agent.models.redact")

FAKE = {
    "auth_tokens": "auth_tokens/AbC123xyz_-9Qw.ZZtop~abcdefgh12",
    "ghp": "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "gho": "gho_" + "x" * 30,
    "github_pat": "github_pat_" + "11ABCDEFG0" + "A" * 30,
    "elevenlabs": "sk_" + "0123456789abcdef0123456789abcdef0123456789abcdef",
    "openai": "sk-" + "proj_AbCdEfGhIjKlMnOpQrSt",
    "google": "AIza" + "SyA-0123456789abcdefghijklmnopqrs",
}


@pytest.mark.parametrize("name", sorted(FAKE))
def test_each_key_shape_is_redacted_wherever_it_appears(name):
    v = FAKE[name]
    for template in ("{v}", "error: request to X failed with {v} in the body", "headers={{'a': '{v}'}}", "[{v}]", "name: {v}, status: 401"):
        out = redact.redact_text(template.format(v=v))
        assert v not in out and "redacted" in out, (name, template, out)
        assert redact.contains_secret(template.format(v=v)) is True
        assert redact.contains_secret(out) is False, out


def test_the_ephemeral_token_name_is_redacted_but_the_resource_prefix_text_survives():
    out = redact.redact_text("setup failed for auth_tokens/AbC123xyz_-9Qw after 3 tries")
    assert out == "setup failed for auth_tokens/<redacted:token> after 3 tries"
    assert redact.redact_text("AUTH_TOKENS/XyZ987abcdef") == "auth_tokens/<redacted:token>"


def test_xi_api_key_header_values_are_redacted_through_the_header_rule():
    out = redact.redact_text("xi-api-key: sk_0123456789abcdef0123 more")
    assert "sk_0123" not in out and "more" in out


@pytest.mark.parametrize("text", [
    "the auth_tokens list is empty", "auth_tokens", "auth_tokens/", "task_tokens/ ok", "a token budget of 4000", "ghp is not a key", "ghp_short",
    "sk_short", "risk_assessment_items", "task_id sk_ is a prefix", "disk_usage_percentage_value_here",
])
def test_ordinary_text_is_left_alone(text):
    assert redact.redact_text(text) == text and redact.contains_secret(text) is False


def test_redaction_is_idempotent_and_truncation_happens_after_redaction():
    s = "a " + FAKE["ghp"] + " b " + FAKE["auth_tokens"] + " c " + FAKE["elevenlabs"]
    once = redact.redact_text(s)
    assert redact.redact_text(once) == once and "ghp_" not in once and "sk_0123" not in once
    long = "x" * 380 + FAKE["ghp"]
    cut = redact.redact_text(long, max_chars=400)
    assert FAKE["ghp"][:12] not in cut and len(cut) <= 403


def test_the_literal_value_of_a_configured_key_is_still_redacted(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "any-shape-key-value-123")
    assert redact.redact_text("bad key any-shape-key-value-123 here") == "bad key <redacted:key> here"
