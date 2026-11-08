"""AGENTIC-3 item 2, the module itself: the typed-input read-back and the pre-submit audit (tiers/form_audit.py), against the real
sandbox pages in a real headless browser (private ports, no network, no model, no desktop).

Pinned here: a typed handle is read back from the focused control INSIDE the page (enums, an id token and a position come back, never a
value); every way a type can fail has its own reason; the pre-submit audit re-reads every bound control (a hidden carried field and a
field of a hidden panel included); a planted wrong value, a drop-down left on its default, a handle never entered, a control that cannot
be read, and a cap on blocks per page. Synthetic households from the development seed only.
"""
from __future__ import annotations

import json

import pytest

from understudy_agent.models.port import Action
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.specs import SITES
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import BrowserPageActuator
from understudy_agent.tiers.facts import _CANON, FactStore, calculator_field_hints
from understudy_agent.tiers.form_audit import FormAudit, ReadBack, key_names, token

DEV = generate_households(20, 7001)        # the development seed only; the held-out seeds are never used here
FINAL_B = ("Calculate", "Get my estimate")


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


async def open_site(host, cluster, site, query=""):
    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.goto(cluster.urls[site] + SITES[site].start_path + query, wait_until="domcontentloaded")
    return page, BrowserPageActuator(page)


def facts_for(site, idx=1):
    return FactStore.for_calculator(site, DEV[idx].params())


def selector(site, handle):
    return SITES[site].selector(_CANON[handle])


async def enter(page, act, audit, facts, handle, site, *, page_key="p1", step=1, focus=True):
    """What the tier-3 loop does for one handle: focus the control, type the resolved value, read it back."""
    if focus:
        await page.focus(selector(site, handle))
    value = facts.peek(handle)
    await act.execute(Action("type", {"text": value}))
    rb = await audit.after_type(act, handle, value, step=step, page_key=page_key)
    del value
    return rb


async def enter_all_b(page, act, audit, facts, *, skip=()):
    for i, h in enumerate(facts.handles):
        if h in skip or not facts.has_value(h):
            continue
        await enter(page, act, audit, facts, h, "b", step=i + 1)


def make_audit(site, facts, **kw):
    labels = {"a": ("Calculate", "Work it out"), "b": FINAL_B, "c": ("Show my results", "See entitlement")}[site]
    return FormAudit(facts, final_labels=labels, field_hints=calculator_field_hints(site), **kw)


# ----------------------------------------------------------------------------- the read-back
async def test_read_back_says_yes_when_the_text_landed_and_never_returns_a_value(cluster, host):
    page, act = await open_site(host, cluster, "b")
    await page.focus("#savings")
    await act.execute(Action("type", {"text": "73519"}))
    raw = await act.read_back(expected="73519")
    assert raw["ok"] and raw["landed"] == "yes" and raw["reason"] == "ok" and raw["focus"] == "input" and raw["role"] == "text"
    assert raw["field"] == "savings" and isinstance(raw["ref"], int)
    assert "73519" not in json.dumps(raw)                                   # the control's value never leaves the page
    assert set(raw) <= {"ok", "focus", "role", "field", "id", "name", "tag", "ref", "landed", "reason"}


async def test_read_back_names_each_way_a_type_can_fail(cluster, host):
    page, act = await open_site(host, cluster, "b")
    # 1. nothing has focus: the text went nowhere (the mechanism behind the lost savings value on calculator A)
    await page.evaluate("document.activeElement && document.activeElement.blur()")
    await act.execute(Action("type", {"text": "6000"}))
    raw = await act.read_back(expected="6000")
    assert (raw["focus"], raw["landed"], raw["reason"]) == ("document", "no", "no_focus")
    # 2. the control holds something else
    await page.focus("#savings")
    await act.execute(Action("type", {"text": "111"}))
    assert (await act.read_back(expected="222"))["reason"] == "mismatch"
    # 3. the same text typed twice is appended, not replaced
    await act.execute(Action("type", {"text": "111"}))
    raw = await act.read_back(expected="111")
    assert (raw["landed"], raw["reason"]) == ("no", "appended")
    # 4. the control is still empty
    await page.focus("#rent")
    assert (await act.read_back(expected="500"))["reason"] == "empty"
    # 5. a drop-down still on its default, and one that took the type-ahead
    await page.focus("#bedrooms")
    raw = await act.read_back(expected="3")
    assert (raw["focus"], raw["role"], raw["landed"], raw["reason"]) == ("select", "select", "no", "select_unmatched")
    await act.execute(Action("type", {"text": "3"}))
    assert (await act.read_back(expected="3"))["landed"] == "yes"
    # 6. focus on something that is not a form control
    await page.evaluate("document.querySelector('button').focus()")
    assert (await act.read_back(expected="3"))["reason"] == "not_a_field"


async def test_a_control_that_is_not_the_one_a_fact_belongs_in_is_wrong_field(cluster, host):
    page, act = await open_site(host, cluster, "b")
    await page.focus("#rent")
    await act.execute(Action("type", {"text": "550"}))
    hint = list(calculator_field_hints("b")["household.savings"])
    raw = await act.read_back(expected="550", hint=hint)                    # the text IS in the field, but the field is the rent field
    assert (raw["landed"], raw["reason"]) == ("no", "wrong_field")
    assert (await act.read_back(expected="550", hint=list(calculator_field_hints("b")["household.rent"])))["landed"] == "yes"


async def test_a_sensitive_field_is_never_read(host):
    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=(
        "<form><input id='pw' name='pw' type='password'><input id='ni' name='national_insurance_number' type='text'>"
        "<input id='ok' name='savings' type='text'></form>")))
    await page.goto("http://app.test/", wait_until="domcontentloaded")
    act = BrowserPageActuator(page)
    for sel in ("#pw", "#ni"):
        await page.focus(sel)
        await act.execute(Action("type", {"text": "SECRET-VALUE-1"}))
        raw = await act.read_back(expected="SECRET-VALUE-1")
        assert (raw["landed"], raw["reason"]) == ("unreadable", "sensitive"), sel
        assert "SECRET" not in json.dumps(raw)
    await page.focus("#ok")
    await act.execute(Action("type", {"text": "42"}))
    assert (await act.read_back(expected="42"))["landed"] == "yes"


@pytest.mark.parametrize("typed, expected", [("6000", "6,000"), ("6,000", "6000"), ("6000.00", "6000"), ("£6000", "6000"),
                                             ("3, 7", "3,7"), ("3,7", "3, 7"), ("Yes", "yes"), ("  Me   and a partner ", "me and a partner")])
async def test_formatting_differences_are_not_mismatches(host, typed, expected):
    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body="<input id='f' type='text'>"))
    await page.goto("http://app.test/", wait_until="domcontentloaded")
    act = BrowserPageActuator(page)
    await page.focus("#f")
    await act.execute(Action("type", {"text": typed}))
    assert (await act.read_back(expected=expected))["landed"] == "yes"


async def test_the_actuator_without_a_browser_context_still_answers(host):
    class Bare:                              # a page double with no browser context: the script runs through a plain evaluate
        def __init__(self, page): self._p, self.context = page, None
        def __getattr__(self, n): return getattr(self._p, n)

    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body="<input id='f'>"))
    await page.goto("http://app.test/", wait_until="domcontentloaded")
    await page.focus("#f")
    await page.keyboard.type("9")
    raw = await BrowserPageActuator(Bare(page)).read_back(expected="9")
    assert raw["landed"] == "yes"


def test_the_record_shapes_are_closed():
    assert ReadBack.from_raw(None).landed == "unreadable" and ReadBack.from_raw({"ok": False}).reason == "unreadable"
    rb = ReadBack.from_raw({"ok": True, "focus": "<script>", "role": "x", "landed": "maybe", "reason": "free text", "field": "Age-Field 12345",
                            "ref": "7", "id": "rawid_xyz", "name": "rawname_xyz"})
    assert (rb.focus, rb.role, rb.landed, rb.reason, rb.ref) == ("other", "other", "unreadable", "unreadable", -1)
    assert rb.field == "age-field_#" and token("A b!c") == "a_b_c"
    assert key_names(["Enter"]) == "enter" and key_names(["a", "Tab"]) == "other+tab" and key_names(["Control", "a"]) == "control+other"
    assert "rawid_xyz" not in repr(rb) and "rawname_xyz" not in repr(rb) and rb.id == "rawid_xyz"   # raw ids are kept to find the control, not shown


# ----------------------------------------------------------------------------- the audit on one long page (site B)
async def test_a_form_entered_correctly_is_clean_and_the_record_holds_no_value(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts)
    await enter_all_b(page, act, audit, facts)
    v = await audit.before_final(act, step=99, page_key="p1")
    assert v.state == "clean" and not v.bad and not v.unreadable and audit.inputs_ok and audit.state == "clean"
    assert audit.pending() == []
    assert audit.readbacks == {"yes": len([h for h in facts.handles if facts.has_value(h)]), "no": 0, "unreadable": 0}
    blob = json.dumps(audit.summary())
    h = DEV[1]
    for secret in {str(int(h.savings)), str(int(h.rent_monthly)), str(h.adults[0].age)}:
        if len(secret) >= 3:
            assert secret not in blob, secret
    assert {r["match"] for r in audit.records} == {"yes"} and {"readback", "preflight"} <= {r["k"] for r in audit.records}


async def test_a_value_changed_after_it_landed_blocks_the_final_button(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts)
    await enter_all_b(page, act, audit, facts)
    await page.fill("#savings", "999")                                     # planted wrong value
    v = await audit.before_final(act, step=99, page_key="p1")
    assert v.state == "mismatch" and v.bad == (("household.savings", "mismatch"),) and not audit.inputs_ok
    note = audit.block_note(v)
    assert "household.savings" in note and "999" not in note and "NOT ready" in note and "checked by the system" in note


async def test_a_drop_down_left_on_its_default_is_caught_as_not_entered_or_select_unmatched(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b", 1)                                              # couple, 3 bedrooms: the default (1) is wrong
    assert facts.peek("household.bedrooms") == "3"
    audit = make_audit("b", facts)
    await enter_all_b(page, act, audit, facts, skip={"household.bedrooms"})
    v = await audit.before_final(act, step=50, page_key="p1")
    assert v.state == "mismatch" and v.bad == (("household.bedrooms", "not_entered"),)
    assert audit.pending() == ["household.bedrooms"]
    # entered, then knocked back to the default by a later key or click: the read-back said yes, the audit says no
    await enter(page, act, audit, facts, "household.bedrooms", "b", step=51)
    assert (await audit.before_final(act, step=52, page_key="p1")).state == "clean"
    await page.select_option("#bedrooms", "1")
    v = await audit.before_final(act, step=53, page_key="p1")
    assert v.bad == (("household.bedrooms", "select_unmatched"),)


async def test_text_typed_when_nothing_had_focus_is_not_entered(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts)
    await page.evaluate("document.activeElement && document.activeElement.blur()")
    value = facts.peek("household.savings")
    await act.execute(Action("type", {"text": value}))
    rb = await audit.after_type(act, "household.savings", value, step=1, page_key="p1")
    assert (rb.landed, rb.reason, rb.focus) == ("no", "no_focus", "document") and "household.savings" in audit.pending()
    assert "household.savings" in audit.readback_note("household.savings", rb) and "NOT entered" in audit.readback_note("household.savings", rb)
    assert not audit.readback_exhausted("household.savings")
    for _ in range(2):
        await audit.after_type(act, "household.savings", value, step=2, page_key="p1")
    assert audit.readback_exhausted("household.savings")                   # the third failure on one handle: stop going round


async def test_a_handle_typed_into_the_wrong_field_is_caught_by_the_hint(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts)
    await page.focus(selector("b", "household.rent"))
    value = facts.peek("household.savings")
    await act.execute(Action("type", {"text": value}))
    rb = await audit.after_type(act, "household.savings", value, step=1, page_key="p1")
    assert (rb.landed, rb.reason) == ("no", "wrong_field")
    without = FormAudit(facts, final_labels=FINAL_B)                       # no hint: the field holds the text, which is all code can see
    assert (await without.after_type(act, "household.savings", value, step=1, page_key="p1")).landed == "yes"


async def test_an_unreadable_control_makes_the_audit_uncertain_not_clean_and_not_a_mismatch(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts)
    await enter_all_b(page, act, audit, facts)
    await page.evaluate("document.querySelector('#rent').remove()")        # the control vanished (a page that re-rendered)
    v = await audit.before_final(act, step=60, page_key="p1")
    assert v.state == "uncertain" and v.unreadable == (("household.rent", "not_found"),) and not v.bad and not audit.inputs_ok
    # the same on a page that is not the page it was typed on: verified at entry, not re-read
    audit2 = make_audit("b", facts_for("b"))
    page2, act2 = await open_site(host, cluster, "b")
    await enter_all_b(page2, act2, audit2, audit2.facts)
    await page2.evaluate("document.querySelector('#rent').remove()")
    v = await audit2.before_final(act2, step=61, page_key="p2")
    assert v.state == "clean"
    assert any(r["handle"] == "household.rent" and r["reason"] == "earlier_page" for r in audit2.records)


async def test_a_sensitive_control_bound_by_mistake_is_uncertain_never_read(host):
    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=(
        "<form><input id='savings' name='national_insurance_number' type='text'></form>")))
    await page.goto("http://app.test/", wait_until="domcontentloaded")
    act = BrowserPageActuator(page)
    facts = FactStore({"household.savings": "savings"}, {"household.savings": lambda: "5000"})
    audit = FormAudit(facts, final_labels=("Calculate",))
    await page.focus("#savings")
    await act.execute(Action("type", {"text": "5000"}))
    rb = await audit.after_type(act, "household.savings", "5000", step=1, page_key="p1")
    assert (rb.landed, rb.reason) == ("unreadable", "sensitive")
    v = await audit.before_final(act, step=2, page_key="p1")
    assert v.state == "uncertain" and v.unreadable == (("household.savings", "sensitive"),)


async def test_blocks_are_capped_per_page_and_the_count_starts_again_on_a_new_page(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b")
    audit = make_audit("b", facts, max_blocks_per_page=3)
    await enter_all_b(page, act, audit, facts, skip={"household.bedrooms"})
    seen = [(await audit.before_final(act, step=70 + i, page_key="p1")).exhausted for i in range(4)]
    assert seen == [False, False, False, True] and audit.blocks == 4
    assert (await audit.before_final(act, step=80, page_key="p9")).exhausted is False        # a different page: its own count


# ----------------------------------------------------------------------------- the final button
def test_which_actions_press_a_final_button():
    audit = FormAudit(facts_for("b"), final_labels=("Calculate", "Get my estimate"))
    assert audit.is_final("click", {"x": 1, "y": 1}, "Calculate") and audit.is_final("double_click", {}, "calculate")
    assert audit.is_final("key", {"keys": ["Enter"]}, "Calculate") and audit.is_final("key", {"keys": ["return"]}, "Get my estimate")
    assert audit.is_final("click", {}, "Savings / Calculate") and audit.is_final("click", {}, "  CALCULATE  ")
    assert not audit.is_final("click", {}, "Continue") and not audit.is_final("click", {}, None) and not audit.is_final("click", {}, "")
    assert not audit.is_final("key", {"keys": ["Tab"]}, "Calculate") and not audit.is_final("type", {"text": "x"}, "Calculate")
    assert not audit.is_final("scroll", {}, "Calculate") and not audit.is_final("click", {}, "Calculate now please")
    off = FormAudit(facts_for("b"))
    assert not off.guarding and off.state == "n/a" and off.inputs_ok and not off.is_final("click", {}, "Calculate")


async def test_stray_text_is_a_mismatch_only_in_strict_mode(cluster, host):
    page, act = await open_site(host, cluster, "b")
    facts = facts_for("b", 0)                                              # one adult: the partner fields are empty and not required
    assert not facts.has_value("household.adult2_age")
    audit = make_audit("b", facts, strict_stray=True)
    await enter_all_b(page, act, audit, facts)
    await page.fill("#partner_age", "41")                                  # a value in a field no fact belongs in
    v = await audit.before_final(act, step=90, page_key="p1")
    assert v.state == "mismatch" and v.bad == (("", "stray_value"),) and v.stray == 1
    page2, act2 = await open_site(host, cluster, "b")                       # a fresh page: the same stray text, but the audit is not strict
    lax = make_audit("b", facts)
    await enter_all_b(page2, act2, lax, facts)
    await page2.fill("#partner_age", "41")
    v = await lax.before_final(act2, step=91, page_key="p1")
    assert v.state == "clean" and v.stray == 0
    # a one-adult household typed correctly has nothing stray
    page3, act3 = await open_site(host, cluster, "b")
    strict = make_audit("b", facts, strict_stray=True)
    await enter_all_b(page3, act3, strict, facts)
    assert (await strict.before_final(act3, step=92, page_key="p1")).state == "clean"


# ----------------------------------------------------------------------------- a hidden panel and hidden carried fields
async def test_site_c_audits_the_fields_of_the_panel_that_is_now_hidden(cluster, host):
    page, act = await open_site(host, cluster, "c")
    facts = facts_for("c")
    audit = make_audit("c", facts)
    panel1 = ["household.adults", "household.adult1_age", "household.adult2_age", "household.children_ages"]
    for i, h in enumerate(facts.handles):
        if not facts.has_value(h):
            continue
        if h not in panel1 and await page.locator("#panel2").is_hidden():
            await page.click("#to-money")                                  # the page's own "next" button: panel 1 is now hidden
        await enter(page, act, audit, facts, h, "c", step=i + 1)
    assert await page.locator("#panel1").is_hidden()
    assert (await audit.before_final(act, step=40, page_key="p1")).state == "clean"
    await page.evaluate("document.querySelector('[data-testid=\"age-1\"]').value = '17'")      # a planted change inside the hidden panel
    v = await audit.before_final(act, step=41, page_key="p1")
    assert v.state == "mismatch" and v.bad == (("household.adult1_age", "mismatch"),)


async def test_site_a_re_reads_the_hidden_fields_that_carry_earlier_pages_forward(cluster, host):
    page, act = await open_site(host, cluster, "a")
    facts = facts_for("a")
    audit = make_audit("a", facts)
    steps = SITES["a"].steps
    canon_to_handle = {c: h for h, c in _CANON.items()}
    for n, params in enumerate(steps, start=1):
        for p in params:
            h = canon_to_handle[p]
            if facts.has_value(h):
                await enter(page, act, audit, facts, h, "a", page_key=f"p{n}", step=n * 10)
        if n < len(steps):
            await page.click("#continue")
            await page.wait_for_load_state("domcontentloaded")
    assert "/step/4" in page.url
    v = await audit.before_final(act, step=99, page_key="p4")
    assert v.state == "clean", v
    assert any(r["role"] == "hidden" and r["match"] == "yes" for r in audit.records if r["k"] == "preflight")   # carried fields were re-read
    # a planted change in a hidden carried field is a mismatch
    await page.evaluate("document.querySelector('input[type=hidden][name=\"bedrooms\"]').value = '1'")
    v = await audit.before_final(act, step=100, page_key="p4")
    assert v.state == "mismatch" and v.bad == (("household.bedrooms", "mismatch"),)
    assert any(r["reason"] == "mismatch" and r.get("hidden") for r in audit.records if r["k"] == "preflight")
