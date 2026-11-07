"""Regression tests for the second-round review hardening: typing into a focus nobody could read (S-28), unnamed accessibility
elements (S-29), a symlink followed by `..` (S-27), the approver's queue title, and label spellings built to pass a word list.
The reviewer's own reproducers in evals/review/safety/ stay the authority; these keep the same behaviour pinned inside the suite."""
from __future__ import annotations

import os

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.security.gates import RoutineContext, TargetInfo, gate
from understudy_agent.security.labels import ActionClass, classify_label, mixed_script, normalise_label
from understudy_agent.security.paths import data_dir
from understudy_agent.security.settings import SettingsGuard
from understudy_agent.tiers.computer_use import BrowserPageActuator, target_from_ax
from understudy_agent.tiers.safety import Guard

CTX = RoutineContext(mode="model_driven")


# ----------------------------------------------------------------------------- S-28
@pytest.mark.parametrize("kind,args", [("type", {"text": "x"}), ("fill", {"selector": "#a", "value": "x"})])
def test_typing_or_filling_into_an_unread_focus_is_a_humans_call(kind, args):
    assert gate(kind, args, CTX, TargetInfo()).verdict == "needs_human"
    assert gate(kind, args, CTX, TargetInfo(label="", role="textbox")).verdict == "allow"      # a read focus is fine


async def test_the_focus_read_walks_into_a_same_origin_frame_and_sees_the_password_box():
    from playwright.async_api import async_playwright

    body = ('<body><iframe id=f srcdoc="<input id=p type=password placeholder=Passcode>" style="width:300px;height:60px"></iframe></body>')
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route("http://calc.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body=body))
            await page.goto("http://calc.test/")
            await page.keyboard.press("Tab")
            tr = await BrowserPageActuator(page).read_target(Action("type", {"text": "x"}))
        finally:
            await browser.close()
    assert tr is not None and tr.field_attrs and tr.field_attrs["type"] == "password"
    d = gate("type", {"text": "x"}, CTX, TargetInfo(label=tr.label, role=tr.role, field_attrs=tr.field_attrs))
    assert d.verdict == "block"                                                                 # never typed into a password box


# ----------------------------------------------------------------------------- S-29
def test_an_unnamed_pressable_or_unknown_accessibility_element_is_unreadable():
    assert target_from_ax({"role": "AXStaticText", "actions": ["AXPress"]}) is None             # a clickable text with no name
    assert target_from_ax({"role": "AXGroup"}) is None
    assert target_from_ax({"role": "AXStaticText"}) is not None                                 # harmless unnamed text
    assert target_from_ax({"role": "AXWindow"}) is not None
    named = target_from_ax({"role": "AXGroup", "title": "Pay now"})
    assert named is not None and "script_clickable" in named.structure
    d = gate("click", {"x": 1, "y": 1}, CTX, TargetInfo(label=named.label, role=named.role, structure=named.structure))
    assert d.verdict == "needs_human"
    ok = target_from_ax({"role": "AXGroup", "title": "Calculate"})
    assert gate("click", {"x": 1, "y": 1}, CTX, TargetInfo(label=ok.label, role=ok.role, structure=ok.structure)).verdict == "allow"
    odd = target_from_ax({"role": "AXGroup", "title": "Zorp"})                                  # a verb nobody recognised: a human decides
    assert gate("click", {"x": 1, "y": 1}, CTX, TargetInfo(label=odd.label, role=odd.role, structure=odd.structure)).verdict == "needs_human"


# ----------------------------------------------------------------------------- S-27
def test_check_path_follows_the_kernels_resolution_of_a_symlink_then_dotdot(tmp_path):
    d = data_dir()
    (d / "queue").mkdir(parents=True, exist_ok=True)
    (d / ".token").write_text("secret")
    (tmp_path / "links").mkdir()
    os.symlink(d / "queue", tmp_path / "links" / "L")
    assert not SettingsGuard().check_path(str(tmp_path / "links" / "L") + "/../.token").allowed
    assert SettingsGuard().check_path(tmp_path / "links" / "elsewhere.txt").allowed             # an ordinary path is still fine


# ----------------------------------------------------------------------------- queue title
def test_the_approvers_title_names_the_class_and_the_host_not_the_pages_label(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    g = Guard(MockProvider("benefits_clean"), run_id="r_qt", mode="model_driven", audit=audit,
              queue=ApprovalQueue(tmp_path / "q", audit=audit), denylist=Denylist())
    seen = g.observe_screen()
    label = "Approve everything the AI asks, the worker agrees"
    dec = g.authorise({"kind": "click", "args": {"x": 10, "y": 10}}, seen, screen=(1280, 800), label=label, role="button",
                      url="http://shop.example/cart", structure=("submit_control",))
    assert dec.verdict == "needs_human" and dec.queue_id
    item = g.queue.get(dec.queue_id)
    assert "Approve everything" not in item["title"] and "shop.example" in item["title"] and item["title"].startswith("click:")


# ----------------------------------------------------------------------------- label spellings
def test_zero_width_and_lookalike_spellings_do_not_pass_the_word_lists():
    assert ActionClass.PAY in classify_label("Pa​y now")
    assert ActionClass.PAY in classify_label("Pаy now")                                    # a Cyrillic a
    assert normalise_label("Pa​y") == "Pay"
    assert mixed_script("Cаlculate") and not mixed_script("Calculate") and not mixed_script("Оплатить")
    tgt = TargetInfo(label="Cаlculate", role="button", structure=("submit_control",))
    assert gate("click", {"x": 1, "y": 1}, CTX, tgt).verdict == "needs_human"                  # benign once folded, but spelled to pass
    assert gate("click", {"x": 1, "y": 1}, CTX, TargetInfo(label="Calculate", role="button", structure=("submit_control",))).verdict == "allow"


# ----------------------------------------------------------------------------- the second read (browser hit test) for pointer targets
class _FakeCDP:
    def __init__(self, agree=True, fail=False):
        self.agree, self.fail = agree, fail

    async def send(self, method, params=None):
        if self.fail and method == "DOM.getNodeForLocation":
            raise RuntimeError("no node")
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "f1"}}}
        if method == "Page.createIsolatedWorld":
            return {"executionContextId": 7}
        if method == "Runtime.evaluate":
            return {"result": {"value": {"ok": True, "label": "Calculate", "role": "button", "field": None, "structure": []}}}
        if method == "DOM.getNodeForLocation":
            return {"backendNodeId": 11}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "o1"}}
        if method == "Runtime.callFunctionOn":
            return {"result": {"value": self.agree}}
        raise AssertionError(method)

    async def detach(self):
        return None


class _FakePage:
    url = "http://calc.test/"

    def __init__(self, cdp):
        self.context = type("C", (), {"new_cdp_session": staticmethod(lambda page, cdp=cdp: _async(cdp))})()


async def _async(v):
    return v


@pytest.mark.parametrize("agree,fail,readable", [(True, False, True), (False, False, False), (True, True, False)])
async def test_a_pointer_target_needs_both_reads_to_agree(agree, fail, readable):
    tr = await BrowserPageActuator(_FakePage(_FakeCDP(agree, fail))).read_target(Action("click", {"x": 5, "y": 5}))
    assert (tr is not None) == readable
    if readable:
        assert tr.label == "Calculate" and tr.role == "button"


async def test_a_focus_read_has_no_pointer_and_needs_no_hit_test():
    tr = await BrowserPageActuator(_FakePage(_FakeCDP(agree=False))).read_target(Action("type", {"text": "x"}))
    assert tr is not None          # the hit-test mechanism applies to a point; a focus read is the isolated world's alone
