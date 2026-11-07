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
