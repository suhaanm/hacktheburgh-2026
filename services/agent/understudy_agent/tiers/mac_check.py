"""Owner-supervised check for the real desktop actuator (spike S2 follow-up). Harmless apps only.

    # dry run: goes through the safety pipeline and the actuator guards with a FAKE backend; nothing happens
    uv run python -m understudy_agent.tiers.mac_check --target TextEdit --click-px 600 300 --text "hello"

    # real run, owner present, TextEdit frontmost (needs pyobjc; see scripts/s2_textedit_test.py for the flags)
    UNDERSTUDY_REAL_ACTUATOR=1 uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa \\
        python -m understudy_agent.tiers.mac_check --real --target TextEdit --click-px 1200 800 --text "hello"

Every event goes: observe_screen -> SafetyPipeline.authorise (kill flag, typed action, denylist, gate, data flow)
-> MacActuator guards (kill flag, locked screen, frontmost app, budgets) -> backend. Only TextEdit and Calculator
are accepted as targets here.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ..audit import AuditLog
from ..models.mock_provider import MockProvider
from ..models.port import Action
from ..queue import ApprovalQueue
from ..security.denylist import Denylist
from .computer_use import ActuatorRefused, MacActuator
from .safety import Guard

HARMLESS = {"TextEdit", "Calculator"}


class DryBackend:
    """Same interface as the real backend; records instead of acting. A fake 'TextEdit' window sits at
    (150, 100) 300x180 pt on an 864 x 558 pt display (scale 2); everything else belongs to 'Claude'."""

    def __init__(self, front: str, scale: float = 2.0) -> None:
        self.front, self.scale = front, scale
        self.events: list[tuple] = []

    def frontmost_app(self) -> str: return self.front
    def screen_locked(self) -> bool: return False
    def backing_scale(self) -> float: return self.scale
    def display_width_pts(self) -> float: return 864.0

    def window_at(self, x: float, y: float) -> dict[str, Any] | None:
        if 150 <= x < 450 and 100 <= y < 280:
            return {"owner": "TextEdit", "bounds": (150.0, 100.0, 300.0, 180.0), "layer": 0}
        return {"owner": "Claude", "bounds": (0.0, 0.0, 864.0, 558.0), "layer": 0}

    def mouse(self, kind: str, x: float, y: float) -> None: self.events.append(("mouse", kind, x, y))
    def type_text(self, text: str) -> None: self.events.append(("type", len(text)))
    def key(self, keys: list[str]) -> None: self.events.append(("key", tuple(keys)))
    def scroll(self, dx: int, dy: int) -> None: self.events.append(("scroll", dx, dy))

    def screenshot_png(self) -> bytes:
        from .computer_use import blank_png

        return blank_png(int(864 * self.scale), 40)

    def release_all(self) -> None: self.events.append(("release_all",))


async def run_check(target: str, click_px: tuple[int, int], text: str, *, real: bool) -> dict[str, Any]:
    if target not in HARMLESS:
        return {"ok": False, "reason": f"{target!r} is not a harmless target; use one of {sorted(HARMLESS)}"}
    guard = Guard(MockProvider(), run_id="r_mac_check", mode="interactive", audit=AuditLog(), queue=ApprovalQueue(),
                  denylist=Denylist.load())
    launch = guard.pipe.authorise_launch(target)
    if not launch.allowed:
        return {"ok": False, "reason": f"launch refused: {launch.verdict} {launch.codes}"}
    backend: Any = None
    if not real:
        backend = DryBackend(target)
    import os

    env = dict(os.environ) if real else {"UNDERSTUDY_REAL_ACTUATOR": "1"}
    try:
        act = MacActuator(target, backend=backend, env=env)
    except (ActuatorRefused, ImportError) as exc:
        return {"ok": False, "reason": str(exc)}
    log: list[dict[str, Any]] = []
    try:
        await act.screenshot()  # verifies the display scale before any pointer action
        for action in (Action("click", {"x": click_px[0], "y": click_px[1]}), Action("type", {"text": text})):
            pobs = guard.observe_screen()
            dec = guard.authorise(action, pobs, screen=(int(click_px[0] * 2 + 1000), int(click_px[1] * 2 + 1000)))
            log.append({"action": action.kind, "verdict": dec.verdict, "codes": dec.codes})
            if not dec.allowed:
                return {"ok": False, "reason": "the safety pipeline did not allow the action", "log": log}
            await act.execute(Action(dec.action.kind, dict(dec.action.args)))  # type: ignore[union-attr]
            guard.record(dec, True)
    except ActuatorRefused as exc:
        return {"ok": False, "reason": f"actuator guard: {exc}", "log": log, "report": act.report}
    finally:
        await act.release_all()
    out: dict[str, Any] = {"ok": True, "real": real, "scale": act.scale, "log": log, "report": act.report}
    if backend is not None:
        out["events"] = [list(e) for e in backend.events]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="TextEdit")
    ap.add_argument("--click-px", nargs=2, type=int, required=True, metavar=("X", "Y"))
    ap.add_argument("--text", default="Understudy check")
    ap.add_argument("--real", action="store_true")
    a = ap.parse_args(argv)
    out = asyncio.run(run_check(a.target, (a.click_px[0], a.click_px[1]), a.text, real=a.real))
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
