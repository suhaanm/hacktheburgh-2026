"""Changing an existing worker's name and role (the owner: "I don't want to be stuck as a benefits processor").

What is pinned here:
* the same request twice changes nothing (no new revision, no duplicate lines), also on another day;
* a role change switches the pack (skills, procedure, rules start clean for it) and keeps what is the worker's own: person id, name, quiet hours, the
  capture choice and usual hours; the earlier role stays in ``history`` and its routines are not listed under the new one;
* a role id outside the packs is a plain 422 that lists the valid ones, and nothing is written;
* the name is validated, lives as one line the worker can read and delete, and never reaches the audit log;
* the routes are the worker's own writes (the same guard as every memory write).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.core import Event
from understudy_engine.memory import (
    MemoryStore, NotOnboarded, OnboardingError, UnknownRole, change_profile, clean_name, list_pack_ids, load_pack, onboard, profile_name, profile_view,
)
from understudy_engine.memory.paths import data_dir as real_data_dir
from understudy_engine.routines.sources import split_by_current_role

D1 = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)
D2 = D1 + timedelta(days=3)
BP, DA, PR = "benefits-processor", "data-analyst", "programmer"


def _store(tmp_path, name="h"):
    return MemoryStore(tmp_path / name)


def _snap(s: MemoryStore) -> tuple[str, dict]:
    return s.read_text(), s.load_state()


# ----------------------------------------------------------------------------- idempotence
def test_the_same_onboarding_twice_changes_nothing_even_on_another_day(tmp_path):
    s = _store(tmp_path)
    a = onboard(s, BP, {"capture": True, "tone": "detailed"}, now=D1)
    before = _snap(s)
    b = onboard(s, BP, {"capture": True, "tone": "detailed"}, now=D2)
    assert _snap(s) == before and a["revision"] == b["revision"] == 1
    assert b["role_changed"] is False and b["previous_role"] is None


def test_a_rerun_with_rules_quiet_hours_and_a_name_is_still_a_no_op_from_the_second_run(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {}, now=D1)
    s.add_line("Preferences", "Quiet hours: 23:00 to 05:00, mon.", actor="worker", line_id="l_quiet_hours")
    s.add_line("Preferences", "Summary length: short.", actor="worker", note="rule: summary_length")
    first = onboard(s, BP, {"tone": "detailed"}, now=D1, name="Amara Okafor")
    text = s.read_text()
    again = onboard(s, BP, {"tone": "detailed"}, now=D2, name="Amara Okafor")
    assert s.read_text() == text and again["revision"] == first["revision"]
    prefs = [ln.text for ln in s.read().section("Preferences").lines()]
    assert len(prefs) == len(set(prefs))                                                      # no duplicate lines
    assert {"Quiet hours: 23:00 to 05:00, mon.", "Summary length: short.", "Name: Amara Okafor"} <= set(prefs)


# ----------------------------------------------------------------------------- the role change
def test_a_role_change_switches_the_pack_and_keeps_what_is_the_workers_own(tmp_path):
    s = _store(tmp_path)
    first = onboard(s, BP, {"capture": True, "tone": "detailed", "hours": {"start": "08:00", "end": "16:00", "days": ["mon", "tue", "wed"]}}, now=D1, name="Amara Okafor")
    s.add_line("Preferences", "Quiet hours: 23:00 to 05:00, mon.", actor="worker", line_id="l_quiet_hours")
    bp_skill = s.read().section("Skill state").lines()[0]
    s.update_line(bp_skill.id, actor="worker", text=bp_skill.text.split(":")[0] + ": L3, streak 2, last seen 2026-11-07")
    s.add_line("Routines", "calc-entry-3x | rung A1", actor="worker")

    out = change_profile(s, role=PR, now=D2)
    d = s.read()
    assert out["role"] == d.role == PR and out["role_changed"] is True and out["previous_role"] == BP and out["created"] is False
    assert out["person"] == first["person"]                                                   # the same person
    assert [ln.text.split(":")[0] for ln in d.section("Skill state").lines()] == [str(k["id"]) for k in load_pack(PR).skills]
    assert all("L1" in ln.text for ln in d.section("Skill state").lines())                    # the new pack starts clean
    assert d.section("Routines").lines() == []                                                # the old role's routine lines are gone
    assert "Checklist" not in "".join(ln.text for ln in d.section("Procedure").lines()) or load_pack(PR).expert_checks
    assert profile_name(d) == "Amara Okafor"                                                  # theirs, not the role's
    assert "Quiet hours: 23:00 to 05:00, mon." in [ln.text for ln in d.section("Preferences").lines()]
    assert out["capture"] is True                                                             # the capture choice is carried over
    assert "Usual hours: 08:00 to 16:00, mon to wed." in [ln.text for ln in d.section("Preferences").lines()]
    st = s.load_state()["profile"]
    assert st["role"] == PR and st["person"] == first["person"]
    assert [(h["role"], h["until"]) for h in st["history"]] == [(BP, st["role_since"])] and st["history"][0]["since"] == first["since"]
    view = profile_view(s)
    assert view["role"] == PR and view["name"] == "Amara Okafor" and view["history"][0]["role"] == BP
    assert {r["id"] for r in view["roles"]} == set(list_pack_ids()) and {BP, DA, PR} <= set(list_pack_ids())


def test_the_same_role_change_twice_is_a_no_op_and_a_third_role_adds_one_history_entry(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {"capture": True}, now=D1)
    first = change_profile(s, role=DA, now=D2)
    after = _snap(s)
    again = change_profile(s, role=DA, now=D2 + timedelta(days=1))
    assert _snap(s) == after and again["revision"] == first["revision"] and again["role_changed"] is False and again["previous_role"] is None
    third = change_profile(s, role=PR, now=D2 + timedelta(days=2))
    assert third["previous_role"] == DA
    assert [h["role"] for h in s.load_state()["profile"]["history"]] == [BP, DA]
    back = change_profile(s, role=BP, now=D2 + timedelta(days=3))
    assert [h["role"] for h in s.load_state()["profile"]["history"]] == [BP, DA, PR] and back["role"] == BP


def test_onboarding_again_without_answers_still_resets_capture_but_a_profile_change_does_not(tmp_path):
    """POST /onboarding is "set up again": an omitted answer is the pack's default. A profile change is for the worker who already exists."""
    a, b = _store(tmp_path, "a"), _store(tmp_path, "b")
    for st in (a, b):
        onboard(st, BP, {"capture": True}, now=D1)
    onboard(a, PR, {}, now=D2)
    change_profile(b, role=PR, now=D2)
    assert load_state_capture(a) is False and load_state_capture(b) is True


def load_state_capture(s: MemoryStore) -> bool:
    return bool(s.load_state()["profile"]["capture"])


def test_tone_and_pace_are_carried_only_when_the_new_pack_offers_them(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {"tone": "detailed", "pace": "quick"}, now=D1)
    out = change_profile(s, role=DA, now=D2)
    ans = s.load_state()["profile"]["answers"]
    pack = load_pack(DA)
    offered_tone = {o["value"] for o in pack.question("tone")["options"]}
    offered_pace = {o["value"] for o in pack.question("pace")["options"]}
    assert (ans["tone"] == "detailed") == ("detailed" in offered_tone) and (ans["pace"] == "quick") == ("quick" in offered_pace)
    assert out["role"] == DA


# ----------------------------------------------------------------------------- the name
@pytest.mark.parametrize("good", ["Amara Okafor", "Siobhán O'Brien-Smith", "李 小龍", "A. B. Jones", "  Priya   Raghunathan  ", "D’Arcy"])
def test_good_names_are_accepted_and_tidied(good):
    out = clean_name(good)
    assert out == " ".join(good.split()) and 1 <= len(out) <= 60


@pytest.mark.parametrize("bad", ["R2D2", "<b>Amara</b>", "x" * 61, "-Bob", ": Bob", "Amara\nOkafor: admin", "Bob; DROP TABLE", "😀 Bob", 7])
def test_bad_names_are_refused(bad):
    if isinstance(bad, str) and "\n" in bad:
        assert " " in clean_name("Amara Okafor")                      # a newline is just whitespace, flattened, then the colon is refused
    with pytest.raises(OnboardingError):
        clean_name(bad)


def test_empty_or_none_clears_the_name():
    assert clean_name("") == "" and clean_name(None) == "" and clean_name("   ") == ""


def test_a_name_change_writes_only_the_name_line_and_never_undoes_the_workers_own_edits(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {}, now=D1)
    summ = next(ln for ln in s.read().section("Preferences").lines() if ln.text.startswith("Summaries:"))
    s.update_line(summ.id, actor="worker", text="Summaries: as short as you can.")
    rev = s.revision()
    out = change_profile(s, name="Amara Okafor", now=D2)
    assert out["name"] == "Amara Okafor" and out["role"] == BP and out["role_changed"] is False and s.revision() == rev + 1
    assert any(ln.text == "Summaries: as short as you can." for ln in s.read().section("Preferences").lines())
    change_profile(s, name="Amara Okafor", now=D2)                         # the same name again
    assert s.revision() == rev + 1
    change_profile(s, name="Amara Okafor-Reyes", now=D2)
    assert profile_name(s.read()) == "Amara Okafor-Reyes" and len([ln for ln in s.read().section("Preferences").lines() if ln.text.startswith("Name: ")]) == 1
    cleared = change_profile(s, name="", now=D2)
    assert profile_name(s.read()) is None and "name" not in cleared
    assert change_profile(s, name=None, now=D2)["role"] == BP              # clearing what is not there changes nothing


def test_deleting_the_name_line_removes_the_name(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {}, now=D1, name="Amara Okafor")
    assert profile_name(s.read()) == "Amara Okafor"
    s.forget("l_name", actor="worker")
    assert profile_name(s.read()) is None and "name" not in profile_view(s)


def test_a_name_on_first_onboarding_and_after_a_role_change(tmp_path):
    s = _store(tmp_path)
    assert onboard(s, DA, {}, now=D1, name="Kwame Mensah")["name"] == "Kwame Mensah"
    out = change_profile(s, role=PR, now=D2)
    assert out["name"] == "Kwame Mensah"
    out = change_profile(s, role=BP, name="Ingrid Lindqvist", now=D2 + timedelta(days=1))
    assert out["name"] == "Ingrid Lindqvist" and out["role"] == BP


# ----------------------------------------------------------------------------- validation and the first call
def test_an_unknown_role_is_refused_and_lists_the_valid_ones_without_writing(tmp_path):
    s = _store(tmp_path)
    with pytest.raises(UnknownRole) as e:
        change_profile(s, role="astronaut", now=D1)
    assert e.value.valid == list_pack_ids() and "astronaut" in str(e.value) and ", ".join(list_pack_ids()) in str(e.value)
    assert not s.path.exists()
    onboard(s, BP, {}, now=D1)
    before = _snap(s)
    for bad in ("astronaut", "../../etc", "benefits-processor ", "BENEFITS-PROCESSOR"):
        with pytest.raises(UnknownRole):
            change_profile(s, role=bad, now=D2)
    assert _snap(s) == before


def test_change_profile_needs_something_to_change_and_a_role_the_first_time(tmp_path):
    s = _store(tmp_path)
    with pytest.raises(OnboardingError):
        change_profile(s)
    with pytest.raises(NotOnboarded):
        change_profile(s, name="Amara Okafor")
    out = change_profile(s, role=PR, name="Amara Okafor", now=D1)
    assert out["created"] is True and out["role"] == PR and out["name"] == "Amara Okafor" and out["person"].startswith("p_")


def test_history_is_capped_and_holds_no_content(tmp_path):
    s = _store(tmp_path)
    onboard(s, BP, {}, now=D1)
    roles = [DA, PR] * 15
    for i, r in enumerate(roles):
        change_profile(s, role=r, now=D1 + timedelta(days=i + 1))
    hist = s.load_state()["profile"]["history"]
    assert len(hist) == 20 and all(set(h) == {"role", "since", "until"} for h in hist)


# ----------------------------------------------------------------------------- routes
@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    from understudy_engine import routes_handoff as rh

    rh._cache.clear()
    app = FastAPI()
    app.include_router(rh.router)
    c = TestClient(app)
    c.data = data
    return c


def _audit_text(client) -> str:
    p = client.data / "audit.jsonl"
    return p.read_text() if p.exists() else ""


def test_profile_routes_end_to_end(client):
    r = client.get("/profile")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_onboarded"
    assert client.post("/profile", json={"name": "Amara Okafor"}).status_code == 409                    # a role first
    assert client.post("/profile", json={}).status_code == 422
    first = client.post("/profile", json={"role": BP, "name": "Amara Okafor"})
    assert first.status_code == 200 and first.json()["created"] is True and first.json()["name"] == "Amara Okafor"
    ident = client.get("/identity").json()
    assert ident["role"] == BP and ident["name"] == "Amara Okafor" and ident["person"] == first.json()["person"]
    changed = client.post("/profile", json={"role": PR}).json()
    assert changed["role"] == PR and changed["role_changed"] is True and changed["previous_role"] == BP and changed["name"] == "Amara Okafor"
    prof = client.get("/profile").json()
    assert prof["role"] == PR and prof["name"] == "Amara Okafor" and [h["role"] for h in prof["history"]] == [BP]
    assert prof["person"] == first.json()["person"] and {r["id"] for r in prof["roles"]} == set(list_pack_ids())
    assert client.get("/identity").json()["role"] == PR and client.get("/memory").json()["role"] == PR
    again = client.patch("/profile", json={"role": PR}).json()                                          # PATCH is the same call; the same request is a no-op
    assert again["revision"] == changed["revision"] and again["role_changed"] is False
    assert client.patch("/profile", json={"name": None}).json().get("name") is None
    assert "name" not in client.get("/identity").json()


def test_unknown_role_over_http_is_a_plain_422_with_the_valid_roles(client):
    client.post("/profile", json={"role": BP})
    rev = client.get("/memory").json()["revision"]
    for call in (lambda: client.post("/profile", json={"role": "astronaut"}), lambda: client.post("/onboarding", json={"role": "astronaut", "answers": {}})):
        r = call()
        body = r.json()
        assert r.status_code == 422 and body["error"]["code"] == "unknown_role" and body["roles"] == list_pack_ids()
        assert "astronaut" in body["error"]["message"] and "Traceback" not in r.text
    assert client.get("/memory").json()["revision"] == rev and client.get("/identity").json()["role"] == BP


def test_bad_names_over_http_are_422_and_change_nothing(client):
    client.post("/profile", json={"role": BP})
    rev = client.get("/memory").json()["revision"]
    for bad in ("R2D2", "x" * 61, "<b>x</b>", 7):
        r = client.post("/profile", json={"name": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "bad_onboarding", bad
    assert client.get("/memory").json()["revision"] == rev


def test_onboarding_route_is_idempotent_and_takes_a_name(client):
    body = {"role": BP, "answers": {"capture": True}, "name": "Amara Okafor"}
    a = client.post("/onboarding", json=body).json()
    b = client.post("/onboarding", json=body).json()
    assert a["revision"] == b["revision"] and a["memory_markdown"] == b["memory_markdown"] and b["name"] == "Amara Okafor"
    c = client.post("/onboarding", json={"role": PR, "answers": {}}).json()                            # another role through "set up again": the name stays
    assert c["name"] == "Amara Okafor" and c["role_changed"] is True and c["previous_role"] == BP


def test_profile_writes_are_the_workers_own(client):
    client.post("/profile", json={"role": BP})
    for headers in ({"X-Understudy-Actor": "agent"}, {"X-Understudy-Actor": "model"}, {"X-Understudy-Actor": "page"}):
        r = client.post("/profile", json={"role": PR}, headers=headers)
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert client.post("/profile", json={"role": PR}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.patch("/profile", json={"name": "Mallory"}, headers={"X-Understudy-Actor": "agent"}).status_code == 403
    assert client.get("/identity").json()["role"] == BP and "name" not in client.get("/identity").json()
    assert client.post("/profile", json={"role": PR}, headers={"X-Understudy-Actor": "worker"}).status_code == 200


def test_the_audit_names_the_roles_and_never_the_name(client):
    client.post("/profile", json={"role": BP, "name": "Amara Okafor"})
    client.post("/profile", json={"role": PR, "name": "Siobhan Gallagher"})
    client.post("/profile", json={"name": ""})
    log = _audit_text(client)
    lines = [json.loads(x) for x in log.splitlines() if x.strip()]
    changed = [x for x in lines if x["kind"] == "profile_changed"]
    assert changed and any("benefits-processor to programmer" in x["note"] for x in changed) and any("name cleared" in x["note"] for x in changed)
    assert "Amara" not in log and "Okafor" not in log and "Siobhan" not in log and "Gallagher" not in log
    assert all(x["actor"] == "system" and x["outcome"] == "ok" for x in changed)


# ----------------------------------------------------------------------------- the old role's events and routines stay apart
def _event(i: int, role: str) -> Event:
    t0 = datetime(2026, 11, 7, 9, 0, 0, tzinfo=timezone.utc)
    return Event.model_validate({"schema": 1, "id": f"ev{i:08d}", "t": (t0 + timedelta(seconds=5 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "origin": "real",
                                 "actor": "human", "person": "p_ann", "role": role, "source": "browser", "type": "click"})


def test_the_current_role_is_the_newest_runs_and_earlier_work_is_kept_apart():
    evs = [_event(i, BP) for i in range(6)] + [_event(i, PR) for i in range(6, 9)]
    role, now, earlier = split_by_current_role(evs)
    assert role == PR and [e.id for e in now] == [f"ev{i:08d}" for i in range(6, 9)] and len(earlier) == 6 and all(e.role == BP for e in earlier)
    only = [_event(i, BP) for i in range(4)]
    assert split_by_current_role(only) == (BP, only, [])
    back = [_event(0, BP), _event(1, PR), _event(2, BP)]                    # went back to an earlier role: only the unbroken run at the end is current
    assert [e.id for e in split_by_current_role(back)[1]] == ["ev00000002"]


SYNTH = real_data_dir() / "synthetic" / "nine-to-five" / "events.jsonl"


@pytest.mark.skipif(not SYNTH.exists(), reason="run `uv run understudy synth --all` first")
def test_routines_found_under_the_old_role_are_not_listed_under_the_new_one(client):
    from understudy_engine.store import EventStore

    rows = [dict(json.loads(line), person="p_real0001", origin="real") for line in SYNTH.read_text().splitlines()]
    EventStore(client.data).append_many(rows)
    client.post("/onboarding", json={"role": BP, "person": "p_real0001", "answers": {"capture": True}})
    before = client.get("/routines", params={"person": "p_real0001"}).json()["data"]
    assert before and all(r["role"] == BP for r in before)
    assert client.post("/profile", json={"role": PR}).status_code == 200
    assert client.get("/routines", params={"person": "p_real0001"}).json()["data"] == []        # nothing under the new role yet, and no consent carried
    assert client.post("/profile", json={"role": BP}).status_code == 200
    again = client.get("/routines", params={"person": "p_real0001"}).json()["data"]
    assert {r["id"] for r in again} == {r["id"] for r in before}                                # back in the role the work was done in: it is all there
