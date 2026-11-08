"""Stand-in MCP server that answers from a fixture file (CONNECTIONS). Ours, written with the official MCP Python SDK.

One script serves every preset that has no dedicated stand-in (Git, Jira, Sentry, Google Sheets and Drive, Jupyter, Notion, SharePoint). Each fixture
in ``fixtures/<name>.json`` lists tools with the SAME NAMES as the real server (so the same class table applies) and an invented, fixed answer:

    python fixture_server.py --fixture jira

A fixture tool takes one optional ``query`` and returns its canned answer; a tool the fixture marks ``"write": true`` only reports that it would
have changed something and changes nothing. All data is invented (fictional names, example addresses). No network, no file access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

HERE = Path(__file__).resolve().parent
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def build(fixture: str) -> MCPServer:
    if not _NAME.match(fixture):
        raise SystemExit("bad fixture name")
    spec = json.loads((HERE / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))
    server = MCPServer(spec.get("server", f"example-{fixture}"))
    for t in spec["tools"]:
        answer = t.get("response", "")
        text = answer if isinstance(answer, str) else json.dumps(answer, indent=1)
        is_write = bool(t.get("write"))

        def make(text: str = text, is_write: bool = is_write):
            def run(query: str = "") -> str:
                return ("Example only: this would have changed something, and nothing was changed." if is_write else text)
            return run

        server.add_tool(make(), name=t["name"], description=t.get("description", ""),
                        annotations=None if is_write else ToolAnnotations(read_only_hint=True))
    return server


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    build(ap.parse_args(argv).fixture).run("stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
