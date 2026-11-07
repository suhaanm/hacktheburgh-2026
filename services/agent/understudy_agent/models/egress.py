"""Where an image or data leaves: the ledger line comes first, and if it cannot be written the call is not made.

`EgressEvent` is metadata only (provider, model, method, purpose, byte count, image hash prefix, source). It never holds pixels.
The default recorder writes a metadata-only line with `understudy_engine.privacy.ledger.record_direct` (the egress ledger,
`<data dir>/egress_ledger.jsonl`). When the privacy track's `egress.send_image` lands this module is the one place that changes
(see the TODO list in `safe_image.py`).

The bake-off uses `null_egress`: its images are synthetic sandbox screenshots, not the worker's screen, and the harness keeps its
own metadata log.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .errors import ProviderError


class EgressBlocked(ProviderError):
    """The egress ledger could not be written, so nothing was sent."""


@dataclass(frozen=True)
class EgressEvent:
    provider: str
    model: str
    method: str          # point | glance | verify_screen | vision | check
    purpose: str         # the routing role
    nbytes: int
    sha256_prefix: str | None = None
    source: str = "sandbox"


EgressFn = Callable[[EgressEvent], None]


def null_egress(ev: EgressEvent) -> None:
    return None


def ledger_egress(ev: EgressEvent) -> None:
    """Write one metadata-only egress ledger line before the send. Fail closed."""
    try:
        from understudy_engine.privacy import ledger

        ledger.record_direct(method=f"{ev.provider}.{ev.method}", model=f"{ev.provider}:{ev.model}", bytes_sent=ev.nbytes,
                             purpose=ev.purpose, note=f"sha={ev.sha256_prefix or '-'} src={ev.source}")
    except Exception:  # noqa: BLE001 - OSError, import problems, anything: no proof of a ledger line means no send
        raise EgressBlocked("The privacy ledger could not be written, so the call was not made.") from None
