#!/usr/bin/env python3
"""Spike S2 preflight. Reports permission state and display geometry.
Performs NO clicks, NO keystrokes and triggers NO permission prompts.

Run: uv run --no-project --python 3.12 --with pyobjc-framework-Quartz \
       --with pyobjc-framework-Cocoa --with pyobjc-framework-ApplicationServices \
       python scripts/s2_probe.py
"""
import json
import os
import subprocess


def process_chain() -> list[str]:
    out, pid = [], os.getpid()
    for _ in range(14):
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if not r:
            break
        ppid, comm = r.split(None, 1)
        out.append(comm)
        pid = int(ppid)
        if pid <= 1:
            break
    return out


def main() -> None:
    from AppKit import NSScreen
    from ApplicationServices import AXIsProcessTrusted
    from Quartz import (
        CGDisplayBounds,
        CGDisplayPixelsHigh,
        CGDisplayPixelsWide,
        CGMainDisplayID,
        CGPreflightScreenCaptureAccess,
    )

    did = CGMainDisplayID()
    b = CGDisplayBounds(did)
    screen = NSScreen.mainScreen()
    info = {
        "process_chain": process_chain(),
        "accessibility_trusted": bool(AXIsProcessTrusted()),
        "screen_recording_granted": bool(CGPreflightScreenCaptureAccess()),
        "main_display_points": [int(b.size.width), int(b.size.height)],
        "main_display_pixels": [int(CGDisplayPixelsWide(did)), int(CGDisplayPixelsHigh(did))],
        "backing_scale_factor": float(screen.backingScaleFactor()) if screen else None,
        "cliclick": subprocess.run(["which", "cliclick"], capture_output=True, text=True).stdout.strip() or None,
    }
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
