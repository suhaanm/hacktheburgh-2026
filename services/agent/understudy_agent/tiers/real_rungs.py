"""The real-click ladder, as code (evals/agentic/REAL_CLICKS.md). Nothing here runs by itself.

R0  read-only: the REAL window list, scale, accessibility and (once, with the owner's go) one real capture, through a backend
    whose mouse, type_text, key and scroll RAISE. It prints where each intended point would land, converted to points, with
    the window that would take it. Zero input events, by construction and by test.
R1  `mac_check` (tiers/mac_check.py): scripted, not a model, one short ASCII word into a fresh TextEdit document, read back.
Preflight  `scripts/real_click_preflight.py`: PASS or FAIL per item, run before R0 and R1.
"""
from __future__ import annotations

from typing import Any

from .computer_use import ActuatorRefused, MacBackend, png_size


class ReadOnlyBackend:
    """Delegates every READ to `inner` and refuses every WRITE. `release_all` is a no-op: nothing is ever held."""

    def __init__(self, inner: MacBackend) -> None:
        self._inner = inner
        self.refused: list[str] = []

    def _no(self, what: str) -> None:
        self.refused.append(what)
        raise ActuatorRefused(f"read-only backend (R0): {what} is not allowed")

    # writes
    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None: self._no(f"mouse {kind}")
    def type_text(self, text: str) -> None: self._no("type_text")
    def key(self, keys: list[str]) -> None: self._no("key")
    def scroll(self, dx: int, dy: int) -> None: self._no("scroll")
    def release_all(self) -> None: return None

    # reads
    def frontmost_app(self) -> str: return self._inner.frontmost_app()
    def screen_locked(self) -> bool: return self._inner.screen_locked()
    def backing_scale(self) -> float: return self._inner.backing_scale()
    def display_width_pts(self) -> float: return self._inner.display_width_pts()
    def window_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None: return self._inner.window_at(x_pt, y_pt)
    def screenshot_png(self) -> bytes: return self._inner.screenshot_png()

    def __getattr__(self, name: str) -> Any:
        # optional reads only: windows_of, element_at, focused_element. Anything else is not forwarded.
        if name in ("windows_of", "all_windows_of", "element_at", "focused_element", "read_document"):
            return getattr(self._inner, name)
        raise AttributeError(name)


def run_r0(target_app: str, points_px: list[tuple[int, int]], backend: MacBackend) -> dict[str, Any]:
    """Where would each point land? Reads only. The marker list is what the overlay should draw, in POINTS, so the owner
    can see a scale error before R1."""
    ro = backend if isinstance(backend, ReadOnlyBackend) else ReadOnlyBackend(backend)
    scale = float(ro.backing_scale())
    shot = ro.screenshot_png()                      # the one capture; needs the Screen Recording permission
    size = png_size(shot)
    pts_w = float(ro.display_width_pts())
    measured = (size[0] / pts_w) if size and pts_w else 0.0
    out: dict[str, Any] = {"target_app": target_app, "backing_scale": scale, "screenshot_px": list(size) if size else None,
                           "measured_scale": round(measured, 3), "scale_agrees": abs(measured - scale) <= 0.05,
                           "frontmost": ro.frontmost_app(), "markers": [], "events": 0}
    windows_of = getattr(ro, "all_windows_of", None) or getattr(ro, "windows_of", None)
    out["target_windows"] = len(windows_of(target_app)) if callable(windows_of) else None
    for px, py in points_px:
        x, y = px / scale, py / scale
        w = ro.window_at(x, y)
        ok = bool(w and w["owner"] == target_app and (size is None or (0 <= px < size[0] and 0 <= py < size[1])))
        out["markers"].append({"x_px": px, "y_px": py, "x_pt": round(x, 2), "y_pt": round(y, 2),
                               "window_owner": (w or {}).get("owner"), "window_number": (w or {}).get("number"),
                               "lands_in_target": ok})
    out["all_in_target"] = all(m["lands_in_target"] for m in out["markers"]) and out["scale_agrees"]
    out["events"] = len(ro.refused)                  # a refused write would be counted here; the run never attempts one
    return out


def main(argv: list[str] | None = None) -> int:
    """R0 from a shell: `python -m understudy_agent.tiers.real_rungs --target TextEdit --point-px 1200 800` (add --fake to rehearse)."""
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="R0: read-only layout check; zero input events")
    ap.add_argument("--target", default="TextEdit")
    ap.add_argument("--point-px", nargs=2, type=int, action="append", required=True, metavar=("X", "Y"))
    ap.add_argument("--fake", action="store_true", help="rehearse with a fake backend (nothing real is read)")
    a = ap.parse_args(argv)
    if a.fake:
        from .mac_check import DryBackend

        backend: Any = DryBackend(a.target)
    else:
        from .computer_use import QuartzBackend

        backend = QuartzBackend()                  # needs pyobjc and the Screen Recording permission for the one capture
    out = run_r0(a.target, [tuple(p) for p in a.point_px], backend)
    print(json.dumps(out, indent=1))
    return 0 if out["all_in_target"] and out["events"] == 0 else 2


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
