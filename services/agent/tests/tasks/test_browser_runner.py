"""The browser route's runner on a real headless Chromium with a SCRIPTED model (no network, no model call): the page is served
by an in-test route handler. Proves the wiring: the safety pipeline is in the loop, a risky click stops the run, Stop and the denylist
win, and a finished run is reported as "not checked"."""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.tasks.browser_runner import BrowserTaskRunner, start_url
from understudy_agent.tasks.model import Task
from understudy_agent.tiers.browser import BrowserHost

from .conftest import wait_for

LINK_PAGE = ('<body style="margin:0"><a href="/more" style="position:absolute;left:100px;top:100px;width:300px;height:40px;display:block">'
             'Read more</a></body>')
ORDER_PAGE = ('<body style="margin:0"><form method=post action="/order"><button type=submit style="position:absolute;left:100px;top:100px;'
              'width:300px;height:40px">Place order</button></form></body>')


class Scripted(MockProvider):
    """A planner that plays a fixed list of computer-use actions, then says done."""

    def __init__(self, script, summary="Read the page about trains", on_step=None):
        super().__init__("benefits_clean")
        self.script, self.summary, self.on_step = list(script), summary, on_step
        self.n = 0

    def computer_step(self, goal, screenshot, history, **kw):
        if self.on_step:
            self.on_step(self.n)
        if self.n >= len(self.script):
            return Done(summary=self.summary, claimed_success=True)
        a = self.script[self.n]
        self.n += 1
        return a


def routed_host(handler, host_pat="http://shop.test/**"):
    class RoutedHost(BrowserHost):
        async def new_context(self, **kw):
            ctx = await super().new_context(**kw)
            await ctx.route(host_pat, handler)
            return ctx

    return lambda **kw: RoutedHost(headless=True)


def task(text="go to http://shop.test/ and read the page online", minutes=2):
    t = Task(task_id="tk_0a0b0c0d", text=text)
    t.max_minutes = minutes
    return t


def runner(port, host_factory, tmp_path, **kw):
    audit = AuditLog(tmp_path / "audit.jsonl")
    return BrowserTaskRunner(lambda: port, host_factory=host_factory, headless=True, audit=audit,
                             queue=ApprovalQueue(tmp_path / "queue", audit=audit), denylist=kw.pop("denylist", Denylist()), **kw)


def test_start_url_takes_the_first_address_or_a_plain_search_page():
    assert start_url("read https://www.nationalrail.co.uk/times, please") == "https://www.nationalrail.co.uk/times"
    assert start_url("find me a train to Glasgow") == "https://duckduckgo.com/"        # the worker's words never ride in a URL
    assert "Glasgow" not in start_url("find me a train to Glasgow")


def test_a_scripted_browse_clicks_through_the_pipeline_and_reports_not_checked(tmp_path):
    seen = []

    async def serve(route):
        seen.append((route.request.method, route.request.url))
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE if route.request.url.endswith("/") else "<p>more</p>")

    steps = []
    port = Scripted([Action("click", {"x": 250, "y": 120, "button": "left"})])
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=steps.append, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: Read the page about trains"}
    assert ("GET", "http://shop.test/more") in seen, seen                                 # the click really went through
    assert steps[0] == "Opening the browser" and "Clicking" in steps
    assert all(len(s) < 40 and "http" not in s for s in steps)                           # plain verbs, no addresses or page text
    assert "task-browser" in (tmp_path / "audit.jsonl").read_text()                        # it ran in a Guard with its own routine id


def test_a_risky_click_stops_the_run_and_sends_nothing(tmp_path):
    posts = []

    async def serve(route):
        if route.request.method == "POST":
            posts.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=ORDER_PAGE)

    port = Scripted([Action("click", {"x": 250, "y": 120, "button": "left", "label": "Place order"})])
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "stopped" and "waiting in Needs you" in out["reason"]
    assert posts == []
    assert any(i for i in ApprovalQueue(tmp_path / "queue").list("pending"))              # the human's call is in the queue


def test_stop_ends_the_run_between_steps(tmp_path):
    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    flag = {"stop": False}
    port = Scripted([Action("move", {"x": 10, "y": 10}), Action("move", {"x": 20, "y": 20}), Action("move", {"x": 30, "y": 30})],
                    on_step=lambda n: flag.__setitem__("stop", n >= 1))
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: flag["stop"])
    assert out == {"state": "stopped", "reason": "Stopped by you."}
    assert port.n <= 2


def test_a_denylisted_start_address_never_opens_a_browser(tmp_path):
    def boom(**kw):
        raise AssertionError("no browser may be opened for a denylisted address")

    out = runner(Scripted([]), boom, tmp_path, denylist=Denylist([{"kind": "domain", "value": "shop.test"}]))(
        task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and "denylist" in out["reason"]


def test_a_page_that_cannot_open_is_a_plain_failure(tmp_path):
    async def serve(route):
        await route.abort()

    out = runner(Scripted([]), routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out == {"state": "failed", "reason": "Knack could not open the page."}


def test_the_model_giving_up_is_not_reported_as_a_result(tmp_path):
    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    class GiveUp(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            return Done(summary="I could not find it", claimed_success=False)

    out = runner(GiveUp([]), routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out == {"state": "failed", "reason": "The browser agent gave up."}


def test_through_the_manager_a_browse_task_waits_for_the_click_and_reports(make_manager, tmp_path):
    from .test_manager import done

    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE if route.request.url.endswith("/") else "<p>more</p>")

    port = Scripted([Action("click", {"x": 250, "y": 120, "button": "left"})], summary="Found the times")
    r = runner(port, routed_host(serve), tmp_path)
    m = make_manager(browser_runner=r)
    created = m.create("go to http://shop.test/ and find the train times online", "typed")
    assert created["route"] == "browser" and created["needs_consent"]["kind"] == "browser" and port.n == 0
    m.consent(created["task_id"], "allow")
    t = done(m, created["task_id"], 60)
    assert t.state == "done" and t.result == "Reported, not checked: Found the times"
    assert t.steps[0] == "Opening the browser" and "Clicking" in t.steps
