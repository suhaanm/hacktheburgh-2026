"""REVIEW-PRIVACY: inventory of TypeScript files that can send content to a provider (OpenAI, Gemini, Google) and whether they go through the
legacy-remote gate (src/main/legacy-remote.ts: flag, privacy gates and a metadata ledger row BEFORE every request, D38). It began as an open
finding (those files had no ledger reference) and is now a regression test: the legacy paths must keep the gate. Static; nothing is executed.
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


# The legacy Alongside paths that sent screenshots or file text to a provider (D38). Each must call authorizeLegacy() from legacy-remote.
LEGACY_REMOTE_FILES = ("main/model-port/openai.ts", "main/gemini/client.ts", "main/files/embed.ts")
AUTHORIZE = re.compile(r"import\s*\{[^}]*\bauthorizeLegacy\b[^}]*\}\s*from\s*'\.\./legacy-remote'")


def test_legacy_provider_paths_go_through_the_legacy_remote_gate():
    """REGRESSION for the open finding (main/model-port/openai.ts, gemini/client.ts, files/embed.ts had no ledger reference): each now
    imports authorizeLegacy from the legacy-remote gate, and the gate's own file writes the ledger row."""
    rows = dict(_rows())
    for rel in LEGACY_REMOTE_FILES:
        assert rel in rows, f"{rel} no longer matches the provider inventory (moved or deleted? update this list)"
        text = (SRC / rel).read_text(encoding="utf-8")
        assert AUTHORIZE.search(text), f"{rel} reaches a provider without authorizeLegacy() from ../legacy-remote"
        assert "legacyRemoteOn" in text or "LegacyRemoteBlocked" in text, f"{rel} does not honour the default-off legacy flag"
    gate = (SRC / "main" / "legacy-remote.ts").read_text(encoding="utf-8")
    assert re.search(r"ledger", gate, re.I) and "UNDERSTUDY_LEGACY_REMOTE" in gate


def test_old_microphone_wake_path_to_gemini_is_gone():
    """REGRESSION: wake/engine-gemini.ts streamed microphone audio to Gemini without a ledger reference. It no longer exists."""
    assert not (SRC / "main" / "wake" / "engine-gemini.ts").exists()
    assert not list(SRC.rglob("engine-gemini*"))
