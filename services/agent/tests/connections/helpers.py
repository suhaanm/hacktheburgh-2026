from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

from understudy_engine.connections.manifest import Preset, ToolTable

HOSTILE = str(Path(__file__).resolve().parent / "servers" / "hostile_server.py")


def preset(pid: str = "hostile", *, classes: dict[str, list[str]] | None = None, unlisted: str = "verbs", classifiers: dict[str, str] | None = None,
           script: str = HOSTILE, args: list[str] | None = None, real: dict[str, Any] | None = None, app: str = "Hostile") -> Preset:
    table = {n: c for c, names in (classes or {}).items() for n in names}
    return Preset(id=pid, app=app, group="dev", kind="mcp", version="0.1.0", description="test", reads="Nothing real.", caution="",
                  standin={"label": "Test", "script": script, "args": args or []}, real=real, tools=ToolTable(table, classifiers or {}, unlisted))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def register(monkeypatch, *presets: Preset) -> None:
    """Make the service and the state module see test presets (the curated registry only holds the shipped ones)."""
    from understudy_engine.connections import registry

    by_id = {p.id: p for p in presets}
    real_get = registry.get
    monkeypatch.setattr(registry, "get", lambda i: by_id.get(i) or real_get(i))


PY = sys.executable
