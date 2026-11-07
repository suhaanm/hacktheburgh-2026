from __future__ import annotations

import pytest

from understudy_engine.personas import PERSONA_BY_SLUG, apprentices, learners, write_persona


@pytest.fixture(scope="session")
def synth_root(tmp_path_factory):
    """Apprentices, learners and the four personas (the hazard model is fitted on them), generated once."""
    root = tmp_path_factory.mktemp("coach_synth")
    apprentices.generate(root)
    learners.generate(root)
    for slug in PERSONA_BY_SLUG:
        write_persona(PERSONA_BY_SLUG[slug], root, with_mc=False)
    return root


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    """No test here may touch the shared data/ directory or the real ~/.understudy (KILL flag, queue, audit, study state,
    memory file): other agents run tests at the same time, and a stale data/KILL would stop the live demo services.
    Tests that need data generate it under their own tmp dir (the synthetic generators are deterministic)."""
    root = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)
