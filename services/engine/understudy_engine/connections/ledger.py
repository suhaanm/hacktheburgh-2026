"""Metadata-only ledger rows for tool calls to connected servers, and the counts the Connections panel shows (CONNECTIONS).

One row per call in the privacy ledger (``kind: "mcp"``), written BEFORE the call is made when it is allowed to go ahead, in the shape of
``record_direct``: the server id, the tool name, our class for the call, the size of the arguments and of the result, the outcome and the
time it took. NEVER the arguments, NEVER the result: a call's content is raw, and this ledger holds none of it. If the row cannot be written
the call is not made (fail closed), the same rule as ``egress.send``.

What the ledger does not say, on purpose: traffic of a connected server goes from that server's own process to its own hosts. It is outside
our frame egress guard, which never sees a frame or page text from a connection.
"""
from __future__ import annotations

import re
from typing import Any

from ..privacy import ledger

_ID = re.compile(r"^[a-z][a-z0-9_\-]{1,40}$")
_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]{0,80}$")
CLASSES = ("read", "write", "send", "destructive", "execute", "unknown")
OUTCOMES = ("ok", "error", "timeout", "blocked", "refused", "needs_click")

TRAFFIC_NOTE = ("A connected server's own traffic goes from that server's process to its own hosts. It is outside the frame egress guard, "
                "which never sends a frame or page text for a connection. These rows record sizes and names only, never what was asked or returned.")


def _clean_tool(name: str) -> str:
    return name if _TOOL.match(name or "") else "?"


def record_call(*, server: str, tool: str, klass: str, bytes_args: int, outcome: str, bytes_result: int = 0, ms: int | None = None,
                mock: bool = False, source: str = "agent") -> dict[str, Any]:
    """Append one row. Raises ``OSError`` when it cannot be written (the caller then does not make the call)."""
    if not _ID.match(server or ""):
        raise ValueError("bad server id")
    if klass not in CLASSES or outcome not in OUTCOMES:
        raise ValueError("bad class or outcome")
    purpose = "connection_read" if klass == "read" else "connection_write"
    return ledger.append({
        "kind": "mcp", "purpose": purpose, "schema": None, "fields": [], "payload": None, "content_logged": False,
        "model": f"mcp:{server}", "method": _clean_tool(tool), "bytes": max(0, int(bytes_args)), "mock": bool(mock),
        "connection": server, "tool": _clean_tool(tool), "class": klass, "outcome": outcome, "bytes_result": max(0, int(bytes_result)),
        "ms": None if ms is None else max(0, int(ms)), "source": source, "note": f"class={klass} outcome={outcome}"[:120],
    })


def finish_call(ref_row: dict[str, Any], *, outcome: str, bytes_result: int, ms: int | None) -> None:
    """The small result line after the call (sizes and outcome only). Never raises: the call already happened."""
    try:
        ledger.append({"kind": "mcp_result", "ref": ref_row.get("id"), "connection": ref_row.get("connection"), "outcome": outcome,
                       "bytes_result": max(0, int(bytes_result)), "ms": None if ms is None else max(0, int(ms))})
    except OSError:
        pass


def rows(connection: str | None = None) -> list[dict[str, Any]]:
    """Every mcp row, oldest first (``read_all`` has already folded each result line into its row: one row per call)."""
    return [r for r in ledger.read_all() if r.get("kind") == "mcp" and (not connection or r.get("connection") == connection)]


def reads_summary(connection: str | None = None, *, _all: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Counts only: calls, reads, changes asked for, refused, bytes returned, the last call's time, and the tools used (names and counts).
    ``_all`` is every mcp row already read (a list of fifteen presets reads the ledger once, not fifteen times)."""
    rs = [r for r in (_all if _all is not None else rows()) if not connection or r.get("connection") == connection]
    by_class: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    bytes_result = 0
    for r in rs:
        by_class[str(r.get("class"))] = by_class.get(str(r.get("class")), 0) + 1
        by_outcome[str(r.get("outcome"))] = by_outcome.get(str(r.get("outcome")), 0) + 1
        by_tool[str(r.get("tool"))] = by_tool.get(str(r.get("tool")), 0) + 1
        bytes_result += int(r.get("bytes_result") or 0)
    reads_ok = sum(1 for r in rs if r.get("class") == "read" and r.get("outcome") == "ok")
    changes = sum(1 for r in rs if r.get("class") != "read")
    mock = sum(1 for r in rs if r.get("mock"))
    return {
        "connection": connection, "calls": len(rs), "reads": reads_ok, "changes_asked": changes,
        "refused": by_outcome.get("refused", 0) + by_outcome.get("blocked", 0), "needed_click": by_outcome.get("needs_click", 0),
        "errors": by_outcome.get("error", 0) + by_outcome.get("timeout", 0), "bytes_returned": bytes_result,
        "by_class": dict(sorted(by_class.items())), "by_outcome": dict(sorted(by_outcome.items())), "by_tool": dict(sorted(by_tool.items())),
        "last_call": rs[-1].get("t") if rs else None, "example_calls": mock, "note": TRAFFIC_NOTE,
    }
