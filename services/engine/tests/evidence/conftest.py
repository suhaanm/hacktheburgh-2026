"""Hermetic fixtures for the evidence tests: private data and home dirs, mock mode, no flags, no network, no key."""
from __future__ import annotations

import pytest

from understudy_engine.evidence import evaluate as EV

_FLAGS = ("UNDERSTUDY_X", "UNDERSTUDY_X_EVIDENCE", "UNDERSTUDY_X_LOCALMODEL", "UNDERSTUDY_X_PRIVACY", "UNDERSTUDY_EVIDENCE_CLOUD",
          "UNDERSTUDY_EVIDENCE_LIVE", "UNDERSTUDY_LOCALMODEL_RULES_ONLY")


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("evidence-hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("AGENT_PORT", "1")            # nothing listens there: the agent service is "down", never the live one
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)
    for k in _FLAGS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(scope="session")
def cohort(tmp_path_factory):
    """32 packets (16 synthetic novices, two cases each) from the real genome builder, with scripted blocks added (``fakes.enrich``)."""
    root = tmp_path_factory.mktemp("evidence-cohort")
    packets, info = EV.build_cohort_packets(root, with_hazard=False)
    return packets


@pytest.fixture(scope="session")
def packets(cohort):
    return [pk for _, _, pk in cohort]


@pytest.fixture(scope="session")
def pk0(packets):
    return packets[0]
