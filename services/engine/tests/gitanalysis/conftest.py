"""Hermetic fixtures for the git-analysis tests: throwaway repos in tmp dirs, no network, no shared data/ or ~/.understudy."""
from __future__ import annotations

import pytest

from understudy_engine.gitanalysis import synth


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("git-hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_GIT", "UNDERSTUDY_X_LOCALMODEL", "UNDERSTUDY_GIT_REPOS", "GIT_DIR", "GIT_WORK_TREE", "UNDERSTUDY_GIT_DIGEST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)


@pytest.fixture(scope="session")
def cohort(tmp_path_factory):
    """Replicate 200 (never used for development): four learners and eight experts, plain."""
    dest = tmp_path_factory.mktemp("cohort-plain")
    return synth.make_cohort(dest, replicate=200)


@pytest.fixture(scope="session")
def canary_cohort(tmp_path_factory):
    dest = tmp_path_factory.mktemp("cohort-canary")
    return synth.make_cohort(dest, replicate=200, canary=True)


@pytest.fixture(scope="session")
def learner_repo(cohort):
    return cohort["learners"]["p_git_learner_4_r200"]


@pytest.fixture(scope="session")
def canary_learner_repo(canary_cohort):
    return canary_cohort["learners"]["p_git_learner_4_r200"]


@pytest.fixture(scope="session")
def cohort_template(tmp_path_factory):
    """The default synthetic cohort (replicate 0), generated once; tests copy it into their own data dir."""
    d = tmp_path_factory.mktemp("cohort-template") / "git"
    synth.ensure_cohort(d)
    return d


@pytest.fixture
def service_env(monkeypatch, tmp_path, cohort_template):
    """A private data dir that already holds the synthetic cohort, the git flag on, mock mode on."""
    import shutil

    from understudy_engine.gitanalysis import service

    data = tmp_path / "data"
    (data / "synthetic").mkdir(parents=True)
    shutil.copytree(cohort_template, data / "synthetic" / "git")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_X_GIT", "1")
    service.clear_caches()
    return data
