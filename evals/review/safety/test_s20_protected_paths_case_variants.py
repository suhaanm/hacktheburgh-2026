"""S-20 (Medium-High on macOS): SettingsGuard.check_path() compares resolved paths, and the default macOS volume (APFS) is case-INSENSITIVE, so
`<data>/Queue`, `<data>/.TOKEN`, `<data>/kill` and `~/.UNDERSTUDY` are the protected files under another spelling that the guard does not recognise.
check_path() is what the browser agent's file:// navigation rule and the runtime's file tools use to keep the model away from the kill flag, the
queue (approvals), consent, the control-plane token, the owner tokens and the queue key. Skipped on a case-sensitive volume. Temp dir only."""
from __future__ import annotations

import pytest

from understudy_agent.security.paths import data_dir
from understudy_agent.security.settings import SettingsGuard

PROTECTED = ["KILL", ".token", "owner_tokens.json", ".queue_key", "denylist.json", "audit.jsonl", "queue/q_1.json", "routines/r/consent.json"]


@pytest.mark.parametrize("rel", PROTECTED)
def test_the_exact_spelling_is_protected_and_so_is_every_other_spelling(rel, tmp_path):
    d = data_dir()
    f = d / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("secret")
    assert not SettingsGuard().check_path(f).allowed, f"CONTROL: {rel} must be protected under its own name"
    variant = d.parent / d.name.upper() / rel.upper().replace("Q_1.JSON", "q_1.json")
    if not variant.exists():
        pytest.skip("case-sensitive volume: the variant is a different file")
    assert variant.read_text() == "secret"                       # the same file, reachable under another spelling
    assert not SettingsGuard().check_path(variant).allowed, f"{variant} reaches the protected {rel} and the guard allows it"
