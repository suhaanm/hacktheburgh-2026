from __future__ import annotations

import pytest

from understudy_engine.privacy import ledger
from understudy_engine.privacy.direct import LedgeredPort, wrap_if_enabled
from understudy_engine.privacy.testing import CapturingPort


def test_every_forwarded_call_gets_one_metadata_only_line_before_it_is_made():
    seen = []

    class Spy(CapturingPort):
        def plan(self, messages, schema=None):
            seen.append(len(ledger.read_all()))
            return super().plan(messages, schema)

    p = LedgeredPort(Spy())
    p.plan([{"role": "user", "content": "raw page text with Ada Lovelace"}], {"type": "object"})
    p.read("untrusted raw text", {"type": "object"})
    p.check("prompt", {"type": "object"})
    p.vision(b"\x89PNG" + b"0" * 100, "what is this", None)
    assert seen == [1]
    rows = ledger.read_all()
    assert [r["method"] for r in rows] == ["plan", "read", "check", "vision"]
    for r in rows:
        assert r["kind"] == "direct" and r["payload"] is None and r["content_logged"] is False and r["fields"] == [] and r["bytes"] > 0
        assert "Lovelace" not in str(r) and "raw page text" not in str(r)
    assert rows[3]["bytes"] >= 104
    assert rows[0]["mock"] is True                      # a capturing port is a test double
    assert ledger.summary()["worker_requested_calls"] == 4


def test_the_call_is_not_made_if_the_ledger_cannot_be_written(monkeypatch):
    inner = CapturingPort()

    def boom(**kw):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "record_direct", boom)
    with pytest.raises(RuntimeError, match="was not made"):
        LedgeredPort(inner).plan([], None)
    assert len(inner) == 0


def test_attributes_and_answers_pass_through():
    inner = CapturingPort()
    inner.script("plan", {"text": "hi"})
    p = LedgeredPort(inner)
    assert p.plan([], None) == {"text": "hi"} and p.name == "capturing" and len(p.requests) == 1


def test_model_id_is_read_from_the_port_never_hard_coded():
    class Remote(CapturingPort):
        name = "openai"
        offline = False

        class models:  # noqa: N801
            planner, fast, computer_use = "PLAN-ID", "FAST-ID", "CU-ID"

    p = LedgeredPort(Remote())
    p.plan([], None)
    p.check("x", {})
    p.computer_step("g", b"", []) if False else None
    rows = ledger.read_all()
    assert [r["model"] for r in rows] == ["openai:PLAN-ID", "openai:FAST-ID"] and rows[0]["mock"] is False


def test_wrap_if_enabled_leaves_the_p0_path_untouched_when_the_flag_is_off(monkeypatch):
    port = CapturingPort()
    assert wrap_if_enabled(port) is port
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    w = wrap_if_enabled(port)
    assert isinstance(w, LedgeredPort) and wrap_if_enabled(w) is w
