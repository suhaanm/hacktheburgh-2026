"""Twelve weeks of the worker's own ledger under another role (programmer, data analyst) for the same worker id: what it writes, that it is idempotent and only ever a top-up, that it
is realistic (not a straight line), and that the worker screens for the role are populated when the profile is switched: Growth, the pointers on Home, the briefing's practice
card, the Cue labels. History stays per role: the benefits rows and the other role's rows never appear under this role."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from understudy_engine import demo
from understudy_engine.api.app import create_app
from understudy_engine.cue import ledger as L
from understudy_engine.cue import vocab as V
from understudy_engine.packs import load_pack
from understudy_engine.seedroles import ledger as LG

NOW = datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)
BP = "benefits-processor"
ROLES = ("programmer", "data-analyst")
OTHER = {"programmer": "data-analyst", "data-analyst": "programmer"}
PERSON = "p_learn01"
HEADERS = {"X-Understudy-Actor": "worker", "Origin": "http://localhost:5173"}


@pytest.fixture()
def dd(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "demo-data"
    d.mkdir()
    (d / demo.DATA_MARKER).write_text("test\n")
    for k, v in (("UNDERSTUDY_DATA_DIR", str(d)), ("UNDERSTUDY_HOME", str(tmp_path / "home")), ("UNDERSTUDY_MOCK", "0"), ("UNDERSTUDY_X", "1"), ("AGENT_PORT", "1"),
                 ("UNDERSTUDY_NO_WARM", "1")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("UNDERSTUDY_X_INSIGHTS_HELDOUT", raising=False)
    return d


def lines(dd: Path) -> list[str]:
    p = dd / "assist" / "ledger.jsonl"
    return p.read_text().splitlines() if p.exists() else []


def rows_of(dd: Path) -> list[dict]:
    return [json.loads(x) for x in lines(dd)]


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


# ------------------------------------------------------------------------------------------------ what it writes
@pytest.mark.parametrize("role", ROLES)
def test_it_writes_twelve_weeks_of_valid_role_rows_beside_the_base_rows(dd, role):
    demo.seed_growth(dd, NOW, lambda m: None)                                  # the demo's own benefits history, as on the live data directory
    base = lines(dd)
    out: list[str] = []
    res = LG.seed(dd, role, NOW, out.append)
    assert res["seeded"] and res["assist"] >= 150 and res["offloaded"] >= 5
    assert not res["unlabelled"]                                               # every skill used has a label in the pack
    now = lines(dd)
    assert now[: len(base)] == base                                           # the benefits rows are byte for byte what they were: appended beside, never over
    rows = [json.loads(x) for x in now[len(base):]]
    assert len(rows) == res["rows"] and out[0].startswith(f"ledger ({role}): ")
    ids = [json.loads(x)["id"] for x in now]
    assert len(ids) == len(set(ids))                                           # no id collides with the base rows or within the role
    for r in rows:
        L.validate_row(r)                                                      # the schema accepts every row exactly as written
        assert r["person"] == PERSON and r["role"] == role and r["origin"] == "synthetic" and r["origin_detail"] == "synthetic_learner"
    assist = [r for r in rows if r["stream"] == "assist"]
    assert 150 <= len(assist) <= 260
    assert {r["stream"] for r in rows} >= {"assist", "automation"}
    first, last = min(r["t_hour"] for r in rows), max(r["t_hour"] for r in rows)
    t0 = datetime.strptime(first, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
    t1 = datetime.strptime(last, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
    assert (t1 - t0).days >= 75 and NOW - timedelta(days=3) <= t1 <= NOW - timedelta(hours=LG.LAG_HOURS - 1)       # twelve weeks, ending a few hours to a couple of days before now


@pytest.mark.parametrize("role", ROLES)
def test_skills_steps_labels_and_routines_come_from_the_role_pack(dd, role):
    LG.seed(dd, role, NOW, lambda m: None)
    pack = load_pack(role)
    skills = {str(s["id"]) for s in pack.file("curriculum")["skills"]}
    steps = {str(c["id"]) for c in pack.nested("expert_policy", "steps")["checks"]}
    routines = {str(t["id"]) for t in pack.file("routines")["templates"]}
    rows = rows_of(dd)
    assist = [r for r in rows if r["stream"] == "assist"]
    used = {r["skill"] for r in assist}
    assert 6 <= len(used) <= 8 and used <= skills                               # four to eight skills practised, every one a skill the pack's curriculum names
    known = {r["step"] for r in assist if r["step"] in steps}
    assert len(known) >= len(used) - 1                                         # the step is the pack's own check for the skill (one skill has no check of its own)
    for sk in used:
        info = V.skill_info(role, sk)
        assert info["label"] != sk and info["name"]                            # the Cue and Growth labels resolve from the pack
    short = V.SHORT_LABELS[role]
    assert sum(1 for s in known if s in short) >= len(known) - 1                # and the chip labels for the steps
    off = [r for r in rows if r["stream"] != "assist"]
    assert off and {r["routine"] for r in off} <= routines                      # routines that emerge are routines the pack's own templates name
    assert all(r["minutes"] and r["minutes"] > 0 and r["offload_outcome"] in ("done", "queued", "failed", "yielded") for r in off)
    assert min(r["t_hour"] for r in off) > min(r["t_hour"] for r in assist)    # and they emerge later than the first assisted work


@pytest.mark.parametrize("role", ROLES)
def test_the_history_is_not_a_straight_line(dd, role):
    LG.seed(dd, role, NOW, lambda m: None)
    assist = [r for r in rows_of(dd) if r["stream"] == "assist"]
    ts = [datetime.strptime(r["t_hour"], "%Y-%m-%dT%H").replace(tzinfo=timezone.utc) for r in assist]
    gaps = [(b - a).days for a, b in zip(ts, ts[1:], strict=False)]
    assert max(gaps) >= 10                                                     # a break of twelve days
    t_end = max(ts)
    weekly = [sum(1 for t in ts if t_end - timedelta(days=7 * (i + 1)) < t <= t_end - timedelta(days=7 * i)) for i in range(12)]
    assert min(weekly) <= 1 or sorted(weekly)[1] <= 3                          # an unwell week with next to nothing
    assert max(weekly) >= 1.4 * sorted(weekly)[6]                             # a busy week against an ordinary one
    outcomes = {r["outcome"] for r in assist}
    assert outcomes == {"clean", "assisted", "error", "abandoned"}
    assert any(r["taught"] for r in assist) and any(r["dismissed"] for r in assist) and any(r["trigger"] == "asked" for r in assist)
    hours = {t.hour for t in ts}
    if role == "programmer":
        assert any(h >= 20 for h in hours) and any(t.weekday() >= 5 for t in ts)   # some evenings and the odd weekend
    else:
        assert all(9 <= h <= 19 for h in hours) and all(t.weekday() < 5 for t in ts)   # office hours, weekdays
    # independence rises over the twelve weeks, with dips: the first twenty against the last twenty
    first20 = sum(1 for r in assist[:20] if r["outcome"] == "clean" and not r["accepted"]) / 20
    last20 = sum(1 for r in assist[-20:] if r["outcome"] == "clean" and not r["accepted"]) / 20
    assert last20 >= first20 + 0.25
    blocks = [sum(1 for r in assist[i:i + 20] if r["outcome"] == "clean" and not r["accepted"]) / 20 for i in range(0, len(assist) - 19, 20)]
    assert any(b < a for a, b in zip(blocks, blocks[1:], strict=False))        # at least one block is worse than the one before it
    # one skill stays hard: the lowest share finished without help in the second half is well under the best
    by: dict[str, list[bool]] = {}
    for r in assist[len(assist) // 2:]:
        by.setdefault(r["skill"], []).append(r["outcome"] == "clean" and not r["accepted"])
    shares = {s: sum(v) / len(v) for s, v in by.items() if len(v) >= 8}
    assert max(shares.values()) - min(shares.values()) >= 0.3


@pytest.mark.parametrize("role", ROLES)
def test_it_is_deterministic_and_moves_with_the_clock(role):
    a, _ = LG.build_rows(role, NOW)
    b, _ = LG.build_rows(role, NOW + timedelta(minutes=20))                   # inside the same hour: the same rows
    assert a == b
    c, _ = LG.build_rows(role, NOW + timedelta(days=2))
    assert [r["t_hour"] for r in c] != [r["t_hour"] for r in a] and max(r["t_hour"] for r in c) > max(r["t_hour"] for r in a)


# ------------------------------------------------------------------------------------------------ top-up behaviour
@pytest.mark.parametrize("role", ROLES)
def test_a_second_run_writes_nothing_and_says_so(dd, role):
    out: list[str] = []
    LG.seed(dd, role, NOW, out.append)
    p = dd / "assist" / "ledger.jsonl"
    before = (p.read_bytes(), p.stat().st_mtime_ns, (dd / LG.MARKER.format(role=role)).read_text())
    again = LG.seed(dd, role, NOW + timedelta(days=1), out.append)
    assert again == {"seeded": False, "reason": "already_seeded"} and "already seeded; nothing changed" in out[-1]
    assert (p.read_bytes(), p.stat().st_mtime_ns, (dd / LG.MARKER.format(role=role)).read_text()) == before


def test_each_role_is_seeded_on_its_own_and_both_sit_in_one_file(dd):
    LG.seed(dd, "programmer", NOW, lambda m: None)
    n1 = len(lines(dd))
    LG.seed(dd, "data-analyst", NOW, lambda m: None)
    rows = rows_of(dd)
    assert len(rows) > n1 and {r["role"] for r in rows} == {"programmer", "data-analyst"}
    assert len({r["id"] for r in rows}) == len(rows)
    assert sum(1 for x in dd.iterdir() if x.name.startswith(".seed-ledger-")) == 2


def test_it_refuses_a_data_dir_that_is_not_a_demo_one_and_an_unknown_role(tmp_path, dd):
    real = tmp_path / "real-data"
    real.mkdir()
    out: list[str] = []
    assert LG.seed(real, "programmer", NOW, out.append) == {"seeded": False, "reason": "not_demo_dir"}
    assert not (real / "assist").exists() and not list(real.iterdir()) and "not a demo data dir" in out[0]
    with pytest.raises(LG.SeedError):
        LG.seed(dd, "benefits-processor", NOW, lambda m: None)


def test_the_package_runs_both_writers_for_one_role_or_all(dd):
    from understudy_engine import seedroles

    assert seedroles.ROLES == ROLES
    with pytest.raises(ValueError):
        seedroles.seed_role(dd, "astronaut", NOW, lambda m: None)


# ------------------------------------------------------------------------------------------------ the screens, through the real app
@pytest.fixture()
def client(dd):
    app = create_app(root=dd, warm=False)
    c = TestClient(app, headers=HEADERS)
    return c


def switch_to(client, role: str) -> None:
    """The worker, onboarded as a benefits processor (the base demo), changes their profile to the role: Account menu, Change profile."""
    assert client.post("/onboarding", json={"role": BP, "answers": {"capture": True}, "person": PERSON}).status_code == 200
    r = client.post("/profile", json={"role": role})
    assert r.status_code == 200 and r.json()["role"] == role and r.json()["person"] == PERSON


@pytest.mark.parametrize("role", ROLES)
def test_growth_is_populated_for_the_role_and_history_stays_per_role(client, dd, role):
    demo.seed_growth(dd, NOW, lambda m: None)
    for r in ROLES:
        LG.seed(dd, r, NOW, lambda m: None)
    switch_to(client, role)
    g = client.get("/growth", params={"person": PERSON}).json()["data"]
    assert g["role"] == role and g["role_scope"]["current"] == role and g["role_scope"]["viewing_earlier"] is False
    assert {x["role"] for x in g["role_scope"]["roles"]} == {BP, *ROLES}
    assert g["readiness"]["ready"] and g["readiness"]["occurrences"] >= 150
    ind = g["components"]["independence"]
    assert ind["n"] == 20 and 0.0 < ind["share"] <= 1.0 and ind["wilson"][0] < ind["share"] < ind["wilson"][1]
    assert g["score"]["composite_experimental"] is not None and g["trend"]["direction"] in ("less_help", "steady", "more_help") and g["curve"]
    skills = {s["skill"] for s in g["by_skill"]}
    pack_skills = {str(s["id"]) for s in load_pack(role).file("curriculum")["skills"]}
    assert 6 <= len(skills) <= 8 and skills <= pack_skills
    assert all(s["label"] != s["skill"] and s["n"] >= 3 and s["mastery"] is not None for s in g["by_skill"])
    assert g["offloaded"]["automation"] >= 1 and g["offloaded"]["minutes"]["automation"] > 0
    assert g["counts"]["assist"] == g["readiness"]["occurrences"]               # only this role's rows are read
    assert not skills & {"check-the-cliff", "enter-household-once", *{str(s["id"]) for s in load_pack(OTHER[role]).file("curriculum")["skills"]} - pack_skills}
    # the benefits history is intact and apart: ?role= reads it, and the other role's too
    old = client.get("/growth", params={"person": PERSON, "role": BP}).json()["data"]
    assert old["role"] == BP and old["role_scope"]["viewing_earlier"] is True and old["readiness"]["occurrences"] == 90
    assert {s["skill"] for s in old["by_skill"]} <= {"check-the-cliff", "reconcile-before-noting", "enter-household-once"}
    other = client.get("/growth", params={"person": PERSON, "role": OTHER[role]}).json()["data"]
    assert other["role"] == OTHER[role] and not ({s["skill"] for s in other["by_skill"]} & skills)
    # and back: the role's history comes back when the worker returns to it
    assert client.post("/profile", json={"role": BP}).status_code == 200
    assert client.post("/profile", json={"role": role}).status_code == 200
    again = client.get("/growth", params={"person": PERSON}).json()["data"]
    assert again["role"] == role and again["readiness"]["occurrences"] == g["readiness"]["occurrences"]


@pytest.mark.parametrize("role", ROLES)
def test_home_pointers_are_the_roles_own(client, dd, role):
    for r in ROLES:
        LG.seed(dd, r, NOW, lambda m: None)
    demo.seed_growth(dd, NOW, lambda m: None)
    switch_to(client, role)
    j = client.get("/insights/worker", params={"person": PERSON}).json()
    d = j["data"]
    assert j["meta"]["source"] == "local" and d["role"] == role and d["status"] == "ok" and not d["nothing_stands_out"]
    ptr = [p for p in d["pointers"] if p["kind"] != "automation_opportunity"]
    assert len(ptr) >= 2 and len(d["pointers"]) <= d["cap"]
    pack_skills = {str(s["id"]) for s in load_pack(role).file("curriculum")["skills"]}
    text = " ".join(p["headline"] for p in ptr).lower()
    assert not re.search(r"cliff|household|calculator|entitlement", text)       # no benefits wording under another role
    blob = json.dumps(d)
    assert "p_f_" not in blob and not re.search(r"\b\d+ (people|colleagues|workers)\b", blob)        # nothing about anyone else
    assert d["monday_note"] and pack_skills


@pytest.mark.parametrize("role", ROLES)
def test_the_briefing_offers_a_practice_card_from_the_roles_own_ledger(client, dd, role):
    for r in ROLES:
        LG.seed(dd, r, NOW, lambda m: None)
    switch_to(client, role)
    j = client.get("/briefing", params={"person": PERSON}).json()
    assert client.get("/briefing", params={"person": PERSON}).status_code == 200
    skills = j["data"]["sources"]["skills"]
    assert skills["available"] and skills["n"] >= 1
    cards = [c for c in j["data"]["cards"] if c["kind"] == "practice"]
    assert cards
    labels = {str(s["label"]) for s in load_pack(role).file("curriculum")["skills"]}
    assert any(c["title"].removeprefix("Practice: ") in labels for c in cards)  # a skill of THIS role's pack, from the worker's own ledger under it
    other_labels = {str(s["label"]) for s in load_pack(OTHER[role]).file("curriculum")["skills"]} | {"Probe the cliff edge on every calculator"}
    assert not any(c["title"].removeprefix("Practice: ") in other_labels for c in j["data"]["cards"])
    for c in cards:
        assert re.search(r"level \d of 4 and your mastery is about \d+%", c["why"])


def test_the_ledger_skill_rows_read_only_the_roles_own_rows(dd):
    from understudy_engine.proactive.sources import skill_rows_from_ledger

    demo.seed_growth(dd, NOW, lambda m: None)
    for r in ROLES:
        LG.seed(dd, r, NOW, lambda m: None)
    from understudy_engine.memory import load_pack as mem_pack

    for role in ROLES:
        pack = mem_pack(role)
        got = skill_rows_from_ledger(PERSON, role, pack, NOW.timestamp())
        assert [g["id"] for g in got] == [str(s["id"]) for s in pack.skills]       # one row per curriculum skill, in the pack's order
        practised = [g for g in got if g["attempts"]]
        assert 6 <= len(practised) <= 8 and all(1 <= g["level"] <= 4 and 0.0 <= g["mastery"] <= 1.0 and g["days_idle"] is not None for g in practised)
        assert all(g["attempts"] == 0 and g["days_idle"] is None for g in got if g not in practised)       # skills with no work under the role are unknown, not a known gap
    assert skill_rows_from_ledger(PERSON, BP, mem_pack(BP), NOW.timestamp()) != []        # the base role has its own rows
    assert skill_rows_from_ledger("p_nobody", "programmer", mem_pack("programmer"), NOW.timestamp()) == []


@pytest.mark.parametrize("role", ROLES)
def test_nothing_a_person_reads_says_how_the_data_was_made(client, dd, role):
    for r in ROLES:
        LG.seed(dd, r, NOW, lambda m: None)
    demo.seed_growth(dd, NOW, lambda m: None)
    switch_to(client, role)
    payloads = [client.get(u, params={"person": PERSON}).json() for u in ("/growth", "/insights/worker", "/briefing")]
    payloads.append(client.get("/cue/ledger", params={"person": PERSON, "limit": 40}).json())
    # The calendar card is not this seed's: it comes from the calendar layer's borrowed week (proactive/candidates.py), and its own wording is the wording track's to settle.
    payloads[2]["data"]["cards"] = [c for c in payloads[2]["data"]["cards"] if c["kind"] != "focus_block"]
    bad = re.compile(r"synthetic|simulated|made[- ]?up|\bdemo\b|sample data|example data|\bfake\b|pretend", re.I)
    offenders = [s for p in payloads for s in strings(p) if bad.search(s)]
    assert offenders == []
