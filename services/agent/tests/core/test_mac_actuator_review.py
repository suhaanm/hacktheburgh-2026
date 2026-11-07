"""The real-desktop actuator after the safety review (S-03, S-05, S-06, S-07, S-08, S-10, S-13, S-14, S-18).

Everything here is a fake: a fake backend, a fake Quartz module, no desktop, no network, no model. The reviewer's own
reproducers live in evals/review/safety; these are the regression tests that stay with the code.
"""
from __future__ import annotations

import struct
import subprocess
import sys
import types
import zlib
from pathlib import Path

import pytest

from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.computer_use import (
    ActuatorRefused, ComputerUse, MacActuator, QuartzBackend, TargetRead, png_size, target_from_ax,
)

ENV_ON = {"UNDERSTUDY_REAL_ACTUATOR": "1"}


def png(w: int, h: int = 1) -> bytes:
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = (b"\x00" + b"\xff" * (w * 3)) * h
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


SANDBOX = {"owner": "TextEdit", "bounds": (100.0, 100.0, 400.0, 300.0), "layer": 0, "number": 11, "pid": 900, "title": "a.txt"}
OTHER = {"owner": "TextEdit", "bounds": (250.0, 150.0, 400.0, 300.0), "layer": 0, "number": 12, "pid": 900, "title": "b.txt"}
TEXT_AREA = {"role": "AXTextArea", "description": "text entry area"}


class Backend:
    """1000 pt wide display at scale 2. `windows` front to back. Accessibility reads come from `element`/`focus`."""

    def __init__(self, windows=None, element=TEXT_AREA, focus=TEXT_AREA):
        self.windows = windows if windows is not None else [SANDBOX]
        self.element, self.focus = element, focus
        self.events: list[tuple] = []
        self.front = "TextEdit"
        self.on_type = None
        self.released = 0
        self.stop = None

    def set_stop_check(self, fn): self.stop = fn
    def frontmost_app(self): return self.front
    def screen_locked(self): return False
    def backing_scale(self): return 2.0
    def display_width_pts(self): return 1000.0

    def window_at(self, x, y):
        for w in self.windows:
            bx, by, bw, bh = w["bounds"]
            if bx <= x < bx + bw and by <= y < by + bh:
                return w
        return None

    def windows_of(self, owner): return [w for w in self.windows if w["owner"] == owner]
    def element_at(self, x, y): return self.element(x, y) if callable(self.element) else self.element
    def focused_element(self): return self.focus
    def read_document(self, app): return ""
    def mouse(self, kind, x, y): self.events.append(("mouse", kind, x, y))
    def key(self, keys): self.events.append(("key", tuple(keys)))
    def scroll(self, dx, dy): self.events.append(("scroll", dx, dy))
    def screenshot_png(self): return png(2000, 1400)
    def release_all(self): self.released += 1

    def type_text(self, text):
        self.events.append(("type", text))
        if self.on_type:
            self.on_type(text)

    def downs(self): return [e for e in self.events if e[0] == "mouse" and e[1] == "down"]
    def typed(self): return [e[1] for e in self.events if e[0] == "type"]


def permit_for(target="TextEdit", routine=None, unattended=False, root=None):
    from understudy_agent.tiers.owner_present import grant_run_permit, issue_owner_token, real_run_description

    desc = real_run_description(target, routine)
    return grant_run_permit(issue_owner_token(desc), desc, target_app=target, routine_id=routine, unattended=unattended, consent_root=root)


def mac(be, tmp_path, **kw):
    kw.setdefault("focus_wait_s", 0.2)
    kw.setdefault("focus_poll_s", 0.005)
    kw.setdefault("permit", permit_for())
    return MacActuator("TextEdit", backend=be, kill_flag=tmp_path / "KILL", env=ENV_ON, **kw)


CLICK = Action("click", {"x": 600, "y": 500})            # (300, 250) pt


def make_guard(**kw):
    from understudy_agent.audit import AuditLog
    from understudy_agent.models.mock_provider import MockProvider
    from understudy_agent.queue import ApprovalQueue
    from understudy_agent.security.denylist import Denylist
    from understudy_agent.tiers.safety import Guard

    kw.setdefault("denylist", Denylist())
    return Guard(MockProvider(), run_id="r_mac_review", mode=kw.pop("mode", "model_driven"), audit=AuditLog(),
                 queue=ApprovalQueue(), **kw)


# ------------------------------------------------------------------ S-03: stop wins inside an action
async def test_a_stop_during_a_long_type_stops_the_remaining_chunks(tmp_path):
    stopped, be = {"v": False}, Backend()
    be.on_type = lambda t: stopped.update(v=len(be.typed()) >= 2)
    act = mac(be, tmp_path, is_cancelled=lambda: stopped["v"])
    await act.screenshot()
    await act.execute(CLICK)
    with pytest.raises(ActuatorRefused, match="stopped"):
        await act.execute(Action("type", {"text": "x" * 120}))
    assert len(be.typed()) <= 3


async def test_the_backend_polls_the_stop_check_between_characters(tmp_path):
    be = Backend()
    act = mac(be, tmp_path, is_cancelled=lambda: True)
    assert be.stop is not None and be.stop() is True           # the actuator handed the backend its stop check


async def test_the_loop_rechecks_is_current_right_before_the_action(tmp_path):
    state = {"stop": False}

    class Thinks:
        def computer_step(self, goal, shot, history, **kw):
            state["stop"] = True                              # Stop pressed while the model was thinking
            return Action("click", {"x": 10, "y": 10})

    from understudy_agent.tiers.computer_use import SimulatedActuator
    import asyncio

    sim = SimulatedActuator(targets=TargetRead("Calculate", "button"))
    cu = ComputerUse(Thinks(), sim, make_guard(), navigator="n", is_current=lambda: not state["stop"])

    async def verify():
        return True

    with pytest.raises(asyncio.CancelledError):
        await cu.run("g", verify)
    assert sim.actions == []


# ------------------------------------------------------------------ S-05: the window is pinned, not just the app
async def test_a_second_window_of_the_same_app_over_the_click_point_is_refused(tmp_path):
    be = Backend(windows=[SANDBOX])
    act = mac(be, tmp_path)
    await act.screenshot()
    await act.execute(CLICK)                                   # pins window 11
    be.windows = [OTHER, SANDBOX]                              # another TextEdit window comes to the front
    with pytest.raises(ActuatorRefused, match="not the window this run started in"):
        await act.execute(CLICK)
    n_downs = len(be.downs())
    with pytest.raises(ActuatorRefused):
        await act.execute(Action("type", {"text": "hello"}))   # typing follows the window, not the app
    assert len(be.downs()) == n_downs and be.typed() == []


async def test_two_windows_of_the_app_refuse_the_first_click(tmp_path):
    be = Backend(windows=[OTHER, SANDBOX])
    act = mac(be, tmp_path)
    await act.screenshot()
    with pytest.raises(ActuatorRefused, match="2 windows"):
        await act.execute(CLICK)
    assert be.downs() == []


# ------------------------------------------------------------------ S-07 / S-10: refuse what cannot be done; right space
@pytest.mark.parametrize("extra", [{"button": "right"}, {"hold_keys": ["cmd"]}, {"hold_keys": ["shift"]}])
async def test_unsupported_buttons_and_modifiers_are_refused_not_dropped(tmp_path, extra):
    be = Backend()
    act = mac(be, tmp_path)
    await act.screenshot()
    with pytest.raises(ActuatorRefused):
        await act.execute(Action("click", {"x": 600, "y": 500, **extra}))
    assert be.downs() == []


async def test_points_outside_the_screenshot_are_refused_and_the_loop_validates_in_the_capture_space(tmp_path):
    be = Backend(windows=[{**SANDBOX, "bounds": (-500.0, 100.0, 400.0, 300.0)}])
    act = mac(be, tmp_path)
    await act.screenshot()
    with pytest.raises(ActuatorRefused, match="negative"):
        await act.execute(Action("click", {"x": -600, "y": 500}))
    with pytest.raises(ActuatorRefused, match="outside"):
        await act.execute(Action("click", {"x": 2500, "y": 500}))
    assert be.downs() == []
    assert png_size(png(3456, 2234)) == (3456, 2234)


async def test_the_loop_takes_its_validation_size_from_the_capture(tmp_path):
    be = Backend(windows=[{**SANDBOX, "bounds": (600.0, 100.0, 300.0, 300.0)}])
    class Clicks:
        def __init__(self): self.n = 0
        def computer_step(self, goal, shot, history, **kw):
            self.n += 1
            return Action("click", {"x": 1500, "y": 500}) if self.n == 1 else Done("done", True)

    async def verify():
        return True

    act = mac(be, tmp_path)
    cu = ComputerUse(Clicks(), act, make_guard(), navigator="n", stall_limit=3)
    try:
        await cu.run("g", verify)
    except BaseException:  # noqa: BLE001
        pass
    assert be.downs(), "a click at x=1500 px of a 2000 px capture was rejected as off-screen (validated in the wrong space)"


# ------------------------------------------------------------------ S-18: the control is re-read right before the press
async def test_a_target_that_changed_before_the_press_aborts_the_click(tmp_path):
    reads = {"n": 0}

    def element(x, y):
        reads["n"] += 1
        return TEXT_AREA if reads["n"] == 1 else {"role": "AXButton", "title": "Delete"}

    be = Backend(element=element)
    act = mac(be, tmp_path)
    await act.screenshot()
    first = await act.read_target(CLICK)                      # what the gate saw
    act.expect_target(first)
    with pytest.raises(ActuatorRefused, match="not the one that was authorised"):
        await act.execute(CLICK)
    assert be.downs() == []


def test_accessibility_elements_become_gate_evidence():
    assert target_from_ax(None) is None
    assert target_from_ax({"role": "AXButton", "title": ""}) is None                      # a nameless button is unreadable
    b = target_from_ax({"role": "AXButton", "title": "Save"})
    assert b and b.label == "Save" and b.role == "button"
    pw = target_from_ax({"role": "AXTextField", "subrole": "AXSecureTextField", "secure": True})
    assert pw and pw.field_attrs["type"] == "password" and pw.label == ""                  # a secure field is recognised
    d = target_from_ax({"role": "AXButton", "title": "OK", "in_dialog": True})
    assert d and "opens_dialog" in d.structure                                            # anything in a sheet or alert is outward


# ------------------------------------------------------------------ S-06 / S-13: the real backend code against a fake Quartz
class FakeOS:
    def __init__(self): self.windows, self.posted, self.flags = [], [], []

    def win(self, owner, x, y, w, h, layer=0, alpha=1.0, number=None, pid=None):
        self.windows.append({"kCGWindowOwnerName": owner, "kCGWindowLayer": layer, "kCGWindowAlpha": alpha,
                             "kCGWindowName": "", "kCGWindowNumber": number, "kCGWindowOwnerPID": pid,
                             "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h}})


@pytest.fixture
def fake_os(monkeypatch):
    me = FakeOS()
    Q, A = types.ModuleType("Quartz"), types.ModuleType("AppKit")
    Q.kCGWindowListOptionOnScreenOnly, Q.kCGWindowListExcludeDesktopElements, Q.kCGNullWindowID = 1, 16, 0
    Q.CGWindowListCopyWindowInfo = lambda o, w: list(me.windows)
    Q.CGMainDisplayID = lambda: 1
    Q.CGDisplayBounds = lambda d: types.SimpleNamespace(size=types.SimpleNamespace(width=1000.0, height=700.0))
    Q.CGEventCreateKeyboardEvent = lambda src, k, down: {"kind": "key", "down": down, "key": k, "text": "", "flags": None}
    Q.CGEventKeyboardSetUnicodeString = lambda ev, n, s: ev.__setitem__("text", s)
    Q.CGEventSetFlags = lambda ev, f: ev.__setitem__("flags", f)
    Q.CGEventPost = lambda tap, ev: me.posted.append(ev)
    Q.kCGHIDEventTap = 0
    monkeypatch.setitem(sys.modules, "Quartz", Q)
    monkeypatch.setitem(sys.modules, "AppKit", A)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return me


@pytest.mark.parametrize("owner,layer", [("Dock", 20), ("NotificationCenter", 23), ("UserNotificationCenter", 8), ("Window Server", 24)])
def test_a_window_above_the_target_that_takes_the_click_is_reported(fake_os, owner, layer):
    fake_os.win(owner, 200, 150, 100, 100, layer=layer)
    fake_os.win("TextEdit", 100, 100, 400, 300, number=5, pid=7)
    hit = QuartzBackend().window_at(250.0, 170.0)
    assert hit and hit["owner"] == owner


def test_the_full_display_overlay_and_the_desktop_surfaces_are_not_targets(fake_os):
    fake_os.win("Understudy", 0, 0, 1000, 700, layer=25)       # the click-through overlay
    fake_os.win("Dock", 0, 0, 1000, 700, layer=-1)             # a full-display Dock surface
    fake_os.win("TextEdit", 100, 100, 400, 300, number=5, pid=7)
    fake_os.win("Ghost", 100, 100, 400, 300, alpha=0.0)        # invisible
    hit = QuartzBackend().window_at(250.0, 170.0)
    assert hit and hit["owner"] == "TextEdit" and hit["number"] == 5 and hit["pid"] == 7


def test_every_synthetic_key_and_chord_sets_its_modifier_flags_explicitly(fake_os):
    QuartzBackend().type_text("ab")
    keys = [e for e in fake_os.posted if e["kind"] == "key"]
    assert len(keys) == 4 and all(e["flags"] == 0 for e in keys)       # never the worker's held modifiers
    fake_os.posted.clear()
    QuartzBackend().key(["cmd", "a"])
    assert [e["flags"] for e in fake_os.posted] == [0x100000, 0x100000] and fake_os.posted[0]["key"] == 0
    with pytest.raises(ActuatorRefused, match="not supported"):
        QuartzBackend().key(["cmd", "f13"])


def test_the_backend_stop_check_ends_a_long_type(fake_os):
    be = QuartzBackend()
    calls = {"n": 0}
    be.set_stop_check(lambda: (calls.__setitem__("n", calls["n"] + 1) or calls["n"] > 3))
    with pytest.raises(ActuatorRefused, match="stopped"):
        be.type_text("x" * 50)
    assert len([e for e in fake_os.posted if e["kind"] == "key" and e["down"]]) == 3


# ------------------------------------------------------------------ S-08 / S-14: the check proves what it claims
async def test_mac_check_is_ok_only_when_the_document_reads_back(fake_os, monkeypatch, tmp_path):
    from understudy_agent.tiers.mac_check import run_check, run_description
    from understudy_agent.tiers.owner_present import issue_owner_token

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_REAL_ACTUATOR", "1")
    # a real run without the owner's one-time token does not start
    no_token = await run_check("TextEdit", (600, 500), "hello", real=True)
    assert no_token["ok"] is False and "owner-present" in no_token["reason"]
    # a dry run issues a token for exactly that run
    dry = await run_check("TextEdit", (600, 300), "hello", real=False)
    assert dry["ok"] is True and dry["postcondition"] == "passed" and dry["owner_token"]
    # a token for another run does not work
    other = issue_owner_token(run_description("TextEdit", (1, 1), "x"))
    assert (await run_check("TextEdit", (600, 500), "hello", real=True, owner_token=other))["ok"] is False


async def test_a_real_run_whose_document_cannot_be_read_back_is_not_ok(fake_os, monkeypatch, tmp_path):
    from understudy_agent.tiers import mac_check
    from understudy_agent.tiers.mac_check import run_check, run_description
    from understudy_agent.tiers.owner_present import issue_owner_token

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_REAL_ACTUATOR", "1")
    fake_os.win("TextEdit", 100, 100, 400, 300, number=5, pid=7)
    # a backend whose keystrokes are posted but whose document never receives them (the 7 Nov symptom)

    class Real(QuartzBackend):
        def frontmost_app(self): return "TextEdit"
        def screen_locked(self): return False
        def backing_scale(self): return 2.0
        def display_width_pts(self): return 1000.0
        def screenshot_png(self): return png(2000, 1400)
        def mouse(self, kind, x, y): pass
        def element_at(self, x, y): return TEXT_AREA
        def focused_element(self): return TEXT_AREA
        def read_document(self, app): return ""

    monkeypatch.setattr(mac_check, "MacActuator", lambda target, backend=None, env=None, **kw: MacActuator(
        target, backend=Real(), env=env, focus_wait_s=0.2, focus_poll_s=0.005, **kw))
    tok = issue_owner_token(run_description("TextEdit", (600, 500), "hello"))
    out = await run_check("TextEdit", (600, 500), "hello", real=True, owner_token=tok)
    assert out["postcondition"] == "failed" and out["ok"] is False
    assert "".join(e["text"] for e in fake_os.posted if e["kind"] == "key" and e["down"]) == "hello"


def test_an_owner_token_works_once_for_its_own_run_and_expires(tmp_path):
    from understudy_agent.tiers.owner_present import consume_owner_token, issue_owner_token

    t = issue_owner_token("run-1", root=tmp_path, now=1000.0)
    assert not consume_owner_token(t, "run-2", root=tmp_path, now=1001.0)         # another run: refused, not consumed
    assert consume_owner_token(t, "run-1", root=tmp_path, now=1001.0)
    assert not consume_owner_token(t, "run-1", root=tmp_path, now=1002.0)         # once only
    t2 = issue_owner_token("run-1", root=tmp_path, now=1000.0)
    assert not consume_owner_token(t2, "run-1", root=tmp_path, now=1000.0 + 601)  # ten minutes
    assert not consume_owner_token(None, "run-1", root=tmp_path) and not consume_owner_token("", "run-1", root=tmp_path)
    assert (tmp_path / "owner_tokens.json").stat().st_mode & 0o777 == 0o600


async def test_a_real_actuator_refuses_every_action_without_a_valid_permit_however_it_is_built(tmp_path, monkeypatch):
    from understudy_agent.offhours import FakeScreenState, run_desktop_task
    from understudy_agent.tiers.owner_present import RunPermit

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    be = Backend()
    guard = make_guard(unattended=True, routine_id="rt_nightly")

    class Model:
        def computer_step(self, goal, shot, history, **kw): return Done("done", True)

    async def ok():
        return True

    # built directly, no permit: ComputerUse -> MacActuator refuses (S-14b)
    with pytest.raises(ActuatorRefused, match="owner permit"):
        await ComputerUse(Model(), mac(be, tmp_path, permit=None), guard, navigator="n").run("g", ok)
    # a forged permit (built by hand, wrong signature) is refused too
    forged = RunPermit("TextEdit", "rt_nightly", True, 9e12, "0" * 64)
    with pytest.raises(ActuatorRefused, match="owner permit"):
        await ComputerUse(Model(), mac(be, tmp_path, permit=forged), guard, navigator="n").run("g", ok)
    # an unattended permit needs the routine's consent record
    with pytest.raises(PermissionError, match="consent"):
        permit_for(routine="rt_nightly", unattended=True, root=tmp_path / "data")
    cdir = tmp_path / "data" / "routines" / "rt_nightly"
    cdir.mkdir(parents=True)
    (cdir / "consent.json").write_text('{"mode": "unattended", "rung": "A2"}')
    good = permit_for(routine="rt_nightly", unattended=True, root=tmp_path / "data")
    # through run_desktop_task: a permit for ANOTHER routine, or an attended permit for an unattended run, is refused
    for bad in (permit_for(routine="rt_other"), permit_for(routine="rt_nightly")):
        with pytest.raises(ActuatorRefused, match="permit"):
            await run_desktop_task("g", model=Model(), guard=guard, actuator=mac(be, tmp_path, permit=bad), screen=FakeScreenState(),
                                   is_current=lambda: True, verify=ok)
    res = await run_desktop_task("g", model=Model(), guard=guard, actuator=mac(be, tmp_path, permit=good), screen=FakeScreenState(),
                                 is_current=lambda: True, verify=ok)
    assert res.outcome == "done"


async def test_r1_gives_the_owner_a_countdown_to_bring_the_target_forward(tmp_path, monkeypatch):
    from understudy_agent.tiers.mac_check import bring_forward

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    be = Backend()
    calls = {"n": 0}

    def front():
        calls["n"] += 1
        return "TextEdit" if calls["n"] >= 40 else "Terminal"           # the owner clicks TextEdit well before the last second

    be.frontmost_app = front
    assert await bring_forward(be, "TextEdit", countdown_s=1.5, poll_s=0.002) is None
    be.frontmost_app = lambda: "Terminal"                                # never brought forward
    why = await bring_forward(be, "TextEdit", countdown_s=1.2, poll_s=0.002)
    assert why and "last second" in why
    flips = {"n": 0}

    def wanders():
        flips["n"] += 1
        return "Terminal" if flips["n"] > 700 else "TextEdit"           # in front, then the owner leaves in the last second
    be.frontmost_app = wanders
    assert "last second" in await bring_forward(be, "TextEdit", countdown_s=1.5, poll_s=0.002)
    be.frontmost_app = lambda: "TextEdit"
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "KILL").write_text("x")
    assert "kill file" in await bring_forward(be, "TextEdit", countdown_s=1.5, poll_s=0.002)


# ------------------------------------------------------------------ the ladder: R0 is read-only, the preflight says PASS or FAIL
def test_r0_reads_the_real_layout_and_cannot_send_one_event(tmp_path):
    from understudy_agent.tiers.real_rungs import ReadOnlyBackend, run_r0

    be = Backend()
    ro = ReadOnlyBackend(be)
    out = run_r0("TextEdit", [(600, 500), (1500, 1300)], ro)
    assert out["scale_agrees"] and out["events"] == 0 and be.events == []
    assert out["markers"][0]["x_pt"] == 300.0 and out["markers"][0]["lands_in_target"] is True
    assert out["markers"][1]["lands_in_target"] is False and out["all_in_target"] is False
    for call in (lambda: ro.mouse("down", 1, 1), lambda: ro.type_text("x"), lambda: ro.key(["enter"]), lambda: ro.scroll(0, 5)):
        with pytest.raises(ActuatorRefused, match="read-only"):
            call()
    assert be.events == [] and len(ro.refused) == 4
    assert not hasattr(ro, "set_cursor")                       # only the named reads are forwarded


def _preflight(tmp_path, backend, **kw):
    import importlib.util

    spec = importlib.util.spec_from_file_location("preflight", Path(__file__).resolve().parents[4] / "scripts" / "real_click_preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    kill = tmp_path / "KILL"
    args = dict(backend=backend, target="TextEdit", point_px=(600, 500), kill_path=kill,
                get_hotkeys=lambda: {"kill": ["Alt+Shift+Command+K"]}, press_kill=lambda: kill.write_text("x"),
                clear_kill=lambda: kill.unlink(missing_ok=True), attest_dnd=True, attest_clipboard_off=True, env={})
    args.update(kw)
    return mod.preflight(**args)


def test_preflight_passes_on_a_clean_desktop_and_names_every_failure(tmp_path):
    assert _preflight(tmp_path, Backend()).ok
    banner = Backend(windows=[{"owner": "NotificationCenter", "bounds": (300.0, 100.0, 200.0, 80.0), "layer": 23, "number": 99}, SANDBOX])
    res = _preflight(tmp_path, banner)
    assert not res.ok and any(n.startswith("5 ") and not ok for n, ok, _ in res.rows)
    assert not _preflight(tmp_path, Backend(windows=[OTHER, SANDBOX])).ok                   # two windows: item 4
    assert not _preflight(tmp_path, Backend(), get_hotkeys=lambda: {"kill": []}).ok          # hotkey not registered
    assert not _preflight(tmp_path, Backend(), attest_dnd=False).ok
    no_ax = Backend(element=None)
    assert not _preflight(tmp_path, no_ax).ok                                              # item 4b: accessibility cannot read the point
    assert not _preflight(tmp_path, Backend(), env={"UNDERSTUDY_REAL_ACTUATOR": "1"}).ok
    slow = _preflight(tmp_path, Backend(), press_kill=lambda: None)                          # the press never writes the file
    assert not slow.ok
    assert not _preflight(tmp_path, Backend(), confirm_stack=lambda: False).ok               # the owner did not confirm the stack may be stopped
    ok_press = _preflight(tmp_path, Backend(), physical_hotkey=True, hotkey_wait_s=0.3,
                          prompt=lambda m: (tmp_path / "KILL").write_text("pressed"))        # the owner presses the real hotkey
    assert ok_press.ok and any(n.startswith("2p") and ok for n, ok, _ in ok_press.rows)
    no_press = _preflight(tmp_path, Backend(), physical_hotkey=True, hotkey_wait_s=0.15, prompt=lambda m: None)
    assert not no_press.ok and any(n.startswith("2p") and not ok for n, ok, _ in no_press.rows)


def test_r1_text_must_be_a_short_printable_ascii_word():
    from understudy_agent.tiers.mac_check import text_problem

    assert text_problem("hello") is None and text_problem("x" * 60, latency_test=True) is None
    assert text_problem("x" * 21) and text_problem("a\nb") and text_problem("tab\there") and text_problem("café") and text_problem("")


# ------------------------------------------------------------------ S-11: an approval is tagged, labelled and bound to its run
def test_the_approval_tag_binding_and_run_checks(tmp_path):
    import json

    from understudy_agent.queue import ApprovalQueue
    from understudy_agent.security.settings import Origin

    q = ApprovalQueue(tmp_path / "q")
    it = q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature="sig", run_id="r1")
    assert q.integrity(q.get(it["id"])) == "ok"
    q.approve(it["id"], origin=Origin.HUMAN_UI)
    assert not q.consume_approval(it["id"], "sig", run_id="r2")                     # another run
    assert q.try_consume_approval(it["id"], "sig", run_id="r2").code == "run_mismatch"
    p = q.root / f"{it['id']}.json"
    d = json.loads(p.read_text())
    d["signature"] = "other"
    p.write_text(json.dumps(d))                                                     # an edit outside the queue
    assert q.integrity(q.get(it["id"])) == "tampered"
    assert q.try_consume_approval(it["id"], "other", run_id="r1").code == "tampered"
    assert (tmp_path / ".queue_key").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "q" / ".queue_key").exists() is False                        # the key is NOT inside the queue folder


def test_a_tampered_pending_item_cannot_be_approved(tmp_path):
    import json

    from understudy_agent.queue import ApprovalQueue, QueueError
    from understudy_agent.security.settings import Origin

    q = ApprovalQueue(tmp_path / "q")
    it = q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature="sig", run_id="r1")
    p = q.root / f"{it['id']}.json"
    d = json.loads(p.read_text())
    d["summary"] = "something else"
    p.write_text(json.dumps(d))
    with pytest.raises(QueueError, match="modified outside"):
        q.approve(it["id"], origin=Origin.HUMAN_UI)


# ------------------------------------------------------------------ S-21, S-22, S-20, S-23
class RealWindows(QuartzBackend):
    """The REAL window-list code over the fake Quartz; the other reads are stubbed (no AppKit in the fake)."""

    def frontmost_app(self): return "TextEdit"
    def screen_locked(self): return False
    def backing_scale(self): return 2.0
    def display_width_pts(self): return 1000.0
    def screenshot_png(self): return png(2000, 1400)
    def mouse(self, kind, x, y): pass


async def test_a_small_second_window_of_the_app_counts_and_refuses_the_first_click(fake_os):
    fake_os.win("TextEdit", 280, 230, 90, 90, number=2, pid=7)                  # a find panel, under the old 10 000 pt2 floor
    fake_os.win("TextEdit", 100, 100, 400, 300, number=1, pid=7)
    assert len(QuartzBackend().windows_of("TextEdit")) == 1 and len(QuartzBackend().all_windows_of("TextEdit")) == 2
    act = MacActuator("TextEdit", backend=RealWindows(), env=ENV_ON, focus_wait_s=0.2, focus_poll_s=0.005, permit=permit_for())
    await act.screenshot()
    with pytest.raises(ActuatorRefused, match="2 windows"):
        await act.execute(Action("click", {"x": 600, "y": 520}))


@pytest.mark.parametrize("keys,literal", [(["cmd", "v"], True), (["ctrl", "v"], True), (["alt", "1"], True), (["option", "e"], True),
                                          (["shift", "insert"], True), (["cmd", "shift", "v"], True), (["cmd", "a"], False),
                                          (["cmd", "c"], False), (["Enter"], False), (["Tab"], False), (["a"], True), (["shift", "A"], True)])
def test_fact_mode_refuses_paste_and_option_character_chords(keys, literal):
    from understudy_agent.tiers.facts import key_would_type_text

    assert key_would_type_text(keys) is literal


def test_a_paste_is_a_humans_call_in_every_mode():
    from understudy_agent.security.gates import RoutineContext, TargetInfo, gate

    for mode in ("interactive", "compiled", "model_driven"):
        assert gate("key", {"keys": ["cmd", "v"]}, RoutineContext(mode=mode), TargetInfo("Notes", "textbox")).verdict == "needs_human"
    assert gate("key", {"keys": ["cmd", "a"]}, RoutineContext(mode="model_driven"), TargetInfo("Notes", "textbox")).verdict == "allow"


def test_protected_paths_are_decided_by_identity_not_spelling(tmp_path, monkeypatch):
    from understudy_agent.security.settings import SettingsGuard

    data = tmp_path / "data"
    (data / "queue").mkdir(parents=True)
    for n in (".token", "KILL", "owner_tokens.json"):
        (data / n).write_text("x")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    g = SettingsGuard()
    assert not g.check_path(data / ".token").allowed and not g.check_path(data / "queue" / "q_1.json").allowed
    assert g.check_path(tmp_path / "scratch.txt").allowed and g.check_path(data / "other.txt").allowed
    upper = tmp_path / "DATA"
    if upper.exists() and upper.samefile(data):                    # a case-insensitive volume (macOS default)
        assert not g.check_path(upper / ".TOKEN").allowed and not g.check_path(upper / "QUEUE" / "NEW.JSON").allowed
        assert not g.check_path(upper / "owner_tokens.JSON").allowed
    # a protected file that does not exist yet is still protected under its own name, and a sibling is not
    assert not g.check_path(data / "denylist.json").allowed and g.check_path(data / "denylist.txt").allowed


def test_the_owner_token_has_64_bits():
    from understudy_agent.tiers.owner_present import issue_owner_token

    assert len(issue_owner_token("x")) >= 16


# ------------------------------------------------------------------ S-30 (D30): a frame is captured and encoded in memory, never written
def test_the_real_capture_functions_never_touch_disk_or_a_helper_process():
    """Source tripwire: the real capture path has no tempfile, no subprocess, no file write and no helper program."""
    import inspect

    for fn in (QuartzBackend.screenshot_png, QuartzBackend.window_png, QuartzBackend.display_pixel_size, QuartzBackend._png_of):
        src = inspect.getsource(fn)
        for banned in ("tempfile", "TemporaryDirectory", "subprocess", "write_bytes", "write_text", "screencapture", "open("):
            assert banned not in src, f"{fn.__name__} contains {banned!r}"


def test_the_capture_is_encoded_into_memory_by_imageio_and_the_display_size_needs_no_encode(monkeypatch):
    import subprocess

    class Img:
        w, h = 3456, 2234

    class Dest:
        pass

    calls = {"final": 0}
    Q = types.ModuleType("Quartz")
    Q.CGMainDisplayID = lambda: 1
    Q.CGDisplayCreateImage = lambda d: Img()
    Q.CGImageGetWidth = lambda i: i.w
    Q.CGImageGetHeight = lambda i: i.h
    Q.CGImageDestinationCreateWithData = lambda data, uti, n, opts: (data.extend(b"") or Dest()) if uti == "public.png" else None
    Q.CGImageDestinationAddImage = lambda dest, img, opts: None
    Q.CGImageDestinationFinalize = lambda dest: calls.__setitem__("final", calls["final"] + 1) or True
    F = types.ModuleType("Foundation")

    class NSMutableData(bytearray):
        @staticmethod
        def data():
            return NSMutableData(b"\x89PNG\r\n\x1a\n")

    F.NSMutableData = NSMutableData
    monkeypatch.setitem(sys.modules, "Quartz", Q)
    monkeypatch.setitem(sys.modules, "AppKit", types.ModuleType("AppKit"))
    monkeypatch.setitem(sys.modules, "Foundation", F)

    def boom(*a, **k):
        raise AssertionError("a helper process was started")

    monkeypatch.setattr(subprocess, "run", boom)
    be = QuartzBackend()
    assert be.display_pixel_size() == (3456, 2234) and calls["final"] == 0          # the size is read without any encode
    assert be.screenshot_png().startswith(b"\x89PNG") and calls["final"] == 1       # one in-memory encode, no process, no file


def test_r0_reads_the_display_size_without_encoding_a_frame():
    from understudy_agent.tiers.real_rungs import ReadOnlyBackend, run_r0

    be = Backend()
    be.screenshot_png = lambda: (_ for _ in ()).throw(AssertionError("R0 must not encode a frame"))     # type: ignore[assignment]
    be.display_pixel_size = lambda: (2000, 1400)                                                           # type: ignore[attr-defined]
    out = run_r0("TextEdit", [(600, 500)], ReadOnlyBackend(be))
    assert out["scale_agrees"] and out["screenshot_px"] == [2000, 1400] and out["events"] == 0
