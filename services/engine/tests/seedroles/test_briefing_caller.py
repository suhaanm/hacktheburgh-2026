"""A briefing is the caller's own (Track R, 8 Nov 2026). On a stack where someone is set up and the engine is not in mock mode, ``GET /briefing?person=<someone else>`` (a screen that asked
before it knew who the worker is) answers with the caller's own briefing under the caller's id, never with another person's cards or id; asked without a person it is the caller's too.
Mock mode keeps ``?person=`` as asked (the evaluation's personas)."""
from __future__ import annotations

import json

import pytest

from .test_routes_worker import PERSON, client, others, seeded  # noqa: F401  (fixtures)


@pytest.mark.parametrize("asked", ["", "?person=p_ninetofive", "?person=p_nightowl", f"?person={PERSON}"])
def test_the_briefing_is_the_callers_whoever_is_asked_for(client, asked):
    r = client.get(f"/briefing{asked}")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["person"] == PERSON and others(json.dumps(body)) == []


def test_mock_mode_keeps_the_person_as_asked(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    r = client.get("/briefing?person=p_ninetofive")
    assert r.status_code == 200 and r.json()["data"]["person"] == "p_ninetofive"
