"""The hit list reads the worker's own traces for the worker's current role. A seeded demo may lend another persona's traces, but only a persona of the SAME role
(as the Routines screen does): a programmer must never be shown a benefits processor's repeated steps."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from understudy_engine import routes_handoff as rh
from understudy_engine.hitlist import service as S


def _pd(person: str, role: str):
    return SimpleNamespace(person=person, role=role, origin="synthetic", t_last=1_794_000_000.0, events=[], earlier_events=[], truth=None)


class _Src:
    def __init__(self, people):
        self.people, self.read = people, []

    def load(self, pid):
        return self.people.get(pid)

    def episodes(self, pd):
        self.read.append(pd.person)
        return []


@pytest.mark.parametrize("lender_role,expect", [("benefits-processor", "p_me"), ("programmer", "p_lender")])
def test_a_lent_persona_is_read_only_when_it_has_the_workers_role(monkeypatch, lender_role, expect):
    me, lender = _pd("p_me", "programmer"), _pd("p_lender", lender_role)
    src = _Src({"p_lender": lender})
    monkeypatch.setattr(rh, "_resolve", lambda person: ("p_me", me))
    monkeypatch.setattr(rh, "_demo", lambda mem: {"person": "p_me", "routine_source": "p_lender", "routine_ids": ["x"]})
    monkeypatch.setattr(rh, "_src", lambda: src)
    monkeypatch.setattr(rh, "_sync_routines", lambda pd, mem, case=None: None)
    S.compute(None, 7)
    assert src.read == [expect]
