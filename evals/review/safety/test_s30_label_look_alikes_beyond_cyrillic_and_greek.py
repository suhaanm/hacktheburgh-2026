"""S-30 (Low-Medium, hostile pages only): normalise_label() now strips zero-width and bidi characters and folds Cyrillic and Greek look-alikes (the control
cases below pass), but a label can still hide "pay" with a combining mark ("Páy"), an accented letter ("Pày"), a Latin small capital (U+1D18), a Cherokee
letter, or a reversed string under an RTL override, and the word lists then see nothing. It matters for controls whose class depends on the NAME alone (type=button,
role=button links); submit controls and script-clickables fall to 'unknown verb -> human'. Fix: NFKD then drop combining marks (Mn), a fuller confusables skeleton
(or: any letter that is not ASCII after folding in a short control label -> unknown -> human), and resolve bidi overrides by treating them as unknown. Pure function."""
from __future__ import annotations

import pytest

from understudy_agent.security.labels import classify_label

CONTROLS = ["Pay now", "Pa​y now", "Pаy now", "Ρay now", "Ｐａｙ now", "Pa­y now"]
EVASIONS = ["Páy now", "Pày now", "ᴘay now", "Ꮲay now", "‮yap‬ now"]


@pytest.mark.parametrize("label", CONTROLS)
def test_control_labels_the_code_already_sees_through(label):
    assert classify_label(label)


@pytest.mark.parametrize("label", EVASIONS)
def test_a_label_that_still_hides_pay_is_classified(label):
    assert classify_label(label), f"{label!r} reads as 'Pay now' to a person and as nothing to the classifier"
