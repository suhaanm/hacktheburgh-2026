"""Hit list routes and service, in process: worker-only writes, hide and reset behaviour, the registry's decisions showing as chips,
capture consent, the firm endpoint, the pointer the insights layer reads. The engine's person source is replaced by planted episodes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_handoff as rh
from understudy_engine.hitlist import routes as R
from understudy_engine.hitlist import service as S
from understudy_engine.hitlist.routes import router
from understudy_engine.memory import MemoryStore
from understudy_engine.routines.detect import detect_routines
from understudy_engine.routines.store import RoutineStore

from .conftest import CALC, DAY, NOTE, NOW, P, many

ORIGIN = {"Origin": "http://localhost:5173", "X-Understudy-Actor": "worker", "Content-Type": "application/json"}


@pytest.fixture()
def world(monkeypatch, pack):
    eps = many(CALC, 12, prefix="c") + many(NOTE, 8, prefix="n", spread_days=4)
    pd = SimpleNamespace(person=P, origin="synthetic", role="benefits-processor", t_last=NOW)
    state = {"pd": pd, "eps": eps}
    monkeypatch.setattr(rh, "_resolve", lambda person: (person or P, state["pd"] if (person in (None, P)) else None))
    source = SimpleNamespace(person="p_src", origin="synthetic", role="benefits-processor", t_last=NOW, eps=many(CALC, 9, prefix="s") + many(NOTE, 9, prefix="t"))
    state["source"] = source
    monkeypatch.setattr(rh, "_src", lambda: SimpleNamespace(
        episodes=lambda _pd: (_pd.eps if hasattr(_pd, "eps") else state["eps"]), load=lambda p: source if p == "p_src" else None))
    monkeypatch.setattr(rh, "_sync_routines", lambda *a, **k: None)
    state["pack"] = pack
    return state


@pytest.fixture()
def client(world):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def audit_lines():
    p = Path(__import__("os").environ["UNDERSTUDY_DATA_DIR"]) / "audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# ------------------------------------------------------------------------------------------------ reads
def test_get_hitlist_answers_meta_and_data(client):
    r = client.get("/hitlist?window=7")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["origin"] == "synthetic" and body["meta"]["n_unit"] == "episodes" and body["meta"]["interval_level"] == 0.95
    assert "Nothing runs unless you press Automate" in body["meta"]["note"] and body["meta"]["n"] == body["data"]["episodes_in_window"]
    d = body["data"]
    assert d["state"] == "ok" and [x["id"] for x in d["rows"]] == ["calc-entry-3x", "case-note-copy"] and d["window_days"] == 7
    assert client.get("/hitlist").json()["data"]["window_days"] == 7
    assert client.get("/hitlist?window=30").json()["data"]["window_days"] == 30


def test_bad_arguments_are_plain_422s(client):
    assert client.get("/hitlist?window=14").status_code == 422
    assert client.get("/hitlist?window=7&now=tomorrow").status_code == 422
    assert client.get("/hitlist/firm?window=3", headers=admin()).json()["error"]["code"] == "bad_window"


def test_now_can_be_replayed(client):
    early = client.get("/hitlist?window=7&now=2026-11-01T00:00:00Z").json()["data"]
    assert early["window_to"] == "2026-11-01T00:00:00Z"


def test_an_unknown_person_is_a_404_but_a_new_install_is_a_calm_empty_answer(client, world, monkeypatch):
    assert client.get("/hitlist?person=p_nobody").status_code == 404
    monkeypatch.setattr(rh, "_resolve", lambda person: (None, None))
    d = client.get("/hitlist").json()["data"]
    assert d["state"] == "new_user" and d["rows"] == [] and "three times" in d["message"]


def test_the_onboarded_person_with_no_events_yet_is_a_new_user_not_an_error(client, monkeypatch):
    mem = MemoryStore()
    mem.save_state({"profile": {"person": "p_me", "role": "benefits-processor"}}, actor="worker")
    monkeypatch.setattr(rh, "_resolve", lambda person: (person, None))
    r = client.get("/hitlist?person=p_me")
    assert r.status_code == 200 and r.json()["data"]["state"] == "new_user"
    assert client.get("/hitlist?person=p_someone_else").status_code == 404


def test_real_capture_needs_the_workers_own_consent(client, world):
    world["pd"] = SimpleNamespace(person=P, origin="real", role="benefits-processor", t_last=NOW)
    off = client.get("/hitlist").json()
    assert off["data"]["state"] == "capture_off" and off["data"]["rows"] == [] and off["meta"]["origin"] == "real"
    home = Path(MemoryStore().home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "memory.md").write_text("---\nrole: benefits-processor\nrevision: 1\n---\n\n## Preferences\n- Capture: times only  <!-- id:l_capture | you agreed -->\n")
    on = client.get("/hitlist?now=" + "2026-11-07T18:00:00Z").json()
    assert on["data"]["state"] == "ok" and on["data"]["rows"]


# ------------------------------------------------------------------------------------------------ writes are the worker's own
@pytest.mark.parametrize("path,body", [("/hitlist/hide", {"id": "calc-entry-3x"}), ("/hitlist/unhide", {"id": "calc-entry-3x"}), ("/hitlist/reset", {})])
def test_only_the_worker_may_write(client, path, body):
    for actor in ("agent", "model", "page", "tool", "extension"):
        r = client.post(path, json=body, headers={"X-Understudy-Actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    r = client.post(path, json=body, headers={**ORIGIN, "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post(path, json=body, headers={**ORIGIN, "X-Understudy-Actor": ""}).status_code == 403
    lines = [x for x in audit_lines() if x["kind"] == "hitlist_write_refused"]
    assert len(lines) == 7 and all(x["outcome"] == "refused" and x["actor"] == "system" for x in lines)
    assert not any("calc-entry" in x["note"] or "household" in x["note"] for x in lines)          # the audit line has no content


def test_hide_removes_the_row_and_unhide_brings_it_back(client):
    r = client.post("/hitlist/hide", json={"id": "calc-entry-3x"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"hidden": "calc-entry-3x", "count": r.json()["count"], "returns_at": 2 * r.json()["count"]}
    d = client.get("/hitlist").json()["data"]
    assert [x["id"] for x in d["rows"]] == ["case-note-copy"]
    assert d["hidden"][0]["id"] == "calc-entry-3x" and d["hidden"][0]["returns_at"] == 2 * d["hidden"][0]["count"]
    assert client.post("/hitlist/unhide", json={"id": "calc-entry-3x"}, headers=ORIGIN).status_code == 200
    assert [x["id"] for x in client.get("/hitlist").json()["data"]["rows"]] == ["calc-entry-3x", "case-note-copy"]
    assert client.post("/hitlist/unhide", json={"id": "calc-entry-3x"}, headers=ORIGIN).status_code == 404
    assert client.post("/hitlist/hide", json={"id": "nope"}, headers=ORIGIN).json()["error"]["code"] == "unknown_row"
    assert client.post("/hitlist/hide", json={}, headers=ORIGIN).status_code == 422


def test_a_hidden_row_comes_back_when_its_count_has_doubled(client, world):
    client.post("/hitlist/hide", json={"id": "case-note-copy"}, headers=ORIGIN)
    world["eps"] = world["eps"] + many(NOTE, 12, prefix="m", spread_days=5)            # 8 became 20: past twice 8
    assert "case-note-copy" in [x["id"] for x in client.get("/hitlist").json()["data"]["rows"]]


def test_reset_clears_the_counts_and_says_what_it_cleared(client, world):
    client.post("/hitlist/hide", json={"id": "case-note-copy"}, headers=ORIGIN)
    home = Path(MemoryStore().home)
    home.mkdir(parents=True, exist_ok=True)
    keep = {"memory.md": "- a memory line", "routines_state.json": "{}"}
    for n, t in keep.items():
        (home / n).write_text(t)
    r = client.post("/hitlist/reset", headers=ORIGIN)
    assert r.status_code == 200
    out = r.json()
    assert out["cleared"] == {"counters": 2, "hidden_marks": 1} and out["counting_since"].startswith("2026-11-07")
    d = client.get("/hitlist").json()["data"]
    assert d["state"] == "counting_again" and d["rows"] == [] and d["hidden"] == [] and d["counting_since"]
    assert {n: (home / n).read_text() for n in keep} == keep                                    # nothing else was touched
    assert len(world["eps"]) == 20                                                               # the episodes are exactly as they were
    resets = [x for x in audit_lines() if x["kind"] == "hitlist_reset"]
    assert len(resets) == 1 and resets[0]["note"] == "cleared 2 counters and 1 hidden marks" and resets[0]["actor"] == "worker"
    assert re.fullmatch(r"cleared \d+ counters and \d+ hidden marks", resets[0]["note"])
    # a day later, new work counts again from zero and the old work stays out of the count
    world["pd"].t_last = NOW + DAY
    world["eps"] = world["eps"] + many(CALC, 4, prefix="after", now=NOW + DAY, days_back=0.5, spread_days=0.2)
    again = client.get("/hitlist?window=7").json()["data"]
    assert again["state"] == "ok" and [(x["id"], x["count"]) for x in again["rows"]] == [("calc-entry-3x", 4)] and again["counting_since"]


# ------------------------------------------------------------------------------------------------ the seeded demo
def test_the_seeded_demo_person_shows_the_routines_the_routines_screen_shows(client, world):
    """The demo person borrows another persona's traces and only the routine ids the seed lists, as GET /routines does."""
    MemoryStore().save_state({"demo": {"person": P, "routine_source": "p_src", "routine_ids": ["calc-entry-3x"]}}, actor="worker")
    d = client.get("/hitlist").json()["data"]
    assert [x["id"] for x in d["rows"]] == ["calc-entry-3x"] and d["rows"][0]["count"] == 9              # the borrowed persona's nine, not this person's twelve
    MemoryStore().save_state({"demo": {"person": P, "routine_source": "p_src", "routine_ids": []}}, actor="worker")
    assert [x["id"] for x in client.get("/hitlist").json()["data"]["rows"]] == ["calc-entry-3x", "case-note-copy"]
    MemoryStore().save_state({"demo": {"person": "someone_else", "routine_source": "p_src", "routine_ids": ["calc-entry-3x"]}}, actor="worker")
    assert [x["id"] for x in client.get("/hitlist").json()["data"]["rows"]] == ["calc-entry-3x", "case-note-copy"]
    assert client.get("/hitlist").json()["data"]["rows"][0]["count"] == 12


# ------------------------------------------------------------------------------------------------ the registry's decisions
def test_chips_follow_the_routine_registry(client, world, pack):
    mem = MemoryStore()
    st = RoutineStore(mem)
    st.merge(detect_routines(world["eps"], pack, person=P, now=NOW))
    assert client.get("/hitlist").json()["data"]["rows"][0]["actions"]["routine_id"] == "calc-entry-3x"
    st.consent("calc-entry-3x", "shadow", skill_override=True, actor="worker", person=P)
    rows = {x["id"]: x for x in client.get("/hitlist").json()["data"]["rows"]}
    assert rows["calc-entry-3x"]["status"] == "learning" and rows["calc-entry-3x"]["actions"]["can_automate"] is True
    st.consent("calc-entry-3x", "never", actor="worker", person=P)
    assert [x["id"] for x in client.get("/hitlist").json()["data"]["rows"]] == ["case-note-copy"]


def test_denylist_file_is_read_but_never_written(client, world):
    deny = Path(__import__("os").environ["UNDERSTUDY_DATA_DIR"]) / "denylist.json"
    deny.write_text(json.dumps({"entries": [{"kind": "app", "value": "GovCalc", "why": "x"}]}))
    before = deny.read_text()
    d = client.get("/hitlist").json()["data"]
    assert [x["id"] for x in d["rows"]] == ["case-note-copy"] and d["held_back"] == [{"reason": "denylist", "count": 1}]
    assert deny.read_text() == before
    deny.write_text("{broken")
    assert len(client.get("/hitlist").json()["data"]["rows"]) == 2                            # a damaged file is no denylist, not a crash


# ------------------------------------------------------------------------------------------------ firm
def admin():
    from understudy_engine import http_guard

    http_guard.ensure_token()
    return {"x-understudy-role": "admin", "x-understudy-token": http_guard.read_token()}


def test_the_firm_endpoint_is_admin_only(client):
    """The firm's repeated work is Admin data: no header, a worker header, an admin header without the token, a bad token and a non-worker actor are all refused (it used to be open to any caller)."""
    from understudy_engine import http_guard

    http_guard.ensure_token()
    token = http_guard.read_token()
    url = "/hitlist/firm?window=7"
    assert client.get(url).status_code == 403 and client.get(url).json()["error"]["code"] == "admin_only"
    assert client.get(url, headers={"x-understudy-role": "worker", "x-understudy-token": token}).json()["error"]["code"] == "admin_only"
    r = client.get(url, headers={"x-understudy-role": "admin"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_token_required"
    assert client.get(url, headers={"x-understudy-role": "admin", "x-understudy-token": "0" * 64}).json()["error"]["code"] == "admin_token_required"
    r = client.get(url, headers={**admin(), "x-understudy-actor": "agent"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_actor_refused"
    assert "p_" not in json.dumps(client.get(url).json())                                           # a refusal carries no data at all
    assert client.get(url, headers=admin()).status_code == 200


def test_the_firm_endpoint_is_an_aggregate_badged_synthetic(client):
    r = client.get("/hitlist/firm?window=30", headers=admin())
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["origin"] == "synthetic" and body["meta"]["n_unit"] == "people" and body["meta"]["n"] == 60
    assert "coaching and onboarding" in body["meta"]["note"]
    d = body["data"]
    assert d["min_group"] == 5 and d["rows"] and all(x["people"] >= 5 for x in d["rows"]) and d["total"]["hours_per_week"]["point"] > 0
    assert not re.search(r"f_(ben|dat|pro)_\d", json.dumps(body))                                  # no person id anywhere
    only = client.get("/hitlist/firm?window=7&role=programmer", headers=admin()).json()["data"]
    assert {x["role"] for x in only["rows"]} <= {"programmer"} and only["people"] == 12


# ------------------------------------------------------------------------------------------------ the pointer for the insights layer
def test_top_rows_gives_ids_numbers_and_enums_only(world):
    (top,) = S.top_rows(P, 1)
    assert set(top) == {"id", "label_id", "count", "window_days", "seconds_per_time", "hours_saved", "n", "origin", "t", "action_to"}
    assert top["id"] == top["label_id"] == "calc-entry-3x" and top["action_to"] == "repeats" and top["origin"] == "synthetic"
    hs = top["hours_saved"]
    assert 0 < hs["lo"] <= hs["value"] <= hs["hi"] and hs["horizon_weeks"] == 4
    assert top["count"] == top["n"] and top["window_days"] == 7 and top["t"] > 0
    assert len(S.top_rows(P, 5)) == 2 and S.top_rows(P, 0) == []
    from understudy_engine.hitlist import top_rows
    assert top_rows(P, 1)[0]["id"] == "calc-entry-3x"


def test_top_rows_falls_back_to_thirty_days_and_never_raises(world, monkeypatch):
    world["eps"] = many(CALC, 8, prefix="o", days_back=15, spread_days=8)
    assert S.top_rows(P, 1)[0]["window_days"] == 30
    world["eps"] = []
    assert S.top_rows(P, 1) == []
    monkeypatch.setattr(rh, "_resolve", lambda person: (_ for _ in ()).throw(RuntimeError("boom")))
    assert S.top_rows(P, 1) == []


# ------------------------------------------------------------------------------------------------ the layer's own switches
def test_the_flag_is_off_by_default_and_read_each_time(monkeypatch):
    assert S.enabled() is False and R.enabled() is False
    monkeypatch.setenv("UNDERSTUDY_X_HITLIST", "1")
    assert S.enabled() is True
    monkeypatch.delenv("UNDERSTUDY_X_HITLIST")
    monkeypatch.setenv("UNDERSTUDY_X", "yes")
    assert S.enabled() is True and R.FLAG == "UNDERSTUDY_X_HITLIST"


def test_the_layer_is_pure_compute_no_network_no_process_no_model():
    root = Path(__file__).resolve().parents[2] / "understudy_engine" / "hitlist"
    banned = re.compile(r"^\s*(import|from)\s+(httpx|requests|urllib|socket|subprocess|http\.client|openai|google|anthropic|aiohttp)\b", re.M)
    files = sorted(root.glob("*.py"))
    assert len(files) >= 7
    for f in files:
        text = f.read_text()
        assert not banned.search(text), f.name
        assert "ModelPort" not in text and "os.system" not in text and "http://" not in text and "https://" not in text, f.name
