"""Screenshot helpers: downscale for the model and map coordinates back (macOS screenshots are 2x)."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from PIL import Image

DEFAULT_MAX_W = 1280
DEFAULT_MAX_H = 720


@dataclass(frozen=True)
class ScaledImage:
    """A PNG sized for the model plus the maths to get back to the caller's pixel space."""

    png: bytes
    orig_w: int
    orig_h: int
    w: int
    h: int

    @property
    def sx(self) -> float:
        return self.w / self.orig_w

    @property
    def sy(self) -> float:
        return self.h / self.orig_h

    def to_original(self, x: float, y: float) -> tuple[int, int]:
        """Model-space point -> original screenshot pixel space (clamped to the image)."""
        ox = round(x / self.sx)
        oy = round(y / self.sy)
        return max(0, min(self.orig_w - 1, ox)), max(0, min(self.orig_h - 1, oy))

    def to_model(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self.sx), round(y * self.sy)

    def length_to_original(self, dx: float, dy: float) -> tuple[int, int]:
        """A distance (e.g. a scroll amount) from model space to original pixels."""
        return round(dx / self.sx), round(dy / self.sy)


def png_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def fit_size(w: int, h: int, max_w: int = DEFAULT_MAX_W, max_h: int = DEFAULT_MAX_H) -> tuple[int, int]:
    """Largest size with the same aspect ratio that fits in max_w x max_h. Never upscales."""
    if w <= 0 or h <= 0:
        raise ValueError("image has no size")
    scale = min(1.0, max_w / w, max_h / h)
    return max(1, round(w * scale)), max(1, round(h * scale))


def downscale_png(data: bytes, max_w: int = DEFAULT_MAX_W, max_h: int = DEFAULT_MAX_H) -> ScaledImage:
    """Re-encode any image bytes as PNG fitting within max_w x max_h."""
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        ow, oh = im.size
        nw, nh = fit_size(ow, oh, max_w, max_h)
        if (nw, nh) != (ow, oh):
            im = im.convert("RGB").resize((nw, nh), Image.LANCZOS)
        elif im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=False)
    return ScaledImage(png=buf.getvalue(), orig_w=ow, orig_h=oh, w=nw, h=nh)


MAX_FRAME_BYTES = 400 * 1024   # the privacy SafeImage limit; every image sent to a model stays inside it (and inside 1280 px on the long edge)


def data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def make_test_png(w: int = 1280, h: int = 720, label: str = "Calculate") -> bytes:
    """A small synthetic screenshot (a labelled button) for tests and live probes."""
    from PIL import ImageDraw

    im = Image.new("RGB", (w, h), (245, 245, 245))
    d = ImageDraw.Draw(im)
    bx0, by0, bx1, by1 = int(w * 0.42), int(h * 0.42), int(w * 0.58), int(h * 0.50)
    d.rectangle([bx0, by0, bx1, by1], fill=(30, 100, 220))
    d.text((bx0 + 20, by0 + 20), label, fill=(255, 255, 255))
    d.text((int(w * 0.03), int(h * 0.05)), "Benefits calculator", fill=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def sniff_mime(data: bytes) -> str:
    """image/png or image/jpeg from the file header, else ValueError (only those two ever go to a model)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    raise ValueError("only PNG and JPEG images are accepted")


def prepare_frame(raw: bytes, *, long_edge: int = 1280, max_bytes: int = 400 * 1024, quality: int = 80) -> bytes:
    """Any image bytes -> a JPEG whose long edge is at most `long_edge` and whose size is at most `max_bytes` (the limits of the
    privacy track's SafeImage). Lowers the JPEG quality in steps to fit. Pure; nothing is written anywhere."""
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        w, h = im.size
        scale = min(1.0, long_edge / max(w, h))
        im = im.convert("RGB")
        if scale < 1.0:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        q = quality
        while True:
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=q, optimize=False)
            if buf.tell() <= max_bytes or q <= 30:
                return buf.getvalue()
            q -= 10
