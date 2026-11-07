"""SafeImage (PLACEHOLDER): the only way an image reaches a remote model from the REQ-5 paths.

The privacy track is adding the real type (`understudy_engine.privacy.image.SafeImage`, `ImageGate`, `egress.send_image`).
Until it lands this module is the stand-in, with the same intent and the smallest surface that keeps image bytes out of
logs, ledgers, cache keys and exceptions:

* the bytes live in memory only (`repr`, `str`, pickling and `dataclasses.asdict` never show or write them),
* an image is identified by `sha256_prefix` (12 hex characters), never by its content,
* the long edge is capped (default 1280 px) and the image is re-encoded, so a 2x Retina frame is never sent whole,
* nothing here touches the disk.

TODO for the PRIVACY track (the swap to the real type is one small change in `egress.py` and `gemini_provider.py`):

1. `register_image_purpose(...)` entries for the purposes this track uses: `glance`, `point`, `verify_screen`. Each has a CLOSED
   response schema (every string an enum). `PointResult` and `GlanceResult` in `schemas.py` already are.
2. `SafeImage` construction that records, in the egress ledger line written BEFORE the send and fail-closed on `OSError`:
   `{purpose, model, provider, bytes, sha256_prefix, width, height, mime, source: "real_screen"|"sandbox", ledger_id}`; never the pixels.
3. `ImageGate(consent, denylisted_app, secure_input, unattended, source)` evaluated by the caller (AWARENESS track) before
   `SafeImage.from_*` is reachable: `real_screen` without consent, on a denylisted app, under secure input or unattended never
   builds an image. The bake-off and agent runs use `source="sandbox"`.
4. The call goes `egress.send_image(purpose, image, payload, gate=..., port=...)` which calls `port.vision(image_bytes, prompt, schema)`;
   this track's `GeminiProvider.vision` / `.point` / `.glance` and the OpenAI provider's `.vision` are the ports it will meet.
5. After the call, `egress` may read `port.last_call == {input_tokens, output_tokens, cost_estimate_usd}` (both providers set it).

Until then `EgressRecorder` in `egress.py` writes a metadata-only line through `understudy_engine.privacy.ledger.record_direct`
(model, method, byte count, sha prefix in the note), fail-closed, before any image leaves.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image

DEFAULT_LONG_EDGE = 1280
Source = Literal["real_screen", "sandbox"]


class ImageRefused(ValueError):
    """The image cannot be turned into a SafeImage (not an image, empty, or a disallowed source)."""


@dataclass(frozen=True, eq=False)
class SafeImage:
    """An in-memory, downscaled frame that is allowed to be sent. Build it with `from_bytes`."""

    data: bytes = field(repr=False)
    mime: str
    width: int
    height: int
    purpose: str
    source: Source
    orig_width: int
    orig_height: int
    sha256_prefix: str

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_bytes(cls, raw: bytes, *, purpose: str, source: Source = "sandbox", long_edge: int = DEFAULT_LONG_EDGE,
                   fmt: Literal["JPEG", "PNG"] = "JPEG", quality: int = 80) -> "SafeImage":
        if not raw:
            raise ImageRefused("empty image")
        if source not in ("real_screen", "sandbox"):
            raise ImageRefused("unknown image source")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                ow, oh = im.size
                scale = min(1.0, long_edge / max(ow, oh))
                nw, nh = max(1, round(ow * scale)), max(1, round(oh * scale))
                im = im.convert("RGB")
                if (nw, nh) != (ow, oh):
                    im = im.resize((nw, nh), Image.LANCZOS)
                buf = io.BytesIO()
                if fmt == "JPEG":
                    im.save(buf, "JPEG", quality=quality, optimize=False)
                else:
                    im.save(buf, "PNG", optimize=False)
        except ImageRefused:
            raise
        except Exception as e:  # noqa: BLE001 - never echo decoder messages (they can carry file content)
            raise ImageRefused(f"not a readable image ({type(e).__name__})") from None
        data = buf.getvalue()
        return cls(data=data, mime="image/jpeg" if fmt == "JPEG" else "image/png", width=nw, height=nh,
                   purpose=purpose, source=source, orig_width=ow, orig_height=oh,
                   sha256_prefix=hashlib.sha256(data).hexdigest()[:12])

    # ------------------------------------------------------------------ safe views
    @property
    def nbytes(self) -> int:
        return len(self.data)

    def describe(self) -> dict[str, object]:
        """Metadata only: what may be written to a ledger or a log."""
        return {"purpose": self.purpose, "source": self.source, "mime": self.mime, "width": self.width,
                "height": self.height, "bytes": self.nbytes, "sha256_prefix": self.sha256_prefix}

    def __repr__(self) -> str:
        return (f"SafeImage({self.width}x{self.height} {self.mime} {self.nbytes}B sha={self.sha256_prefix} "
                f"purpose={self.purpose} source={self.source})")

    __str__ = __repr__

    def __reduce__(self):  # noqa: D105 - frames are never pickled to disk or a queue
        raise TypeError("SafeImage cannot be pickled: frames stay in memory")

    def __getstate__(self):  # noqa: D105
        raise TypeError("SafeImage cannot be serialised: frames stay in memory")
