"""The routes: off by default (404 extension_off), worker-only writes, the packet and the explanation, and the engine app wiring."""
from __future__ import annotations

import json

import jsonschema
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.evidence import packet as P
from understudy_engine.evidence import routes as R
from understudy_engine.evidence.sources import Sources

WORKER = {"X-Understudy-Actor": "worker"}


@pytest.fixture(scope="module")
def genome_env(tmp_path_factory):
    from understudy_engine.genome import TASK, GenomeError, GenomeService
    from understudy_engine.personas import apprentices
    from understudy_engine.store import EventStore

    root = tmp_path_factory.mktemp("evidence-routes")
    apprentices.generate(root)
    svc = GenomeService(EventStore(root))

    def genome(person, case):
        try:
            return svc.genome(TASK, person=person, episode=case)
        except GenomeError:
            return None

    return root, Sources(genome=genome)


@pytest.fixture()
def client(genome_env):
    _, src = genome_env
    app = FastAPI()
    app.include_router(R.router)
    app.state.evidence_sources = src
    return TestClient(app)


def test_everything_is_off_by_default(client):
    for r in (client.get("/evidence/packet"), client.post("/evidence/explain", json={}, headers=WORKER)):
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off"
    assert R.enabled() is False


@pytest.mark.parametrize("flag", ["UNDERSTUDY_X_EVIDENCE", "UNDERSTUDY_X"])
def test_either_flag_turns_it_on(client, monkeypatch, flag):
    monkeypatch.setenv(flag, "1")
    assert R.enabled() and client.get("/evidence/packet").status_code == 200


def test_get_packet_returns_the_closed_schema_packet_and_its_facts(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    r = client.get("/evidence/packet", params={"person": "p_nov03"})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["origin"] == "synthetic" and body["meta"]["n"] == 24 and body["meta"]["n_unit"] == "people"
    d = body["data"]
    assert d["person"] == "p_nov03" and d["case"].startswith("t_nov03") and d["blocks"]["genome"] == "ok"
    jsonschema.validate(d["packet"], json.loads(P.SCHEMA_PATH.read_text()))
    paths = {f["path"] for f in d["facts"]}
    assert "gap.case_s" in paths and "meta.n" in paths and all(isinstance(f["value"], (int, float)) for f in d["facts"])
    assert {x["id"] for x in d["limitations"]} >= {"synthetic_data", "association_only"} and all(x["text"] for x in d["limitations"])
    text = json.dumps(d["packet"])
    assert "p_nov" not in text and "t_nov" not in text                       # ids of people and cases are not part of the packet


def test_get_packet_default_person_and_a_named_case(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    d0 = client.get("/evidence/packet").json()["data"]
    assert d0["person"] and d0["case"]
    d1 = client.get("/evidence/packet", params={"person": "p_nov03", "case": "t_nov03b"}).json()["data"]
    assert d1["case"] == "t_nov03b"


def test_unknown_person_and_bad_ids(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    r = client.get("/evidence/packet", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_evidence"
    assert client.get("/evidence/packet", params={"person": "../etc/passwd"}).status_code == 422
    assert client.get("/evidence/packet", params={"person": "x" * 200}).status_code == 422


def test_post_explain_in_mock_mode_uses_the_template_and_says_so(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    r = client.post("/evidence/explain", json={"person": "p_nov03", "question": "why did this case take 14 minutes?"}, headers=WORKER)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["source"] == "template" and d["intent"] == "why_slow" and d["check"]["ok"] and d["person"] == "p_nov03"
    assert d["question"]["asked_s"] == 840.0 and d["question"]["matches_case"] is False
    kinds = [s["kind"] for s in d["sections"]]
    assert kinds[0] in ("answer", "explanation") and "coaching" in kinds and kinds[-1] == "limits"
    assert "packet" not in d
    assert "Words from the built-in template" in r.json()["meta"]["note"] and "not that it is true" in r.json()["meta"]["note"]
    d2 = client.post("/evidence/explain", json={"person": "p_nov03", "include_packet": True}, headers=WORKER).json()["data"]
    assert d2["packet"]["meta"]["n"] == 24 and d2["intent"] == "where_time_went"


def test_writes_are_the_workers_only(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    for actor in ("agent", "model", "page", "tool"):
        r = client.post("/evidence/explain", json={"person": "p_nov03"}, headers={"X-Understudy-Actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    r = client.post("/evidence/explain", json={"person": "p_nov03"}, headers={"X-Understudy-Actor": "worker", "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/evidence/explain", json={"person": "p_nov03"}, headers={"X-Understudy-Actor": "worker", "Origin": "http://localhost:5173"}).status_code == 200
    assert client.post("/evidence/explain", json={"person": "p_nov03"}).status_code == 200            # the default actor is the worker


def test_body_is_validated(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    assert client.post("/evidence/explain", json={"question": "x" * 1000}, headers=WORKER).status_code == 422
    assert client.post("/evidence/explain", json={"person": "p_nov03", "model": "gpt"}, headers=WORKER).status_code == 422
    assert client.post("/evidence/explain", json={"person": "p_zzz"}, headers=WORKER).status_code == 404


def test_the_engine_app_includes_the_router_only_when_the_flag_is_on(genome_env, monkeypatch):
    from understudy_engine.api.app import create_app

    root, _ = genome_env
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root))
    app = create_app(root, warm=False)
    assert app.state.extensions.get("evidence") is False
    assert not any(getattr(r, "path", "") == "/evidence/packet" for r in app.routes)
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    app = create_app(root, warm=False)
    assert app.state.extensions.get("evidence") is True
    c = TestClient(app)
    assert c.get("/health").json()["extensions"]["evidence"] is True
    r = c.get("/evidence/packet", params={"person": "p_nov03"})
    assert r.status_code == 200 and r.json()["data"]["blocks"]["genome"] == "ok"
    r = c.post("/evidence/explain", json={"person": "p_nov03", "question": "how sure are the numbers?"}, headers=WORKER)
    assert r.status_code == 200 and r.json()["data"]["source"] == "template" and r.json()["data"]["intent"] == "how_sure"
