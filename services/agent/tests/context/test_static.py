"""The context package can never send anything: it imports no model client, provider, egress guard or network library, calls no
model, reads no clock and writes no file. Checked on the source (AST), so a future edit that breaks it fails here."""
from __future__ import annotations

import ast
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "understudy_agent" / "context"
FORBIDDEN_TOP = {"openai", "httpx", "requests", "urllib", "urllib3", "socket", "http", "aiohttp", "anthropic", "google", "websockets",
                 "subprocess", "asyncio", "threading", "ftplib", "smtplib", "ssl", "playwright"}
FORBIDDEN_REL = ("models", "tiers", "orchestrator", "navigator", "queue", "supervisor", "runtime", "voice")
# the only import that leaves the package is `..security.sanitize`: the pure text sanitiser the pipeline already uses


def imports(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield 0, a.name.split(".")[0], a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, (node.module or "").split(".")[0], node.module or ""


def test_no_network_model_or_runtime_imports():
    files = sorted(PKG.glob("*.py"))
    assert len(files) >= 8
    for f in files:
        for level, top, full in imports(f):
            if level == 0:
                assert top not in FORBIDDEN_TOP, f"{f.name} imports {full}"
                assert not full.startswith("understudy_engine.privacy"), f"{f.name} imports the egress guard"
            else:
                if level >= 2:                                          # `from ..x import y` leaves the package
                    assert top == "security" and full == "security.sanitize", f"{f.name} imports from outside the package: {full}"
                    assert top not in FORBIDDEN_REL


def test_no_clock_no_file_writes_no_environment_reads():
    banned = ("time.time", "time.monotonic", "datetime.now", "os.environ", "write_text", "write_bytes", "os.getenv", "subprocess")
    for f in sorted(PKG.glob("*.py")):
        src = f.read_text()
        for b in banned:
            assert b not in src, f"{f.name} uses {b}"
        assert not re.search(r"(?<![.\w])open\(", src), f"{f.name} calls the builtin open"   # Image.open on in-memory bytes is fine
