"""S-23 (Low) and the honest limit of S-14. issue_owner_token() returns secrets.token_hex(4): 32 bits. And the token proves 'a human pasted it' only if
the dry run's output never reaches the process that does the real run: mac_check prints the token in its own dry-run JSON, so the same shell (or the
same agent that runs commands for the owner) mints and spends it. The lead's chat approval, not the token, is the owner-present control: say so.
Controls pass: one use, bound to its description, expiry, protected from the agent's file tools."""
from __future__ import annotations

from understudy_agent.security.paths import data_dir
from understudy_agent.security.settings import SettingsGuard
from understudy_agent.tiers.owner_present import TTL_S, consume_owner_token, issue_owner_token


def test_controls_one_use_bound_expiring_and_protected():
    t = issue_owner_token("run A", now=1000.0)
    assert not consume_owner_token(t, "run B", now=1001.0) and consume_owner_token(t, "run A", now=1002.0) and not consume_owner_token(t, "run A", now=1003.0)
    t2 = issue_owner_token("run A", now=1000.0)
    assert not consume_owner_token(t2, "run A", now=1000.0 + TTL_S + 1)
    for name in (".token", "owner_tokens.json", ".queue_key"):
        assert not SettingsGuard().check_path(data_dir() / name).allowed


def test_the_token_has_at_least_64_bits():
    t = issue_owner_token("run A")
    assert len(t) >= 16, f"{len(t) * 4}-bit token: {len(t)} hex characters"
