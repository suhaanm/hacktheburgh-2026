"""S-13 (Medium, needs one real-desktop confirmation): QuartzBackend.type_text() builds key events with CGEventCreateKeyboardEvent(None, ...)
and never calls CGEventSetFlags(ev, 0) or uses a private event source, so each synthetic key inherits whatever modifiers the worker is
physically holding. The kill hotkey is Command+Option+Shift+K: the moment the worker presses it, the in-flight chunk (up to 6 characters)
is typed WITH those modifiers, i.e. as Command-Option-Shift shortcuts in the target app. Runs the real QuartzBackend on the fake Quartz."""
from __future__ import annotations

from understudy_agent.tiers.computer_use import QuartzBackend


def test_every_synthetic_key_event_has_its_modifier_flags_cleared_explicitly(fake_os, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    QuartzBackend().type_text("abc")
    keys = [e for e in fake_os.posted if e["kind"] == "key"]
    assert len(keys) == 6
    assert all(e["flags"] == 0 for e in keys), f"flags were never set: {[e['flags'] for e in keys]} (source={keys[0]['src']!r})"
