"""Layer 4 in tier 3: the gate classifies a pixel click, an Enter press or a newline from what TRUSTED code reads in the DOM
(S-01), by what the control IS as well as what it is called (S-16), with verbs it does not know on a submit control going to a
human (S-17). Pages are served from page.route, so there is no network; nothing here touches a desktop or a model."""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.base import ActionRejected, GateStop
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import BrowserPageActuator, ComputerUse, SimulatedActuator
from understudy_agent.tiers.safety import Guard

BOX = "position:absolute;left:100px;top:100px;width:200px;height:40px"
APP = "http://app.test"


def page_of(inner: str) -> str:
    return f"<html><body style='margin:0'>{inner}</body></html>"


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


class Script:
    name = "script"

    def __init__(self, *acts): self.acts, self.n = list(acts), 0

    def computer_step(self, goal, shot, history, **kw):
        self.n += 1
        return self.acts[self.n - 1] if self.n <= len(self.acts) else Done("done", True)


class Recording(BrowserPageActuator):
    def __init__(self, page):
        super().__init__(page)
        self.did: list[str] = []

    async def execute(self, action):
        self.did.append(action.kind)
        await super().execute(action)


async def drive(host, inner, *actions, url=APP + "/", focus=None, denylist=None, recorded=()):
    """Run the actions through the real ComputerUse + gate on a page made of `inner`; returns (what was performed, error)."""
    ctx = await host.new_context()
    page = await ctx.new_page()

    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=page_of(inner))

    await page.route("**/*", serve)
    await page.goto(url, wait_until="domcontentloaded")
    if focus:
        await page.focus(focus)
    audit = AuditLog()
    guard = Guard(MockProvider(), run_id="r_gate3", mode="model_driven", audit=audit, queue=ApprovalQueue(),
                  denylist=denylist or Denylist(), recorded_hosts=frozenset(recorded))
    act = Recording(page)

    async def verify():
        return True

    err = None
    try:
        await ComputerUse(Script(*actions, Done("done", True)), act, guard, navigator="n", stall_limit=3).run("g", verify)
    except (GateStop, ActionRejected) as exc:
        err = exc
    return act.did, err


CLICK = Action("click", {"x": 120, "y": 120})


# ------------------------------------------------------------------ S-16: what the control IS, not what it is called
async def test_a_submit_button_posting_to_another_site_is_gated_whatever_it_is_called(host):
    form = f'<form method="post" action="https://pay.example/charge"><button type="submit" aria-label="Continue" style="{BOX}">Continue</button></form>'
    did, err = await drive(host, form, CLICK)
    assert did == [] and isinstance(err, GateStop)
    assert err.decision.layer == "gates"


async def test_the_visible_text_and_the_aria_label_are_both_classified(host):
    form = f'<form method="post" action="/x"><button type="submit" aria-label="Continue" style="{BOX}">Pay now</button></form>'
    did, err = await drive(host, form, CLICK)
    assert did == [] and isinstance(err, GateStop)


async def test_a_name_that_disagrees_with_the_visible_text_is_gated(host):
    form = f'<form method="post" action="/x"><button type="submit" aria-label="Save" style="{BOX}">Next page</button></form>'
    did, err = await drive(host, form, CLICK)
    assert did == [] and isinstance(err, GateStop)


@pytest.mark.parametrize("link", [
    f'<a href="https://elsewhere.example/page" style="{BOX};display:block">Read more</a>',
    f'<a href="/file.pdf" download style="{BOX};display:block">Get the form</a>',
    f'<a href="javascript:alert(1)" style="{BOX};display:block">Learn more</a>',
    f'<button aria-haspopup="dialog" style="{BOX}">Options</button>',
])
async def test_cross_origin_links_downloads_scripts_and_dialog_openers_are_gated(host, link):
    did, err = await drive(host, link, CLICK)
    assert did == [] and isinstance(err, GateStop)


async def test_the_one_harmless_script_link_and_ordinary_same_site_links_are_fine(host):
    did, err = await drive(host, f'<a href="javascript:history.back()" style="{BOX};display:block">Go back</a>', CLICK)
    assert err is None and did == ["click"]
    did, err = await drive(host, f'<a href="/step/2" style="{BOX};display:block">Next step</a>', CLICK)
    assert err is None and did == ["click"]


# ------------------------------------------------------------------ S-17: unknown verbs on submit controls, and more known ones
async def test_a_submit_control_with_a_verb_nobody_recognised_goes_to_a_human(host):
    form = f'<form method="post" action="/go"><button type="submit" style="{BOX}">Proceed</button></form>'
    did, err = await drive(host, form, CLICK)
    assert did == [] and isinstance(err, GateStop)


@pytest.mark.parametrize("label", ["Calculate", "Continue", "Next", "Work it out", "Get my estimate", "See entitlement",
                                   "Save draft", "Show my results"])
async def test_ordinary_same_site_form_buttons_are_not_in_the_way(host, label):
    form = f'<form method="post" action="/go"><button type="submit" style="{BOX}">{label}</button></form>'
    did, err = await drive(host, form, CLICK)
    assert err is None and did == ["click"], label


@pytest.mark.parametrize("label", ["Submit application", "Proceed to payment", "Sign up", "Declare", "Book now", "Quit",
                                   "Submit to claimant record", "Bezahlen", "提交"])
async def test_risky_verbs_on_a_same_site_form_are_gated(host, label):
    form = f'<form method="post" action="/go"><button type="submit" style="{BOX}">{label}</button></form>'
    did, err = await drive(host, form, CLICK)
    assert did == [] and isinstance(err, GateStop), label


# ------------------------------------------------------------------ S-01: unreadable means a human, in every case
async def test_a_text_box_captioned_with_a_risky_word_is_still_just_a_text_box(host):
    box = f'<label for="p">Your monthly take-home pay (£)</label><input id="p" name="pay" style="{BOX}">'
    did, err = await drive(host, box, CLICK)
    assert err is None and did == ["click"]


async def test_a_button_with_no_name_cannot_be_read_so_it_is_not_clicked(host):
    did, err = await drive(host, f'<button type="button" style="{BOX}"></button>', CLICK)
    assert did == [] and isinstance(err, GateStop)


async def test_a_click_inside_a_frame_cannot_be_read_so_it_is_not_clicked(host):
    did, err = await drive(host, f'<iframe srcdoc="<button>OK</button>" style="{BOX};border:0"></iframe>', CLICK)
    assert did == [] and isinstance(err, GateStop)


async def test_the_models_own_label_never_makes_a_click_readable():
    from understudy_agent.audit import AuditLog

    guard = Guard(MockProvider(), run_id="r_hint", mode="model_driven", audit=AuditLog(), queue=ApprovalQueue(), denylist=Denylist())
    sim = SimulatedActuator()                                    # reads nothing
    cu = ComputerUse(Script(Action("click", {"x": 5, "y": 5, "label": "Calculate"})), sim, guard, navigator="n")

    async def verify():
        return True

    with pytest.raises(GateStop):
        await cu.run("g", verify)
    assert sim.actions == []


# ------------------------------------------------------------------ Enter and newlines act as the focused control
async def test_enter_in_a_field_acts_as_the_forms_default_button(host):
    form = (f'<form method="post" action="/go"><input id="f" name="note" style="{BOX}">'
            f'<button type="submit" style="position:absolute;left:400px;top:100px">Submit application</button></form>')
    did, err = await drive(host, form, Action("key", {"keys": ["Enter"]}), focus="#f")
    assert did == [] and isinstance(err, GateStop)
    did, err = await drive(host, form, Action("type", {"text": "done\n"}), focus="#f")
    assert did == [] and isinstance(err, GateStop)               # a newline is an Enter


async def test_enter_and_newlines_are_fine_when_the_default_button_is_ordinary(host):
    form = (f'<form method="post" action="/go"><input id="f" name="note" style="{BOX}">'
            f'<button type="submit" style="position:absolute;left:400px;top:100px">Calculate</button></form>')
    did, err = await drive(host, form, Action("key", {"keys": ["Enter"]}), focus="#f")
    assert err is None and did == ["key"]
    did, err = await drive(host, form, Action("type", {"text": "hello"}), focus="#f")
    assert err is None and did == ["type"]


async def test_typing_into_a_password_field_is_blocked(host):
    pw = f'<input id="f" type="password" name="pw" style="{BOX}">'
    did, err = await drive(host, pw, Action("type", {"text": "x"}), focus="#f")
    assert did == [] and err is not None


# ------------------------------------------------------------------ S-09: tier 3 tells the pipeline where it is
async def test_a_click_on_a_page_the_worker_denied_is_not_made(host):
    deny = Denylist([{"kind": "domain", "value": "bank.example"}])
    did, err = await drive(host, f'<button type="button" style="{BOX}">Continue</button>', CLICK, url="http://bank.example/login",
                           denylist=deny)
    assert did == [] and err is not None


# ------------------------------------------------------------------ recorded hosts: a destination this run already uses is not "new"
async def test_a_form_posting_to_a_host_the_run_recorded_is_not_flagged_but_an_unseen_host_is(host):
    form = f'<form method="post" action="https://scribe.test/draft"><button type="submit" style="{BOX}">Save draft</button></form>'
    did, err = await drive(host, form, CLICK, recorded=("scribe.test",))
    assert err is None and did == ["click"]                       # the run's own other site: an ordinary form submit
    did, err = await drive(host, form, CLICK)                     # the same form, a host this run never used
    assert did == [] and isinstance(err, GateStop)
    hostile = f'<form method="post" action="https://pay.example/charge"><button type="submit" aria-label="Continue" style="{BOX}">Continue</button></form>'
    did, err = await drive(host, hostile, CLICK, recorded=("scribe.test", "app.test"))
    assert did == [] and isinstance(err, GateStop)                # planted pay.example form labelled Continue: refused
    real = f'<form method="post" action="/calculate"><button type="submit" style="{BOX}">Calculate</button></form>'
    did, err = await drive(host, real, CLICK, recorded=("scribe.test", "app.test"))
    assert err is None and did == ["click"]                       # the real Calculate passes
