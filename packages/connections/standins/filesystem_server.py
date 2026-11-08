"""Stand-in Filesystem MCP server (CONNECTIONS). Ours, written with the official MCP Python SDK; it is NOT the MCP project's server.

Serves ONE sandbox folder of invented files over stdio, with the same tool names as the real Filesystem server so the same class table
applies. Run by the agent as a subprocess of our own code, only after the worker's click, badged Example everywhere:

    python filesystem_server.py --root <folder>

The folder is filled on first use with invented notes. Every path is resolved and must stay inside the root; links are refused. No network.
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

SEED = {
    "README.md": "# Example folder\n\nInvented files for trying Knack. Nothing here is real.\n",
    "notes/standup.md": "# Stand-up, Tuesday\n\n- Reconcile the example claims queue (12 left)\n- Check the housing-cost rule on case EX-104\n- Ask the team lead about the rota\n",
    "notes/todo.txt": "1. Recheck partner income on EX-104\n2. Chase the missing tenancy letter on EX-117\n3. Close three stale drafts\n",
    "data/queue.csv": "case,age_days,state\nEX-101,2,open\nEX-104,5,waiting\nEX-117,9,waiting\nEX-120,1,open\n",
    "src/hello.py": "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
}

RO = ToolAnnotations(read_only_hint=True)
server = MCPServer("example-files")
ROOT: Path = Path(".")


def _seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        return
    for rel, text in SEED.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def _safe(rel: str) -> Path:
    cur = ROOT
    for part in Path(rel).parts:                  # a link anywhere on the way is refused before it is followed
        cur = cur / part
        if cur.is_symlink():
            raise ValueError("Links are not followed.")
    p = (ROOT / rel).resolve()
    if ROOT.resolve() not in (p, *p.parents):
        raise ValueError("That path is outside the example folder.")
    return p


@server.tool(annotations=RO)
def list_allowed_directories() -> str:
    """List the folders this server may read."""
    return str(ROOT.resolve())


@server.tool(annotations=RO)
def read_text_file(path: str, head: int | None = None, tail: int | None = None) -> str:
    """Read a text file inside the example folder."""
    lines = _safe(path).read_text(encoding="utf-8").splitlines()
    if head:
        lines = lines[:head]
    elif tail:
        lines = lines[-tail:]
    return "\n".join(lines)


@server.tool(annotations=RO)
def read_file(path: str) -> str:
    """Alias of read_text_file."""
    return _safe(path).read_text(encoding="utf-8")


@server.tool(annotations=RO)
def read_multiple_files(paths: list[str]) -> str:
    """Read several text files."""
    return "\n---\n".join(f"{p}:\n{_safe(p).read_text(encoding='utf-8')}" for p in paths[:10])


@server.tool(annotations=RO)
def list_directory(path: str = ".") -> str:
    """List a folder."""
    d = _safe(path)
    return "\n".join(f"[{'DIR' if c.is_dir() else 'FILE'}] {c.name}" for c in sorted(d.iterdir()))


@server.tool(annotations=RO)
def list_directory_with_sizes(path: str = ".") -> str:
    """List a folder with file sizes."""
    d = _safe(path)
    return "\n".join(f"[{'DIR' if c.is_dir() else 'FILE'}] {c.name} {c.stat().st_size if c.is_file() else ''}".rstrip() for c in sorted(d.iterdir()))


@server.tool(annotations=RO)
def directory_tree(path: str = ".") -> str:
    """A tree of names under a folder."""
    base = _safe(path)
    return "\n".join(str(p.relative_to(base)) for p in sorted(base.rglob("*")))


@server.tool(annotations=RO)
def search_files(path: str, pattern: str) -> str:
    """Find files whose path matches a glob pattern."""
    base = _safe(path)
    hits = [str(p.relative_to(ROOT)) for p in sorted(base.rglob("*")) if fnmatch.fnmatch(p.name, pattern)]
    return "\n".join(hits[:50]) or "(none)"


@server.tool(annotations=RO)
def get_file_info(path: str) -> str:
    """Size and kind of a file or folder."""
    p = _safe(path)
    return f"kind={'dir' if p.is_dir() else 'file'} size={p.stat().st_size}"


@server.tool()
def create_directory(path: str) -> str:
    """Create a folder (a change; the agent asks first)."""
    _safe(path).mkdir(parents=True, exist_ok=True)
    return f"created {path}"


@server.tool()
def append_file(path: str, content: str) -> str:
    """Append text to a file (a change; the agent asks first)."""
    with _safe(path).open("a", encoding="utf-8") as fh:
        fh.write(content)
    return f"appended to {path}"


@server.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file (a change that can lose data; the agent asks first)."""
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {path}"


@server.tool()
def move_file(source: str, destination: str) -> str:
    """Move a file (a change; the agent asks first)."""
    _safe(source).rename(_safe(destination))
    return f"moved {source}"


def main(argv: list[str] | None = None) -> None:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args(argv)
    ROOT = Path(args.root)
    _seed(ROOT)
    server.run("stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
