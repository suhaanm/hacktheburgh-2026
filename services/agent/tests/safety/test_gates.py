from __future__ import annotations

import pytest

from understudy_agent.security.gates import RoutineContext, TargetInfo, gate
from understudy_agent.security.killflag import clear_kill, set_kill
from understudy_agent.security.labels import ActionClass, classify_label, classify_keys, highest, risk_class

C = ActionClass


def btn(label):
    return TargetInfo(label=label, role="button", url="http://localhost:7801/")


def g(kind, args, ctx=None, target=None, **kw):
    return gate(kind, args, ctx or RoutineContext(), target, **kw)


@pytest.mark.parametrize("label,cls", [
    ("Submit case note", C.SUBMIT), ("Confirm", C.SUBMIT), ("Send email", C.SEND), ("Reply all", C.SEND),
    ("Post comment", C.POST), ("Publish", C.POST), ("Pay now", C.PAY), ("Place order", C.PAY), ("Checkout", C.PAY),
    ("Delete account", C.DELETE), ("Remove item", C.DELETE), ("Install update", C.INSTALL),
    ("Allow", C.PERMISSION), ("Grant access", C.PERMISSION), ("Sign in", C.CREDENTIAL), ("Change password", C.CREDENTIAL),
    ("Enter passcode", C.CREDENTIAL), ("Send OTP", C.CREDENTIAL), ("Resend one-time code", C.CREDENTIAL), ("Show seed phrase", C.CREDENTIAL),
    ("Export private key", C.CREDENTIAL), ("Copy secret key", C.CREDENTIAL), ("Use login code", C.CREDENTIAL), ("One-time passcode", C.CREDENTIAL),
    ("Pay invoice", C.PAY), ("Send wire transfer", C.PAY), ("Wire funds", C.PAY), ("View invoice", C.PAY),
])
def test_label_classes(label, cls):
    assert cls in classify_label(label)


@pytest.mark.parametrize("label", ["Calculate", "Next", "Back", "Household size", "Postcode", "Show result", "Cancel", "Help", "",
                                   "Information", "Formatting guide", "Passport photo", "Hotpot recipes", "Wire frame", "Invoicing guide", "Private keyboard",
                                   "Secret garden", "Seed catalogue", "Passes and permits"])
def test_ordinary_labels_are_not_risky(label):
    assert classify_label(label) == set()


def test_new_credential_and_payment_words_are_word_bounded():
    assert classify_label("information") == set() and classify_label("Format") == {C.DELETE}  # 'format' inside 'information' is not a match
    assert classify_label("Hotpot") == set() and classify_label("OTP") == {C.CREDENTIAL} and classify_label("otp:") == {C.CREDENTIAL}
    assert classify_label("Private keyboard") == set() and classify_label("Private key") == {C.CREDENTIAL}
    assert classify_label("Invoicing") == set() and classify_label("Invoices") == {C.PAY}
    assert classify_label("Wire frame") == set() and classify_label("Wire transfer") == {C.PAY}


@pytest.mark.parametrize("label", ["Enter passcode", "Resend OTP", "Show seed phrase", "Pay invoice", "Wire transfer"])
def test_new_words_can_never_be_opted_in_pay_and_credential(label):
    cls = next(iter(classify_label(label)))
    ctx = RoutineContext(mode="compiled", rung="A3", opted_in=frozenset({cls}), typed_confirm=True)
    d = g("click", {"x": 1, "y": 1}, ctx, btn(label))
    assert d.verdict == "needs_human" and "cannot be opted in" in d.reason


def test_key_combos():
    assert classify_keys(["Cmd", "Q"]) == {C.SYSTEM}
    assert classify_keys(["command", "q"]) == {C.SYSTEM}
    assert classify_keys(["Cmd", "Backspace"]) == {C.DELETE}
    assert classify_keys(["Enter"]) == set()


def test_highest_and_risk_class():
    assert highest({C.SUBMIT, C.PAY}) == C.PAY
    assert risk_class(C.SEND) == "outward" and risk_class(C.DELETE) == "irreversible" and risk_class(C.FILL) == "normal"


# ---- the gate blocks by default
def test_normal_clicks_and_typing_are_allowed():
    assert g("click", {"x": 1, "y": 1}, target=btn("Calculate")).verdict == "allow"
    assert g("type", {"text": "2 adults"}, target=TargetInfo(label="Adults", role="textbox")).verdict == "allow"
    assert g("goto", {"url": "http://localhost:7801/"}).verdict == "allow"


@pytest.mark.parametrize("label", ["Submit case note", "Send", "Post", "Pay now", "Delete", "Install", "Allow", "Sign in"])
def test_risky_clicks_need_a_human_by_default(label):
    d = g("click", {"x": 1, "y": 1}, target=btn(label))
    assert d.verdict == "needs_human" and d.risk_class in ("outward", "irreversible")
    assert d.queue_kind in ("outward_step", "irreversible_step")


def test_hint_label_from_proposer_can_add_risk_but_not_remove_it():
    assert g("click", {"x": 1, "y": 1, "label": "Delete account"}, target=btn("Calculate")).verdict == "needs_human"
    assert g("click", {"x": 1, "y": 1, "label": "Calculate"}, target=btn("Submit")).verdict == "needs_human"


def test_key_enter_acts_like_the_focused_control():
    assert g("key", {"keys": ["Enter"]}, target=btn("Submit")).verdict == "needs_human"
    assert g("key", {"keys": ["Enter"]}, target=TargetInfo(label="Adults", role="textbox")).verdict == "allow"
    assert g("key", {"keys": ["cmd", "q"]}).verdict == "needs_human"


def test_compiled_routine_opt_in_lets_named_class_through_at_a2():
    ctx = RoutineContext(mode="compiled", rung="A2", opted_in=frozenset({C.SUBMIT}))
    d = g("click", {"x": 1, "y": 1}, ctx, btn("Submit case note"))
    assert d.verdict == "allow" and d.opt_in_used
    # but not for a class the worker did not name
    assert g("click", {"x": 1, "y": 1}, ctx, btn("Send")).verdict == "needs_human"
    assert g("click", {"x": 1, "y": 1}, ctx, btn("Delete")).verdict == "needs_human"


def test_opt_in_has_no_effect_on_low_rungs():
    for rung in ("A0", "A1"):
        ctx = RoutineContext(mode="compiled", rung=rung, opted_in=frozenset({C.SUBMIT}))
        assert g("click", {"x": 1, "y": 1}, ctx, btn("Submit")).verdict == "needs_human"


def test_model_driven_needs_typed_confirmation():
    base = dict(mode="model_driven", rung="A2", opted_in=frozenset({C.SUBMIT}))
    assert g("click", {"x": 1, "y": 1}, RoutineContext(**base), btn("Submit")).verdict == "needs_human"
    assert g("click", {"x": 1, "y": 1}, RoutineContext(**base, typed_confirm=True), btn("Submit")).verdict == "allow"


@pytest.mark.parametrize("label", ["Pay now", "Install", "Allow", "Sign in"])
def test_pay_install_permission_credential_can_never_be_opted_in(label):
    cls = next(iter(classify_label(label)))
    ctx = RoutineContext(mode="compiled", rung="A3", opted_in=frozenset({cls}), typed_confirm=True)
    d = g("click", {"x": 1, "y": 1}, ctx, btn(label))
    assert d.verdict == "needs_human" and "cannot be opted in" in d.reason


def test_interactive_mode_always_confirms_even_when_opted_in():
    ctx = RoutineContext(mode="interactive", rung="A3", opted_in=frozenset({C.SUBMIT}))
    assert g("click", {"x": 1, "y": 1}, ctx, btn("Submit")).verdict == "needs_human"


def test_unattended_unresolved_click_is_queued_unless_routine_says_ok():
    ctx = RoutineContext(mode="model_driven", unattended=True)
    assert g("click", {"x": 1, "y": 1}, ctx, TargetInfo()).verdict == "needs_human"
    assert g("click", {"x": 1, "y": 1}, ctx, btn("Calculate")).verdict == "allow"
    ok = RoutineContext(mode="model_driven", unattended=True, unresolved_clicks_ok=True)
    assert g("click", {"x": 1, "y": 1}, ok, TargetInfo()).verdict == "allow"
    assert g("click", {"x": 1, "y": 1}, RoutineContext(mode="model_driven"), TargetInfo()).verdict == "allow"  # attended


def test_never_types_into_sensitive_fields():
    t = TargetInfo(label="Password", role="textbox", field_attrs={"type": "password", "name": "pw"})
    d = g("type", {"text": "hunter2"}, RoutineContext(mode="compiled", rung="A3", opted_in=frozenset(C)), t)
    assert d.verdict == "block"
    t2 = TargetInfo(field_attrs={"name": "cardNumber", "type": "text"})
    assert g("fill", {"selector": "#c", "value": "4111"}, target=t2).verdict == "block"


def test_typing_credential_paths_is_classified():
    d = g("type", {"text": "cat ~/.ssh/id_rsa"}, target=TargetInfo(label="Notes", role="textbox"))
    assert d.verdict == "needs_human" and C.CREDENTIAL in d.classes


def test_kill_flag_blocks_everything():
    set_kill("test")
    try:
        assert g("screenshot", {}).verdict == "block"
        assert g("click", {"x": 1, "y": 1}, target=btn("Calculate")).verdict == "block"
    finally:
        clear_kill()
    assert g("screenshot", {}).verdict == "allow"


def test_gate_switched_off_allows():
    assert g("click", {"x": 1, "y": 1}, target=btn("Delete"), enabled=False).verdict == "allow"
