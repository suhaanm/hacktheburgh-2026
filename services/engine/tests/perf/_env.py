"""Shared set-up for the performance scripts in this folder (not a test module).

Copies a data root and a home folder to a throwaway place, points the engine at the copy and returns an app, so a measurement or a load
run never touches the owner's live data or the live engine on port 7700.

    from tests.perf._env import prepare
    ctx = prepare()                       # copies data/live-data and data/live-home (or the directories named by the arguments)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[2]          # services/engine
REPO = ENGINE_DIR.parents[1]


def _live_source(name: str) -> Path:
    """data/<name> in this checkout, else in the main checkout this worktree hangs off (data/ is not tracked, so a worktree has none)."""
    here = REPO / "data" / name
    if here.exists():
        return here
    for parent in REPO.parents:
        cand = parent / "data" / name
        if cand.exists():
            return cand
    raise FileNotFoundError(f"data/{name} not found next to {REPO} or above it")


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _copy_tree(src: Path, dst: Path, *, link_over: int = 80_000_000) -> None:
    """Copy a folder. A symlink in it (data/live-data links synthetic, golden, eval, voice_cache to the shared folders next to it) is followed and
    copied when what it points at is small (the engine reads data/live-data/synthetic: cohorts, learners), otherwise it stays a link to the original,
    which the engine only reads."""
    shutil.copytree(src, dst, symlinks=True)
    for child in list(dst.iterdir()):
        if child.is_symlink():
            target = (src / os.readlink(child)).resolve() if not os.path.isabs(os.readlink(child)) else Path(os.readlink(child))
            if not target.exists():
                continue
            child.unlink()
            if target.is_dir() and _size(target) <= link_over:
                shutil.copytree(target, child)
            elif target.is_dir() or target.is_file():
                child.symlink_to(target)


@dataclass
class Ctx:
    data: Path
    home: Path
    tmp: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def prepare(data: str | Path | None = None, home: str | Path | None = None, *, tmp: str | Path | None = None, mock: bool = False) -> Ctx:
    """Copy the data and home folders to ``tmp`` (default: a new temp dir) and set the environment to the copy."""
    src_data = Path(data) if data else _live_source("live-data")
    src_home = Path(home) if home else _live_source("live-home")
    root = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="understudy-perf-"))
    root.mkdir(parents=True, exist_ok=True)
    dst_data, dst_home = root / "data", root / "home"
    if not dst_data.exists():
        _copy_tree(src_data, dst_data)
    if not dst_home.exists():
        _copy_tree(src_home, dst_home)
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    os.environ["UNDERSTUDY_DATA_DIR"] = str(dst_data)
    os.environ["UNDERSTUDY_HOME"] = str(dst_home)
    os.environ["UNDERSTUDY_MOCK"] = "1" if mock else "0"
    os.environ["UNDERSTUDY_TEST_RELAXED_GUARD"] = "1"
    return Ctx(dst_data, dst_home, root)
