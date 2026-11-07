"""S-25 (Medium-High, found reading labels.py in the second round): canonical_keys() orders modifiers ctrl, alt, shift, cmd, but the chord sets are written
in other orders (`cmd+alt+esc`, `cmd+ctrl+q`, `cmd+shift+q`, `cmd+shift+delete`, `cmd+alt+delete`, `cmd+alt+power`), so those entries can never match what the
pipeline computes. Force Quit, Lock Screen (ctrl+cmd+q locks at once, no confirmation), Log Out and Empty Trash are classed FILL and allowed. The real backend
presses any chord whose key is in its keycode table, which includes esc and q. Part (a) is a self-consistency check on the code's own sets; part (b) lists
other chords that leave the app or write a file (Spotlight, app switch, save, close window, new, print, hide, minimise, screenshots) and are also allowed."""
from __future__ import annotations

import pytest

from understudy_agent.security import labels
from understudy_agent.security.gates import RoutineContext, TargetInfo, gate

CTX, FIELD = RoutineContext(mode="model_driven"), TargetInfo(label="text entry area", role="textbox")
OWN = sorted(labels._SYSTEM_KEYS | labels._DELETE_KEYS)
MORE = ["cmd+space", "cmd+tab", "cmd+s", "cmd+shift+s", "cmd+w", "cmd+n", "cmd+o", "cmd+p", "cmd+h", "cmd+m", "cmd+shift+3", "cmd+shift+4", "cmd+shift+5"]


@pytest.mark.parametrize("chord", OWN)
def test_every_chord_in_the_codes_own_system_and_delete_sets_is_gated(chord):
    assert gate("key", {"keys": chord.split("+")}, CTX, FIELD).verdict != "allow", f"{chord} is in _SYSTEM_KEYS/_DELETE_KEYS and is allowed"


@pytest.mark.parametrize("chord", MORE)
def test_chords_that_leave_the_app_or_write_a_file_are_gated(chord):
    assert gate("key", {"keys": chord.split("+")}, CTX, FIELD).verdict != "allow", f"{chord} is allowed"


def test_control_plain_editing_keys_are_allowed():
    for k in (["enter"], ["tab"], ["backspace"], ["left"]):
        assert gate("key", {"keys": k}, CTX, FIELD).verdict == "allow" or k == ["enter"]
