"""The routes the worker's own page reads answer for THE WORKER under each role, and never default to or echo another person (Track R, 8 Nov 2026).

On the live stack the worker's Growth sections were on example data because /calendar/week, /calendar/suggestions, /genome/<task> and /git/habits answered 404 for the worker's id, and the same
routes, asked without a person, defaulted to a generated person (p_ninetofive, p_nov13, p_git_learner_1). Pinned here, through the real app on a throwaway demo data directory seeded for the
programmer and the data analyst, with the profile switched through POST /profile:

* for each role (benefits processor, programmer, data analyst), with and without ``?person=<worker>``: /calendar/week, /calendar/suggestions, /calendar/people and the role's genome answer 200
  under the worker's id and role; the experienced worker is the unnamed reference ``expert``; no body holds another person's id;
* /git/habits answers 200 for the programmer's own repository, and a calm 404 (no other id, not the shared default learner) under the other roles; /git/people lists at most the worker's own;
* every other route that defaults its person (briefing, growth, presence, graph, hit list, coach, attention) answers for the worker or says calmly there is nothing, never for someone else;
* nobody set up: the calendar, genome and git routes behave exactly as before (the evaluation's personas)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from understudy_engine import routes_handoff as rh
from understudy_engine.seedroles import PERSON, events as E
from understudy_engine.store.jsonl import EventStore

SHARED = Path("/Users/suhaan/Desktop/hacktheburgh/data/synthetic")
NOW = datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)
BP, PR, DA = "benefits-processor", "programmer", "data-analyst"
ANOTHER = re.compile(r"\bp_(?:irregular|nightowl|ninetofive|shiftwkr)\b|\bp_(?:[a-z]+_)*[a-z]*\d+[a-z0-9_]*\b")
BAD = re.compile(r"synthetic|simulated|made[- ]?up|\bdemo\b|example data|sample data|stand-in|fake|pretend", re.I)

pytestmark = pytest.mark.skipif(not (SHARED / "learners" / "events.jsonl").exists(), reason="the shared synthetic data is not generated here")


def others(body: str) -> list[str]:
    return sorted({m for m in ANOTHER.findall(body) if m != PERSON})


def strings(o, skip=("origin", "origin_detail")):
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v, skip)
    elif isinstance(o, str):
        yield o


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    dd = tmp_path_factory.mktemp("worker-routes") / "demo-data"
    dd.mkdir()
    (dd / "synthetic").symlink_to(SHARED)                                    # the shared dataset, read only (calendars, learners, apprentices, git cohort)
    live = [{"schema": 1, "id": f"liveevt-{i:04d}", "t": f"2026-11-08T01:{i:02d}:00.000Z", "origin": "real", "actor": "human", "person": PERSON, "role": BP, "source": "browser", "type": "click",
             "target": {"role": "button"}, "meta": {"zone": "household_form"}} for i in range(8)]
    EventStore(dd).append_many(live)
    for role in (PR, DA):
        E.seed(dd, role, NOW, lambda m: None)
    return SimpleNamespace(dd=dd)


@pytest.fixture()
def client(seeded, tmp_path, monkeypatch):
    for k, v in (("UNDERSTUDY_DATA_DIR", str(seeded.dd)), ("UNDERSTUDY_HOME", str(tmp_path / "home")), ("UNDERSTUDY_MOCK", "0"), ("UNDERSTUDY_X", "1"), ("UNDERSTUDY_NO_WARM", "1")):
        monkeypatch.setenv(k, v)
    rh._cache.clear()
    from understudy_engine.calendar import store as cs

    cs.reset_default()
    from understudy_engine.api.app import create_app

    c = TestClient(create_app(seeded.dd, warm=False))
    r = c.post("/onboarding", json={"role": BP, "answers": {"capture": True}, "person": PERSON})
    assert r.status_code == 200, r.text
    return c


def switch(c: TestClient, role: str) -> None:
    r = c.post("/profile", json={"role": role})
    assert r.status_code == 200 and r.json()["role"] == role, r.text


GENOME = {BP: "t_entitlement_check", PR: "programmer", DA: "data-analyst"}


@pytest.mark.parametrize("role", [BP, PR, DA])
def test_the_calendar_answers_for_the_worker_under_each_role(client, role):
    switch(client, role)
    for qs in ("", f"?person={PERSON}"):
        week = client.get(f"/calendar/week{qs}")
        assert week.status_code == 200, week.text
        d = week.json()["data"]
        assert d["person"] == PERSON and d["role"] == role and d["days"] and d["features"] and d["weeks_available"]
        assert d["expert"]["person"] == "expert" and d["gap"]["ribbon"]["nearest_expert"] == "expert"
        assert others(week.text) == [], others(week.text)
        sug = client.get(f"/calendar/suggestions{qs}")
        assert sug.status_code == 200, sug.text
        assert others(sug.text) == [] and all(PERSON in s["id"] for s in sug.json()["data"])
    people = client.get("/calendar/people").json()["data"]
    assert [p["person"] for p in people] == [PERSON] and people[0]["role"] == role and people[0]["weeks"]


def test_the_role_switch_changes_the_calendar_the_week_is_read_from(client):
    switch(client, PR)
    pr = client.get("/calendar/week").json()["data"]
    switch(client, DA)
    da = client.get("/calendar/week").json()["data"]
    switch(client, BP)
    bp = client.get("/calendar/week").json()["data"]
    assert (pr["role"], da["role"], bp["role"]) == (PR, DA, BP)
    assert len({json.dumps(x["features"], sort_keys=True) for x in (pr, da, bp)}) == 3                  # three different weeks, one per role


@pytest.mark.parametrize("role", [BP, PR, DA])
def test_the_genome_answers_in_the_workers_own_scope_under_each_role(client, role):
    switch(client, role)
    for qs in ("", f"&person={PERSON}"):
        r = client.get(f"/genome/{GENOME[role]}?reference=nearest_expert{qs}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["person"] == PERSON and d["scope"] == "person" and d["alignment"] and d["cases"] and d["expert"]["segments"] and d["novice"]["segments"]
        assert "expert_person" not in d and "people" not in d and "decomposition" not in d and "controls" not in d      # no other person, no cohort figures
        assert others(r.text) == [], others(r.text)
    if role != BP:                                                    # in a role's own cohort page the other learners are not reachable by id
        other = client.get(f"/genome/{GENOME[role]}?person=p_nov13")
        assert other.status_code == 404 and others(other.text) == [] and "Known people" not in other.text      # not even the id the caller sent comes back


def test_the_benefits_worker_can_open_one_of_their_own_cases_and_the_graph(client):
    switch(client, BP)
    d = client.get("/genome/t_entitlement_check").json()["data"]
    case = d["cases"][3]["episode"]
    one = client.get(f"/genome/{case}?person={PERSON}")
    assert one.status_code == 200 and one.json()["data"]["episode"] == case
    g = client.get("/graph/transitions")
    assert g.status_code == 200 and others(g.text) == []


def test_git_habits_are_the_programmers_own_and_a_calm_nothing_for_the_other_roles(client):
    switch(client, PR)
    for qs in ("", f"?person={PERSON}"):
        r = client.get(f"/git/habits{qs}")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["person"] == PERSON and r.json()["data"]["habits"] and others(r.text) == []
    ppl = client.get("/git/people").json()
    assert [x["person"] for x in ppl["learners"]] == [PERSON] and ppl["experts"] == [] and ppl["default_person"] == PERSON
    for role in (BP, DA):
        switch(client, role)
        for qs in ("", f"?person={PERSON}"):
            r = client.get(f"/git/habits{qs}")
            assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person" and others(r.text) == [], r.text
        assert client.get("/git/people").json()["learners"] == []


@pytest.mark.parametrize("role", [BP, PR, DA])
def test_no_defaulting_route_answers_for_someone_else(client, role):
    switch(client, role)
    for path in ("/briefing", "/growth", "/presence", "/graph/work", "/hitlist", "/coach/state", "/routines", "/attention/digest", "/attention/next", "/calendar/week", "/calendar/suggestions",
                 "/genome/" + GENOME[role], "/git/habits", "/git/people", "/insights/worker"):
        r = client.get(path)
        assert r.status_code in (200, 404), (path, r.status_code, r.text[:200])
        assert others(r.text) == [], (path, others(r.text))
        if r.status_code == 404:
            assert "Known people" not in r.text and "Try one of" not in r.text, (path, r.text[:200])


def test_nothing_a_person_reads_in_these_answers_says_how_the_data_was_made(client):
    for role in (BP, PR, DA):
        switch(client, role)
        for path in ("/calendar/week", "/calendar/suggestions", "/calendar/people", "/genome/" + GENOME[role], "/git/habits"):
            r = client.get(path)
            if r.status_code == 200:
                body = r.json()
                offenders = [s for s in strings({"data": body.get("data"), "meta": {k: v for k, v in (body.get("meta") or {}).items() if k != "origin"}}) if BAD.search(s)]
                assert offenders == [], (role, path, offenders[:2])


def test_an_unknown_person_error_names_nobody(client):
    switch(client, BP)
    r = client.get("/routines/detect")                       # any route that falls back to the unknown-person answer
    r = client.get("/presence?person=p_nobody_here")
    assert r.status_code == 404 and "Known people" not in r.text and others(r.text) == []


def test_with_nobody_set_up_the_routes_behave_as_before(seeded, tmp_path, monkeypatch):
    for k, v in (("UNDERSTUDY_DATA_DIR", str(seeded.dd)), ("UNDERSTUDY_HOME", str(tmp_path / "empty-home")), ("UNDERSTUDY_MOCK", "0"), ("UNDERSTUDY_X", "1"), ("UNDERSTUDY_NO_WARM", "1")):
        monkeypatch.setenv(k, v)
    rh._cache.clear()
    from understudy_engine.calendar import store as cs

    cs.reset_default()
    from understudy_engine.api.app import create_app

    c = TestClient(create_app(seeded.dd, warm=False))
    w = c.get("/calendar/week").json()["data"]
    assert w["person"] == "p_ninetofive"                                       # the evaluation's persona, as before
    assert c.get("/git/habits").json()["data"]["person"].startswith("p_git_learner")
    assert len(c.get("/calendar/people").json()["data"]) > 10
