#!/usr/bin/env python3
"""Spike S2: one real click and one line of typing in TextEdit (harmless app), owner present.

Measures: Retina scale, screenshot-pixel -> point mapping error, click and typing latency.
Safety: only ever types if TextEdit is the frontmost app; aborts otherwise. Touches nothing else.
Closes its own document without saving, and quits TextEdit only if this script launched it.

Run (owner watching, hands off keyboard and mouse for ~15 s):
  uv run --no-project --python 3.12 --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa \
     --with pyobjc-framework-ApplicationServices python scripts/s2_textedit_test.py [--dry]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

DRY = "--dry" in sys.argv
TEXT = "Understudy S2 spike OK"
OUT = Path(__file__).resolve().parent.parent / "data" / "s2"
OUT.mkdir(parents=True, exist_ok=True)


def osa(script: str, timeout: float = 20.0) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def frontmost() -> str:
    from AppKit import NSWorkspace

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return str(app.localizedName()) if app else ""


def pointer() -> tuple[float, float]:
    from Quartz import CGEventCreate, CGEventGetLocation

    p = CGEventGetLocation(CGEventCreate(None))
    return (float(p.x), float(p.y))


def mouse(kind, x: float, y: float) -> None:
    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap, kCGMouseButtonLeft

    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kind, (x, y), kCGMouseButtonLeft))


def type_text(s: str) -> None:
    from Quartz import CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString, CGEventPost, kCGHIDEventTap

    for ch in s:
        for down in (True, False):
            ev = CGEventCreateKeyboardEvent(None, 0, down)
            CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            CGEventPost(kCGHIDEventTap, ev)
            time.sleep(0.012)


def png_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], capture_output=True, text=True).stdout
    w = int([l for l in out.splitlines() if "pixelWidth" in l][0].split()[-1])
    h = int([l for l in out.splitlines() if "pixelHeight" in l][0].split()[-1])
    return w, h


def main() -> int:
    from Quartz import (
        CGDisplayBounds,
        CGMainDisplayID,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventMouseMoved,
    )

    res: dict = {"dry_run": DRY, "steps": []}
    t_all = time.time()
    was_running = subprocess.run(["pgrep", "-x", "TextEdit"], capture_output=True).returncode == 0
    res["textedit_was_running"] = was_running
    b = CGDisplayBounds(CGMainDisplayID())
    pts_w, pts_h = int(b.size.width), int(b.size.height)

    if DRY:
        print(json.dumps({"dry": True, "would": ["open TextEdit", "new document", "bounds 300,200,900,560",
                                                  "screenshot", "click window centre", f"type '{TEXT}'", "read back text",
                                                  "close without saving"], "display_points": [pts_w, pts_h]}, indent=2))
        return 0

    # 1. Launch TextEdit with a fresh document in a known place.
    subprocess.run(["open", "-a", "TextEdit"], check=True)
    time.sleep(1.2)
    osa('tell application "TextEdit" to make new document')
    osa('tell application "TextEdit" to set bounds of window 1 to {300, 200, 900, 560}')
    osa('tell application "TextEdit" to activate')
    time.sleep(0.8)
    res["frontmost_after_launch"] = frontmost()
    if res["frontmost_after_launch"] != "TextEdit":
        res["aborted"] = "TextEdit is not frontmost; nothing was clicked or typed"
        print(json.dumps(res, indent=2))
        return 2

    # 2. Screenshot: Retina scale and coordinate mapping.
    shot = OUT / "s2_before.png"
    t = time.time()
    subprocess.run(["screencapture", "-x", str(shot)], check=True)
    res["screenshot_latency_ms"] = round((time.time() - t) * 1000)
    px_w, px_h = png_size(shot)
    scale = px_w / pts_w
    res["screenshot_pixels"] = [px_w, px_h]
    res["display_points"] = [pts_w, pts_h]
    res["scale"] = round(scale, 3)

    # Target chosen in screenshot pixels (centre of the window), mapped back to points.
    target_px = ((300 + 900) / 2 * scale, (200 + 560) / 2 * scale)
    tx, ty = target_px[0] / scale, target_px[1] / scale
    res["target_px"] = [round(target_px[0]), round(target_px[1])]
    res["target_pt"] = [round(tx, 2), round(ty, 2)]

    # 3. Move, verify pointer, click.
    mouse(kCGEventMouseMoved, tx, ty)
    time.sleep(0.15)
    px, py = pointer()
    res["pointer_after_move_pt"] = [round(px, 2), round(py, 2)]
    res["mapping_error_pt"] = round(((px - tx) ** 2 + (py - ty) ** 2) ** 0.5, 3)
    if frontmost() != "TextEdit":
        res["aborted"] = "TextEdit lost focus before the click; nothing typed"
        print(json.dumps(res, indent=2))
        return 2
    t = time.time()
    mouse(kCGEventLeftMouseDown, tx, ty)
    time.sleep(0.04)
    mouse(kCGEventLeftMouseUp, tx, ty)
    res["click_latency_ms"] = round((time.time() - t) * 1000)
    time.sleep(0.3)

    # 4. Type one line (only if TextEdit is still frontmost).
    if frontmost() != "TextEdit":
        res["aborted"] = "TextEdit lost focus after the click; nothing typed"
        print(json.dumps(res, indent=2))
        return 2
    t = time.time()
    type_text(TEXT)
    res["typing_latency_ms"] = round((time.time() - t) * 1000)
    time.sleep(0.4)

    # 5. Oracle: read the document text back, then screenshot for the record.
    got = osa('tell application "TextEdit" to get text of document 1')
    res["document_text"] = got
    res["pass"] = got == TEXT
    subprocess.run(["screencapture", "-x", str(OUT / "s2_after.png")])

    # 6. Clean up our own document; quit TextEdit only if we launched it.
    try:
        osa('tell application "TextEdit" to close document 1 saving no')
        if not was_running:
            osa('tell application "TextEdit" to quit')
    except Exception as e:  # noqa: BLE001
        res["cleanup_error"] = str(e)
    res["total_s"] = round(time.time() - t_all, 2)
    print(json.dumps(res, indent=2))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
