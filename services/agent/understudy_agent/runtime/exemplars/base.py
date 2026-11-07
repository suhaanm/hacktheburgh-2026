"""Exemplar plumbing: what a spawn kind is, what each role may be offered, and the registries (BGA-4, BGA-5, BGA-6).

A `Menu` is the closed list of things a child can ask for by id: files (logical id -> workspace path) and script
templates (id -> vetted text). In the default, privacy-preserving mode a child's planner replies with ids only; code
turns an id into the real path or text, so no file content, name or path ever has to go to (or come back from) the model.
The vetted templates are written by us and packaged with the runtime; a template is the model's tool, not its input.

Playbooks are plain-words instructions per role in `playbooks/<id>.md`, written without file names, URLs or the words
the egress backstop looks for, because they travel inside the registered purpose's instructions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

_HERE = Path(__file__).parent
PLAYBOOK_DIR = _HERE / "playbooks"
SCRIPT_DIR = _HERE / "scripts"


def script_text(name: str) -> str:
    return (SCRIPT_DIR / name).read_text(encoding="utf-8")


def load_playbook(playbook_id: str) -> str:
    p = PLAYBOOK_DIR / f"{playbook_id}.md"
    if not p.is_file():
        raise KeyError(f"unknown playbook {playbook_id!r}")
    return p.read_text(encoding="utf-8").strip()


def known_playbooks() -> set[str]:
    return {p.stem for p in PLAYBOOK_DIR.glob("*.md")}


@dataclass(frozen=True)
class Menu:
    files: Mapping[str, str]                   # file id -> relative path inside the workspace
    templates: Mapping[str, str] = field(default_factory=dict)   # template id -> script text
    max_commits: int = 300


@dataclass(frozen=True)
class WorkspaceNeeds:
    inputs: tuple[tuple[Path, str], ...] = ()  # (source file, name under input/), copied in by trusted code
    repo_source: Path | None = None            # a repository to CLONE (worktree kind)


@dataclass(frozen=True)
class Exemplar:
    kind: str                                   # API spawn kind, for example data.profile
    title: str
    describe: str                               # trusted one-liner
    roles: tuple[str, ...]
    needs: Callable[[str, dict[str, Any]], WorkspaceNeeds]
    prepare: Callable[[dict[str, Any], Path], dict[str, Any]]   # (params, run dir) -> cleaned params (may make fixtures)
    mock_steps: Callable[[str, dict[str, Any]], list[dict[str, Any]]]   # role -> scripted menu steps
    explicit_files: tuple[str, ...] = ()        # params naming files the worker chose (for raw mode)
    # optional adaptive stand-in for the model (mock mode): (role, params, payload) -> menu reply, a function of the typed
    # payload the model would receive (steps left, last outcome, typed history, typed signals)
    policy: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None
    budget: tuple[int, float, int] = (10, 120.0, 20000)   # (steps, seconds, size units) the mock plan gives each child


KINDS: dict[str, Exemplar] = {}
MENUS: dict[str, Menu] = {}
GOALS: dict[str, str] = {}


def register_exemplar(ex: Exemplar) -> Exemplar:
    KINDS[ex.kind] = ex
    return ex


def register_menu(role: str, menu: Menu, goal: str) -> None:
    MENUS[role] = menu
    GOALS[role] = goal


def kind_id(kind: str) -> str:
    """The id form used in payloads and vocabularies (no dots)."""
    return kind.replace(".", "_")
