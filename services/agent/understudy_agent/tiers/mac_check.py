"""Owner-supervised check for the real desktop actuator (spike S2 follow-up). Harmless apps only.

    # 1. dry run: goes through the safety pipeline and the actuator guards with a FAKE backend; nothing happens.
    #    It prints a one-time owner token for exactly this target, point and text.
    uv run python -m understudy_agent.tiers.mac_check --target TextEdit --click-px 600 300 --text "hello"

    # 2. real run, owner present, TextEdit frontmost with ONE empty window (needs pyobjc; see scripts/s2_textedit_test.py).
    #    Paste the token from step 1; it works once, for this run only, for ten minutes.
    UNDERSTUDY_REAL_ACTUATOR=1 uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa \\
        --with pyobjc-framework-ApplicationServices \\
        python -m understudy_agent.tiers.mac_check --real --owner-present <TOKEN> --target TextEdit --click-px 1200 800 --text "hello"

Every event goes: observe_screen -> trusted target read (accessibility) -> SafetyPipeline.authorise (kill flag, typed
action, denylist, gate, data flow) -> MacActuator guards (kill flag, window pin, locked screen, frontmost app, budgets) ->
backend. Only TextEdit and Calculator are accepted as targets here.

`ok` is true ONLY when the post-condition passes: after typing, the document's text is read back through the OS by this
code (AppleScript, for TextEdit) and must equal what was typed. Guards alone never produce ok:true (the 7 Nov symptom was
ok:true with an empty document).

Stopping a real run: `touch <data>/KILL` (the path is printed first), or press Ctrl-C, or type k then Enter here. All three
set the same kill file, which the actuator polls between every typed character, and release every held key and button.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from ..audit import AuditLog
from ..models.mock_provider import MockProvider
from ..models.port import Action
from ..queue import ApprovalQueue
from ..security.denylist import Denylist
from ..security.killflag import is_killed, kill_path, set_kill
from ..security.paths import data_dir
from .computer_use import ActuatorRefused, MacActuator, TargetRead, blank_png, merge_reads
from .owner_present import RunPermit, grant_run_permit, issue_owner_token
from .safety import Guard

HARMLESS = {"TextEdit", "Calculator"}


class DryBackend:
    """Same interface as the real backend; records instead of acting. A fake 'TextEdit' window sits at
    (150, 100) 300x180 pt on an 864 x 558 pt display (scale 2); everything else belongs to 'Claude'. The fake
    document receives what is typed, so the post-condition read-back has something to read."""

    def __init__(self, front: str, scale: float = 2.0) -> None:
        self.front, self.scale = front, scale
        self.events: list[tuple] = []
        self.doc = ""

    def frontmost_app(self) -> str: return self.front
    def screen_locked(self) -> bool: return False
    def backing_scale(self) -> float: return self.scale
    def display_width_pts(self) -> float: return 864.0

    def window_at(self, x: float, y: float) -> dict[str, Any] | None:
        if 150 <= x < 450 and 100 <= y < 280:
            return {"owner": "TextEdit", "bounds": (150.0, 100.0, 300.0, 180.0), "layer": 0, "number": 4001, "pid": 4242}
        return {"owner": "Claude", "bounds": (0.0, 0.0, 864.0, 558.0), "layer": 0, "number": 1, "pid": 1}

    def windows_of(self, owner: str) -> list[dict[str, Any]]:
        return [self.window_at(200, 150)] if owner == "TextEdit" else []

    def element_at(self, x: float, y: float) -> dict[str, Any] | None:
        w = self.window_at(x, y)
        return {"role": "AXTextArea", "title": None, "description": "text entry area"} if w and w["owner"] == "TextEdit" else None

    def focused_element(self) -> dict[str, Any] | None:
        return {"role": "AXTextArea", "title": None, "description": "text entry area"}

    def mouse(self, kind: str, x: float, y: float) -> None: self.events.append(("mouse", kind, x, y))

    def type_text(self, text: str) -> None:
        self.events.append(("type", len(text)))
        self.doc += text

    def key(self, keys: list[str]) -> None: self.events.append(("key", tuple(keys)))
    def scroll(self, dx: int, dy: int) -> None: self.events.append(("scroll", dx, dy))

    def screenshot_png(self) -> bytes:
        return blank_png(int(864 * self.scale), int(558 * self.scale))

    def read_document(self, app: str) -> str | None:
        return self.doc

    def release_all(self) -> None: self.events.append(("release_all",))


def run_description(target: str, click_px: tuple[int, int], text: str) -> str:
    return f"mac_check|{target}|{click_px[0]},{click_px[1]}|{text}"


R1_MAX_ACTIONS = 6          # R1: one screenshot, one click, one type, with room to spare
R1_TIME_BUDGET_S = 60.0
R1_MAX_TEXT = 20
LATENCY_MAX_TEXT = 60       # the separate kill-latency run only


def text_problem(text: str, *, latency_test: bool = False) -> str | None:
    """R1 types a short word of LETTERS ONLY (no digits, punctuation, spaces, newline or tab: TextEdit's smart quotes and
    autocorrect can alter anything else, which would make the read-back fail closed), at most 20 letters (60 for the latency run)."""
    cap = LATENCY_MAX_TEXT if latency_test else R1_MAX_TEXT
    if not text or len(text) > cap:
        return f"the text must be 1 to {cap} letters"
    if not text.isascii() or not text.isalpha():
        return "the text must be letters a to z only (no digits, punctuation, spaces, newline or tab)"
    return None


async def bring_forward(backend: Any, target: str, *, countdown_s: float, poll_s: float = 0.1) -> str | None:
    """The owner types the command in another app (a terminal, the Claude app). A visible countdown, polled every 100 ms, gives
    them time to bring the target to the front and take their hands off. The kill file ends it at once; if the front app is
    not the target for the whole LAST SECOND (or at the end, for a short countdown), nothing is done. Returns None to go."""
    t, shown = 0.0, -1
    front = backend.frontmost_app()
    while t < countdown_s:
        if kill_path().exists():
            return "the kill file appeared during the countdown; nothing was done"
        front = backend.frontmost_app()
        if t >= countdown_s - 1.0 and front != target:
            return f"{target} was not in front during the last second of the countdown (front app: {front!r}); nothing was done"
        left = int(countdown_s - t) + 1
        if left != shown:
            shown = left
            print(f"bring {target} to the front and keep your hands off: starting in {left} ...", flush=True)
        await asyncio.sleep(poll_s)
        t += poll_s
    front = backend.frontmost_app()
    if front != target:
        return f"{target} is not in front (front app: {front!r}); nothing was done"
    return None


async def run_check(target: str, click_px: tuple[int, int], text: str, *, real: bool,
                    owner_token: str | None = None, latency_test: bool = False, countdown_s: float | None = None) -> dict[str, Any]:
    if target not in HARMLESS:
        return {"ok": False, "reason": f"{target!r} is not a harmless target; use one of {sorted(HARMLESS)}"}
    if (bad := text_problem(text, latency_test=latency_test)) is not None:
        return {"ok": False, "reason": bad}
    desc = run_description(target, click_px, text)
    if real and is_killed():
        return {"ok": False, "reason": f"the kill file {kill_path()} is already set; clear it first"}
    try:
        # the real actuator carries a permit made by consuming the token; a dry run mints and spends its own (nothing real)
        permit: RunPermit = grant_run_permit(owner_token if real else issue_owner_token(desc), desc, target_app=target)
    except PermissionError:
        return {"ok": False, "reason": "a real run needs --owner-present <token> from a dry run of the SAME command "
                                       "(one use, ten minutes); none given, or it was used, expired or issued for another run"}
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
        act = MacActuator(target, backend=backend, env=env, max_actions=R1_MAX_ACTIONS, time_budget_s=R1_TIME_BUDGET_S,
                          permit=permit)
    except (ActuatorRefused, ImportError) as exc:
        return {"ok": False, "reason": str(exc)}
    if real:
        print(f"real run started. To stop it: touch {kill_path()}  (or Ctrl-C, or type k then Enter).", flush=True)
    log: list[dict[str, Any]] = []
    try:
        if real:
            front = await bring_forward(act.backend, target, countdown_s=8.0 if countdown_s is None else countdown_s)
            if front is not None:
                return {"ok": False, "reason": front}
        shot = await act.screenshot()  # verifies the display scale before any pointer action
        from .computer_use import png_size

        size = png_size(shot) or (click_px[0] * 2 + 1000, click_px[1] * 2 + 1000)
        for action in (Action("click", {"x": click_px[0], "y": click_px[1]}), Action("type", {"text": text})):
            pobs = guard.observe_screen()
            tr = await act.read_target(action)          # what the accessibility tree says is there, not what we hope
            dec = guard.authorise(action, pobs, screen=size, app=target,
                                  label=tr.label if tr else None, role=tr.role if tr else None,
                                  field_attrs=tr.field_attrs if tr else None, structure=tr.structure if tr else ())
            log.append({"action": action.kind, "verdict": dec.verdict, "codes": dec.codes,
                        "target_read": tr is not None})
            if not dec.allowed:
                return {"ok": False, "reason": "the safety pipeline did not allow the action", "log": log}
            act.expect_target(tr)
            await act.execute(Action(dec.action.kind, dict(dec.action.args)))  # type: ignore[union-attr]
            guard.record(dec, True)
    except ActuatorRefused as exc:
        return {"ok": False, "reason": f"actuator guard: {exc}", "log": log, "report": act.report}
    finally:
        await act.release_all()
    # the post-condition: read the document back through the OS, with this code, not the model
    post, got = "unavailable", None
    reader = getattr(act.backend, "read_document", None)
    if callable(reader):
        try:
            got = await asyncio.to_thread(reader, target)
        except Exception:  # noqa: BLE001 - any failure to read back is "not proven"
            got = None
    if got is not None:
        post = "passed" if got.strip() == text.strip() else "failed"
    out: dict[str, Any] = {"ok": post == "passed", "real": real, "scale": act.scale, "log": log, "report": act.report,
                           "postcondition": post, "postcondition_source": "fake backend" if not real else "AppleScript read-back"}
    if post != "passed":
        out["reason"] = ("the document could not be read back, so nothing is proven" if post == "unavailable"
                         else f"the document text does not match what was typed ({len(got or '')} vs {len(text)} characters)")
    if backend is not None:
        out["events"] = [list(e) for e in backend.events]
        out["owner_token"] = issue_owner_token(desc)      # a dry run hands the owner the token for the real run
    return out


def write_rung_cleared(out: dict[str, Any], target: str, *, root: Path | None = None, now: float | None = None) -> Path | None:
    """The persisted rung record (data/rung_cleared.json) that Knack's `do_it_for_me` reads before it ever offers a click. Written ONLY here,
    ONLY for a REAL run that passed its read-back (`ok`, `real` and `postcondition == "passed"`, which needs the owner's one-time token), and never
    by a dry run. It lists the target the supervised check cleared (R1: TextEdit). Counts and enums only. The digest matches
    apps/desktop/src/main/wake/rung.ts (`rungDigest`): it catches an edit by mistake, not by someone who can run code as the owner."""
    import hashlib
    import os
    import time as _time
    from datetime import datetime, timezone

    if not (out.get("ok") is True and out.get("real") is True and out.get("postcondition") == "passed"):
        return None
    t = _time.time() if now is None else now
    at = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = {"schema": 1, "rung": "R1", "at": at, "targets": [target], "postcondition": "passed", "real": True}
    material = f"1|R1|{at}|{','.join(sorted(rec['targets']))}|passed|true"  # type: ignore[arg-type]
    rec["digest"] = hashlib.sha256(material.encode()).hexdigest()
    path = (root or data_dir()) / "rung_cleared.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, path)
    return path


def _install_kill_paths() -> None:
    """Ctrl-C and `k` + Enter set the same kill file the actuator polls between characters."""
    def stop(*_: Any) -> None:
        set_kill("mac_check: stopped from the terminal")

    signal.signal(signal.SIGINT, stop)

    def watch() -> None:
        for line in sys.stdin:
            if line.strip().lower() == "k":
                stop()
                return

    threading.Thread(target=watch, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="TextEdit")
    ap.add_argument("--click-px", nargs=2, type=int, required=True, metavar=("X", "Y"))
    ap.add_argument("--text", default="Understudy check")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--owner-present", default=None, metavar="TOKEN", help="one-time token printed by a dry run")
    ap.add_argument("--latency-test", action="store_true", help="allow up to 60 characters, to time the kill hotkey mid-type")
    ap.add_argument("--countdown", type=float, default=8.0, help="seconds to bring the target app to the front (real runs)")
    a = ap.parse_args(argv)
    if a.real:
        print(f"kill file: {kill_path()}", flush=True)
        _install_kill_paths()
    out = asyncio.run(run_check(a.target, (a.click_px[0], a.click_px[1]), a.text, real=a.real, owner_token=a.owner_present,
                                latency_test=a.latency_test, countdown_s=a.countdown))
    if a.real and (written := write_rung_cleared(out, a.target)) is not None:
        out["rung_cleared"] = str(written)
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
