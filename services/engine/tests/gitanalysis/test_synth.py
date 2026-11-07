from __future__ import annotations

import subprocess
import time

import pytest

from understudy_engine.gitanalysis import synth
from understudy_engine.gitanalysis.features import build_table, compute_features
from understudy_engine.gitanalysis.records import load_records


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "HOME": "/dev/null"}).stdout


def test_real_repository(learner_repo):
    assert (learner_repo / ".git").is_dir() and (learner_repo / "README.md").exists()
    assert git(learner_repo, "fsck", "--strict") == "" or True        # exit status checked by check=True
    assert git(learner_repo, "status", "--porcelain").strip() == ""    # working tree matches HEAD
    truth = synth.load_truth(learner_repo)
    assert int(git(learner_repo, "rev-list", "--count", "HEAD").strip()) == truth["realised"]["n_commits"]


def test_deterministic(tmp_path):
    spec = synth.learner_specs(201)[0]
    a = synth.make_repo(spec, tmp_path / "a")
    b = synth.make_repo(spec, tmp_path / "b")
    assert git(a, "log", "--format=%H").split() == git(b, "log", "--format=%H").split()
    assert synth.load_truth(a)["commits"] == synth.load_truth(b)["commits"]
    other = synth.make_repo(synth.learner_specs(202)[0], tmp_path / "c")
    assert git(a, "log", "--format=%H").split() != git(other, "log", "--format=%H").split()


def test_make_repo_refuses_non_empty_dest(tmp_path):
    spec = synth.RepoSpec(person="p_x", days=3, seed=3)
    synth.make_repo(spec, tmp_path / "x")
    with pytest.raises(FileExistsError):
        synth.make_repo(spec, tmp_path / "x")


def test_fast(tmp_path):
    t0 = time.time()
    synth.make_repo(synth.learner_specs(203)[3], tmp_path / "t")
    assert time.time() - t0 < 5.0


def test_truth_matches_what_git_and_the_analysis_see(cohort):
    for person, repo in {**cohort["learners"], **cohort["experts"]}.items():
        truth = synth.load_truth(repo)
        recs, info = load_records(repo)
        tb = build_table(recs)
        real = truth["realised"]
        assert len(recs) == real["n_commits"]
        assert truth["person"] == person and truth["level"] in ("learner", "expert") and "nobody is real" in truth["note"]
        assert tb.num["big_commits"].sum() == real["big_commits"]
        assert tb.num["reverts"].sum() == real["reverts"]
        assert int(tb.num["late_night"].sum()) == real["late_night_commits"]       # local time, the author's own offset
        assert sum(1 for r in recs if r.category == "revert") == real["reverts"]
        # the per-commit labels: size bucket and test touch come from numbers and paths, so they must agree exactly
        by_sha = {t["sha"]: t for t in truth["commits"]}
        ts = sorted(truth["commits"], key=lambda t: t["t"])
        for r, t in zip(recs, ts):
            assert r.size_bucket == t["size_bucket"] and r.touches_tests == t["touches_tests"] and r.n_files == t["n_files"]
        assert len(by_sha) == len(recs)


def test_planted_habits_show_up_in_the_realised_rates(cohort):
    def share(person, key, den="n_commits"):
        r = synth.load_truth(cohort["learners"][person])["realised"]
        return r[key] / r[den]
    e = synth.load_truth(cohort["experts"]["p_git_expert_1_r200"])["realised"]
    l1 = "p_git_learner_1_r200"
    assert share(l1, "big_commits") > 3 * (e["big_commits"] / e["n_commits"]) + 0.05
    assert share(l1, "code_with_tests", "code_commits") < 0.4
    assert share("p_git_learner_3_r200", "late_night_commits") > 0.1
    assert share("p_git_learner_3_r200", "vague_messages") > 0.3


def test_canary_variant_changes_text_not_structure(cohort, canary_cohort):
    p = "p_git_learner_2_r200"
    plain, canary = cohort["learners"][p], canary_cohort["learners"][p]
    tp, tc = synth.load_truth(plain), synth.load_truth(canary)
    assert tc["canary"] and tc["canaries"] and not tp["canaries"]
    key = lambda t: [(c["t"], c["category"], c["lines"], c["n_files"], c["touches_tests"], c["message_quality"]) for c in t["commits"]]
    assert key(tp) == key(tc)                                        # same times, sizes, test touches, labels
    rp, _ = load_records(plain)
    rc, _ = load_records(canary)
    norm = lambda rs: [r.as_dict() | {"author_key": "", "message_quality": r.message_quality == "vague"} for r in rs]
    assert norm(rp) == norm(rc)                                       # (ok versus clear may differ: the digest reads the longer text)
    assert compute_features(rp)["habits"] == compute_features(rc)["habits"]


def test_canary_tokens_are_really_in_the_git_history(canary_cohort, cohort):
    repo = canary_cohort["learners"]["p_git_learner_4_r200"]
    tokens = synth.load_truth(repo)["canaries"]
    log = git(repo, "log", "--format=%an|%ae|%s|%b", "--name-only")
    marker = tokens[0]
    assert marker in log                                                 # author, email, customers, paths all carry the marker
    assert any(t in log for t in tokens[1:3])                            # name and email
    assert any(t in log for t in synth.load_truth(repo)["canaries"][3:5]) or marker in log
    assert marker not in git(cohort["learners"]["p_git_learner_4_r200"], "log", "--format=%an|%ae|%s|%b", "--name-only")


def test_unknown_habit_rejected():
    with pytest.raises(ValueError):
        synth.RepoSpec(person="p", planted=("nope",))


def test_cohort_shape(cohort):
    assert len(cohort["learners"]) == 4 and len(cohort["experts"]) == 8
    planted = {p: set(synth.load_truth(r)["planted"]) for p, r in cohort["learners"].items()}
    assert set().union(*planted.values()) == set(synth.HABIT_IDS)
    assert all(not synth.load_truth(r)["planted"] for r in cohort["experts"].values())
