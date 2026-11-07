"""Isolated workspaces for child agents (BGA-1, BGA-4).

Kinds: `tmp` (an empty temp directory), `worktree` (`git worktree add` on a COPY of a repository; the source is only
ever cloned, never touched, and the copy has no remote), `none`.

Layout (ROOT is a fresh temp directory carrying a marker file; only WORK is writable by any tool or by run_python):

    ROOT/.understudy-workspace   marker (cleanup refuses to delete a directory without it)
    ROOT/copy/                   the repository copy (worktree kind only)
    ROOT/work/                   the tool root: tmp dir, or the git worktree of the copy
    ROOT/work/input/             files copied in by trusted code (never the model)
    ROOT/work/out/               what the child leaves for the worker; becomes the artifacts

Everything that resolves a path goes through `Workspace.resolve`: relative paths only, no `..`, no symlink in any
component, no `.git`, no credential-looking names, and the real path must stay inside WORK. Writes use O_NOFOLLOW and
refuse files with several hard links. After any sandboxed run, `integrity_scan` removes symlinks, hard-linked files and
special files so a child cannot leave a way out for a later step or for artifact collection.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..security.labels import sensitive_path
from ..security.paths import data_dir, repo_root
from ..security.settings import SettingsGuard
from . import policy
from .spec import Artifact

MARKER = ".understudy-workspace"
_FORBIDDEN_PARTS = {".git", ".hg", ".svn", MARKER}
_NAME_OK = re.compile(r"^[A-Za-z0-9._\-]{1,60}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_GIT_ENV_KEEP = ("PATH",)


class WorkspaceError(Exception):
    """A refused or failed workspace operation. `code` is a short stable reason; the message never echoes content."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def workspace_base() -> Path:
    env = os.environ.get("UNDERSTUDY_RUNTIME_WS_ROOT", "").strip()
    base = Path(env).expanduser() if env else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def git_env() -> dict[str, str]:
    """A cleared environment for git: no config from the user's home, no hooks, no prompts, no credential helpers."""
    return {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C",
            "GIT_ASKPASS": "/usr/bin/false", "GIT_ALLOW_PROTOCOL": "file"}


def run_git(args: list[str], cwd: Path, *, timeout: float = 60.0, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.ext.allow=never", "-c", "core.fsmonitor=false", *args]
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=git_env(), capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as e:
        raise WorkspaceError("git_timeout") from e
    except FileNotFoundError as e:
        raise WorkspaceError("git_missing") from e
    if check and p.returncode != 0:
        raise WorkspaceError("git_failed", f"git {args[0]} failed")
    return p


def _within(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(child), str(parent)]) == str(parent)
    except ValueError:
        return False


def assert_not_real_working_copy(path: Path) -> None:
    """Refuse to operate in the owner's real working copy (or their home directory, or the filesystem root).
    Workspaces are always fresh copies; this guards the places a copy is made FROM and made IN."""
    p = Path(path).resolve()
    root = repo_root().resolve()
    home = Path.home().resolve()
    if p == Path("/") or p == home:
        raise WorkspaceError("real_working_copy", "refusing to use the home directory or the filesystem root")
    if p == root or _within(root, p):
        raise WorkspaceError("real_working_copy", "refusing to use the owner's working copy or a directory that contains it")
    if _within(p, root) and not _within(p, data_dir().resolve()):
        raise WorkspaceError("real_working_copy", "refusing to operate inside the owner's working copy")


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Workspace:
    kind: str
    root: Path | None
    work: Path | None
    ws_id: str
    run_id: str
    child_id: str
    repo_copy: Path | None = None
    _closed: bool = False
    stats: dict[str, int] = field(default_factory=lambda: {"writes": 0, "refused": 0, "integrity_fixes": 0})

    # ------------------------------------------------------------------------------------------------ creation
    @classmethod
    def create(cls, kind: str, *, run_id: str, child_id: str, base: Path | None = None,
               inputs: list[tuple[Path, str]] | None = None, repo_source: Path | None = None,
               scratch: tuple[str, ...] | list[str] = ()) -> "Workspace":
        if kind not in policy.WORKSPACE_KINDS:
            raise WorkspaceError("bad_kind")
        ws_id = uuid.uuid4().hex[:10]
        if kind == "none":
            return cls("none", None, None, ws_id, run_id, child_id)
        base = (base or workspace_base()).resolve()
        assert_not_real_working_copy(base)
        root = Path(tempfile.mkdtemp(prefix="understudy-ws-", dir=str(base))).resolve()
        os.chmod(root, 0o700)
        (root / MARKER).write_text(f"{run_id}\n{child_id}\n{kind}\n")
        ws = cls(kind, root, root / "work", ws_id, run_id, child_id)
        try:
            if kind == "tmp":
                ws.work.mkdir(mode=0o700)  # type: ignore[union-attr]
            else:
                if repo_source is None:
                    raise WorkspaceError("repo_source_required")
                ws._make_worktree(Path(repo_source))
            for d in ("input", "out", ".run", ".tmp", "scratch"):
                (ws.work / d).mkdir(mode=0o700, exist_ok=True)  # type: ignore[operator]
            if kind == "worktree":
                excl = ws.repo_copy / ".git" / "info" / "exclude"  # type: ignore[operator]
                excl.parent.mkdir(parents=True, exist_ok=True)
                with open(excl, "a") as f:
                    f.write("\n/input/\n/out/\n/.run/\n/.tmp/\n/scratch/\n/status.json\n/state.json\n/control.json\n")
                    # the child's own scratch files (its script, its result file, the saved history) are not part of a patch
                    for name in scratch:
                        if re.fullmatch(r"[A-Za-z0-9._/\-]{1,100}", name) and ".." not in name:
                            f.write("/" + name + "\n")
            for src, name in inputs or []:
                ws.copy_input(Path(src), name)
        except BaseException:
            ws.cleanup()
            raise
        return ws

    def _make_worktree(self, src: Path) -> None:
        src = src.expanduser().resolve()
        assert_not_real_working_copy(src)
        if not src.is_dir():
            raise WorkspaceError("repo_missing")
        if run_git(["rev-parse", "--git-dir"], src, check=False).returncode != 0:
            raise WorkspaceError("not_a_git_repo")
        gitdir = src / ".git"
        if gitdir.is_dir():
            size = sum(f.stat().st_size for f in gitdir.rglob("*") if f.is_file() and not f.is_symlink())
            if size > 300_000_000:
                raise WorkspaceError("repo_too_large")
        copy = self.root / "copy"  # type: ignore[operator]
        # A local clone is a COPY of the committed history. It reads the source and writes only into `copy`.
        run_git(["clone", "--local", "--no-hardlinks", "--quiet", "--no-tags", str(src), str(copy)], self.root,  # type: ignore[arg-type]
                timeout=120)
        run_git(["remote", "remove", "origin"], copy, check=False)          # nothing in the copy can push back
        run_git(["config", "user.name", "understudy-agent"], copy)
        run_git(["config", "user.email", "agent@understudy.invalid"], copy)
        run_git(["config", "commit.gpgsign", "false"], copy)
        self.repo_copy = copy
        branch = f"understudy/{re.sub(r'[^A-Za-z0-9_-]', '-', self.run_id)[:30]}-{self.child_id}"
        run_git(["worktree", "add", "-b", branch, str(self.work), "HEAD"], copy)

    # ------------------------------------------------------------------------------------------------ paths
    def _need(self) -> Path:
        if self.work is None or self._closed:
            raise WorkspaceError("no_workspace")
        return self.work

    def resolve(self, rel: Any, *, must_exist: bool = False) -> Path:
        """Turn a model-supplied relative path into a safe absolute path inside WORK, or refuse."""
        work = self._need()
        try:
            p = self._resolve(work, rel, must_exist)
        except WorkspaceError:
            self.stats["refused"] += 1
            raise
        return p

    @staticmethod
    def _resolve(work: Path, rel: Any, must_exist: bool) -> Path:
        if not isinstance(rel, str) or not rel or len(rel) > 200:
            raise WorkspaceError("bad_path")
        if _CONTROL.search(rel) or "\\" in rel:
            raise WorkspaceError("bad_path")
        if rel.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", rel):
            raise WorkspaceError("absolute_path")
        parts = [x for x in rel.split("/") if x not in ("", ".")]
        if not parts:
            raise WorkspaceError("bad_path")
        if any(x == ".." for x in parts):
            raise WorkspaceError("path_traversal")
        if any(x in _FORBIDDEN_PARTS for x in parts):
            raise WorkspaceError("forbidden_name")
        if sensitive_path(rel):
            raise WorkspaceError("credential_path")
        cur = work
        for x in parts:
            cur = cur / x
            try:
                st = os.lstat(cur)
            except (FileNotFoundError, NotADirectoryError):
                continue
            if stat.S_ISLNK(st.st_mode):
                raise WorkspaceError("symlink")
        real = Path(os.path.realpath(cur))
        if not _within(real, work):
            raise WorkspaceError("outside_workspace")
        if must_exist and not os.path.lexists(cur):
            raise WorkspaceError("not_found")
        return cur

    def relpath(self, p: Path) -> str:
        return str(p.relative_to(self._need()))

    # ------------------------------------------------------------------------------------------------ file tools
    def read_text(self, rel: str, offset: int = 0, max_bytes: int = policy.MAX_READ_BYTES) -> tuple[str, int, bool]:
        """(text, total_bytes, truncated). Regular files only; one hard link only; bounded."""
        p = self.resolve(rel, must_exist=True)
        st = os.lstat(p)
        if not stat.S_ISREG(st.st_mode):
            raise WorkspaceError("not_a_file")
        if st.st_nlink > 1:
            raise WorkspaceError("hardlink")
        max_bytes = max(1, min(int(max_bytes), policy.MAX_READ_BYTES))
        offset = max(0, int(offset))
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fst = os.fstat(fd)
            if not stat.S_ISREG(fst.st_mode) or fst.st_ino != st.st_ino:
                raise WorkspaceError("changed_under_us")
            os.lseek(fd, offset, os.SEEK_SET)
            data = os.read(fd, max_bytes)
        finally:
            os.close(fd)
        return data.decode("utf-8", "replace"), st.st_size, (offset + len(data)) < st.st_size

    def list_dir(self, rel: str = ".", limit: int = 200) -> list[dict[str, Any]]:
        work = self._need()
        if rel in (".", "", "./"):
            d = work
        else:
            d = self.resolve(rel, must_exist=True)
        if not stat.S_ISDIR(os.lstat(d).st_mode):
            raise WorkspaceError("not_a_directory")
        out: list[dict[str, Any]] = []
        with os.scandir(d) as it:
            for e in sorted(it, key=lambda x: x.name):
                if e.name in _FORBIDDEN_PARTS or e.name.startswith(".run") or e.name == ".tmp":
                    continue
                st = e.stat(follow_symlinks=False)
                kind = "link" if stat.S_ISLNK(st.st_mode) else "dir" if stat.S_ISDIR(st.st_mode) else \
                    "file" if stat.S_ISREG(st.st_mode) else "other"
                out.append({"name": e.name[:80], "kind": kind, "bytes": st.st_size if kind == "file" else 0})
                if len(out) >= limit:
                    break
        return out

    def _usage(self) -> tuple[int, int]:
        total = n = 0
        for dp, dn, fn in os.walk(self._need(), followlinks=False):
            if ".git" in dn and Path(dp) == self._need():
                dn.remove(".git")
            for f in fn:
                try:
                    st = os.lstat(os.path.join(dp, f))
                except OSError:
                    continue
                total += st.st_size
                n += 1
        return total, n

    def write_text(self, rel: str, content: Any) -> tuple[int, str]:
        """Write a UTF-8 text file inside WORK. Returns (bytes, sha256). Bounded in size, count and total."""
        if not isinstance(content, str):
            raise WorkspaceError("bad_content")
        data = content.encode("utf-8")
        if len(data) > policy.MAX_FILE_BYTES:
            raise WorkspaceError("file_too_large")
        p = self.resolve(rel)
        total, n = self._usage()
        existing = 0
        parts = Path(self.relpath(p)).parts
        # parents: create one level at a time, each must be a real directory (no symlink)
        cur = self._need()
        for part in parts[:-1]:
            cur = cur / part
            if os.path.lexists(cur):
                st = os.lstat(cur)
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                    self.stats["refused"] += 1
                    raise WorkspaceError("parent_not_a_directory")
            else:
                os.mkdir(cur, 0o700)
        if os.path.lexists(p):
            st = os.lstat(p)
            if not stat.S_ISREG(st.st_mode):
                raise WorkspaceError("not_a_file")
            if st.st_nlink > 1:
                self.stats["refused"] += 1
                raise WorkspaceError("hardlink")
            existing = st.st_size
        else:
            n += 1
        if total - existing + len(data) > policy.MAX_WORKSPACE_BYTES or n > policy.MAX_WORKSPACE_FILES:
            raise WorkspaceError("workspace_full")
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            fst = os.fstat(fd)
            if not stat.S_ISREG(fst.st_mode) or fst.st_nlink > 1:
                raise WorkspaceError("hardlink")
            os.write(fd, data)
        finally:
            os.close(fd)
        self.stats["writes"] += 1
        return len(data), hashlib.sha256(data).hexdigest()

    def copy_input(self, src: Path, name: str) -> None:
        """Trusted code copies a file in (never the model). Regular files only, bounded, not credential material."""
        if not _NAME_OK.match(name):
            raise WorkspaceError("bad_input_name")
        src = Path(src).expanduser()
        try:
            st = os.lstat(src)
        except OSError as e:
            raise WorkspaceError("input_missing") from e
        if not stat.S_ISREG(st.st_mode):
            raise WorkspaceError("input_not_a_file")
        if st.st_size > policy.MAX_INPUT_BYTES:
            raise WorkspaceError("input_too_large")
        if sensitive_path(str(src)) or not SettingsGuard().check_path(src).allowed:
            raise WorkspaceError("input_protected")
        dest = self._need() / "input" / name
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            data = os.read(fd, policy.MAX_INPUT_BYTES + 1)
        finally:
            os.close(fd)
        dest.write_bytes(data)

    # ------------------------------------------------------------------------------------------------ integrity
    def integrity_scan(self) -> dict[str, int]:
        """After a sandboxed run: remove symlinks, hard-linked files and special files; report limit breaches."""
        work = self._need()
        fixed = {"symlinks": 0, "hardlinks": 0, "special": 0, "over_limit": 0}
        total = n = 0
        for dp, dn, fn in os.walk(work, followlinks=False):
            if Path(dp) == work and ".git" in dn:
                dn.remove(".git")
            for name in list(dn) + list(fn):
                full = os.path.join(dp, name)
                try:
                    st = os.lstat(full)
                except OSError:
                    continue
                if stat.S_ISLNK(st.st_mode):
                    os.unlink(full)
                    fixed["symlinks"] += 1
                    if name in dn:
                        dn.remove(name)
                elif stat.S_ISREG(st.st_mode):
                    if st.st_nlink > 1:
                        os.unlink(full)
                        fixed["hardlinks"] += 1
                    else:
                        total += st.st_size
                        n += 1
                elif not stat.S_ISDIR(st.st_mode):
                    os.unlink(full)
                    fixed["special"] += 1
        if total > policy.MAX_WORKSPACE_BYTES or n > policy.MAX_WORKSPACE_FILES:
            fixed["over_limit"] = 1
        self.stats["integrity_fixes"] += fixed["symlinks"] + fixed["hardlinks"] + fixed["special"]
        return fixed

    # ------------------------------------------------------------------------------------------------ git
    def diff_patch(self, max_bytes: int = policy.MAX_FILE_BYTES) -> str:
        """The patch draft for a worktree: everything the child changed, as a unified diff computed by code (never by
        the model). Nothing is committed to any remote and nothing is applied anywhere."""
        if self.kind != "worktree":
            raise WorkspaceError("not_a_worktree")
        work = self._need()
        run_git(["add", "-A"], work)
        p = run_git(["diff", "--cached", "--no-color", "--no-ext-diff", "--binary", "HEAD"], work)
        return p.stdout[:max_bytes]

    # ------------------------------------------------------------------------------------------------ artifacts
    def collect_artifacts(self, dest: Path, repo: Path | None = None, *, limit: int = 20) -> list[Artifact]:
        """Copy the regular files in WORK/out to `dest` (a run directory). Symlinks and odd names are skipped."""
        out_dir = self._need() / "out"
        arts: list[Artifact] = []
        if not out_dir.is_dir() or out_dir.is_symlink():
            return arts
        dest.mkdir(parents=True, exist_ok=True)
        for entry in sorted(out_dir.iterdir(), key=lambda e: e.name):
            if len(arts) >= limit:
                break
            if not _NAME_OK.match(entry.name):
                continue
            try:
                st = os.lstat(entry)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1 or st.st_size > 2_000_000:
                continue
            fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                data = os.read(fd, 2_000_001)
            finally:
                os.close(fd)
            target = dest / entry.name
            tmp = dest / (entry.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
            arts.append(Artifact(name=entry.name, kind=_kind_of(entry.name), path_ref=_ref(target, repo),
                                 sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
        return arts

    # ------------------------------------------------------------------------------------------------ cleanup
    def cleanup(self) -> None:
        if self._closed or self.root is None:
            self._closed = True
            return
        self._closed = True
        root = self.root
        marker = root / MARKER
        if not marker.is_file() or marker.is_symlink():
            return                                   # not ours: never delete
        if self.repo_copy is not None and self.work is not None:
            run_git(["worktree", "remove", "--force", str(self.work)], self.repo_copy, check=False)
        shutil.rmtree(root, ignore_errors=True)


def _kind_of(name: str) -> str:
    n = name.lower()
    if n.endswith((".png", ".svg", ".jpg")):
        return "chart"
    if n.endswith((".patch", ".diff")):
        return "patch"
    if n.endswith((".md", ".txt")):
        return "summary"
    if n.endswith(".json"):
        return "findings"
    if n.endswith((".csv", ".tsv")):
        return "data"
    return "log"


def _ref(p: Path, repo: Path | None) -> str:
    """The contract's `path_ref`: relative to the repo root when the file is under it, else under the data directory."""
    root = (repo or repo_root()).resolve()
    rp = p.resolve()
    try:
        return str(rp.relative_to(root))
    except ValueError:
        try:
            return "data/" + str(rp.relative_to(data_dir().resolve()))
        except ValueError:
            return rp.name
