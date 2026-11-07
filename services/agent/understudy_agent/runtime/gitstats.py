"""Read-only git aggregates for the `git_log` tool and for the result verifiers (BGA-4).

One parser, used both by the child's tool and by the code that CHECKS the child's claims, so a claim is compared with
an independent recomputation. Commit subjects are classified into a small fixed vocabulary and then dropped: only the
class, times, sizes and file paths leave this module, never message text. Authors become indexes.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

from .workspace import WorkspaceError, run_git

KLASSES = ("revert", "fix", "test", "refactor", "docs", "feat", "other")
_REVERT = re.compile(r"^\s*revert\b", re.I)
_FIX = re.compile(r"\b(fix(es|ed)?|bug ?fix|hotfix|patch|repair)\b", re.I)
_TEST = re.compile(r"^\s*(test|tests|add tests?|testing)\b", re.I)
_REFACTOR = re.compile(r"^\s*(refactor|clean ?up|tidy|rename|extract|simplify|restructure)\b", re.I)
_DOCS = re.compile(r"^\s*(docs?|readme|document)\b", re.I)
_FEAT = re.compile(r"^\s*(feat|feature|add|implement|introduce|create|support)\b", re.I)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs)(/|$)|(^|/)test_[^/]*\.py$|_test\.(py|go|rb)$|\.(test|spec)\.[jt]sx?$")
_SEP_REC, _SEP_FLD = "\x1e", "\x1f"


def classify_subject(subject: str) -> str:
    if _REVERT.search(subject):
        return "revert"
    if _TEST.search(subject):
        return "test"
    if _REFACTOR.search(subject):
        return "refactor"
    if _DOCS.search(subject):
        return "docs"
    if _FIX.search(subject):
        return "fix"
    if _FEAT.search(subject):
        return "feat"
    return "other"


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def parse_git_log(repo: Path, *, max_commits: int = 300) -> dict[str, Any]:
    """Structured history of the checked-out branch: commits (newest first) with files and sizes, no message text."""
    max_commits = max(1, min(int(max_commits), 1000))
    p = run_git(["log", f"--max-count={max_commits}", "--no-color", "--numstat", "--no-renames",
                 f"--format={_SEP_REC}%H{_SEP_FLD}%at{_SEP_FLD}%an{_SEP_FLD}%s"], repo, timeout=60, check=False)
    if p.returncode != 0:
        raise WorkspaceError("git_log_failed")
    authors: dict[str, int] = {}
    commits: list[dict[str, Any]] = []
    for rec in p.stdout.split(_SEP_REC):
        if not rec.strip():
            continue
        head, _, rest = rec.partition("\n")
        parts = head.split(_SEP_FLD)
        if len(parts) < 4:
            continue
        sha, ts, author, subject = parts[0], parts[1], parts[2], _SEP_FLD.join(parts[3:])
        files = []
        add = dele = 0
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            a = int(cols[0]) if cols[0].isdigit() else 0
            d = int(cols[1]) if cols[1].isdigit() else 0
            files.append({"path": cols[2], "add": a, "del": d, "test": is_test_path(cols[2])})
            add += a
            dele += d
        idx = authors.setdefault(author, len(authors))
        commits.append({"sha": sha[:10], "ts": int(ts) if ts.isdigit() else 0, "author": idx,
                        "klass": classify_subject(subject), "files": files, "add": add, "del": dele,
                        "n_files": len(files), "touches_test": any(f["test"] for f in files)})
    return {"commits": commits, "n_authors": len(authors)}


def summarize(log: dict[str, Any]) -> dict[str, Any]:
    """Numbers only: what the planner sees about a history."""
    cs = log["commits"]
    n = len(cs)
    if n == 0:
        return {"n_commits": 0, "n_authors": 0, "median_files": 0, "p90_lines": 0, "max_lines": 0,
                "share_touch_test": 0.0, "reverts": 0, "fix_commits": 0, "n_files_touched": 0}
    lines = sorted(c["add"] + c["del"] for c in cs)
    paths = {f["path"] for c in cs for f in c["files"]}
    return {
        "n_commits": n, "n_authors": log["n_authors"],
        "median_files": float(statistics.median(c["n_files"] for c in cs)),
        "p90_lines": lines[min(n - 1, int(0.9 * n))], "max_lines": lines[-1],
        "share_touch_test": round(sum(1 for c in cs if c["touches_test"]) / n, 3),
        "reverts": sum(1 for c in cs if c["klass"] == "revert"),
        "fix_commits": sum(1 for c in cs if c["klass"] == "fix"),
        "n_files_touched": len(paths),
    }
