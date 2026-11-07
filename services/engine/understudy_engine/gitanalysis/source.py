"""Git source adapter (PLG-2): reads LOCAL repositories through ``git log --numstat`` and yields commit RawItems.

Implements the plugin framework's ``Source`` interface (``understudy_engine.plugins.base``): ``read(since, until)`` yields
``RawItem(kind="commit", t0, t1, fields)`` oldest first, ``plugin_id = "git"``, ``schema_id = "commit.v1"``. The adapter is
read-only by construction:

* one subprocess, ``git log``, with a scrubbed environment: no global or system config, no pager, no terminal prompt,
  no optional index locks, ``core.hooksPath`` and ``core.fsmonitor`` switched off (so a repository cannot make this read
  run a program), ``protocol.allow=never`` (no network even if a remote is configured);
* it never writes: no ``fetch``, ``gc``, ``checkout`` or ``status`` (which can refresh the index);
* commit messages, paths and author identities live only inside ``RawItem.fields`` and are never logged. Errors carry a
  return code, never any output from git (PRV-4).

``fields`` of a commit item (the ``commit.v1`` names): ``sha``, ``author`` (the author email: raw, sensitive), ``message``
(subject, blank line, body), ``paths`` (up to ``MAX_FILES_KEPT``), ``n_files``, ``additions`` and ``deletions`` (totals over
every file, binary excluded), ``test_files``, ``is_revert``, ``is_merge``; plus ``tz_min`` (the author's UTC offset in
minutes, so "late night" can mean the author's own night; NEED: add it to the ``commit.v1`` schema).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Iterator
from datetime import datetime, UTC
from pathlib import Path

from ..plugins.base import RawItem, Source, SourceError, overlaps
from .digest import is_test_path

PLUGIN_ID = "git"
SEP_REC = "\x1e"
SEP_FIELD = "\x1f"
MAX_FILES_KEPT = 400
DEFAULT_MAX_COMMITS = 5000
HEADER_FIELDS = 8     # sha, parents, author date (raw), author email, subject, body, then the numstat tail

# The format has one extra trailing field so the numstat lines (which git appends after the format) are the tail.
LOG_FORMAT = SEP_REC + SEP_FIELD.join(["%H", "%P", "%ad", "%ae", "%s", "%b"]) + SEP_FIELD

GIT_CONFIG_OVERRIDES = (
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "core.pager=cat",
    "core.quotePath=false",
    "core.untrackedCache=false",
    "protocol.allow=never",
    "log.showSignature=false",
    "diff.external=",
    "diff.renames=false",
    "color.ui=never",
)


class GitSourceError(SourceError):
    """The repository could not be read. The message never contains git's output."""

    def __init__(self, message: str, code: str = "git_unreadable") -> None:
        super().__init__(code, message)


def author_key(email: str) -> str:
    return "a_" + hashlib.sha256(email.strip().lower().encode("utf-8", "replace")).hexdigest()[:10]


def scrubbed_env() -> dict[str, str]:
    """A minimal environment for git: nothing from the user's configuration reaches it."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.devnull,
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_ASKPASS": "true",
        "GIT_EXTERNAL_DIFF": "",
    }


def git_argv(repo: Path, *args: str) -> list[str]:
    cmd = ["git", "--no-pager", "-C", str(repo)]
    for kv in GIT_CONFIG_OVERRIDES:
        cmd += ["-c", kv]
    return cmd + list(args)


def _to_epoch(since: float | int | datetime | None) -> float | None:
    if since is None:
        return None
    if isinstance(since, datetime):
        return since.timestamp()
    return float(since)


def _parse_date_raw(raw: str) -> tuple[float, int]:
    """``--date=raw`` gives ``<unix> <+hhmm>``."""
    parts = raw.strip().split()
    ts = float(parts[0])
    tz = 0
    if len(parts) > 1 and len(parts[1]) == 5 and parts[1][0] in "+-":
        sign = -1 if parts[1][0] == "-" else 1
        tz = sign * (int(parts[1][1:3]) * 60 + int(parts[1][3:5]))
    return ts, tz


def _parse_numstat(tail: str) -> tuple[list[str], int, int, int]:
    paths: list[str] = []
    n_files = added = deleted = 0
    for line in tail.splitlines():
        if not line.strip():
            continue
        bits = line.split("\t", 2)
        if len(bits) != 3:
            continue
        a, d, path = bits
        binary = a == "-" or d == "-"
        n_files += 1
        added += 0 if binary or not a.isdigit() else int(a)
        deleted += 0 if binary or not d.isdigit() else int(d)
        if len(paths) < MAX_FILES_KEPT:
            paths.append(path)
    return paths, n_files, added, deleted


def _parse_commit(chunk: str) -> RawItem | None:
    parts = chunk.split(SEP_FIELD)
    if len(parts) < HEADER_FIELDS - 1:
        return None
    sha, parents, date_raw, email, subject, body = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
    tail = SEP_FIELD.join(parts[6:])
    try:
        ts, tz = _parse_date_raw(date_raw)
    except (ValueError, IndexError):
        return None
    paths, n_files, added, deleted = _parse_numstat(tail)
    n_parents = len(parents.split())
    t = datetime.fromtimestamp(ts, UTC)
    body = body.strip()
    return RawItem("commit", t, t, {
        "sha": sha.strip(),
        "author": email.strip().lower(),
        "message": subject + ("\n\n" + body if body else ""),
        "paths": paths,
        "n_files": n_files,
        "additions": added,
        "deletions": deleted,
        "test_files": sum(1 for p in paths if is_test_path(p)),
        "is_revert": subject.lstrip().lower().startswith("revert"),
        "is_merge": n_parents > 1,
        "tz_min": tz,
    })


class GitSource(Source):
    """Read one local repository. ``read(since, until)`` yields commits oldest first."""

    plugin_id = PLUGIN_ID
    schema_id = "commit.v1"

    def __init__(self, repo: str | os.PathLike, *, max_commits: int = DEFAULT_MAX_COMMITS, rev: str = "HEAD",
                 author: str | None = None, timeout_s: float = 60.0) -> None:
        super().__init__()
        self.repo = Path(repo)
        self.max_commits = int(max_commits)
        self.rev = rev
        self.author = author          # an author_key to keep (None keeps everyone)
        self.timeout_s = timeout_s

    def _argv(self, since: float | None) -> list[str]:
        args = ["log", "--numstat", "--no-renames", "--no-ext-diff", "--no-color", "--date=raw", "--reverse",
                f"--format={LOG_FORMAT}", "-n", str(self.max_commits)]
        if since is not None:
            args.append(f"--since=@{int(since)}")      # git's own cut-off; the exact filter is applied again below
        args += [self.rev, "--"]
        return git_argv(self.repo, *args)

    def read(self, since: datetime | float | int | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        t_since = _to_epoch(since)
        if not self.repo.exists():
            raise GitSourceError("repository path does not exist", "repo_missing")
        try:
            proc = subprocess.run(self._argv(t_since), capture_output=True, env=scrubbed_env(),
                                  timeout=self.timeout_s, check=False, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise GitSourceError("git log timed out", "git_timeout") from exc
        except OSError as exc:
            raise GitSourceError("git is not available", "git_missing") from exc
        if proc.returncode != 0:
            # An empty repository (no commits yet) is not an error: nothing to read.
            err = proc.stderr.decode("utf-8", "replace")
            if "does not have any commits" in err or "unknown revision" in err or "bad revision" in err or "ambiguous argument" in err:
                return
            raise GitSourceError(f"git log failed (exit {proc.returncode})")
        text = proc.stdout.decode("utf-8", "replace")
        del proc
        since_dt = since if isinstance(since, datetime) else (datetime.fromtimestamp(t_since, UTC) if t_since is not None else None)
        n = 0
        for chunk in text.split(SEP_REC):
            if not chunk.strip():
                continue
            item = _parse_commit(chunk)
            if item is None:
                self._note("unparsed_commits")
                continue
            if not overlaps(item.t0, item.t1, since_dt, until):
                continue
            if self.author is not None and author_key(item.fields["author"]) != self.author:
                continue
            n += 1
            yield item
        self._note("commits_read", n)

    def authors(self) -> dict[str, int]:
        """Commit counts per author_key (grouping keys only, no identities)."""
        out: dict[str, int] = {}
        for it in self.read():
            k = author_key(it.fields["author"])
            out[k] = out.get(k, 0) + 1
        return out


def read_repo(repo: str | os.PathLike, since: datetime | float | None = None, **kw) -> Iterator[RawItem]:
    return GitSource(repo, **kw).read(since)
