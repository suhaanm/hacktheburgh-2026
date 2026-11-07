from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path

import pytest

from understudy_engine.gitanalysis import synth
from understudy_engine.gitanalysis.records import load_records
from understudy_engine.gitanalysis.source import GitSource, GitSourceError, author_key, git_argv, scrubbed_env
from understudy_engine.plugins.base import RawItem, Source, SourceError


def tree_fingerprint(repo: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(repo.rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(repo)}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()


def test_items_match_truth(learner_repo):
    truth = synth.load_truth(learner_repo)
    items = list(GitSource(learner_repo).read())
    assert len(items) == truth["realised"]["n_commits"]
    assert all(isinstance(i, RawItem) and i.kind == "commit" and i.t0 == i.t1 for i in items)
    ts = [i.t0 for i in items]
    assert ts == sorted(ts)                                    # oldest first
    by_sha = {t["sha"]: t for t in truth["commits"]}
    for it in items:
        f = it.fields
        t = by_sha[f["sha"]]
        assert f["additions"] + f["deletions"] == t["lines"]    # numstat equals what the generator planned
        assert f["n_files"] == t["n_files"] == len(f["paths"])
        assert f["tz_min"] == truth["tz_min"]
        assert it.t0.timestamp() == t["t"]
        assert f["is_revert"] == (t["category"] == "revert") and f["is_merge"] is False
        assert f["test_files"] >= (1 if t["touches_tests"] else 0)
        assert author_key(f["author"]).startswith("a_") and "@" not in author_key(f["author"])


def test_is_a_framework_source(learner_repo):
    src = GitSource(learner_repo)
    assert isinstance(src, Source) and src.plugin_id == "git" and src.schema_id == "commit.v1"
    items = list(src.read())
    assert src.stats["commits_read"] == len(items)
    assert "withheld" in repr(items[0]) and "@" not in repr(items[0])           # the framework's repr hides fields
    from understudy_engine.plugins.schemas import check_item, get_schema
    problems = check_item(get_schema("commit.v1"), "commit", dict(items[0].fields))
    assert problems == ["unknown field tz_min"]                                   # NEED: commit.v1 gains tz_min
    with pytest.raises(SourceError):
        list(GitSource(learner_repo / "nope").read())


def test_since_until_filter(learner_repo):
    from datetime import datetime, timedelta
    items = list(GitSource(learner_repo).read())
    cut = items[len(items) // 2].t0
    later = list(GitSource(learner_repo).read(since=cut))
    assert later and all(i.t0 >= cut for i in later) and len(later) < len(items)
    assert list(GitSource(learner_repo).read(since=items[-1].t0 + timedelta(seconds=1))) == []
    assert list(GitSource(learner_repo).read(since=cut.timestamp())) == later          # epoch seconds also accepted
    earlier = list(GitSource(learner_repo).read(until=cut))
    assert earlier and all(i.t0 < cut for i in earlier) and len(earlier) + len(later) == len(items)


def test_read_is_read_only(learner_repo):
    before = tree_fingerprint(learner_repo)
    list(GitSource(learner_repo).read())
    load_records(learner_repo)
    assert tree_fingerprint(learner_repo) == before


def test_hooks_and_fsmonitor_never_run(tmp_path):
    repo = synth.make_repo(synth.RepoSpec(person="p_hook", days=5, seed=5), tmp_path / "h")
    marker = tmp_path / "ran"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n")
    script.chmod(0o755)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for name in ("post-checkout", "post-commit", "reference-transaction", "pre-auto-gc"):
        (hooks / name).write_text(f"#!/bin/sh\ntouch {marker}\n")
        (hooks / name).chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "config", "core.fsmonitor", str(script)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", str(hooks)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.pager", str(script)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "diff.external", str(script)], check=True)
    assert list(GitSource(repo).read())
    assert not marker.exists()


def test_caller_git_env_is_ignored(learner_repo, tmp_path, monkeypatch):
    other = synth.make_repo(synth.RepoSpec(person="p_other", days=3, seed=9), tmp_path / "o")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    n = len(list(GitSource(learner_repo).read()))
    assert n == synth.load_truth(learner_repo)["realised"]["n_commits"]


def test_no_network_and_scrubbed_env():
    argv = git_argv(Path("/x"), "log")
    assert "protocol.allow=never" in argv and "core.hooksPath=/dev/null" in argv and "core.fsmonitor=false" in argv
    env = scrubbed_env()
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull and env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert not any(k.startswith(("GIT_DIR", "GIT_WORK")) for k in env)


def test_errors_carry_no_git_output(tmp_path):
    with pytest.raises(GitSourceError):
        list(GitSource(tmp_path / "missing").read())
    plain = tmp_path / "notrepo"
    plain.mkdir()
    with pytest.raises(GitSourceError) as e:
        list(GitSource(plain).read())
    assert "fatal" not in str(e.value).lower() and str(plain) not in str(e.value)


def test_empty_repo_yields_nothing(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path / "e")], check=True)
    assert list(GitSource(tmp_path / "e").read()) == []


def test_canary_never_reaches_logs(canary_learner_repo, caplog):
    tokens = synth.load_truth(canary_learner_repo)["canaries"]
    assert tokens
    with caplog.at_level(logging.DEBUG):
        recs, _ = load_records(canary_learner_repo)
    text = caplog.text.lower()
    assert recs and not any(t.lower() in text for t in tokens)
    blob = repr([r.as_dict() for r in recs]).lower()               # records hold numbers and enums only
    assert not any(t.lower() in blob for t in tokens)
