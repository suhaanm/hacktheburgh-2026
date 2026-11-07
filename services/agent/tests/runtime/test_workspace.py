"""Workspaces (BGA-1, BGA-4): isolation, traversal and symlink refusal, worktrees on a COPY, cleanup, and the guard on the
owner's real working copy."""
from __future__ import annotations

import os
import subprocess

import pytest

from understudy_agent.runtime.workspace import MARKER, Workspace, WorkspaceError, assert_not_real_working_copy
from understudy_agent.security.paths import repo_root

from .helpers import git, tiny_repo


@pytest.fixture
def ws(tmp_path):
    w = Workspace.create("tmp", run_id="r_test0001", child_id="c1")
    yield w
    w.cleanup()


def test_tmp_workspace_has_a_marker_and_cleans_up(tmp_path):
    w = Workspace.create("tmp", run_id="r_test0001", child_id="c1")
    assert (w.root / MARKER).is_file() and w.work.is_dir() and (w.work / "out").is_dir()
    root = w.root
    w.cleanup()
    assert not root.exists()


def test_cleanup_refuses_a_directory_without_our_marker(tmp_path):
    w = Workspace.create("tmp", run_id="r_test0001", child_id="c1")
    (w.root / MARKER).unlink()
    root = w.root
    w.cleanup()
    assert root.exists()                       # not ours any more: never deleted
    (root / "work").rmdir() if not any((root / "work").iterdir()) else None


@pytest.mark.parametrize("bad,code", [
    ("../x", "path_traversal"), ("a/../../x", "path_traversal"), ("/etc/passwd", "absolute_path"), ("~/x", "absolute_path"),
    ("a\\b", "bad_path"), ("", "bad_path"), ("x\x00y", "bad_path"), (".git/config", "forbidden_name"),
    ("sub/.git/hooks/pre-commit", "forbidden_name"), (".env", "credential_path"), (".ssh/id_rsa", "credential_path"),
    ("C:\\x", "bad_path"), ("a" * 300, "bad_path"), (None, "bad_path"), (5, "bad_path"),
])
def test_paths_are_refused(ws, bad, code):
    with pytest.raises(WorkspaceError) as e:
        ws.resolve(bad)
    assert e.value.code == code


def test_a_symlink_component_is_refused_and_a_canary_outside_stays_untouched(ws, tmp_path):
    canary = tmp_path / "canary.txt"
    canary.write_text("untouched")
    os.symlink(canary, ws.work / "link")
    os.symlink(tmp_path, ws.work / "dirlink")
    for rel in ("link", "dirlink/canary.txt"):
        with pytest.raises(WorkspaceError) as e:
            ws.read_text(rel)
        assert e.value.code == "symlink"
        with pytest.raises(WorkspaceError):
            ws.write_text(rel, "pwned")
    assert canary.read_text() == "untouched"


def test_hard_links_are_refused_for_reads_and_writes(ws, tmp_path):
    canary = tmp_path / "canary.txt"
    canary.write_text("untouched")
    os.link(canary, ws.work / "hard")
    with pytest.raises(WorkspaceError) as e:
        ws.write_text("hard", "pwned")
    assert e.value.code == "hardlink"
    with pytest.raises(WorkspaceError):
        ws.read_text("hard")
    assert canary.read_text() == "untouched"


def test_integrity_scan_removes_symlinks_hardlinks_and_special_files(ws, tmp_path):
    canary = tmp_path / "canary.txt"
    canary.write_text("untouched")
    os.symlink(canary, ws.work / "out" / "s")
    os.link(canary, ws.work / "out" / "h")
    os.mkfifo(ws.work / "out" / "f")
    fixed = ws.integrity_scan()
    assert fixed["symlinks"] == 1 and fixed["hardlinks"] == 1 and fixed["special"] == 1
    assert sorted(os.listdir(ws.work / "out")) == [] and canary.read_text() == "untouched"


def test_write_read_roundtrip_and_limits(ws):
    n, sha = ws.write_text("src/a.txt", "héllo\n")
    assert n == len("héllo\n".encode()) and ws.read_text("src/a.txt")[0] == "héllo\n"
    with pytest.raises(WorkspaceError) as e:
        ws.write_text("big.txt", "x" * 500_000)
    assert e.value.code == "file_too_large"
    names = {e["name"] for e in ws.list_dir(".")}
    assert {"src", "input", "out"} <= names


def test_a_parent_that_is_a_file_or_symlink_is_refused(ws, tmp_path):
    ws.write_text("f", "x")
    with pytest.raises(WorkspaceError):
        ws.write_text("f/g.txt", "y")


def test_worktree_is_a_copy_the_source_is_untouched_and_the_patch_is_code_made(tmp_path):
    src = tiny_repo(tmp_path / "src_repo")
    before = git(src, "log", "--format=%H")
    status_before = git(src, "status", "--porcelain")
    w = Workspace.create("worktree", run_id="r_test0001", child_id="c1", repo_source=src)
    try:
        assert (w.work / "src" / "billing.py").is_file() and w.repo_copy != src
        assert git(w.repo_copy, "remote").strip() == ""                    # nothing in the copy can push back
        w.write_text("src/billing.py", "def total(xs):\n    return sum(xs) + 0\n")
        w.write_text("out/notes.txt", "scratch")                           # out/ is excluded from the patch
        patch = w.diff_patch()
        assert "billing.py" in patch and "notes.txt" not in patch
        assert git(src, "log", "--format=%H") == before and git(src, "status", "--porcelain") == status_before
        assert "+0" not in (src / "src" / "billing.py").read_text()
    finally:
        root = w.root
        w.cleanup()
    assert not root.exists()
    # the copy's git metadata lived inside the workspace, so the source has no extra worktrees
    assert "worktrees" not in os.listdir(src / ".git") or not os.listdir(src / ".git" / "worktrees")


def test_the_owners_real_working_copy_is_refused(tmp_path):
    with pytest.raises(WorkspaceError) as e:
        assert_not_real_working_copy(repo_root())
    assert e.value.code == "real_working_copy"
    with pytest.raises(WorkspaceError):
        Workspace.create("worktree", run_id="r_test0001", child_id="c1", repo_source=repo_root())
    with pytest.raises(WorkspaceError):
        Workspace.create("tmp", run_id="r_test0001", child_id="c1", base=repo_root() / "services")
    with pytest.raises(WorkspaceError):
        assert_not_real_working_copy(os.path.expanduser("~"))


def test_input_files_are_copied_by_code_and_credential_material_is_refused(tmp_path):
    good = tmp_path / "d.csv"
    good.write_text("a,b\n1,2\n")
    w = Workspace.create("tmp", run_id="r_test0001", child_id="c1", inputs=[(good, "data.csv")])
    try:
        assert (w.work / "input" / "data.csv").read_text() == "a,b\n1,2\n"
        env = tmp_path / ".env"
        env.write_text("KEY=1")
        with pytest.raises(WorkspaceError):
            w.copy_input(env, "x.csv")
        link = tmp_path / "ln.csv"
        os.symlink(good, link)
        with pytest.raises(WorkspaceError):
            w.copy_input(link, "y.csv")
    finally:
        w.cleanup()
