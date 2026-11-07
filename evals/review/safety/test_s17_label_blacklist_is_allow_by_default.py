"""S-17 (High, after the S-01 fix this is the remaining way past layer 4): the gate is a word blacklist on the control's label, so anything
not on the list is 'normal' and allowed. gates.py says 'The gate blocks by default'; it does not. Verbs that are plainly outward or
irreversible are classed READ: payment pages ("Proceed to payment"), account creation ("Sign up", "Register"), consent ("Accept", "I agree"),
the product's own domain verb ("Declare"), ordering ("Order", "Book now"), refunds, withdrawals, revocations, shutting the machine down, and
every non-English verb. classify_label() is pure code: no browser needed."""
from __future__ import annotations

import pytest

from understudy_agent.security.labels import classify_label

RISKY = ["Proceed to payment", "Payment details", "Make a payment", "Sign up", "Register", "Create account", "Join now", "Accept", "I agree",
         "Accept all cookies", "Book now", "Reserve", "Declare", "Request refund", "Unsubscribe", "Withdraw", "Revoke access", "Disconnect",
         "Order", "Add to basket", "Shut down", "Restart", "Quit", "Sign out", "Bezahlen", "Kaufen", "Absenden", "Loeschen", "Pagar", "Enviar",
         "Eliminar", "确认", "提交", "支付", "删除"]


@pytest.mark.parametrize("label", RISKY)
def test_an_outward_or_irreversible_label_is_not_classed_normal(label):
    assert classify_label(label), f"{label!r} is classed as a normal, allowed click"
