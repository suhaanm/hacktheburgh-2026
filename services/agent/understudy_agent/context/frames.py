"""Screenshot retention for the computer-use loop: the latest frame at full size, at most one previous frame as a small thumbnail.

Why: a loop that keeps every frame pays for every frame on every later step (about 1150 estimated input tokens each), so cost grows
with the square of the run length and the oldest items, possibly the goal, are what the provider drops first when its window
fills. One current frame carries the state; one small thumbnail of the previous screen is enough to see what the last action did.
`changed` is measured by code from fingerprints, so the model can also be told in a sentence that the screen did not change.

Privacy rules kept: frames live in memory only. This object holds ONE thumbnail and ONE grey fingerprint of the previous screen
(not the full frame, which is handed to the caller and not kept) and nothing is ever written to disk. `clear()` wipes both. Where a
frame may be stored at all stays the existing run-evidence rule; this module does not store.

Pure Pillow code. No model call, no network.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from .tokens import estimate_image_tokens

CURRENT_MAX = (1280, 720)
THUMB_LONG_EDGE = 384
THUMB_QUALITY = 60
FP_SIZE = (640, 400)
PIXEL_DELTA = 24        # grey levels a pixel must move to count as changed (as tiers/computer_use.py)
CHANGED_PIXELS = 12


@dataclass(frozen=True)
class Frame:
    role: str            # "current" | "previous_thumb"
    data: bytes
    mime: str            # image/png | image/jpeg
    width: int
    height: int

    @property
    def tokens(self) -> int:
        return estimate_image_tokens(self.width, self.height)


@dataclass(frozen=True)
class FramePlan:
    frames: tuple[Frame, ...]       # current first, then the previous thumbnail if there is one
    changed: bool | None            # None: no previous frame to compare with
    dropped: int                    # earlier frames released this step (never sent, never kept)
    hint: str                       # one code-written line saying what each image is

    @property
    def tokens(self) -> int:
        return sum(f.tokens for f in self.frames)

    @property
    def single_hint(self) -> str:
        """The hint when ONLY the current frame is sent (the frozen ModelPort carries one image): no mention of an Image 2."""
        if self.changed is None:
            return "Image 1 is the current screen."
        return "Image 1 is the current screen. " + ("It changed since the last step." if self.changed else "It did not change since the last step.")


def _fingerprint(im: Image.Image) -> bytes:
    return im.convert("L").resize(FP_SIZE).tobytes()


def _changed(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y and abs(x - y) > PIXEL_DELTA:
            n += 1
            if n >= CHANGED_PIXELS:
                return True
    return False


class FrameRetention:
    """`push(png)` once per step with the fresh capture; send `plan.frames` with the step. Order of sections for caching puts the
    images last (they are the most volatile part of the prompt)."""

    def __init__(self, *, keep_previous: bool = True, current_max: tuple[int, int] = CURRENT_MAX,
                 thumb_long_edge: int = THUMB_LONG_EDGE) -> None:
        self.keep_previous = keep_previous
        self.current_max = current_max
        self.thumb_long_edge = thumb_long_edge
        self._thumb: Frame | None = None
        self._fp: bytes | None = None
        self.pushed = 0
        self._last_n = 0
        self.released = 0       # frames that were seen once and then dropped for good (never kept, never stored)

    def push(self, image_bytes: bytes, *, passthrough: bool = False) -> FramePlan:
        """`passthrough=True`: the current frame's `data` is the caller's own bytes, untouched (its `width` and `height` are the size
        the provider will see after its own downscale, for token accounting). Use it when the caller sends its original screenshot,
        because a model's click coordinates come back in the pixel space of the image it was given."""
        with Image.open(io.BytesIO(image_bytes)) as src:
            src.load()
            im = src.convert("RGB")
        w, h = im.size
        scale = min(1.0, self.current_max[0] / w, self.current_max[1] / h)
        cur_im = im if scale >= 1.0 else im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        if passthrough:
            current = Frame("current", image_bytes, "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg", cur_im.width, cur_im.height)
        else:
            buf = io.BytesIO()
            cur_im.save(buf, "PNG")
            current = Frame("current", buf.getvalue(), "image/png", cur_im.width, cur_im.height)
        fp = _fingerprint(cur_im)

        prev, prev_fp = self._thumb, self._fp
        changed = None if prev_fp is None else _changed(prev_fp, fp)
        frames = [current] + ([prev] if (prev is not None and self.keep_previous) else [])
        # frames of the previous plan that are not in this one: its thumbnail always, and its full frame when no thumbnail is kept
        dropped = max(0, self._last_n - (1 if (self.keep_previous and self._last_n) else 0))

        # retain only a thumbnail and a fingerprint of THIS frame for the next step
        if self.keep_previous:
            tl = self.thumb_long_edge
            ts = min(1.0, tl / max(cur_im.width, cur_im.height))
            t_im = cur_im if ts >= 1.0 else cur_im.resize((max(1, round(cur_im.width * ts)), max(1, round(cur_im.height * ts))), Image.LANCZOS)
            tb = io.BytesIO()
            t_im.save(tb, "JPEG", quality=THUMB_QUALITY)
            self._thumb = Frame("previous_thumb", tb.getvalue(), "image/jpeg", t_im.width, t_im.height)
        self._fp = fp
        self.released += dropped
        self._last_n = len(frames)
        self.pushed += 1

        if len(frames) == 2:
            hint = ("Image 1 is the current screen. Image 2 is a small thumbnail of the screen one step ago, for comparison only. "
                    + ("The screen changed since then." if changed else "The screen did not change since then."))
        elif changed is None:
            hint = "Image 1 is the current screen."
        else:
            hint = "Image 1 is the current screen. " + ("It changed since the last step." if changed else "It did not change since the last step.")
        return FramePlan(tuple(frames), changed, dropped, hint)

    def clear(self) -> None:
        self._thumb, self._fp, self._last_n = None, None, 0

    @property
    def held_bytes(self) -> int:
        """Bytes this object keeps between steps: one thumbnail and one fingerprint (a few tens of KB), never a full frame."""
        return (len(self._thumb.data) if self._thumb else 0) + (len(self._fp) if self._fp else 0)
