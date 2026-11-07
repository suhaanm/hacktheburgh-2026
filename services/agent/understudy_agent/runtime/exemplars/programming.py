"""Programming exemplar (BGA-4): commit analyst, test-gap finder and refactor suggester, each in an isolated worktree.

Each child works in a `git worktree` of a COPY of the repository (the source is only cloned; the copy has no remote),
writes a vetted script into it, runs the script in the sandbox, and emits a typed result. CODE then recounts the history
itself and compares; for the refactor, code computes the patch draft from the diff, applies it to a FRESH copy with
`git apply` and runs the repository's tests there. Patch drafts are never applied or pushed: each becomes a pending
approval item, and `apply_patch_draft` refuses unless that item was approved by the worker and the patch is unchanged.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..gitstats import parse_git_log
from ..results import VerifyCtx, close, register_schema, register_verifier
from ..sandbox import run_python
from ..spec import Check, RoleDef, register_role
from ..workspace import Workspace, WorkspaceError, assert_not_real_working_copy, run_git
from .base import Exemplar, Menu, WorkspaceNeeds, register_exemplar, register_menu, script_text

_SHA = {"type": "string", "pattern": "^[0-9a-f]{10}$"}
_PATH = {"type": "string", "maxLength": 200}
COMMITS_V1: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["n_commits", "n_authors", "giant_threshold", "giant_commits", "test_touch_share", "reverts",
                 "fix_after_fix_chains", "by_class"],
    "properties": {
        "n_commits": {"type": "integer", "minimum": 0}, "n_authors": {"type": "integer", "minimum": 0},
        "giant_threshold": {"type": "integer"},
        "giant_commits": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "required": ["sha", "lines", "files"], "additionalProperties": False,
            "properties": {"sha": _SHA, "lines": {"type": "integer"}, "files": {"type": "integer"}}}},
        "test_touch_share": {"type": "number", "minimum": 0, "maximum": 1}, "reverts": {"type": "integer", "minimum": 0},
        "fix_after_fix_chains": {"type": "integer", "minimum": 0},
        "by_class": {"type": "object", "additionalProperties": {"type": "integer"}, "maxProperties": 10},
    },
}
TESTGAP_V1: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["n_commits", "min_untested_changes", "gaps"],
    "properties": {
        "n_commits": {"type": "integer", "minimum": 0}, "min_untested_changes": {"type": "integer"},
        "gaps": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "required": ["path", "changes", "untested_changes"], "additionalProperties": False,
            "properties": {"path": _PATH, "changes": {"type": "integer"}, "untested_changes": {"type": "integer"}}}},
    },
}
REFACTOR_V1: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["candidates", "files_changed"],
    "properties": {
        "files_changed": {"type": "integer", "minimum": 0},
        "candidates": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "required": ["path", "literal", "occurrences", "constant"], "additionalProperties": False,
            "properties": {"path": _PATH, "literal": {"type": "string", "maxLength": 20},
                           "occurrences": {"type": "integer", "minimum": 3}, "constant": {"type": "string", "maxLength": 40}}}},
    },
}
register_schema("commits_v1", COMMITS_V1)
register_schema("testgap_v1", TESTGAP_V1)
register_schema("refactor_v1", REFACTOR_V1)

_GIT_TOOLS = frozenset({"git_log", "write_workspace", "run_python", "emit_result", "list_dir"})
_EDIT_TOOLS = frozenset({"write_workspace", "run_python", "emit_result", "list_dir"})
register_role(RoleDef("commit_analyst", "Describe a repository's history: giant commits, reverts, fix chains, test share.",
                      _GIT_TOOLS, frozenset({"worktree"}), "commits_v1", "commit_analyst"))
register_role(RoleDef("test_gap", "Find source files that keep changing without a test.", _GIT_TOOLS,
                      frozenset({"worktree"}), "testgap_v1", "test_gap"))
register_role(RoleDef("refactor_suggest", "Suggest one small safe refactor as a patch draft that keeps the tests green.",
                      _EDIT_TOOLS, frozenset({"worktree"}), "refactor_v1", "refactor_suggest"))
_FILES = {"gitlog": "gitlog.json", "script": "analyze.py", "result": "result.json"}
register_menu("commit_analyst", Menu(files=_FILES, templates={"commit_stats": script_text("commit_stats.py")}),
              "Describe the commit history of the repository the worker named.")
register_menu("test_gap", Menu(files=_FILES, templates={"test_gap": script_text("gap_finder.py")}),
              "Find source files that keep changing without a test in the repository the worker named.")
register_menu("refactor_suggest", Menu(files={"script": "refactor.py", "result": "result.json"},
                                       templates={"refactor_literals": script_text("refactor_literals.py")}),
              "Suggest one small safe refactor for the repository the worker named, as a patch draft.")


# ------------------------------------------------------------------------------------------------ recounts
def _count_commits(repo: Path) -> int:
    return int(run_git(["rev-list", "--count", "HEAD"], repo).stdout.strip())


def _subjects(repo: Path) -> list[str]:
    return run_git(["log", "--format=%s"], repo).stdout.splitlines()


def recount_commits(repo: Path) -> dict[str, Any]:
    log = parse_git_log(repo, max_commits=1000)
    cs = sorted(log["commits"], key=lambda c: (c["ts"], c["sha"]))
    giants = {c["sha"] for c in cs if c["add"] + c["del"] > 450}
    chains, last = 0, {}
    for c in cs:
        if c["klass"] == "fix":
            if c["author"] in last and c["ts"] - last[c["author"]] <= 7200:
                chains += 1
            last[c["author"]] = c["ts"]
    return {"n_commits": _count_commits(repo), "giants": giants, "chains": chains,
            "reverts": sum(1 for s in _subjects(repo) if re.match(r"\s*revert\b", s, re.I)),
            "test_share": sum(1 for c in cs if c["touches_test"]) / len(cs) if cs else 0.0, "n_authors": log["n_authors"]}


def recount_gaps(repo: Path) -> set[str]:
    code = (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".swift", ".kt")
    changes: dict[str, int] = {}
    untested: dict[str, int] = {}
    for c in parse_git_log(repo, max_commits=1000)["commits"]:
        for f in c["files"]:
            if f["test"] or not f["path"].endswith(code):
                continue
            changes[f["path"]] = changes.get(f["path"], 0) + 1
            if not c["touches_test"]:
                untested[f["path"]] = untested.get(f["path"], 0) + 1
    return {p for p in changes if untested.get(p, 0) >= 3 and untested.get(p, 0) / changes[p] >= 0.7}


def tests_pass_with_patch(patch: str, repo_copy: Path) -> tuple[bool, bool]:
    """(patch applies cleanly to a FRESH copy, the repository's unittest tests pass there). Both by code, sandboxed."""
    ws = Workspace.create("worktree", run_id="r_verify00", child_id="c1", repo_source=repo_copy)
    try:
        ws.write_text(".tmp/draft.patch", patch)
        p = run_git(["apply", "--check", ".tmp/draft.patch"], ws.work, check=False)  # type: ignore[arg-type]
        if p.returncode != 0:
            return False, False
        run_git(["apply", ".tmp/draft.patch"], ws.work)  # type: ignore[arg-type]
        ws.write_text("run_tests.py", "import sys, unittest\nsys.path.insert(0, '.')\n"
                      "r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover('tests'))\n"
                      "sys.exit(0 if r.wasSuccessful() else 1)\n")
        res = run_python(ws, "run_tests.py", timeout_s=30)
        return True, res.exit_code == 0
    except WorkspaceError:
        return False, False
    finally:
        ws.cleanup()


def _need_repo(ctx: VerifyCtx) -> Path:
    if ctx.repo_copy is None:
        raise WorkspaceError("no_repo_copy")
    return ctx.repo_copy


def verify_commits(ctx: VerifyCtx) -> list[Check]:
    t, o = recount_commits(_need_repo(ctx)), ctx.output
    return [Check(name="commit_count_matches", ok=o["n_commits"] == t["n_commits"]),
            Check(name="authors_match", ok=o["n_authors"] == t["n_authors"]),
            Check(name="giant_commits_match", ok={g["sha"] for g in o["giant_commits"]} == t["giants"]),
            Check(name="reverts_match", ok=o["reverts"] == t["reverts"]),
            Check(name="fix_chains_match", ok=o["fix_after_fix_chains"] == t["chains"]),
            Check(name="test_share_matches", ok=close(o["test_touch_share"], t["test_share"], 1e-3, 1e-3))]


def verify_gaps(ctx: VerifyCtx) -> list[Check]:
    repo = _need_repo(ctx)
    claimed = {g["path"] for g in ctx.output["gaps"]}
    return [Check(name="commit_count_matches", ok=ctx.output["n_commits"] == _count_commits(repo)),
            Check(name="gaps_match", ok=claimed == recount_gaps(repo))]


def _literals(repo: Path) -> dict[str, tuple[str, int]]:
    """(path -> (literal, count)) of numbers written 3 or more times, recounted with `ast` (not the template's tokenizer)."""
    import ast

    skip = {0, 1, 2, 10, 100}
    out: dict[str, tuple[str, int]] = {}
    for p in sorted((repo / "src").rglob("*.py")) if (repo / "src").is_dir() else []:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        counts: dict[float, int] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool) \
                    and n.value not in skip:
                counts[n.value] = counts.get(n.value, 0) + 1
        rep = [(c, v) for v, c in counts.items() if c >= 3]
        if rep:
            c, v = max(rep)
            out[str(p.relative_to(repo))] = (repr(v), c)
    return out


def verify_refactor(ctx: VerifyCtx) -> list[Check]:
    repo = _need_repo(ctx)
    claimed = {c["path"]: (c["literal"], c["occurrences"]) for c in ctx.output["candidates"]}
    truth = _literals(repo)
    checks = [Check(name="candidates_match", ok=claimed == truth)]
    patch = ctx.ws.diff_patch() if ctx.ws is not None else ""
    heads = re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)
    checks.append(Check(name="patch_matches_claim", ok=bool(patch.strip()) == bool(claimed) and
                        (not claimed or set(heads) == set(claimed))))
    checks.append(Check(name="patch_touches_only_src", ok=all(h.startswith("src/") for h in heads)))
    if patch.strip():
        applies, passes = tests_pass_with_patch(patch, repo)
        checks += [Check(name="patch_applies_to_a_fresh_copy", ok=applies), Check(name="tests_pass_with_the_patch", ok=passes)]
    return checks


register_verifier("commit_analyst", verify_commits)
register_verifier("test_gap", verify_gaps)
register_verifier("refactor_suggest", verify_refactor)


# ------------------------------------------------------------------------------------------------ approval-gated apply
def apply_patch_draft(patch_file: Path, target: Path, *, queue: Any, queue_id: str, signature: str) -> dict[str, Any]:
    """Apply a patch draft to `target` ONLY if the worker approved its queue item and the patch is the one that was
    approved (the item's signature is the patch's sha256). `target` must be a git working tree that is not the owner's
    real working copy. Without an approved item nothing is touched. Returns {applied, files}."""
    import hashlib

    assert_not_real_working_copy(target)               # first: a refused target never spends an approval
    patch = patch_file.read_text()
    if hashlib.sha256(patch.encode()).hexdigest() != signature:
        raise PermissionError("the patch changed since it was queued")
    if not queue.consume_approval(queue_id, signature):
        raise PermissionError("no approved queue item for this patch draft")
    tmp = target / ".understudy-draft.patch"
    tmp.write_text(patch)
    try:
        run_git(["apply", "--check", tmp.name], target)
        run_git(["apply", tmp.name], target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"applied": True, "files": re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)}


# ------------------------------------------------------------------------------------------------ the spawn kinds
def prepare(params: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    from .fixtures import make_dev_repo

    p = dict(params or {})
    if not p.get("repo_path"):
        repo = run_dir / "fixtures" / "repo"
        truth = make_dev_repo(repo, canary=p.get("canary"))
        p.update(repo_path=str(repo), synthetic=True, truth=truth)
    path = Path(str(p["repo_path"])).expanduser()
    if not path.is_dir():
        raise ValueError("repo_path must name a directory")
    assert_not_real_working_copy(path)
    p["repo_path"] = str(path.resolve())
    return p


def needs(role: str, params: dict[str, Any]) -> WorkspaceNeeds:
    return WorkspaceNeeds(repo_source=Path(params["repo_path"]))


def mock_steps(role: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    tpl = {"commit_analyst": "commit_stats", "test_gap": "test_gap", "refactor_suggest": "refactor_literals"}[role]
    seq: list[dict[str, Any]] = [] if role == "refactor_suggest" else [{"tool": "git_log", "file": "gitlog"}]
    return seq + [{"tool": "write_workspace", "file": "script", "template": tpl}, {"tool": "run_python", "file": "script"},
                  {"tool": "emit_result", "file": "result"}]


for _kind, _roles, _title in (
    ("programming.commit_analyst", ("commit_analyst",), "Analyse a repository's commits"),
    ("programming.test_gap", ("test_gap",), "Find files that change without tests"),
    ("programming.refactor_suggest", ("refactor_suggest",), "Suggest a refactor as a patch draft"),
    ("programming.suite", ("commit_analyst", "test_gap", "refactor_suggest"), "Commit analyst, test-gap finder and refactor suggester in parallel"),
):
    register_exemplar(Exemplar(kind=_kind, title=_title, describe=_title + " in an isolated worktree copy.", roles=_roles,
                               needs=needs, prepare=prepare, mock_steps=mock_steps, explicit_files=("repo_path",)))
