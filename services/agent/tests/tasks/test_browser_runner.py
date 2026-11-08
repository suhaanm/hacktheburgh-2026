"""The browser route's runner on a real headless Chromium with a SCRIPTED model (no network, no model call): the page is served
by an in-test route handler. Proves the wiring: the safety pipeline is in the loop, a risky click stops the run, Stop and the denylist
win, and a finished run is reported as "not checked"."""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done, Unsupported
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
        self.asked = 0                      # every model call, including the ones that return a Done
        self.profile = None
        self.goals: list[str] = []

    def begin_task(self, session=None, profile=None):
        self.profile = profile

    def computer_step(self, goal, screenshot, history, **kw):
        self.asked += 1
        self.goals.append(goal)
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


def test_the_search_page_can_be_replaced_from_the_environment_but_only_by_a_web_address(monkeypatch):
    monkeypatch.setenv("KNACK_SEARCH_PAGE", "https://search.example.test/")
    assert start_url("find me a train to Glasgow") == "https://search.example.test/"
    monkeypatch.setenv("KNACK_SEARCH_PAGE", "file:///etc/passwd")
    assert start_url("find me a train to Glasgow") == "https://www.bing.com/"


def test_start_url_takes_the_first_address_or_a_plain_search_page():
    assert start_url("read https://www.nationalrail.co.uk/times, please") == "https://www.nationalrail.co.uk/times"
    assert start_url("find me a train to Glasgow") == "https://www.bing.com/"          # the worker's words never ride in a URL
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


def test_a_control_trusted_code_cannot_read_stops_the_run_and_says_so_in_plain_words(tmp_path):
    """A page built from custom elements (YouTube, many web apps) hides what a control does, so the gate asks a person (fail closed). The
    worker is told that, not that "something it can't undo" was about to happen."""
    page = ('<body style="margin:0"><my-button style="position:absolute;left:100px;top:100px;width:300px;height:40px;display:block">'
            'Read more</my-button></body>')

    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=page)

    port = Scripted([Action("click", {"x": 250, "y": 120, "button": "left"})])
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "stopped" and out["why"] == "unreadable" and "couldn't tell what that control does" in out["reason"], out
    assert any(i for i in ApprovalQueue(tmp_path / "queue").list("pending"))            # still the human's call, in the queue


def test_stop_ends_the_run_between_steps(tmp_path):
    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    flag = {"stop": False}
    port = Scripted([Action("move", {"x": 10, "y": 10}), Action("move", {"x": 20, "y": 20}), Action("move", {"x": 30, "y": 30})],
                    on_step=lambda n: flag.__setitem__("stop", n >= 1))
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: flag["stop"])
    assert out == {"state": "stopped", "reason": "Stopped by you.", "why": "you"}
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
    assert out == {"state": "failed", "reason": "Knack could not open the page.", "why": "no_page"}


async def serve_link(route):
    await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)


@pytest.mark.parametrize("said,why,words", [
    ("FAILED: login", "login", "The page needed a login"),
    ("FAILED: captcha", "captcha", "only a person can pass"),
    ("FAILED: blocked", "blocked", "The page blocked the browser"),
    ("FAILED: payment", "payment", "never pays"),
    ("FAILED: missing", "missing", "couldn't find"),
    ("FAILED: the cat ate it", "other", "could not finish"),          # model prose is never shown, only a closed word it chose
    ("FAILED", "other", "could not finish"),
])
def test_a_model_that_says_it_cannot_finish_tells_the_worker_why_in_plain_words(tmp_path, said, why, words):
    class GiveUp(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            self.asked += 1
            return Done(summary=said, claimed_success=False)

    out = runner(GiveUp([]), routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and out["why"] == why and words in out["reason"], out
    assert "gave up" not in out["reason"] and "the cat" not in out["reason"]


def test_a_model_that_answers_in_prose_is_asked_to_act_then_reports_it_did_nothing(tmp_path):
    class Chatty(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            self.asked += 1
            self.goals.append(goal)
            return Done(summary="I could not find it", claimed_success=False)

    port = Chatty([])
    out = runner(port, routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and out["why"] == "no_action" and "without doing anything" in out["reason"], out
    assert port.asked == 3                                                 # the first answer plus two asks to carry on, then the end
    assert "DONE:" in port.goals[1] and "final screen" not in port.goals[1]    # the ask says what to reply, not "a final screen is not showing"


@pytest.mark.parametrize("status,why", [(403, "blocked"), (429, "blocked"), (503, "blocked"), (401, "login"), (404, "no_action")])
def test_a_vague_ending_names_the_page_status_trusted_code_saw(tmp_path, status, why):
    """A model that only chats while the page answers 403 or 401 is reported as blocked or needing a login, from the browser's own
    HTTP status for the last page; any other status leaves the ending as it was."""
    async def serve(route):
        await route.fulfill(status=status, content_type="text/html", body=LINK_PAGE)

    class Chatty(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            self.asked += 1
            return Done(summary="I am not sure what to do", claimed_success=False)

    out = runner(Chatty([]), routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and out["why"] == why, out


def test_a_proper_done_is_reported_at_once_and_never_sent_back_for_a_final_screen_a_free_task_does_not_have(tmp_path):
    port = Scripted([])                                                    # the first call already answers DONE
    out = runner(port, routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: Read the page about trains"}
    assert port.asked == 1


def test_the_run_starts_the_model_on_the_web_profile(tmp_path):
    port = Scripted([])
    runner(port, routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert port.profile == "web"
    assert "FAILED:" in port.goals[0] and "login" in port.goals[0]         # the goal tells the model the closed words to use


def test_a_navigate_proposal_opens_the_address_through_the_pipeline(tmp_path):
    seen, steps = [], []

    async def serve(route):
        seen.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    port = Scripted([Action("goto", {"url": "http://shop.test/elsewhere"}), Action("back", {})], summary="Looked at both")
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=steps.append, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: Looked at both"}
    assert "http://shop.test/elsewhere" in seen and "Opening a page" in steps and "Going back" in steps
    assert all("http" not in s for s in steps)
    assert '"note":"goto"' in (tmp_path / "audit.jsonl").read_text().replace(" ", "")           # the gate allowed it, and said so


def test_back_and_forward_go_through_the_pipeline_and_the_page_history(tmp_path):
    seen, steps = [], []

    async def serve(route):
        seen.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    port = Scripted([Action("goto", {"url": "http://shop.test/a"}), Action("back", {}), Action("forward", {})], summary="walked")
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=steps.append, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: walked"}
    assert steps.count("Opening a page") == 1 and "Going back" in steps and "Going forward" in steps


def test_opening_the_address_the_page_is_already_on_is_noted_so_the_model_stops_opening_it(tmp_path):
    port = Scripted([Action("goto", {"url": "http://shop.test"})], summary="Read it")          # the run started on http://shop.test/
    runner(port, routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert "already open" in port.goals[1] and "already open" not in port.goals[0]


def test_a_click_on_a_text_box_is_followed_by_a_note_that_it_has_focus(tmp_path):
    page = ('<body style="margin:0"><input type="text" aria-label="Search" style="position:absolute;left:100px;top:100px;width:300px;'
            'height:40px"></body>')

    async def serve(route):
        await route.fulfill(status=200, content_type="text/html", body=page)

    port = Scripted([Action("click", {"x": 250, "y": 120, "button": "left"})], summary="ok")
    out = runner(port, routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "done"
    assert "text box and it now has focus" in port.goals[1] and "handle" not in port.goals[1]      # the form wording is not used here


def test_the_form_fit_notes_are_off_on_the_web_profile_even_for_gemini():
    from understudy_agent.tiers.computer_use import ComputerUse

    class G:
        name = "gemini"

    assert ComputerUse(G(), None, None, navigator="t").dropdown_note is True              # the benefits-form configuration, unchanged
    web = ComputerUse(G(), None, None, navigator="t", profile="web")
    assert (web.dropdown_note, web.entered_note, web.final_note) == (False, False, False)


def test_a_navigate_to_a_denylisted_address_is_refused_and_nothing_is_requested(tmp_path):
    seen = []

    async def serve(route):
        seen.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    port = Scripted([Action("goto", {"url": "http://blocked.test/secret"})])
    out = runner(port, routed_host(serve, "**"), tmp_path, denylist=Denylist([{"kind": "domain", "value": "blocked.test"}]))(
        task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and "denylist" in out["reason"] and "Needs you" not in out["reason"], out
    assert not any("blocked.test" in u for u in seen)


def test_a_navigate_to_a_script_address_is_refused_by_the_typed_action_layer(tmp_path):
    seen, steps = [], []

    async def serve(route):
        seen.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=LINK_PAGE)

    port = Scripted([Action("goto", {"url": "javascript:alert(1)"}), Action("goto", {"url": "file:///etc/passwd"})], summary="ok")
    out = runner(port, routed_host(serve, "**"), tmp_path)(task(), progress=steps.append, should_stop=lambda: False)
    assert out["state"] == "done" and port.n == 2                          # both were proposed, neither ran, the run went on
    assert seen == ["http://shop.test/"] and "Opening a page" not in steps


def test_an_action_nobody_maps_is_noted_and_asked_again_not_treated_as_giving_up(tmp_path):
    steps = []
    port = Scripted([Unsupported(summary="not mapped", claimed_success=False, name="teleport"),
                     Unsupported(summary="not mapped", claimed_success=False, name="teleport"),
                     Action("goto", {"url": "http://shop.test/more"})], summary="Found it")
    out = runner(port, routed_host(serve_link), tmp_path)(task(), progress=steps.append, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: Found it"}, out
    assert port.asked == 4 and "teleport" in port.goals[1] and "not available" in port.goals[1]
    assert "action_unsupported" in (tmp_path / "audit.jsonl").read_text()


def test_a_model_that_keeps_asking_for_an_action_nobody_maps_ends_with_a_reason(tmp_path):
    class Stubborn(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            self.asked += 1
            return Unsupported(summary="not mapped", claimed_success=False, name="teleport")

    port = Stubborn([])
    out = runner(port, routed_host(serve_link), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and out["why"] == "unsupported" and "can't do" in out["reason"], out
    assert port.asked == 4


def test_the_real_gemini_provider_with_the_reply_that_broke_the_owners_task_now_finishes(tmp_path):
    """The exact shape of the owner's failing run (8 Nov 2026): the first answer is a `navigate` call with an address, the next the closing
    words. Driven through the real Gemini provider (scripted HTTP client) and the real runner on a real headless page."""
    from understudy_agent.models.config import GeminiModelIds
    from understudy_agent.models.gemini_provider import GeminiProvider
    from understudy_agent.models.mock_provider import MockProvider as Mock

    from ..models.helpers import FakeGeminiClient, reply

    seen = []

    async def serve(route):
        seen.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body="<h1>Example Domain</h1>")

    nav = reply("", calls=({"id": "c1", "name": "navigate", "arguments": {"url": "http://shop.test/page", "intent": "open it"}},))
    gem = GeminiProvider(client=FakeGeminiClient(nav, reply("DONE: the main heading is Example Domain")),
                         models=GeminiModelIds(fast="lite", accurate="flash"))
    mock = Mock("benefits_clean")

    class Port:                                    # the computer-use calls go to the real provider, the gate's own checks to the mock
        name = "gemini"

        def begin_task(self, session=None, profile=None):
            gem.begin_task(session, profile=profile)

        def computer_step(self, *a, **kw):
            return gem.computer_step(*a, **kw)

        def __getattr__(self, item):
            return getattr(mock, item)

    out = runner(Port(), routed_host(serve), tmp_path)(task(), progress=lambda s: None, should_stop=lambda: False)
    assert out == {"state": "done", "result": "Reported, not checked: the main heading is Example Domain"}, out
    assert "http://shop.test/page" in seen and len(gem.client.calls) == 2


def test_through_the_manager_a_failed_browse_task_carries_the_reason_into_the_result_and_the_audit_row(make_manager, tmp_path):
    from .test_manager import done

    class Blocked(Scripted):
        def computer_step(self, goal, screenshot, history, **kw):
            self.asked += 1
            return Done(summary="FAILED: blocked", claimed_success=False)

    r = runner(Blocked([]), routed_host(serve_link), tmp_path)
    m = make_manager(browser_runner=r)
    created = m.create("go to http://shop.test/ and find the train times online", "typed")
    m.consent(created["task_id"], "allow")
    t = done(m, created["task_id"], 60)
    assert t.state == "failed" and t.reason == "The page blocked the browser."
    rows = [line for line in (tmp_path / "data" / "audit.jsonl").read_text().splitlines() if '"failed"' in line and '"task"' in line]
    assert any('"why":"blocked"' in line.replace(" ", "") for line in rows), rows


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
