"""S-01b (Medium, latent, found while re-testing the S-01 fix): `target.resolved` is true when ANY label is present, and ComputerUse takes the
label from the MODEL's own action args (args["label"], accepted by validate_action for clicks). A provider (or a hijacked planner) that sends
label="Next" for the pixel of the Submit button turns an unresolved click, which the fix sends to the human, into a resolved READ click that
is allowed. gates.py promises TargetInfo is 'read by trusted code, never by the model'. The OpenAI provider does not set label today;
MockProvider does, and a future provider might. Fakes only."""
from __future__ import annotations

from test_s01_gate_blind_in_tier3 import run
from understudy_agent.models.port import Action


async def test_a_model_supplied_label_must_not_make_a_pixel_click_trusted():
    screen, coro = run(Action("click", {"x": 500, "y": 320, "button": "left", "label": "Next"}))   # the pixel is the Submit button
    await coro
    assert screen.pressed == [], f"the Submit button was pressed on the strength of the model's own label: {screen.pressed}"
