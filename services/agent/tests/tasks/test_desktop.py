"""The desktop route of a typed task, end to end with a FAKE Mac and a SCRIPTED model: no real click, key, capture or model call.

What it proves: the card (its words, its target, its schema), that a click needs a real mouse click on the card (the release route),
every reason the card is not shown (rung record, switch, permissions, model, refused apps) with the plain words and the fix, that
Allow becomes a RunPermit for ONE pinned window, that Stop and the kill file win, that an irreversible step waits in Needs you, that frames
leave only through the real-screen gate, and that a result line never says verified.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from understudy_agent.audit import AuditLog
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.security.killflag import clear_kill, set_kill
from understudy_agent.security.paths import repo_root
from understudy_agent.tasks import TaskError, desktop as dk, manager as mgr_mod, routing
from understudy_agent.tiers.computer_use import ActuatorRefused, MacActuator
from understudy_agent.tiers.mac_check import write_rung_cleared
from understudy_agent.tiers.owner_present import grant_run_permit, issue_owner_token, real_run_description

from .conftest import wait_for
from .desktop_fakes import SEND_BUTTON, FakeMac, Scripted, png, win
from .test_manager import done
from .test_schema import check_detail, check_row

ENV_ON = {"UNDERSTUDY_REAL_ACTUATOR": "1"}
CLICK = Action("click", {"x": 300, "y": 200, "button": "left"})          # the window's own pixels: (100 + 150, 100 + 100) pt on the display
TYPE = Action("type", {"text": "hello"})
ORIGIN = "http://localhost:5173"
BANNED = json.loads((repo_root() / "docs" / "knack-ux" / "banned-phrases.json").read_text())


def data_path() -> Path:
    return Path(os.environ["UNDERSTUDY_DATA_DIR"])


def clear_rung() -> None:
    """The record only the supervised first-click test writes; here it is written through that test's own writer, in the temporary data folder."""
    out = {"ok": True, "real": True, "postcondition": "passed"}
    assert write_rung_cleared(out, "TextEdit", root=data_path()) is not None


@pytest.fixture
def ready():
    clear_rung()


def real_runner(port, mac, tmp_path, **kw):
    audit = AuditLog(tmp_path / "audit.jsonl")
    kw.setdefault("countdown_s", 0.3)
    return dk.DesktopTaskRunner(lambda: port, mac, audit=audit, queue=ApprovalQueue(tmp_path / "queue", audit=audit),
                                denylist=kw.pop("denylist", Denylist()), actuator_env=ENV_ON, poll_s=0.01, focus_wait_s=0.2,
                                focus_poll_s=0.005, **kw)


def desk(make_manager, mac, runner=None, *, armed=True, **kw):
    return make_manager(desktop_env=mac, desktop_armed=lambda: armed, desktop_runner=runner, **kw)


class Spy:
    """A runner that only records how it was called."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"state": "done", "result": "Reported, not checked: spy."}

    def __call__(self, task, *, permit, progress, status, should_stop):
        self.calls.append({"permit": permit, "target": dict(task.target or {}), "text": task.text})
        return self.result


def visible_problems(text: str) -> list[str]:
    low = text.lower()
    bad = [p for p in BANNED["phrases"] if re.search(r"(?<![\w])" + re.escape(p.lower()) + r"(?![\w])", low)]
    bad += [w for w in BANNED["visible_words"] if re.search(r"(?<![\w])" + re.escape(w.lower()) + r"(?![\w])", low)]
    return bad


# ----------------------------------------------------------------------------------------------------------- the router
@pytest.mark.parametrize("text", ["help me with this form", "click the blue button", "fill this in", "fill in this form for me", "fill this out",
                                  "tick the boxes on this page", "select the second option", "press Send", "close this window",
                                  "finish this form", "enter the dates here", "rename this file in Finder", "what is this error on my screen",
                                  "scroll down and press Next"])
def test_something_on_the_screen_right_now_routes_to_desktop(text):
    got, scores = routing.decide_by_rules(text)
    assert got == "desktop", scores


@pytest.mark.parametrize("text,route", [
    ("go to bbc.co.uk and read the news", "browser"), ("look up opening hours for the Royal Mile Tesco", "browser"),
    ("find the cheapest train to Glasgow tomorrow", "browser"), ("search the web for UK benefits rates", "browser"),
    ("write a python script that renames my photos", "claude_agent"), ("fix the bug in my repo", "claude_agent"),
    ("summarise the csv in ~/Downloads/data.csv", "claude_agent"),
    ("what is the capital of Scotland?", "answer"), ("how do I convert pounds to euros", "answer"), ("explain what a gate is", "answer")])
def test_other_tasks_keep_their_routes(text, route):
    assert routing.decide_by_rules(text)[0] == route


def test_the_ambiguous_ones_still_ask():
    for text in ("do this for me", "help me with this spreadsheet cell", "sort this out for me", "can you look at my spreadsheet"):
        assert routing.decide_by_rules(text)[0] is None, text


# ----------------------------------------------------------------------------------------------------------------- card
def test_the_card_names_the_app_one_window_the_countdown_and_the_kill_keys(make_manager, ready):
    mac = FakeMac([win(title="Council tax form")])
    spy = Spy()
    m = desk(make_manager, mac, spy)
    r = m.create("help me with this form", "typed")
    assert r["route"] == "desktop" and r["summary"] == "Knack will work in the TextEdit window for this once you allow it."
    c = r["needs_consent"]
    assert c["kind"] == "desktop" and c["folder"] == "TextEdit, Council tax form"
    assert "TextEdit, Council tax form" in c["scope_text"] and "8 seconds" in c["scope_text"] and dk.KILL_HOTKEY in c["scope_text"]
    assert any("one window" in x or "that window" in x for x in c["can"]) and any(dk.KILL_HOTKEY in x for x in c["cannot"])
    assert "Work in any other window or app" in c["cannot"] and "Run while you are away" in c["cannot"]
    assert c["buttons"] == {"allow": "Allow for this task", "decline": "Not now", "more": []} and c["command_hash"] is None
    assert "click it and press Allow again" in c["cost_note"] and c["max_minutes"] == 10
    t = m.get(r["task_id"])
    assert t.state == "waiting_consent" and t.target["number"] == 11 and t.target["pid"] == 900
    assert not spy.calls and mac.events == [] and mac.captures == 0, "nothing happens before the click on the card"
    check_detail(m.detail(r["task_id"]))                                        # the card fits the closed schema
    check_row(t.row())
    for text in [c["scope_text"], *c["can"], *c["cannot"], c["cost_note"], c["folder"], *dk.FRAME_REASON_TEXT.values()]:
        assert not visible_problems(text), (text, visible_problems(text))


def test_a_long_title_still_fits_the_card_limits(make_manager, ready):
    m = desk(make_manager, FakeMac([win(owner="Microsoft PowerPoint", title="Q" * 300)]), Spy())
    c = m.create("click the blue button", "typed")["needs_consent"]
    assert len(c["scope_text"]) <= 300 and len(c["folder"]) <= 120 and all(len(x) <= 120 for x in c["can"] + c["cannot"])
    check_row(m.list_rows()[0])


def test_the_card_names_the_window_behind_knack_and_a_browser_counts_like_any_app(make_manager, ready):
    mac = FakeMac([win(owner="Knack", number=6), win(owner="Numbers", number=7, pid=71, title="Budget")])
    m = desk(make_manager, mac, Spy())
    c = m.create("click the blue button", "typed")["needs_consent"]
    assert c["folder"] == "Numbers, Budget"                                    # Knack's own window is never the one named
    mac = FakeMac([win(owner="Google Chrome", number=5, title="Inbox"), win(owner="Numbers", number=7, pid=71, title="Budget")])
    c = desk(make_manager, mac, Spy()).create("click the blue button", "typed")["needs_consent"]
    assert c["folder"] == "Google Chrome, Inbox"                               # a browser is a window like any other: the card names it


def test_not_now_starts_nothing(make_manager, ready):
    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    t = m.consent(tid, "decline")
    assert t.state == "stopped" and t.reason == "You chose not to start this." and not spy.calls and mac.events == []
    with pytest.raises(TaskError) as e:
        m.consent(tid, "allow")
    assert e.value.code == "not_waiting"
    tid = m.create("click the blue button", "typed")["task_id"]
    with pytest.raises(TaskError) as e:
        m.consent(tid, "everything")                                           # there is no "allow everything" on a screen task
    assert e.value.code == "not_offered"


# ------------------------------------------------------------------------------------- a click needs a real click on the card
@pytest.fixture
def desk_client(make_manager, monkeypatch, ready):
    monkeypatch.setenv("UNDERSTUDY_GUARD_STRICT", "1")
    from understudy_agent.server import create_app

    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    app = create_app(base_urls={"a": "http://127.0.0.1:9", "b": "http://127.0.0.1:9", "c": "http://127.0.0.1:9"}, autostart_sandbox=False, shared_sites=False)
    app.state.tasks = m
    with TestClient(app, base_url="http://127.0.0.1:7710") as c:
        c.manager, c.mac, c.spy = m, mac, spy
        c.token = (data_path() / ".token").read_text().strip()
        yield c


def test_only_a_real_mouse_click_on_the_card_can_allow_it(desk_client):
    c = desk_client
    h = {"Origin": ORIGIN, "X-Understudy-Actor": "worker", "Content-Type": "application/json"}
    r = c.post("/tasks", json={"text": "click the blue button", "source": "typed"}, headers=h)
    assert r.status_code == 201 and r.json()["needs_consent"]["kind"] == "desktop"
    tid = r.json()["task_id"]
    for actor in ("worker", "voice", "agent", "model", "tool", "page", "extension"):             # nobody but the card's own click
        r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers={**h, "X-Understudy-Actor": actor, "X-Understudy-Token": c.token})
        assert r.status_code == 403, actor
    ha = {**h, "X-Understudy-Actor": "worker_approval"}
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers=ha)
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_required"
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers={**ha, "X-Understudy-Token": "0" * 64})
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_invalid"
    assert c.manager.get(tid).state == "waiting_consent" and not c.spy.calls and c.mac.events == []
    r = c.post(f"/tasks/{tid}/consent", json={"choice": "allow"}, headers={**ha, "X-Understudy-Token": c.token})
    assert r.status_code == 200 and wait_for(lambda: c.manager.get(tid).state == "done", 10)
    assert len(c.spy.calls) == 1 and not (data_path() / "KILL").exists()


def test_creating_a_task_never_starts_one_and_stop_needs_no_token(desk_client):
    c = desk_client
    h = {"Origin": ORIGIN, "X-Understudy-Actor": "worker", "Content-Type": "application/json"}
    tid = c.post("/tasks", json={"text": "click the blue button", "source": "voice"}, headers={**h, "X-Understudy-Actor": "voice"}).json()["task_id"]
    assert c.manager.get(tid).state == "waiting_consent" and not c.spy.calls
    r = c.post(f"/tasks/{tid}/stop", json={}, headers=h)
    assert r.status_code == 200 and r.json()["state"] == "stopped" and not c.spy.calls and c.mac.events == []


def test_allow_turns_the_click_into_one_permit_for_the_pinned_window(make_manager, ready):
    mac, spy = FakeMac([win(title="Notes")]), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    assert not (data_path() / "owner_tokens.json").exists(), "no token exists until the click"
    m.consent(tid, "allow")
    t = done(m, tid)
    p = spy.calls[0]["permit"]
    assert t.state == "done" and p.valid_for("TextEdit") and p.routine_id == "task-desktop" and p.unattended is False
    assert not p.valid_for("Numbers"), "the permit is for the one app of the card"
    assert spy.calls[0]["target"]["number"] == 11 and spy.calls[0]["target"]["pid"] == 900
    assert json.loads((data_path() / "owner_tokens.json").read_text()) == {}, "the one-time token was spent by the click"
    assert tid not in m._permits


def test_a_window_the_worker_moved_to_gets_its_own_card_and_a_second_allow(make_manager, ready):
    mac, spy = FakeMac([win(title="Notes")]), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    mac.windows_list.insert(0, win(owner="Numbers", number=21, pid=77, title="Budget"))      # the worker clicked another window
    mac.front = "Numbers"
    t = m.consent(tid, "allow")
    assert t.state == "waiting_consent" and not spy.calls, "nothing starts for a window the card did not name"
    assert t.consent["folder"] == "Numbers, Budget" and "Numbers, Budget" in t.consent["scope_text"] and t.target["number"] == 21
    m.consent(tid, "allow")                                                    # the second Allow is the go-ahead for the new window
    done(m, tid)
    assert spy.calls[0]["target"]["number"] == 21 and spy.calls[0]["permit"].valid_for("Numbers")


def test_the_unclear_question_then_desktop_meets_its_own_card(make_manager, ready):
    mac = FakeMac()
    m = desk(make_manager, mac, Spy())
    tid = m.create("sort this out for me", "typed")["task_id"]
    t = m.answer(tid, "desktop")
    assert t.route == "desktop" and t.state == "waiting_consent" and t.row()["needs_consent"]["kind"] == "desktop"


def test_an_unattended_task_never_gets_this_route(make_manager, ready):
    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    r = m.create("click the blue button", "typed", attended=False)
    t = m.get(r["task_id"])
    assert t.state == "failed" and t.reason == dk.UNATTENDED.text and r["needs_consent"] is None and not spy.calls and mac.events == []


# ------------------------------------------------------------------- every reason there is no card, in plain words, with the fix
def result_of(m, text="click the blue button"):
    r = m.create(text, "typed")
    assert r["route"] == "desktop" and r["needs_consent"] is None
    return r, done(m, r["task_id"])


def test_without_the_rung_record_the_result_says_which_check_is_missing(make_manager):
    mac = FakeMac()
    m = desk(make_manager, mac, Spy())
    r, t = result_of(m)
    assert r["summary"].startswith("Knack's first supervised click test hasn't been done on this Mac")
    assert t.state == "done" and t.result == dk.RUNG_TEXT["absent"].text + " Here are the steps."
    assert t.steps[:2] == ["Open the app", "Press the button"] and mac.events == [] and mac.captures == 0
    assert "Typed tasks don't use" not in t.result and "doesn't click on your screen yet" not in t.result


@pytest.mark.parametrize("record", ["{}", "not json", '{"schema":1,"rung":"R1","at":"x","targets":["TextEdit"],"postcondition":"passed","real":true,"digest":"0"}'])
def test_a_record_that_is_not_valid_is_not_a_cleared_rung(make_manager, record):
    (data_path() / "rung_cleared.json").write_text(record)
    m = desk(make_manager, FakeMac(), Spy())
    _, t = result_of(m)
    assert t.result == dk.RUNG_TEXT["invalid"].text + " Here are the steps."


def test_the_rung_record_round_trips_through_its_own_writer_and_a_dry_run_is_not_one(tmp_path):
    assert dk.read_rung(tmp_path) == (False, "absent")
    assert write_rung_cleared({"ok": True, "real": False, "postcondition": "passed"}, "TextEdit", root=tmp_path) is None     # a dry run writes nothing
    assert dk.read_rung(tmp_path) == (False, "absent")
    write_rung_cleared({"ok": True, "real": True, "postcondition": "passed"}, "TextEdit", root=tmp_path)
    assert dk.read_rung(tmp_path) == (True, "")
    p = tmp_path / "rung_cleared.json"
    rec = json.loads(p.read_text())
    p.write_text(json.dumps({**rec, "targets": ["Terminal"]}))                  # an edit by mistake changes the digest
    assert dk.read_rung(tmp_path) == (False, "digest")


@pytest.mark.parametrize("kw,problem", [
    ({"ax": False}, dk.NO_ACCESSIBILITY), ({"ax": None}, dk.UNKNOWN_ACCESSIBILITY), ({"sr": False}, dk.NO_SCREEN), ({"sr": None}, dk.UNKNOWN_SCREEN),
    ({"helper": "pyobjc"}, dk.HELPER_MISSING)])
def test_a_missing_permission_or_helper_is_named_with_the_fix(make_manager, ready, kw, problem):
    mac = FakeMac(**kw)
    m = desk(make_manager, mac, Spy())
    r, t = result_of(m)
    assert r["summary"] == problem.text + " It will show you the steps instead."
    assert t.result == problem.text + " Here are the steps." and mac.events == [] and mac.captures == 0
    assert not visible_problems(t.result)


def test_the_accessibility_sentence_is_the_one_the_worker_is_promised(make_manager, ready):
    _, t = result_of(desk(make_manager, FakeMac(ax=False), Spy()))
    assert t.result.startswith("Knack needs Accessibility. Open System Settings, Privacy and Security, Accessibility, and switch Knack on.")


def test_a_switch_that_is_off_is_named(make_manager, ready):
    m = desk(make_manager, FakeMac(), Spy(), armed=False)
    _, t = result_of(m)
    assert t.result == dk.NOT_ARMED.text + " Here are the steps." and "UNDERSTUDY_REAL_ACTUATOR=1" in t.result


def test_a_model_that_is_not_reachable_is_named(make_manager, ready):
    m = desk(make_manager, FakeMac(), Spy(), offline=True)
    _, t = result_of(m)
    assert t.result == dk.NO_MODEL.text + " Here are the steps." or t.result == dk.NO_MODEL.text


def test_several_problems_each_get_a_line(make_manager):
    mac = FakeMac(ax=False, sr=False)
    m = desk(make_manager, mac, Spy(), armed=False)
    _, t = result_of(m)
    assert t.result.startswith(dk.RUNG_TEXT["absent"].text)
    assert f"Also needed: {dk.NOT_ARMED.label}" in t.steps


def test_both_permissions_missing_are_both_named(make_manager, ready):
    mac = FakeMac(ax=False, sr=False)
    _, t = result_of(desk(make_manager, mac, Spy()))
    assert t.result.startswith(dk.NO_ACCESSIBILITY.text) and f"Also needed: {dk.NO_SCREEN.label}" in t.steps


def test_the_mac_is_not_read_while_the_record_or_the_switch_is_missing(make_manager):
    class Untouchable(FakeMac):
        def helper_missing(self): raise AssertionError("the Mac must not be read")
        def windows(self): raise AssertionError("the Mac must not be read")

    for armed in (True, False):
        _, t = result_of(desk(make_manager, Untouchable(), Spy(), armed=armed))
        assert t.result.startswith(dk.RUNG_TEXT["absent"].text)
    clear_rung()
    _, t = result_of(desk(make_manager, Untouchable(), Spy(), armed=False))
    assert t.result.startswith(dk.NOT_ARMED.text)


def test_every_problem_sentence_fits_the_result_line_with_the_steps_note():
    problems = [*dk.RUNG_TEXT.values(), dk.NOT_ARMED, dk.HELPER_MISSING, dk.NO_ACCESSIBILITY, dk.UNKNOWN_ACCESSIBILITY, dk.NO_SCREEN, dk.UNKNOWN_SCREEN,
                dk.NO_MODEL, dk.NO_WINDOW, dk.UNATTENDED, dk.PROBE_FAILED, dk.refused_problem("Keychain Access", dk.app_refusal("Keychain Access", dk.desktop_denylist(Denylist())))]
    for p in problems:
        assert len(p.text + " Here are the steps.") <= 140, p.code
        assert len(f"Also needed: {p.label}") <= 90, p.code
        assert not visible_problems(p.text) and not visible_problems(p.label), p.code


def test_no_window_to_work_in_is_a_plain_failure(make_manager, ready):
    _, t = result_of(desk(make_manager, FakeMac([win(owner="Knack")]), Spy()))       # only Knack's own window is on screen
    assert t.result.startswith(dk.NO_WINDOW.text)


def test_a_probe_that_throws_is_a_reason_not_to_click(make_manager, ready):
    class Broken(FakeMac):
        def windows(self): raise RuntimeError("boom")

    _, t = result_of(desk(make_manager, Broken(), Spy()))
    assert t.result == dk.PROBE_FAILED.text + " Here are the steps."


# ------------------------------------------------------------------------------------ apps Knack never works in stay refused
@pytest.mark.parametrize("app", ["Keychain Access", "Passwords", "System Settings", "System Preferences", "1Password", "Bitwarden", "Claude", "Claude Code",
                                 "Knack", "Understudy"])
def test_an_app_that_holds_personal_data_is_refused_by_default(make_manager, ready, app):
    mac = FakeMac([win(owner=app, number=31)])
    spy = Spy()
    m = desk(make_manager, mac, spy)
    r = m.create("click the blue button", "typed")
    t = done(m, r["task_id"]) if r["needs_consent"] is None else None
    assert t is not None, f"{app} must not get a card"
    if app.lower() in ("knack", "understudy"):                                   # Knack's own surface is skipped, so there is no window left
        assert t.result.startswith(dk.NO_WINDOW.text)
    else:
        assert t.result.startswith(f"Knack won't work in {app}:"), t.result
    assert not spy.calls and mac.events == [] and mac.captures == 0 and not (data_path() / "owner_tokens.json").exists()


@pytest.mark.parametrize("app", ["Safari", "Google Chrome", "Firefox", "Arc", "Brave Browser", "Microsoft Edge", "Terminal", "iTerm2", "Warp"])
def test_a_browser_or_terminal_of_yours_gets_a_card_like_any_other_app(make_manager, ready, app):
    mac = FakeMac([win(owner=app, number=41, title="Work")])
    m = desk(make_manager, mac, Spy())
    r = m.create("click the blue button", "typed")
    assert r["needs_consent"] is not None, f"{app} must get a card (the owner asked for the whole computer)"
    assert r["needs_consent"]["folder"] == f"{app}, Work"
    assert mac.events == []                                                     # nothing happens until the worker's click


def test_the_refusal_names_the_app_and_the_reason_when_it_is_the_window_to_work_in():
    deny = dk.desktop_denylist(Denylist())
    assert dk.app_refusal("Keychain Access", deny) == "Knack won't work in Keychain Access: it can hold your passwords."
    assert dk.app_refusal("System Settings", deny) == "Knack won't work in System Settings: it changes your Mac's security settings."
    assert dk.app_refusal("Safari", deny) is None and dk.app_refusal("Terminal", deny) is None   # browsers and terminals are allowed (D74)
    assert dk.app_refusal("Claude", deny).startswith("Knack won't work in Claude:")
    assert dk.app_refusal("TextEdit", deny) is None and dk.app_refusal("Calculator", deny) is None
    assert dk.app_refusal("Knack", deny) == "Knack won't work in Knack: it is Knack itself."


def test_the_workers_own_denylist_is_kept_and_adds_to_the_built_in_refusals(make_manager, ready):
    Denylist([{"kind": "app", "value": "TextEdit", "why": "mine"}]).save()
    mac = FakeMac()
    m = desk(make_manager, mac, Spy())
    _, t = result_of(m)
    assert t.result.startswith("Knack won't work in TextEdit: mine.") and mac.events == []
    deny = dk.desktop_denylist(Denylist([{"kind": "app", "value": "Numbers"}]))
    assert deny.check_app("Numbers").denied and deny.check_app("Keychain Access").denied


def test_a_denylisted_app_added_after_the_card_is_refused_at_allow(make_manager, ready):
    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    Denylist([{"kind": "app", "value": "TextEdit"}]).save()
    t = m.consent(tid, "allow")
    assert t.state == "failed" and t.reason.startswith("Knack won't work in TextEdit") and not spy.calls and mac.events == []


def test_a_permission_taken_away_after_the_card_is_refused_at_allow(make_manager, ready):
    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    mac.ax = False
    t = m.consent(tid, "allow")
    assert t.state == "failed" and t.reason == dk.NO_ACCESSIBILITY.text and not spy.calls and mac.events == []
    assert not (data_path() / "owner_tokens.json").exists() or json.loads((data_path() / "owner_tokens.json").read_text()) == {}


def test_the_kill_switch_stops_a_card_from_being_allowed(make_manager, ready):
    mac, spy = FakeMac(), Spy()
    m = desk(make_manager, mac, spy)
    tid = m.create("click the blue button", "typed")["task_id"]
    set_kill("test")
    try:
        with pytest.raises(TaskError) as e:
            m.consent(tid, "allow")
        assert e.value.status == 423 and not spy.calls
    finally:
        clear_kill()


def test_only_one_screen_task_runs_at_a_time(make_manager, ready):
    import threading

    mac = FakeMac()
    hold = threading.Event()

    def slow(task, *, permit, progress, status, should_stop):
        hold.wait(5)
        return {"state": "done", "result": "Reported, not checked: slow."}

    m = desk(make_manager, mac, slow)
    a = m.create("click the blue button", "typed")["task_id"]
    b = m.create("fill this in", "typed")["task_id"]
    m.consent(a, "allow")
    try:
        with pytest.raises(TaskError) as e:
            m.consent(b, "allow")
        assert e.value.status == 429 and m.get(b).state == "waiting_consent"
    finally:
        hold.set()
    done(m, a)


# ----------------------------------------------------------------------------------------------------- the real runner, fake Mac
def test_a_scripted_run_clicks_and_types_in_the_one_window_and_reports_not_checked(make_manager, ready, tmp_path):
    mac = FakeMac([win(title="Notes")])
    port = Scripted([CLICK, TYPE], summary="Typed the word into the note")
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "done" and t.result == "Reported, not checked: Typed the word into the note", t.result
    assert mac.downs() == [("mouse", "down", 250.0, 200.0)], "the pixel (300, 200) of the window's own picture is (250, 200) on the display"
    assert mac.typed() and "".join(mac.typed()) == "hello" and mac.captures >= 2
    assert "Clicking" in t.steps and "Typing" in t.steps and t.steps[0] == "Working in TextEdit"
    assert port.frames == 3
    assert all("verified" not in s.lower() for s in t.steps) and "verified" not in (t.result or "").lower()


@pytest.mark.parametrize("said", ["Typed hello and verified it", "I double-checked and it is confirmed", "Checked: all fine"])
def test_the_result_never_repeats_a_claim_of_checking(make_manager, ready, tmp_path, said):
    mac = FakeMac()
    port = Scripted([CLICK], summary=said)
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "done" and t.result.startswith("Reported, not checked: ")
    assert not re.search(r"verif|confirm|checked:|double", t.result.split("Reported, not checked:")[1], re.I), t.result
    assert not visible_problems(t.result)


def test_a_model_that_gives_up_is_not_reported_as_a_result(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([], summary="I could not find the button", claimed=False)
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "failed" and t.reason == "Knack couldn't do that and stopped." and t.result is None and mac.events == []


def test_the_model_is_never_told_to_carry_on_after_it_says_it_is_done(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([CLICK], summary="Done")
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    done(m, tid, 30)
    assert port.frames == 2, "one action, then the claim; no nudge asks for a third frame"


def test_an_irreversible_step_waits_in_needs_you_and_is_never_clicked(make_manager, ready, tmp_path):
    mac = FakeMac(element=SEND_BUTTON)
    port = Scripted([Action("click", {"x": 300, "y": 200, "button": "left", "label": "Send"})])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "stopped" and "waiting in Needs you" in t.reason
    assert mac.downs() == [] and mac.events == [], "the send button was not pressed"
    pending = ApprovalQueue(tmp_path / "queue").list("pending")
    assert len(pending) == 1 and pending[0]["kind"] in ("irreversible_step", "outward_step")
    assert ApprovalQueue(tmp_path / "queue").list("approved") == [], "nothing is pre-approved"


def test_a_control_that_cannot_be_read_waits_for_a_human_too(make_manager, ready, tmp_path):
    mac = FakeMac(element=None)
    port = Scripted([CLICK])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "stopped" and "Needs you" in t.reason and mac.downs() == []


def test_the_kill_file_during_the_run_stops_it_before_the_next_action(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([CLICK, TYPE, TYPE], on_step=lambda n: set_kill("test") if n == 1 else None)
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    try:
        t = done(m, tid, 30)
        assert t.state == "stopped" and t.reason == "Stopped by the kill switch."
        assert len(mac.downs()) == 1 and mac.typed() == [], "the click before the kill happened; nothing after it did"
        assert mac.released >= 1
    finally:
        clear_kill()


def test_stop_from_the_screen_ends_the_run_between_events(make_manager, ready, tmp_path):
    mac = FakeMac()
    box = {}
    port = Scripted([CLICK, TYPE, TYPE], on_step=lambda n: box["m"].stop(box["tid"]) if n == 1 else None)
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    box["m"] = m
    tid = box["tid"] = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "stopped" and t.reason == "Stopped by you."
    assert len(mac.downs()) == 1 and mac.typed() == []
    assert wait_for(lambda: m.running_count() == 0, 10)


def test_stop_during_the_countdown_does_nothing_at_all(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([CLICK])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path, countdown_s=5.0))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    assert wait_for(lambda: (m.get(tid).latest or "").startswith("Starting in"), 5)
    assert dk.KILL_HOTKEY in m.get(tid).latest and "TextEdit" in m.get(tid).latest
    m.stop(tid)
    assert done(m, tid, 10).state == "stopped"
    assert wait_for(lambda: m.running_count() == 0, 10)
    assert mac.events == [] and mac.captures == 0 and port.frames == 0


def test_the_countdown_goes_only_if_the_app_is_in_front_for_its_last_second(make_manager, ready, tmp_path):
    mac = FakeMac()
    mac.front = "Numbers"                                                       # the worker never brought the window forward
    port = Scripted([CLICK])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "stopped" and "wasn't in front" in t.reason and "nothing was done" in t.reason
    assert mac.events == [] and mac.captures == 0 and port.frames == 0


def test_the_kill_file_ends_the_countdown(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([CLICK])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path, countdown_s=5.0))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    assert wait_for(lambda: (m.get(tid).latest or "").startswith("Starting in"), 5)
    set_kill("test")
    try:
        t = done(m, tid, 10)
        assert t.state in ("stopped", "failed") and mac.events == [] and port.frames == 0
    finally:
        clear_kill()


def test_a_run_without_a_permit_does_nothing(tmp_path):
    mac = FakeMac()
    runner = real_runner(Scripted([CLICK]), mac, tmp_path)
    t = type("T", (), {"task_id": "tk_0a0b0c0d", "text": "x", "max_minutes": 5, "target": dk.WindowRef("TextEdit", 11, 900, "Notes", (100.0, 100.0, 400.0, 300.0)).to_json()})()
    out = runner(t, permit=None, progress=lambda s: None, status=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and "go-ahead" in out["reason"] and mac.events == [] and mac.captures == 0


def test_a_permit_for_another_app_does_nothing(tmp_path):
    mac = FakeMac()
    desc = real_run_description("Numbers", dk.ROUTINE_ID)
    permit = grant_run_permit(issue_owner_token(desc), desc, target_app="Numbers", routine_id=dk.ROUTINE_ID)
    runner = real_runner(Scripted([CLICK]), mac, tmp_path)
    t = type("T", (), {"task_id": "tk_0a0b0c0d", "text": "x", "max_minutes": 5, "target": dk.WindowRef("TextEdit", 11, 900, "Notes", (100.0, 100.0, 400.0, 300.0)).to_json()})()
    out = runner(t, permit=permit, progress=lambda s: None, status=lambda s: None, should_stop=lambda: False)
    assert out["state"] == "failed" and mac.downs() == []


def test_the_actuator_switch_is_still_the_actuators_own(make_manager, ready, tmp_path):
    mac = FakeMac()
    runner = real_runner(Scripted([CLICK]), mac, tmp_path)
    runner.actuator_env = {}
    m = desk(make_manager, mac, runner)
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "failed" and t.reason == dk.NOT_ARMED.text and mac.events == []


# ---------------------------------------------------------------------------------------------------------- frames and gate
class Inner:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def computer_step(self, goal, screenshot, history, **kw):
        self.calls += 1
        return Done(summary="ok", claimed_success=True)


def blocked_rows():
    from understudy_engine.privacy import ledger

    return [r for r in ledger.read_all() if r.get("status") == "blocked"]


@pytest.mark.parametrize("kw,mac_kw,reason", [
    ({"unattended": True}, {}, "unattended"), ({}, {"secure": True}, "secure_input"), ({"consent": False}, {}, "no_consent")])
def test_a_closed_real_screen_gate_sends_nothing_and_writes_one_blocked_row(kw, mac_kw, reason):
    mac, inner = FakeMac(**mac_kw), Inner()
    port = dk.ScreenFramePort(inner, backend=mac, app="TextEdit", load_denylist=lambda: dk.desktop_denylist(Denylist()), **kw)
    before = len(blocked_rows())
    with pytest.raises(dk.FrameBlocked) as e:
        port.computer_step("goal", png(10, 10), [])
    assert e.value.reason == reason and inner.calls == 0 and port.blocked == [reason]
    rows = blocked_rows()[before:]
    assert len(rows) == 1 and rows[0]["reason"] == reason and rows[0]["source"] == "real_screen" and rows[0]["bytes"] == 0
    assert rows[0]["purpose"] == dk.FRAME_PURPOSE and rows[0].get("image") is None, "no frame, no hash, nothing about the picture"


def test_a_frame_never_leaves_while_a_denylisted_app_is_in_front():
    mac, inner = FakeMac(front="1Password"), Inner()
    port = dk.ScreenFramePort(inner, backend=mac, app="TextEdit", load_denylist=lambda: dk.desktop_denylist(Denylist()))
    with pytest.raises(dk.FrameBlocked) as e:
        port.computer_step("goal", png(10, 10), [])
    assert e.value.reason == "denylisted_app" and inner.calls == 0
    port2 = dk.ScreenFramePort(inner, backend=FakeMac(front="Numbers"), app="Numbers",
                               load_denylist=lambda: dk.desktop_denylist(Denylist([{"kind": "app", "value": "Numbers"}])))
    with pytest.raises(dk.FrameBlocked) as e:
        port2.computer_step("goal", png(10, 10), [])
    assert e.value.reason == "denylisted_app"


def test_an_open_gate_forwards_the_frame_and_a_backend_that_cannot_say_counts_as_secure_input():
    mac, inner = FakeMac(), Inner()
    port = dk.ScreenFramePort(inner, backend=mac, app="TextEdit", load_denylist=lambda: dk.desktop_denylist(Denylist()))
    assert port.reason() is None
    port.computer_step("goal", png(10, 10), [])
    assert inner.calls == 1 and port.sent == 1 and port.name == "fake"

    class NoSecure(FakeMac):
        secure_input = None

    unsure = dk.ScreenFramePort(inner, backend=NoSecure(), app="TextEdit", load_denylist=lambda: dk.desktop_denylist(Denylist()))
    assert unsure.reason() == "secure_input"


def test_secure_input_turning_on_mid_run_stops_the_run_before_the_next_frame(make_manager, ready, tmp_path):
    mac = FakeMac()
    port = Scripted([CLICK, TYPE], on_step=lambda n: setattr(mac, "secure", True) if n == 0 else None)
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    before = len(blocked_rows())
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "stopped" and t.reason == dk.FRAME_REASON_TEXT["secure_input"]
    assert port.frames == 1 and mac.typed() == [] and len(blocked_rows()) == before + 1


def test_the_model_sees_the_pinned_window_only_never_the_display(make_manager, ready, tmp_path):
    mac = FakeMac([win(owner="Numbers", number=9, pid=5, bounds=(0.0, 0.0, 1000.0, 600.0), title="Other app"), win(title="Notes")])
    mac.windows_list.reverse()                                                  # TextEdit in front of a big Numbers window
    mac.front = "TextEdit"
    port = Scripted([CLICK])
    m = desk(make_manager, mac, real_runner(port, mac, tmp_path))
    tid = m.create("click the blue button", "typed")["task_id"]
    m.consent(tid, "allow")
    t = done(m, tid, 30)
    assert t.state == "done" and mac.captures == 2                               # FakeMac.screenshot_png raises if the display were captured


# --------------------------------------------------------------------------------- the actuator with a window pinned from the start
def permit_for(app="TextEdit"):
    desc = real_run_description(app, dk.ROUTINE_ID)
    return grant_run_permit(issue_owner_token(desc), desc, target_app=app, routine_id=dk.ROUTINE_ID)


def pinned_actuator(mac, tmp_path, **kw):
    return MacActuator("TextEdit", backend=mac, kill_flag=tmp_path / "KILL", env=ENV_ON, permit=permit_for(), pinned_window=win(), window_capture=True,
                       focus_wait_s=0.2, focus_poll_s=0.005, **kw)


async def test_a_window_pinned_from_the_start_maps_its_own_pixels_and_refuses_a_window_that_moved(tmp_path):
    mac = FakeMac([win(), win(number=12, bounds=(300.0, 150.0, 400.0, 300.0), title="Second")])        # two windows of the app are fine: one is pinned
    act = pinned_actuator(mac, tmp_path)
    shot = await act.screenshot()
    assert act.report["pinned_window"] == {"number": 11, "pid": 900} and mac.captures == 1 and act.report["scale_check"]["agree"]
    assert shot[:8] == b"\x89PNG\r\n\x1a\n"
    await act.execute(CLICK)
    assert mac.downs() == [("mouse", "down", 250.0, 200.0)]
    mac.windows_list[0] = win(bounds=(160.0, 100.0, 400.0, 300.0))                 # the window moved after the picture was taken
    with pytest.raises(ActuatorRefused, match="moved"):
        await act.execute(CLICK)
    assert len(mac.downs()) == 1


async def test_a_click_that_lands_on_another_window_of_the_same_app_is_refused(tmp_path):
    other = win(number=12, bounds=(150.0, 150.0, 400.0, 300.0), title="Second")
    mac = FakeMac([other, win()])                                                  # the second window covers the point (250, 200)
    act = pinned_actuator(mac, tmp_path)
    await act.screenshot()
    with pytest.raises(ActuatorRefused, match="not the window this run started in"):
        await act.execute(CLICK)
    assert mac.downs() == []


async def test_the_pinned_window_going_away_is_refused(tmp_path):
    mac = FakeMac()
    act = pinned_actuator(mac, tmp_path)
    mac.windows_list = []
    with pytest.raises(ActuatorRefused, match="no longer on screen"):
        await act.screenshot()


async def test_window_capture_needs_a_window_and_a_permit(tmp_path):
    with pytest.raises(ActuatorRefused, match="needs the pinned window"):
        MacActuator("TextEdit", backend=FakeMac(), env=ENV_ON, window_capture=True)
    act = MacActuator("TextEdit", backend=FakeMac(), env=ENV_ON, pinned_window=win(), window_capture=True, kill_flag=tmp_path / "KILL")
    with pytest.raises(ActuatorRefused, match="owner permit"):
        await act.screenshot()


async def test_the_display_actuator_path_is_unchanged(tmp_path):
    class Display(FakeMac):
        def screenshot_png(self):
            return png(2000, 1400)

    mac = Display()
    act = MacActuator("TextEdit", backend=mac, kill_flag=tmp_path / "KILL", env=ENV_ON, permit=permit_for(), focus_wait_s=0.2, focus_poll_s=0.005)
    await act.screenshot()
    await act.execute(Action("click", {"x": 600, "y": 500}))
    assert mac.downs() == [("mouse", "down", 300.0, 250.0)] and act.report["pinned_window"] == {"number": 11, "pid": 900}


# ----------------------------------------------------------------------------------------------------------- misc wording
def test_a_secret_in_the_request_is_not_started(make_manager, ready):
    m = desk(make_manager, FakeMac(), Spy())
    r = m.create("click the blue button and type password: hunter2hunter2", "typed")
    t = m.get(r["task_id"])
    assert r["route"] == "desktop" and t.state == "failed" and "key or a password" in t.reason and r["needs_consent"] is None


def test_plain_reasons_never_echo_the_actuators_own_words():
    for raw in ("frontmost app is 'Secret App', not 'TextEdit'", "kill flag present", "the run was stopped (supervisor stop or a human took over)",
                "screen is locked or asleep", "action budget used up", "scale disagreement: backing scale 2.0", "some other thing with /Users/me/secret"):
        out = dk._plain_reason(raw)
        assert "Secret" not in out and "/Users" not in out and not visible_problems(out) and len(out) <= 160
