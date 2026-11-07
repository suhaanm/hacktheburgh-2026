"""The exemplars (BGA-4, BGA-5, BGA-6): planted facts recovered and verified by code, patch drafts never applied without an
approved queue item, the source repository untouched, and an adversarial child caught."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.queue import ApprovalQueue
from understudy_agent.runtime.exemplars import base
from understudy_agent.runtime.exemplars.fixtures import TRUTH_DEV, make_dev_repo
from understudy_agent.runtime.exemplars.programming import apply_patch_draft
from understudy_agent.runtime.mockscripts import scripts_for
from understudy_agent.runtime.run import AgentRun, register
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.runtime.workspace import WorkspaceError
from understudy_agent.security.paths import repo_root
from understudy_agent.security.settings import Origin

from .helpers import git

pytestmark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")


def run_to_end(kind, params=None, *, timeout=120, **kw) -> AgentRun:
    r = AgentRun(kind=kind, params=params or {}, **kw)
    register(r).start()
    assert r.wait(timeout), f"run did not finish: {r.state}"
    return r


@pytest.fixture
def repo(tmp_path):
    p = tmp_path / "source_repo"
    make_dev_repo(p)
    return p


def test_the_suite_runs_three_children_in_parallel_and_recovers_every_planted_fact(repo):
    before = (git(repo, "log", "--format=%H"), git(repo, "status", "--porcelain"), git(repo, "branch", "--list"))
    r = run_to_end("programming.suite", {"repo_path": str(repo)})
    assert r.state == "done", r.to_dict(True)["result"]["children"]
    assert set(r.results) == {"c1", "c2", "c3"} and all(c.verified for c in r.results.values())
    assert len({id(rec.sup) for rec in r.children.values()}) == 3                # three supervisors, three workers
    byrole = {c.role: c for c in r.results.values()}
    ca = byrole["commit_analyst"].output
    assert ca["n_commits"] == TRUTH_DEV["n_commits"] and ca["reverts"] == TRUTH_DEV["reverts"]
    assert len(ca["giant_commits"]) == TRUTH_DEV["giant_commits"] and ca["fix_after_fix_chains"] == 2
    gaps = {g["path"] for g in byrole["test_gap"].output["gaps"]}
    assert gaps == set(TRUTH_DEV["hot_untested"]) and "src/auth.py" not in gaps
    cand = byrole["refactor_suggest"].output["candidates"]
    assert cand == [{"path": "src/billing.py", "literal": "0.2", "occurrences": 4, "constant": "CONST_0_2"}]
    # zero writes outside the worktree: the source repository is exactly as it was
    assert (git(repo, "log", "--format=%H"), git(repo, "status", "--porcelain"), git(repo, "branch", "--list")) == before
    assert "worktrees" not in {p.name for p in (repo / ".git").iterdir()}


def _patch_file(r: AgentRun):
    from understudy_agent.security.paths import data_dir

    art = next(a for a in r.results["c1"].artifacts if a.kind == "patch")
    rel = art.path_ref[len("data/"):] if art.path_ref.startswith("data/") else art.path_ref
    p = data_dir() / rel
    assert p.is_file(), p
    return p, art


def test_the_refactor_patch_draft_is_code_made_checked_and_queued_not_applied(repo):
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    r = run_to_end("programming.refactor_suggest", {"repo_path": str(repo)}, audit=audit, queue=q)
    res = r.results["c1"]
    assert r.state == "done" and res.verified
    names = {c.name for c in res.checks}
    assert {"patch_applies_to_a_fresh_copy", "tests_pass_with_the_patch", "patch_touches_only_src"} <= names
    pfile, patch_art = _patch_file(r)
    assert "CONST_0_2" in pfile.read_text() and hashlib.sha256(pfile.read_bytes()).hexdigest() == patch_art.sha256
    items = q.list("pending")
    patch_item = next(i for i in items if i["title"].startswith("Patch draft ready"))
    assert patch_item["status"] == "pending" and patch_item["signature"] == patch_art.sha256 and patch_item["risk_class"] == "normal"
    assert "0.2" in (repo / "src" / "billing.py").read_text() and "CONST_0_2" not in (repo / "src" / "billing.py").read_text()


def test_a_patch_is_applied_only_after_the_worker_approves_that_exact_patch(repo, tmp_path):
    audit = AuditLog()
    q = ApprovalQueue(audit=audit)
    r = run_to_end("programming.refactor_suggest", {"repo_path": str(repo)}, audit=audit, queue=q)
    pfile, art = _patch_file(r)
    item = next(i for i in q.list("pending") if i["title"].startswith("Patch draft ready"))
    target = tmp_path / "scratch_checkout"
    subprocess.run(["git", "clone", "-q", str(repo), str(target)], check=True)
    # 1. pending: refused, target untouched
    with pytest.raises(PermissionError):
        apply_patch_draft(pfile, target, queue=q, queue_id=item["id"], signature=art.sha256)
    assert "CONST_0_2" not in (target / "src" / "billing.py").read_text()
    # 2. approved by the worker's own action: applied once
    q.approve(item["id"], origin=Origin.HUMAN_UI)
    out = apply_patch_draft(pfile, target, queue=q, queue_id=item["id"], signature=art.sha256)
    assert out["applied"] and "CONST_0_2" in (target / "src" / "billing.py").read_text()
    # 3. single use: a replay is refused
    with pytest.raises(PermissionError):
        apply_patch_draft(pfile, target, queue=q, queue_id=item["id"], signature=art.sha256)
    # 4. a tampered patch is refused even with an approved item
    other = q.enqueue(kind="batch_result", title="x", summary="y", signature=art.sha256)
    q.approve(other["id"], origin=Origin.HUMAN_UI)
    pfile.write_text(pfile.read_text() + "\n+evil\n")
    with pytest.raises(PermissionError):
        apply_patch_draft(pfile, target, queue=q, queue_id=other["id"], signature=art.sha256)
    # 5. the owner's real working copy is never a target
    with pytest.raises(WorkspaceError):
        apply_patch_draft(pfile, repo_root(), queue=q, queue_id=other["id"], signature=hashlib.sha256(pfile.read_text().encode()).hexdigest())
    # approvals only by the worker's UI: an agent origin cannot approve
    third = q.enqueue(kind="batch_result", title="z", summary="z", signature="s")
    from understudy_agent.queue import NotPermitted

    with pytest.raises(NotPermitted):
        q.approve(third["id"], origin=Origin.AGENT)


def test_commit_analyst_and_test_gap_work_on_the_git_analysis_tracks_synthetic_repos(tmp_path):
    from understudy_engine.gitanalysis.synth import RepoSpec, make_repo

    src = make_repo(RepoSpec(person="p_t", level="learner", seed=5, days=14, planted=("big_commits", "tests_with_changes")), tmp_path / "s")
    r = run_to_end("programming.suite", {"repo_path": str(src)})
    assert r.results["c1"].verified and r.results["c2"].verified and r.results["c3"].verified, r.to_dict(True)["result"]["children"]
    assert r.results["c1"].output["n_commits"] > 20
    assert r.results["c3"].output["candidates"] == [] and not any(a.kind == "patch" for a in r.results["c3"].artifacts)


def test_the_weekly_summary_cites_supplied_digest_ids_only():
    r = run_to_end("creative.weekly_summary")
    c = r.results["c1"]
    assert r.state == "done" and c.verified
    draft = c.output["draft"]
    assert "12 changes" in draft and "[d_3a1000]" in draft and set(c.output["cited"]) <= {f"d_{(0x3a1000 + i * 977):06x}" for i in range(12)}
    assert "http" not in draft and "@" not in draft


def test_a_summary_that_cites_an_unknown_id_is_not_verified():
    tpl = base.MENUS["weekly_writer"].templates["weekly_summary"]
    bad = tpl.replace('cited = [i for cat in order for i in groups.get(cat, [])[:3]]',
                      'cited = [i for cat in order for i in groups.get(cat, [])[:3]] + ["d_ffffff"]').replace(
        'draft = "This week had "', 'draft = "See [d_ffffff]. This week had "')
    assert bad != tpl
    base.MENUS["weekly_writer"].templates["weekly_bad"] = bad
    try:
        port = MockProvider("benefits_clean")
        for title, replies in scripts_for("creative.weekly_summary", {}).items():
            if title == "child_step_weekly_writer":
                replies = [dict(replies[0], template="weekly_bad"), *replies[1:]]
            port.script_plan(title, *replies)
        r = run_to_end("creative.weekly_summary", port=port, auto_script=False)
    finally:
        del base.MENUS["weekly_writer"].templates["weekly_bad"]
    c = r.results["c1"]
    assert not c.verified and any(ch.name == "cites_only_supplied_ids" and not ch.ok for ch in c.checks)


def test_a_real_repo_path_inside_the_owners_working_copy_is_refused():
    r = run_to_end("programming.commit_analyst", {"repo_path": str(repo_root())})
    assert r.state in ("failed", "rejected") and not r.results


def test_programming_runs_are_deterministic(repo):
    def shape(r):
        d = r.to_dict(True)
        return d["state"], {cid: (c["output"], [a for a in [x["name"] for x in d["artifacts"] if x["child"] == cid]]) for cid, c in d["result"]["children"].items()}

    assert shape(run_to_end("programming.suite", {"repo_path": str(repo)})) == shape(run_to_end("programming.suite", {"repo_path": str(repo)}))
