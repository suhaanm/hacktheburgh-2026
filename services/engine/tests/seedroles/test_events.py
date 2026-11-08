"""Twelve weeks of captured work for the worker under each role (programmer, data analyst), written as an idempotent top-up (seedroles.events), and the engine reading it per role.

The owner switches role in the Account menu and must find that role's week, hours, routines and steps, not a blank page and never another role's: history is kept per role, for the SAME
worker id, in any order of switching. What is pinned here:

* the seed writes schema-valid events under ``<data>/history/<person>/`` only (never the ``real`` partition, never the shared ``synthetic`` dataset), skips nothing it should not, refuses a data
  directory that is not a demo one, and a second run changes nothing;
* for each role, through the real app: /presence, /graph/work, /routines (the pack's own templates, some proposable), /coach/state, and for the programmer /git/habits all have content;
* switching roles back and forth gives each role its own history every time, and the benefits role keeps only its own (live capture);
* the generated week uses the pack's own cogs and routine templates (nothing typed into a screen), a week off is in it, and nothing a person reads says how it was made;
* the benefits learner trajectory is never read as another role's skill state, and the demo routine source is only used under the role it belongs to.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from understudy_engine import routes_handoff as rh
from understudy_engine.memory import load_pack
from understudy_engine.routines.sources import PersonSource
from understudy_engine.seedroles import PERSON, events as E
from understudy_engine.store.jsonl import EventStore

NOW = datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)
BP, PR, DA = "benefits-processor", "programmer", "data-analyst"
BAD = re.compile(r"synthetic|simulated|made[- ]?up|\bdemo\b|example data|sample data|fake|pretend", re.I)


def _strings(o, skip=("origin", "origin_detail")):
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from _strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v, skip)
    elif isinstance(o, str):
        yield o


def _tree(d: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(d)): (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """A demo data directory with both roles seeded and one live-capture file for today (as the live stack has), once for the module."""
    dd = tmp_path_factory.mktemp("roles") / "demo-data"
    dd.mkdir()
    live = [{"schema": 1, "id": f"liveevt-{i:04d}", "t": f"2026-11-08T01:{i:02d}:00.000Z", "origin": "real", "actor": "human", "person": PERSON, "role": BP, "source": "browser", "type": "click",
             "target": {"role": "button"}, "meta": {"zone": "household_form"}} for i in range(8)]
    EventStore(dd).append_many(live)
    out: list[str] = []
    results = {role: E.seed(dd, role, NOW, out.append) for role in (PR, DA)}
    return SimpleNamespace(dd=dd, results=results, out=out, live=(dd / "real" / PERSON / "2026-11-08.jsonl").read_bytes())


@pytest.fixture()
def client(seeded, tmp_path, monkeypatch):
    for k, v in (("UNDERSTUDY_DATA_DIR", str(seeded.dd)), ("UNDERSTUDY_HOME", str(tmp_path / "home")), ("UNDERSTUDY_MOCK", "0"), ("UNDERSTUDY_X", "1"), ("UNDERSTUDY_NO_WARM", "1")):
        monkeypatch.setenv(k, v)
    rh._cache.clear()
    from understudy_engine.api.app import create_app

    c = TestClient(create_app(seeded.dd, warm=False))
    r = c.post("/onboarding", json={"role": BP, "answers": {"capture": True}, "person": PERSON})
    assert r.status_code == 200, r.text
    return c


def switch(c: TestClient, role: str) -> None:
    r = c.post("/profile", json={"role": role})
    assert r.status_code == 200 and r.json()["role"] == role, r.text


# ------------------------------------------------------------------------------------------------ what the seed writes
def test_the_seed_wrote_valid_events_for_the_worker_under_history_only(seeded):
    dd = seeded.dd
    assert all(r["events"] and r["written"] for r in (seeded.results[PR], seeded.results[DA]))
    assert (dd / ".seed-events-programmer").exists() and (dd / ".seed-events-data-analyst").exists()
    files = sorted((dd / "history" / PERSON).glob("*.jsonl"))
    assert files and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}-(pg|da)\.jsonl", f.name) for f in files)
    assert not (dd / "synthetic").exists()                                                     # the shared dataset is never written
    assert (dd / "real" / PERSON / "2026-11-08.jsonl").read_bytes() == seeded.live             # nor the live capture, nor the real partition
    assert sorted(p.name for p in (dd / "real" / PERSON).iterdir()) == ["2026-11-08.jsonl"]
    store = EventStore(dd)
    for code, role in (("pg", PR), ("da", DA)):
        mine = [f for f in files if f.name.endswith(f"-{code}.jsonl")]
        evs = [e for f in mine for e in store.read_file(f)]                                     # read_file validates every row against the event schema and the model
        assert len(evs) == seeded.results[role]["rows"] > 20000
        assert {e.person for e in evs} == {PERSON} and {e.role for e in evs} == {role} and {e.origin for e in evs} == {"synthetic"}
        assert len({e.id for e in evs}) == len(evs)
        days = sorted({e.t.date().isoformat() for e in evs})
        assert len(days) >= 45 and days[0] >= "2026-08-10" and days[-1] <= "2026-11-07"       # twelve weeks, ending the day before the live capture
        off0 = datetime.fromisoformat(seeded.results[role]["off_week"]).date()
        assert not {(off0 + timedelta(days=i)).isoformat() for i in range(7)} & set(days)       # the week away has no events


def test_the_seed_is_idempotent_and_refuses_a_data_dir_that_is_not_a_demo_one(seeded, tmp_path):
    before = _tree(seeded.dd)
    out: list[str] = []
    assert E.seed(seeded.dd, PR, NOW, out.append) == {"events": True, "written": False} and "already seeded" in out[-1]
    assert E.seed(seeded.dd, DA, NOW, out.append)["written"] is False
    assert _tree(seeded.dd) == before                                                          # not a byte, not a timestamp
    real = tmp_path / "real-data"
    real.mkdir()
    assert E.seed(real, PR, NOW, out.append) == {"events": False} and not any(real.iterdir()) and "not a demo data dir" in out[-1]
    with pytest.raises(ValueError):
        E.seed(seeded.dd, BP, NOW)


def test_a_day_file_that_already_exists_is_skipped_not_overwritten(tmp_path):
    dd = tmp_path / "demo-data"
    (dd / "history" / PERSON).mkdir(parents=True)
    clash = dd / "history" / PERSON / "2026-09-01-da.jsonl"
    clash.write_text("kept\n")
    res = E.seed(dd, DA, NOW, lambda m: None)
    assert res["written"] and res["skipped_days"] == 1 and clash.read_text() == "kept\n"


def test_the_history_is_made_from_the_packs_own_cogs_and_routine_templates():
    for role, planted in ((PR, {"rerun-failed-ci", "ci-status-sweep"}), (DA, {"weekly-metric-refresh", "parameterised-weekly-query"})):
        spec = E.derived_spec(role)
        pack = load_pack(role)
        ids = {r.id for r in spec.routines}
        assert len(ids) == 4 and ids <= {t["id"] for t in pack.templates} and planted <= ids        # four of the pack's own templates, the frozen one among them
        emitted = [c for c in pack.extra_cogs if c in spec.emit]
        assert len(emitted) >= 14                                                                  # the cogs the pack adds have an emission, taken from the pack's own mapping
        prior = pack.priors["cog_dwell_s"]
        assert all(spec.dwell[c][0] == float(prior[c]) for c in emitted if c in prior)             # and a dwell time from the pack's own priors


def test_the_week_has_the_new_cogs_and_the_routines_repeat_enough_to_be_found(seeded):
    store = EventStore(seeded.dd)
    for code, role in (("pg", PR), ("da", DA)):
        evs = [e for f in sorted((seeded.dd / "history" / PERSON).glob(f"*-{code}.jsonl")) for e in store.read_file(f)]
        spec = E.derived_spec(role)
        base = {z for c in __import__("understudy_engine.personas_v2.roles", fromlist=["get_role"]).get_role(role).emit.values() for z in [c.zone]}
        pack_zones = {spec.emit[c].zone for c in load_pack(role).extra_cogs if c in spec.emit} - base
        seen = {e.meta.get("zone") for e in evs if e.meta}
        assert len(seen & pack_zones) >= 5, f"{role}: too few of the zones the deepened pack added are in the week ({sorted(seen & pack_zones)})"
        assert sum(1 for e in evs if e.type == "task_start") > 600


# ------------------------------------------------------------------------------------------------ the engine reads it per role
@pytest.mark.parametrize("role", [PR, DA])
def test_every_event_section_has_content_under_each_role(client, role):
    switch(client, role)
    pack = load_pack(role)
    p = client.get("/presence").json()
    assert p["meta"]["origin"] == "real" and p["meta"]["n"] >= 60 and p["data"]["active_h_per_week"] >= 20 and len(p["data"]["bins"]) == 672
    g = client.get("/graph/work").json()["data"]
    kinds = {n["type"] for n in g["nodes"]}
    assert kinds >= {"routine", "skill", "memory"} and len(g["nodes"]) >= 25
    skill_labels = {n["label"] for n in g["nodes"] if n["type"] == "skill"}
    assert len(skill_labels) >= 10 and all(s.get("id") for s in pack.skills)
    rt = client.get("/routines").json()["data"]
    templated = [r for r in rt if r.get("template_id")]
    assert len(templated) >= 4 and {r["template_id"] for r in templated} <= {t["id"] for t in pack.templates} and {r["role"] for r in rt} == {role}
    assert sum(1 for r in templated if r["proposable"]) >= 1                                    # something is worth proposing...
    assert sum(1 for r in templated if not r["proposable"]) >= 1                                # ...and something is honestly held back (the skill gate)
    coach = client.get("/coach/state").json()
    assert coach["task"]["name"] == {PR: "Programmer", DA: "Data analyst"}[role]
    assert not [s for s in _strings([p, g, rt, coach]) if BAD.search(s)]


def test_the_programmers_commit_history_is_theirs(client):
    switch(client, PR)
    d = client.get(f"/git/habits?person={PERSON}")
    assert d.status_code == 200
    data = d.json()["data"]
    assert data["person"] == PERSON and data["n_commits"] >= 150 and len(data["habits"]) == 6
    assert any(h["flagged"] for h in data["habits"]) and not all(h["flagged"] for h in data["habits"])
    assert PERSON in {x["person"] for x in client.get("/git/people").json()["learners"]}
    assert not [s for s in _strings(d.json()) if BAD.search(s)]


@pytest.mark.parametrize("task,role", [("programmer", PR), ("fix-a-failing-build", PR), ("data-analyst", DA)])
def test_the_steps_against_an_experienced_worker_are_the_workers_own_and_name_nobody_else(client, task, role):
    switch(client, role)
    r = client.get(f"/genome/{task}?person={PERSON}")
    assert r.status_code == 200, r.text
    d, meta = r.json()["data"], r.json()["meta"]
    assert d["scope"] == "person" and d["person"] == PERSON and d["task"] in (task, role)
    assert len(d["alignment"]) >= 8 and d["expert"]["segments"] and d["novice"]["segments"] and isinstance(d["person_gap_s"], float)
    assert len(d["cases"]) == E.COHORT_CASES and all(isinstance(c["gap_s"], float) for c in d["cases"]) and len({round(c["gap_s"]) for c in d["cases"]}) >= 6       # a case each, varied
    assert {w["label"] for w in d["person_waterfall"]} >= {"Slower on shared steps", "Other extra steps"}
    assert meta["n_unit"] == "cases" and meta["n"] == E.COHORT_CASES
    blob = json.dumps(r.json())
    assert re.findall(r"\bp_[a-z0-9_]+", blob) == [PERSON] * blob.count(PERSON)                                                    # no other person's id anywhere
    assert not {"people", "waterfall", "controls", "decomposition", "expert_person"} & set(d)                                       # no cohort figure, no named expert
    assert not [s for s in _strings(r.json()) if BAD.search(s)]
    one = client.get(f"/genome/{task}?person={PERSON}&episode={d['cases'][2]['episode']}").json()["data"]
    assert one["episode"] == d["cases"][2]["episode"] and one["person_gap_s"] == d["cases"][2]["gap_s"]
    assert client.get(f"/genome/{task}?person={PERSON}&reference=consensus").status_code == 200
    tr = client.get(f"/graph/transitions?task={task}&person={PERSON}")
    assert tr.status_code == 200 and len(tr.json()["data"]["edges"]) >= 20 and tr.json()["meta"]["n_unit"] == "cases"
    assert client.get(f"/genome/{task}?person=p_pt005003").status_code in (404, 422)                                                # another learner of the cohort is not reachable by id
    assert client.get("/genome/no-such-task").status_code == 404


def test_the_role_cohort_is_written_apart_from_the_week_and_the_workers_own_cases_are_among_its_learners(seeded):
    for role in (PR, DA):
        d = seeded.dd / "roles" / role / "cohort"
        levels = json.loads((d / "roster.json").read_text())
        assert levels[PERSON] == "novice" and sum(v == "expert" for v in levels.values()) >= 3 and len(levels) == E.COHORT_PEOPLE
        assert (d / "events.jsonl").stat().st_size > 1_000_000
        assert not list((seeded.dd / "history").rglob("roster*")) and not list((seeded.dd / "history").rglob("events.jsonl"))          # the cohort never sits in the worker's week


def test_switching_roles_keeps_each_history_apart_in_any_order(client):
    def snap(role: str) -> dict:
        switch(client, role)
        p = client.get("/presence").json()
        rt = client.get("/routines").json()["data"]
        return {"days": p["meta"]["n"], "active": p["data"]["active_h_per_week"], "routines": sorted(r["id"] for r in rt), "roles": {r["role"] for r in rt}}

    first = {r: snap(r) for r in (PR, DA, BP)}
    assert first[PR]["roles"] == {PR} and first[DA]["roles"] == {DA}
    assert not set(first[PR]["routines"]) & set(first[DA]["routines"])                          # never the other's routines
    assert first[PR]["days"] >= 60 and first[DA]["days"] >= 60 and first[PR]["active"] != first[DA]["active"]
    assert first[BP]["days"] == 1 and first[BP]["routines"] == []                               # benefits keeps only its own: today's live capture
    for role in (DA, PR, BP, PR, DA):                                                           # back and forth: every return finds the same history
        assert snap(role) == first[role]


def test_the_benefits_role_is_not_given_the_other_roles_events_by_the_set_up_call(client):
    r = client.post("/onboarding", json={"role": PR, "answers": {"capture": True}, "person": PERSON})                       # "set up again" for another role is the same
    assert r.status_code == 200
    assert len(client.get("/routines").json()["data"]) >= 4
    assert client.post("/onboarding", json={"role": BP, "answers": {"capture": True}, "person": PERSON}).status_code == 200
    assert client.get("/routines").json()["data"] == []


# ------------------------------------------------------------------------------------------------ the engine edits
def _ev(role: str, i: int):
    from understudy_engine.core import Event

    return Event.model_construct(schema_version=1, id=f"e{role[:2]}{i:03d}", t=datetime(2026, 9, 1 + i // 20, 9, i % 20, tzinfo=timezone.utc), origin="real", actor="human", person="p1", role=role,
                                 source="browser", type="click", target=None, task_id=None, meta={})


def test_current_events_are_all_the_profile_roles_events_whatever_the_order(monkeypatch):
    from understudy_engine.routines.sources import PersonData

    evs = [_ev(BP, i) for i in range(5)] + [_ev(PR, i) for i in range(5, 12)] + [_ev(BP, i) for i in range(12, 15)]       # benefits, then programmer, then benefits again (live capture)
    pd = PersonData("p1", "real", evs[12:], BP, None, "p1", evs[:12])                                                       # what PersonSource hands over: the newest unbroken run, the rest earlier
    prof = {"person": "p1", "role": PR, "history": [{"role": BP, "since": "x", "until": "y"}]}
    monkeypatch.setattr(rh, "_mem", lambda: SimpleNamespace(load_state=lambda: {"profile": prof}))
    cur = rh._as_current(pd)
    assert cur.role == PR and len(cur.events) == 7 and {e.role for e in cur.events} == {PR}
    assert len(cur.earlier_events) == 8 and {e.role for e in cur.earlier_events} == {BP}
    assert [e.t for e in cur.events] == sorted(e.t for e in cur.events)
    prof["role"] = BP
    back = rh._as_current(pd)
    assert back.role == BP and len(back.events) == 8 and len(back.earlier_events) == 7           # ALL benefits events, not only the newest run
    prof["role"] = DA                                                                           # a role with no work yet: clean (as before)
    empty = rh._as_current(pd)
    assert empty.role == DA and empty.events == [] and len(empty.earlier_events) == 15
    prof["person"] = "someone-else"
    assert rh._as_current(pd) is pd
    monkeypatch.setattr(rh, "_mem", lambda: SimpleNamespace(load_state=lambda: {}))
    assert rh._as_current(pd) is pd                                                             # no profile: untouched
    assert rh._as_current(None) is None


def test_a_generated_learners_own_truth_does_not_describe_another_roles_days(monkeypatch):
    from understudy_engine.routines.sources import PersonData

    evs = [_ev(BP, i) for i in range(5)] + [_ev(PR, i) for i in range(5, 9)]
    pd = PersonData("p1", "synthetic", evs, BP, {"role": BP, "start_date": "2026-09-01", "n_days": 3}, "learners")
    prof = {"person": "p1", "role": PR, "history": []}
    monkeypatch.setattr(rh, "_mem", lambda: SimpleNamespace(load_state=lambda: {"profile": prof}))
    assert rh._as_current(pd).truth is None and rh._as_current(pd).role == PR
    prof["role"] = BP
    assert rh._as_current(pd).truth is pd.truth


def test_the_benefits_learner_trajectory_is_never_read_as_another_roles_skill_state(monkeypatch):
    import understudy_engine.routines.learners as L

    monkeypatch.setattr(L, "learner_people", lambda root=None: [PERSON])
    monkeypatch.setattr(L, "tracker_at", lambda person, case: SimpleNamespace(person=person, case=case))
    assert rh._learner(PERSON, 5, PR) is None and rh._learner(PERSON, 5, DA) is None
    assert rh._learner(PERSON, 5, BP).case == 5 and rh._learner(PERSON, 5).case == 5            # benefits, or no role given: as before


def test_the_demo_routine_source_is_only_used_under_the_role_it_belongs_to(monkeypatch):
    other = SimpleNamespace(role=BP, person="p_src")
    mem = SimpleNamespace(load_state=lambda: {"demo": {"person": PERSON, "routine_source": "p_src", "routine_ids": ["calc-entry-3x"]}})
    monkeypatch.setattr(rh, "_src", lambda: SimpleNamespace(load=lambda p: other))
    seen: list[str] = []
    monkeypatch.setattr(rh, "_detected", lambda pd, m: (seen.append(pd.person) or [{"id": "calc-entry-3x", "person": pd.person}]) if pd is other else [{"id": "own", "person": pd.person}])
    own = SimpleNamespace(person=PERSON, role=PR)
    assert [r["id"] for r in rh._detections_for(own, mem)] == ["own"]                           # under another role the worker's own events are read
    own_bp = SimpleNamespace(person=PERSON, role=BP)
    assert [r["id"] for r in rh._detections_for(own_bp, mem)] == ["calc-entry-3x"] and seen == ["p_src"]


def test_person_source_merges_history_without_changing_the_persons_origin(tmp_path):
    dd = tmp_path / "demo-data"
    EventStore(dd).append_many([{"schema": 1, "id": "liveevt-0001", "t": "2026-11-08T01:00:00.000Z", "origin": "real", "actor": "human", "person": PERSON, "role": BP, "source": "browser", "type": "click"}])
    E.seed(dd, DA, NOW, lambda m: None)
    src = PersonSource(dd)
    assert src.persons()[PERSON] == "real"                                                      # the live capture decides the origin
    pd = src.load(PERSON)
    assert pd.origin == "real" and {e.role for e in [*pd.events, *pd.earlier_events]} == {BP, DA} and len(pd.earlier_events) > 20000
    assert src._signature(PERSON)                                                               # the history files are part of the data version (caches follow them)
