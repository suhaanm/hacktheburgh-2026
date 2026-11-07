"""Shared fakes for the review reproducers. FakeBackend implements the MacBackend protocol of tiers/computer_use.py."""
from __future__ import annotations

from conftest import png_of_width
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.computer_use import MacActuator, TargetRead

ENV_ON = {"UNDERSTUDY_REAL_ACTUATOR": "1"}


class FakeBackend:
    """A 1000 pt wide display at scale 2 (screenshots are 2000 px wide). `windows` is front-to-back: dicts with owner, bounds."""

    def __init__(self, front="TextEdit", backing=2.0, shot_scale=2.0, windows=None):
        self.front, self.backing, self.shot_scale = front, backing, shot_scale
        self.windows = windows if windows is not None else [
            {"owner": "TextEdit", "bounds": (100.0, 100.0, 400.0, 300.0), "layer": 0}]
        self.events: list[tuple] = []
        self.on_type = None          # callable(text) run after each typed chunk
        self.released = 0

    def frontmost_app(self): return self.front
    def screen_locked(self): return False
    def backing_scale(self): return self.backing
    def display_width_pts(self): return 1000.0

    def window_at(self, x, y):
        for w in self.windows:
            bx, by, bw, bh = w["bounds"]
            if bx <= x < bx + bw and by <= y < by + bh:
                return w
        return None

    def windows_of(self, owner):          # the real QuartzBackend has this; MacActuator uses it to refuse an ambiguous first click
        return [w for w in self.windows if w["owner"] == owner and w.get("layer", 0) == 0]

    def mouse(self, kind, x, y): self.events.append(("mouse", kind, x, y))
    def key(self, keys): self.events.append(("key", tuple(keys)))
    def scroll(self, dx, dy): self.events.append(("scroll", dx, dy))
    def screenshot_png(self): return png_of_width(int(1000 * self.shot_scale))
    def release_all(self): self.released += 1

    def type_text(self, text):
        self.events.append(("type", text))
        if self.on_type:
            self.on_type(text)

    def typed_chunks(self): return [e[1] for e in self.events if e[0] == "type"]
    def downs(self): return [e for e in self.events if e[0] == "mouse" and e[1] == "down"]


def permit(target="TextEdit"):
    """A RunPermit the way an entry point gets one: the owner's one-time token consumed for this run (S-14b: MacActuator refuses without one)."""
    from understudy_agent.tiers.owner_present import grant_run_permit, issue_owner_token

    desc = f"review-test|{target}"
    return grant_run_permit(issue_owner_token(desc), desc, target_app=target)


class TrustedMac(MacActuator):
    """MacActuator plus a reader that answers like a working AX lookup (a plain 'Continue' button), so the S-01 fix
    (unreadable target -> human) cannot mask the layer a reproducer is about. Controls prove the action path is reachable."""

    async def read_target(self, action):
        return TargetRead("Continue", "button", None, None)


def mac(backend, tmp_path, **kw):
    kw.setdefault("focus_wait_s", 0.2)
    kw.setdefault("focus_poll_s", 0.005)
    if kw.pop("no_permit", False):
        return TrustedMac("TextEdit", backend=backend, kill_flag=tmp_path / "KILL", env=ENV_ON, **kw)
    kw.setdefault("permit", permit())
    return TrustedMac("TextEdit", backend=backend, kill_flag=tmp_path / "KILL", env=ENV_ON, **kw)


class Scripted:
    """A computer-use model that replays a script (the last item repeats); `before` runs inside each model call."""
    name = "scripted"

    def __init__(self, *acts, before=None):
        self.acts, self.before, self.n = list(acts), before, 0

    def computer_step(self, goal, shot, history, **kw):
        if self.before:
            self.before(self.n)
        self.n += 1
        return self.acts[min(self.n - 1, len(self.acts) - 1)]


def make_guard(**kw):
    from understudy_agent.audit import AuditLog
    from understudy_agent.models.mock_provider import MockProvider
    from understudy_agent.queue import ApprovalQueue
    from understudy_agent.security.denylist import Denylist
    from understudy_agent.tiers.safety import Guard

    kw.setdefault("denylist", Denylist())
    return Guard(MockProvider(), run_id="r_review", mode=kw.pop("mode", "model_driven"), audit=AuditLog(), queue=ApprovalQueue(), **kw)


async def always_true():
    return True
