"""Evidence layer (REQ-6): evidence packets, the number-provenance check, and a plain-English explainer over them.

    from understudy_engine.evidence import packet, provenance, explain, templates, menu, intent
    pk = packet.from_genome(data, meta)                    # a closed-schema EvidencePacket (no free text)
    out = explain.explain(pk, "why did this case take 14 minutes?")      # template, local or cloud wording, always checked

Importing this package imports nothing heavy and starts nothing. The HTTP routes (``evidence.routes``) are off unless
``UNDERSTUDY_X_EVIDENCE=1`` or ``UNDERSTUDY_X=1``. See docs/REQ5_PLAN.md section 8 for the honesty rules this layer follows.
"""
from __future__ import annotations

__all__ = ["evaluate_evidence"]


def evaluate_evidence(fast: bool = False, **kw):
    from .evaluate import evaluate_evidence as f

    return f(fast=fast, **kw)
