"""Image canary flows for the privacy evaluation (``understudy_engine/privacy/evaluate.py`` discovers ``IMAGE_FLOWS`` here).

Each flow runs the REAL glance handler (``glance_service.handle_glance``, the same function the agent service's ``/glance`` route calls) on a
frame the evaluation planted a unique token in (``planted.data``: a PNG with the token in its pixels and metadata). The evaluation then
looks for any residue of that frame in the data directory, logs, exception text, ledger rows and captured provider requests, over several
seeds. A flow that returns normally or lets an error escape is fine: refusals are a normal outcome and their text is scanned too.

Flows: an open gate (the frame is sent and a closed answer returns), each gate that must refuse, a provider that fails with the frame in
its own error text, an answer that tries to carry text back, and a frame whose declared size lies.

The awareness package has no text path to a model (events and features are numbers and enums; the only content that can leave is a frame,
and only through ``privacy.egress.send_image``), so ``FLOWS`` is empty.
"""
from __future__ import annotations

import base64
from typing import Any

from ..privacy.image import sniff
from ..privacy.testing import CapturingPort, ImageCanaryFlow
from .glance_service import handle_glance

OPEN = {"consent": True, "denylisted_app": False, "secure_input": False, "unattended": False}
GOOD_ANSWER = {"app_kind": "browser", "task_phase": "reading", "blocker": "none", "confidence": 0.7}


def _body(planted: Any, *, gates: dict[str, bool] | None = None, width: int | None = None) -> dict[str, Any]:
    _, w, h = sniff(planted.data)
    return {"frame_b64": base64.b64encode(planted.data).decode(), "gates": gates or dict(OPEN), "trigger": "hotkey", "app_kind": "browser",
            "width": w if width is None else width, "height": h}


def _call(body: dict[str, Any], port: CapturingPort) -> Any:
    return handle_glance(body, client_host="127.0.0.1", origin=None, port=port)


def _open_gate(planted: Any, port: CapturingPort) -> Any:
    port.script("vision", GOOD_ANSWER)
    reply = _call(_body(planted), port)
    assert reply.status == 200 and reply.body.get("ok") is True
    return reply


def _gate(**closed: bool):
    def run(planted: Any, port: CapturingPort) -> Any:
        reply = _call(_body(planted, gates={**OPEN, **closed}), port)
        assert reply.body.get("ok") is False and not port.requests
        return reply

    return run


def _provider_error_names_the_frame(planted: Any, port: CapturingPort) -> Any:
    # a real provider's error text can echo what it was sent; none of it may reach a reply, a log or the ledger
    port.fail_with(RuntimeError(f"upstream rejected frame {planted.token} {base64.b64encode(planted.data[:64]).decode()}"))
    reply = _call(_body(planted), port)
    assert reply.status == 502
    return reply


def _answer_carries_text(planted: Any, port: CapturingPort) -> Any:
    port.script("vision", {**GOOD_ANSWER, "description": f"a screen showing {planted.token}"})
    reply = _call(_body(planted), port)
    assert reply.body == {"ok": False, "blocked_reason": "output_rejected"}
    return reply


def _answer_enum_carries_text(planted: Any, port: CapturingPort) -> Any:
    port.script("vision", {**GOOD_ANSWER, "blocker": planted.token})
    reply = _call(_body(planted), port)
    assert reply.body.get("ok") is False
    return reply


def _declared_size_lies(planted: Any, port: CapturingPort) -> Any:
    reply = _call(_body(planted, width=7), port)
    assert reply.status == 422 and not port.requests
    return reply


IMAGE_FLOWS = [
    ImageCanaryFlow("awareness.glance (open gate)", _open_gate, layer="awareness"),
    ImageCanaryFlow("awareness.glance (no consent)", _gate(consent=False), layer="awareness"),
    ImageCanaryFlow("awareness.glance (secure input)", _gate(secure_input=True), layer="awareness"),
    ImageCanaryFlow("awareness.glance (denylisted app)", _gate(denylisted_app=True), layer="awareness"),
    ImageCanaryFlow("awareness.glance (unattended)", _gate(unattended=True), layer="awareness"),
    ImageCanaryFlow("awareness.glance (provider error echoes the frame)", _provider_error_names_the_frame, layer="awareness"),
    ImageCanaryFlow("awareness.glance (answer tries to carry text)", _answer_carries_text, layer="awareness"),
    ImageCanaryFlow("awareness.glance (enum tries to carry text)", _answer_enum_carries_text, layer="awareness"),
    ImageCanaryFlow("awareness.glance (declared size lies)", _declared_size_lies, layer="awareness"),
]

FLOWS: list[Any] = []
