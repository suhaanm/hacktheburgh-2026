#!/usr/bin/env python3
"""Pre-R0 / pre-R1 preflight for the real-click ladder. Prints PASS or FAIL for every item and exits 1 if any fails.

    # a rehearsal with a fake backend and a fake desktop (what the agent runs; nothing real is touched)
    uv run python scripts/real_click_preflight.py --fake

    # the real thing, run by the owner, in a shell where UNDERSTUDY_REAL_ACTUATOR is NOT set
    uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa python scripts/real_click_preflight.py \\
        --target TextEdit --point-px 1200 800 --attest-dnd --attest-clipboard-manager-off

The items (evals/agentic/REAL_CLICKS.md, "Preflight"):
  1  kill hotkey registered: the desktop app reports a non-empty accelerator
  2  a dry press writes data/KILL within 100 ms, and it is cleared afterwards
  3  display scale agrees: backing scale vs capture width / display width
  4  the intended point's hit test names exactly one window of the target app, and the app has exactly one window
  4b accessibility reads an AXTextArea at the point (else the R1 click is a human's call)
  4c the AppleScript read-back works and the new document is empty (Automation permission)
  5  the target region is clear: a grid over the window, every cell hits the pinned window (no Dock, banner, menu, other app)
  6  Do Not Disturb is on (the owner attests: macOS offers no reliable read)
  7  clipboard manager is off (the owner attests)
  8  UNDERSTUDY_REAL_ACTUATOR is not set in THIS process (it is set only in the process that runs the check)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "agent"))

DEBUG_URL = os.environ.get("ALONGSIDE_DEBUG_URL", "http://127.0.0.1:7777")


def http(method: str, path: str, base: str = DEBUG_URL) -> dict[str, Any]:
    req = urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read() or b"{}")


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}{('  (' + detail + ')') if detail else ''}", flush=True)

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.rows)


def preflight(*, backend: Any, target: str, point_px: tuple[int, int], kill_path: Path,
              get_hotkeys: Callable[[], dict[str, Any]], press_kill: Callable[[], None], clear_kill: Callable[[], None],
              attest_dnd: bool, attest_clipboard_off: bool, env: dict[str, str] | None = None,
              clock: Callable[[], float] = time.monotonic, grid: int = 5,
              confirm_stack: Callable[[], bool] | None = None, physical_hotkey: bool = False,
              prompt: Callable[[str], None] = print, hotkey_wait_s: float = 20.0) -> Result:
    from understudy_agent.tiers.computer_use import png_size

    env = os.environ if env is None else env
    r = Result()
    # 1 hotkey registered
    try:
        rep = get_hotkeys()
        r.add("1 kill hotkey registered", bool(rep.get("kill")), f"accelerator {rep.get('kill')!r}" if rep.get("kill") else "report.kill is empty")
    except Exception as exc:  # noqa: BLE001
        r.add("1 kill hotkey registered", False, f"could not ask the desktop app: {type(exc).__name__}")
    # 2 a dry press writes data/KILL within 100 ms and is cleared. The dry press POSTs /kill to the RUNNING stack, so the owner
    #   must confirm that this is a stack that may be stopped now (never the shared dev stack by accident).
    try:
        if confirm_stack is not None and not confirm_stack():
            r.add("2 dry press writes data/KILL within 100 ms", False, "the owner did not confirm that the running stack may be stopped")
        elif kill_path.exists():
            r.add("2 dry press writes data/KILL within 100 ms", False, "data/KILL already exists; clear it first")
        else:
            t0 = clock()
            press_kill()
            while not kill_path.exists() and clock() - t0 < 0.5:
                time.sleep(0.005)
            dt = (clock() - t0) * 1000
            appeared = kill_path.exists()
            clear_kill()
            time.sleep(0.05)
            r.add("2 dry press writes data/KILL within 100 ms", appeared and dt <= 100, f"{dt:.0f} ms" if appeared else "no file appeared")
            r.add("2b data/KILL cleared afterwards", not kill_path.exists())
    except Exception as exc:  # noqa: BLE001
        r.add("2 dry press writes data/KILL within 100 ms", False, f"{type(exc).__name__}")
    # 2p the PHYSICAL hotkey, not only the endpoint: the owner presses it now, the file must appear
    if physical_hotkey:
        prompt(f"Press Option-Shift-Command-K now (waiting up to {hotkey_wait_s:.0f} s) ...")
        t0 = clock()
        while not kill_path.exists() and clock() - t0 < hotkey_wait_s:
            time.sleep(0.01)
        appeared = kill_path.exists()
        dt = (clock() - t0) * 1000
        try:
            clear_kill()
        except Exception:  # noqa: BLE001
            pass
        r.add("2p the physical hotkey writes data/KILL", appeared, f"{dt:.0f} ms after the prompt" if appeared else "no press seen: the app may not own the shortcut")
    # 3 scale
    scale = float(backend.backing_scale())
    size = png_size(backend.screenshot_png())
    pts = float(backend.display_width_pts())
    measured = (size[0] / pts) if size and pts else 0.0
    r.add("3 display scale agrees", abs(measured - scale) <= 0.05, f"backing {scale}, measured {measured:.3f}")
    # 4 one window
    x, y = point_px[0] / scale, point_px[1] / scale
    w = backend.window_at(x, y)
    wins = getattr(backend, "all_windows_of", None) or getattr(backend, "windows_of", None)   # every window, any size or layer
    n_windows = len(wins(target)) if wins else None
    r.add("4 hit test names exactly one window of the target", bool(w and w["owner"] == target and n_windows == 1),
          f"point ({x:.0f}, {y:.0f}) pt -> {(w or {}).get('owner')!r}; {target} has {n_windows} window(s)")
    # 5 region clear
    clear, bad = True, []
    if w and w["owner"] == target:
        bx, by, bw, bh = w["bounds"]
        for i in range(grid):
            for j in range(grid):
                gx, gy = bx + bw * (i + 0.5) / grid, by + bh * (j + 0.5) / grid
                h = backend.window_at(gx, gy)
                if not h or h["owner"] != target or h.get("number") != w.get("number"):
                    clear = False
                    bad.append((h or {}).get("owner"))
    else:
        clear = False
    r.add("5 target region is clear of other windows, banners and the Dock", clear, ("covered by " + ", ".join(sorted({str(b) for b in bad}))) if bad else "")
    # 4b the accessibility tree can read the control under the point (else the R1 click is needs_human), and it is a text area
    try:
        el = backend.element_at(x, y) if hasattr(backend, "element_at") else None
    except Exception:  # noqa: BLE001
        el = None
    r.add("4b accessibility reads an AXTextArea at the point", bool(el and el.get("role") == "AXTextArea"),
          f"read role {(el or {}).get('role')!r}" if el else "unreadable: grant Accessibility and install pyobjc-framework-ApplicationServices")
    # 4c the document can be read back (Automation permission granted) and is empty
    try:
        doc = backend.read_document(target) if hasattr(backend, "read_document") else None
    except Exception:  # noqa: BLE001
        doc = None
    r.add("4c document read-back works and the document is empty", doc == "", "unreadable: grant Automation for TextEdit" if doc is None else f"{len(doc)} characters in it")
    # 6 and 7: attested
    r.add("6 Do Not Disturb is on (owner attests)", attest_dnd, "" if attest_dnd else "pass --attest-dnd after turning it on")
    r.add("7 clipboard manager is off (owner attests)", attest_clipboard_off, "" if attest_clipboard_off else "pass --attest-clipboard-manager-off")
    # 8 env var
    r.add("8 UNDERSTUDY_REAL_ACTUATOR not set in this process", env.get("UNDERSTUDY_REAL_ACTUATOR") in (None, "", "0"))
    return r


def ask_stack() -> bool:
    print("Item 2 sends POST /kill to the desktop app's debug server (port 7777): it STOPS whatever agent run is going on that "
          "stack and writes data/KILL. Run it only on a stack started for this check or in a quiet window.", flush=True)
    return input("Type YES to go on: ").strip() == "YES"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="rehearse with a fake backend and a fake desktop; nothing real is touched")
    ap.add_argument("--target", default="TextEdit")
    ap.add_argument("--point-px", nargs=2, type=int, default=[600, 300], metavar=("X", "Y"))
    ap.add_argument("--attest-dnd", action="store_true")
    ap.add_argument("--attest-clipboard-manager-off", action="store_true")
    ap.add_argument("--press-hotkey", action="store_true", help="also wait up to 20 s for the owner to press Option-Shift-Command-K")
    ap.add_argument("--yes-stack-may-be-stopped", action="store_true",
                    help="skip the question: the dry press will stop the running desktop stack (use only on a stack started for this)")
    a = ap.parse_args(argv)
    from understudy_agent.security.paths import data_dir

    kill = data_dir() / "KILL"
    if a.fake:
        import tempfile

        from understudy_agent.tiers.mac_check import DryBackend

        tmp = Path(tempfile.mkdtemp(prefix="preflight-fake-"))
        kill = tmp / "KILL"
        res = preflight(backend=DryBackend(a.target), target=a.target, point_px=tuple(a.point_px), kill_path=kill,
                        get_hotkeys=lambda: {"kill": ["Alt+Shift+Command+K"], "talk": []},
                        press_kill=lambda: kill.write_text("fake press"), clear_kill=lambda: kill.unlink(missing_ok=True),
                        attest_dnd=a.attest_dnd, attest_clipboard_off=a.attest_clipboard_manager_off, env={},
                        physical_hotkey=a.press_hotkey, hotkey_wait_s=0.2, prompt=lambda m: kill.write_text("fake physical press"))
    else:
        from understudy_agent.tiers.computer_use import QuartzBackend

        res = preflight(backend=QuartzBackend(), target=a.target, point_px=tuple(a.point_px), kill_path=kill,
                        get_hotkeys=lambda: http("GET", "/hotkeys"), press_kill=lambda: http("POST", "/kill"),
                        clear_kill=lambda: http("POST", "/kill/clear"),
                        attest_dnd=a.attest_dnd, attest_clipboard_off=a.attest_clipboard_manager_off,
                        confirm_stack=(lambda: True) if a.yes_stack_may_be_stopped else ask_stack, physical_hotkey=a.press_hotkey)
    print("\nPREFLIGHT " + ("PASSED" if res.ok else "FAILED"))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
