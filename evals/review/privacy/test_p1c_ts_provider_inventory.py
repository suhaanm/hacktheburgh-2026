"""REVIEW-PRIVACY: inventory of TypeScript files that can send content to a provider (OpenAI, Gemini, Google) and whether the same
file or its caller chain mentions the privacy ledger. Report-only asserts: it PASSES while the listed files exist without a ledger
reference, and fails when they are routed through the engine (then delete the case). Static; nothing is executed.
Run: .venv/bin/python -m pytest evals/review/privacy/test_p1c_ts_provider_inventory.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "src"
SEND = re.compile(r"api\.openai\.com|OPENAI_BASE_URL|new GoogleGenAI|generativelanguage\.googleapis|input_image|inlineData|realtimeInput|sendRealtimeInput|\bfetch\(")
LEDGER = re.compile(r"ledger", re.I)


def _files():
    for p in sorted(SRC.rglob("*.ts*")):
        if p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".test-util.ts")) or "node_modules" in p.parts:
            continue
        yield p


def _rows():
    rows = []
    for p in _files():
        t = p.read_text(encoding="utf-8", errors="replace")
        if SEND.search(t) and re.search(r"openai|gemini|googleapis|GoogleGenAI|realtimeInput", t, re.I):
            rows.append((p.relative_to(SRC).as_posix(), bool(LEDGER.search(t))))
    return rows


def test_old_renderer_live_path_is_gone():
    """REGRESSION: the renderer streamed 1 fps frames to Gemini Live behind a flag (renderer/live/LiveSession.ts:499). It was deleted (~17:46)."""
    assert not (SRC / "renderer" / "live" / "LiveSession.ts").exists()
    assert not [r for r in _rows() if r[0].startswith("renderer/live/") and "msg.video" in (SRC / r[0]).read_text(errors="replace")]


def test_ts_files_that_call_a_provider_without_any_ledger_reference_STILL_OPEN():
    """OPEN while it passes: main/model-port/openai.ts (screenshots to OpenAI), gemini/client.ts and files/embed.ts (file text and images
    to Gemini), wake/engine-gemini.ts (microphone audio) have no ledger reference. Fails when DESKTOP's legacy-remote gating lands."""
    rows = _rows()
    print("\nprovider-capable TS files (path, mentions ledger):")
    for r in rows:
        print("  ", r)
    no_ledger = [r[0] for r in rows if not r[1]]
    assert any(x.startswith("main/model-port/openai") for x in no_ledger), "the TS OpenAI port now references the ledger (fixed? verify manually)"
