"""Retention (M9): delete the evidence that grows without bound, and nothing else.

``sweep(data_dir, max_age_days)`` looks at exactly three places and reports, or removes, files older than the limit:

* ``<data dir>/runs/<run id>/s<N>.png``: the step screenshots kept as evidence for agent runs (the run's JSON and artifacts stay);
* ``<data dir>/voice_cache/``: cached spoken sentences (audio of coach lines), except the voice choice file;
* the debug replay folder (``replay_dir=``, else ``ALONGSIDE_REPLAY_DIR``): recorded provider replies for the offline backup.

It is a DRY RUN unless ``dry_run=False`` is passed. It never deletes the egress ledger (or its refusal, clear-note and canary files), the
audit log, the approval queue, the kill flag, the per-boot token, the golden run or the synthetic data, because it never looks there; and a
second check refuses any path whose name or parent is protected, any symlink (the demo data directory links ``voice_cache`` to the shared
one), and any path that resolves outside the folder it is sweeping. A replay folder must have "replay" in its name, so a mistaken setting
cannot point it at a home folder.

Honest limits: age is the file's modification time; a deleted file is gone (no trash); the sweep does not securely wipe disk blocks.
CLI: ``python -m understudy_engine.privacy.retention [--days 30] [--apply] [--replay-dir DIR]``.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from ._paths import data_dir as default_data_dir

#: never deleted, by file name, wherever they are found
PROTECTED_NAMES = frozenset({
    "egress_ledger.jsonl", "egress_blocked.jsonl", "egress_ledger_meta.json", "privacy_canary.json", "audit.jsonl", "KILL", ".token", "voice_choice.json",
    "consent.json", "memory.md", "truth.json", "events.jsonl", "salt",
})
#: never entered, by directory name
PROTECTED_DIRS = frozenset({"queue", "golden", "synthetic", "real", "eval", "models", "routines", "locks", "pids", "logs"})
DEFAULT_DAYS = 30.0
_STEP_SHOT = re.compile(r"s[0-9]+\.png")          # the evidence screenshot of step N: s1.png, s12.png (not screenshot.png)


def _check_days(days: Any) -> float:
    if isinstance(days, bool) or not isinstance(days, (int, float)) or not math.isfinite(days) or days < 0:
        raise ValueError("max_age_days must be a number of days, zero or more")
    return float(days)


def _safe_file(path: Path, root: Path) -> bool:
    """A regular file that is not a symlink, is not protected by name or by an ancestor, and really lives under ``root``."""
    try:
        if path.is_symlink() or not path.is_file():
            return False
        if path.name in PROTECTED_NAMES:
            return False
        real = path.resolve()
        real_root = root.resolve()
        if real_root not in real.parents:
            return False
        rel = real.relative_to(real_root)
        return not any(part in PROTECTED_DIRS for part in rel.parts[:-1])
    except OSError:
        return False


def _walk_files(root: Path) -> list[Path]:
    """Files under ``root`` without following symlinked directories."""
    out: list[Path] = []
    if not root.is_dir() or root.is_symlink():
        return out
    for cur, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(cur, d)) and d not in PROTECTED_DIRS]
        out.extend(Path(cur) / f for f in files)
    return out


def _candidates(data: Path, replay: Path | None) -> list[tuple[str, Path, Path]]:
    """(category, file, the root it must stay inside)."""
    out: list[tuple[str, Path, Path]] = []
    runs = data / "runs"
    if runs.is_dir() and not runs.is_symlink():
        for run in sorted(p for p in runs.iterdir() if p.is_dir() and not p.is_symlink()):
            out.extend(("run_screenshot", f, runs) for f in sorted(run.iterdir()) if _STEP_SHOT.fullmatch(f.name))
    vc = data / "voice_cache"
    out.extend(("voice_cache", f, vc) for f in sorted(_walk_files(vc)))
    if replay is not None:
        if "replay" not in replay.name.lower():
            raise ValueError("the replay folder must have 'replay' in its name; refusing to sweep a folder that is not clearly one")
        out.extend(("debug_replay", f, replay) for f in sorted(_walk_files(replay)))
    return out


def sweep(data_dir: Path | str | None = None, max_age_days: float = DEFAULT_DAYS, *, dry_run: bool = True, now: float | None = None,
          replay_dir: Path | str | None = None) -> dict[str, Any]:
    """Report (``dry_run=True``, the default) or delete (``dry_run=False``) files older than ``max_age_days``. Returns
    ``{dry_run, max_age_days, cutoff, scanned, candidates, deleted, bytes_candidates, bytes_freed, by_category, protected_skipped, errors}``;
    each entry names a path relative to the swept root, its category, size and age. Nothing outside the three places is ever looked at."""
    days = _check_days(max_age_days)
    data = Path(data_dir) if data_dir is not None else default_data_dir()
    rp = replay_dir if replay_dir is not None else os.environ.get("ALONGSIDE_REPLAY_DIR")
    replay = Path(rp).expanduser() if rp else None
    t_now = time.time() if now is None else float(now)
    cutoff = t_now - days * 86400.0
    cands: list[dict[str, Any]] = []
    skipped = 0
    scanned = 0
    for category, f, root in _candidates(data, replay):
        scanned += 1
        if not _safe_file(f, root):
            skipped += 1
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_mtime > cutoff:
            continue
        cands.append({"category": category, "path": f.relative_to(root).as_posix() if root in f.parents else f.name, "root": root.name,
                      "bytes": st.st_size, "age_days": round((t_now - st.st_mtime) / 86400.0, 2), "_file": f})
    deleted: list[dict[str, Any]] = []
    errors: list[str] = []
    freed = 0
    if not dry_run:
        for c in cands:
            f = c["_file"]
            try:
                if f.is_symlink() or f.name in PROTECTED_NAMES:        # a second look immediately before deleting
                    continue
                f.unlink()
                freed += c["bytes"]
                deleted.append({k: v for k, v in c.items() if k != "_file"})
            except OSError as exc:
                errors.append(f"{c['category']}/{c['path']}: {type(exc).__name__}")
    by_cat: dict[str, dict[str, int]] = {}
    for c in cands:
        b = by_cat.setdefault(c["category"], {"files": 0, "bytes": 0})
        b["files"] += 1
        b["bytes"] += c["bytes"]
    return {
        "dry_run": dry_run, "max_age_days": days, "cutoff": cutoff, "scanned": scanned,
        "candidates": [{k: v for k, v in c.items() if k != "_file"} for c in cands], "deleted": deleted,
        "bytes_candidates": sum(c["bytes"] for c in cands), "bytes_freed": freed, "by_category": by_cat, "protected_skipped": skipped, "errors": errors,
        "note": ("Dry run: nothing was deleted. Pass dry_run=False to delete." if dry_run else "Deleted files are gone (no trash). The ledger, audit log, queue and "
                 "golden run are never swept."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.privacy.retention")
    ap.add_argument("--days", type=float, default=DEFAULT_DAYS, help="delete files older than this many days (default 30)")
    ap.add_argument("--apply", action="store_true", help="actually delete (the default is a dry run)")
    ap.add_argument("--replay-dir", help="the debug replay folder (default: $ALONGSIDE_REPLAY_DIR)")
    a = ap.parse_args(argv)
    rep = sweep(max_age_days=a.days, dry_run=not a.apply, replay_dir=a.replay_dir)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("candidates", "deleted")}, indent=1))
    print(f"{len(rep['candidates'])} candidate file(s); {len(rep['deleted'])} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
