"""S-29 (Medium, real desktop R2 and later; R1 clicks an AXTextArea and is not affected): target_from_ax() demands a name only for the roles in _AX_NAMED
(button, link, checkbox, radio, menuitem, tab). Any other role, named or not, becomes a resolved target with an EMPTY label, which the gate classes READ and
allows. Actionable roles that apps use for custom buttons (AXGroup, AXImage, AXMenuButton, AXDisclosureTriangle, AXCell, AXRow, AXSlider, AXColorWell,
AXIncrementor, an unknown role) pass. This is the desktop twin of the DOM div-button gap (S-19). Pure function plus the gate; no OS involved."""
from __future__ import annotations

import pytest

from understudy_agent.security.gates import RoutineContext, TargetInfo, gate
from understudy_agent.tiers.computer_use import target_from_ax

ACTIONABLE = ["AXGroup", "AXImage", "AXMenuButton", "AXDisclosureTriangle", "AXCell", "AXRow", "AXSlider", "AXColorWell", "AXIncrementor", "AXUnknown"]


def verdict(el):
    tr = target_from_ax(el)
    if tr is None:
        return "needs_human"
    return gate("click", {"x": 1, "y": 1}, RoutineContext(mode="model_driven"), TargetInfo(label=tr.label, role=tr.role, structure=tr.structure)).verdict


@pytest.mark.parametrize("role", ACTIONABLE)
def test_an_unnamed_actionable_element_is_a_humans_call(role):
    assert verdict({"role": role}) != "allow", f"an unnamed {role} reads as a resolved empty-label target and is allowed"


def test_controls_the_text_area_is_allowed_and_an_unnamed_button_is_not():
    assert verdict({"role": "AXTextArea", "description": "text entry area"}) == "allow"
    assert verdict({"role": "AXButton"}) == "needs_human"
