"""Hermetic fixtures for the mlv2 tests: tiny seeded generators, mock mode, no network, no model calls, no repo data."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("UNDERSTUDY_MOCK", "1")


@pytest.fixture(scope="session")
def sim_episodes():
    from understudy_engine.hazard.sim import simulate_people

    eps, truth = simulate_people(6, 40, seed=3)
    return eps


@pytest.fixture(scope="session")
def sim_tab(sim_episodes):
    from understudy_engine.hazard.features import build_bins

    return build_bins(sim_episodes)
