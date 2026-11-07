from __future__ import annotations

import os

import pytest

os.environ.setdefault("UNDERSTUDY_MOCK", "1")


@pytest.fixture(scope="session")
def synthetic_data():
    """The repo's synthetic data (seeded, deterministic). Regenerates only what is missing, like `understudy synth --all`."""
    from understudy_engine.eval.data import ensure_synthetic

    ensure_synthetic(None, log=lambda m: None)


@pytest.fixture(scope="session")
def apprentices_root(tmp_path_factory):
    """A private copy of the apprentices dataset: the deficit tests do not depend on what is in data/."""
    from understudy_engine.personas import apprentices

    root = tmp_path_factory.mktemp("eval_data")
    apprentices.generate(root)
    return root
