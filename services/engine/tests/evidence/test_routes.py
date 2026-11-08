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


def test_the_real_app_packet_for_an_apprentice_says_it_is_the_v1_genome_block_and_the_check_passes(genome_env, monkeypatch):
    """ML2's builder now answers for an apprentice with v1 inputs (accepted None). The packet must record the v1 numbers as the genome
    block, record no mlv2 block, never claim v2, and the explanation must still pass the provenance check for every intent."""
    from understudy_engine.api.app import create_app
    from understudy_engine.mlv2 import evidence_inputs as ei

    root, _ = genome_env
    seen = {}
    real = ei.build

    def spy(person, case=None, **kw):
        seen.update(kw)
        out = real(person, case, **kw)
        seen["model_version"], seen["accepted"] = out.model_version, out.accepted
        return out

    monkeypatch.setattr(ei, "build", spy)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root))
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    c = TestClient(create_app(root, warm=False))
    d = c.get("/evidence/packet", params={"person": "p_nov03"}).json()["data"]
    assert str(seen["root"]) == str(root), "the builder reads the store the app uses"
    assert (seen["model_version"], seen["accepted"]) == ("v1", None)
    pb = d["packet"]["blocks"]
    assert pb["genome"] == {"status": "ok", "source": "v1"} and pb["mlv2"] == {"status": "absent"}
    assert not [b for b in pb.values() if b.get("source") == "v2"]
    assert d["blocks"]["genome"] == "ok" and d["blocks"]["mlv2"].startswith("v1 inputs only")
    assert "cohort_habits" in d["packet"] and d["packet"]["gap"]["cohort_gap_s"]                     # the genome path keeps the cohort
    from understudy_engine.evidence import vocab as V

    for intent in V.INTENTS:
        q = {"where_time_went": None, "why_slow": "why did this case take 14 minutes?", "biggest_habit": "biggest habit?", "compare_expert": "vs the expert?",
             "stuck_reading": "was I stuck?", "how_sure": "how sure are the numbers?", "routine_worth": "is the routine worth it?",
             "trust_level": "what is the trust level?", "what_to_practise": "what should I practise?", "unsupported": "tell me a joke"}[intent]
        r = c.post("/evidence/explain", json={"person": "p_nov03", "question": q}, headers=WORKER)
        out = r.json()["data"]
        assert r.status_code == 200 and out["intent"] == intent and out["check"]["ok"] and out["check"]["template_ok"], (intent, out["check"])


def test_the_real_app_packet_for_a_person_with_no_apprentice_data_still_passes_the_check(tmp_path, monkeypatch):
    """A live user id: no apprentice cohort, so the builder has nothing (ValueError or no cohort) and the genome path has nothing either. The
    packet is built from whatever the app's other sources hold (here a synthetic persona's coach and routines) and every block says what it is."""
    from understudy_engine.api.app import create_app
    from understudy_engine.personas import PERSONA_BY_SLUG, write_persona

    root = tmp_path / "persona-data"
    root.mkdir()
    write_persona(PERSONA_BY_SLUG["irregular"], root, with_mc=False)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root))
    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    c = TestClient(create_app(root, warm=False))
    r = c.get("/evidence/packet", params={"person": "p_irregular"})
    if r.status_code == 404:
        assert r.json()["error"]["code"] == "no_evidence"               # nothing at all for this id: said plainly, never an invented packet
        r2 = c.post("/evidence/explain", json={"person": "p_irregular"}, headers=WORKER)
        assert r2.status_code == 404 and r2.json()["error"]["code"] == "no_evidence"
        return
    d = r.json()["data"]
    pb = d["packet"]["blocks"]
    assert pb["genome"]["status"] == "absent" and pb["mlv2"]["status"] == "absent" and not [b for b in pb.values() if b.get("source") == "v2"]
    out = c.post("/evidence/explain", json={"person": "p_irregular", "question": "was I stuck?"}, headers=WORKER).json()["data"]
    assert out["check"]["ok"] and out["check"]["template_ok"] and out["source"] == "template"


def test_a_live_user_id_with_a_coach_decision_and_routines_gets_a_checked_explanation(genome_env, monkeypatch):
    """The same case through injected sources: no apprentice data (the builder raises ValueError, the genome source has nothing), but the
    coach and routines answer. The check must pass for every intent and the badge must not claim synthetic structure it does not have."""
    from understudy_engine.evidence import explain as E
    from understudy_engine.evidence import vocab as V
    from understudy_engine.evidence.sources import build_packet

    def no_cohort(person, case):
        raise ValueError(f"person {person!r} is not in the generated cohort")

    src = Sources(inputs=no_cohort, genome=lambda p, c: None,
                  coach=lambda p: {"action": "nudge", "level": "L2", "trigger": "stuck", "reason_codes": ["stuck_signal", "gate_act"], "gate": {"consecutive": 2},
                                   "missed": [], "p_stuck": 0.62, "p_source": "hazard"},
                  routines=lambda p: {"meta": {"origin": "real", "n": 40, "n_unit": "episodes"},
                                      "data": [{"id": "calc-entry-3x", "episodes": 14, "minutes_per_week": 96, "value": {"hours_saved": [3.1, 5.2], "horizon_weeks": 4},
                                                "status": "shadow", "rung": "A1", "shadow": {"runs": 12, "matches": 12, "wilson_lower": 0.757}}]})
    built = build_packet("p_live_user", None, src)
    pk = built.packet
    assert pk.blocks["genome"].status == "absent" and pk.blocks["mlv2"].status == "absent" and pk.blocks["coach"].status == "ok"
    assert pk.meta.origin == "live" and "synthetic_data" not in pk.limitations
    for it in V.INTENTS:
        out = E.explain(pk, None, intent=it)
        assert out["check"]["ok"] and out["check"]["template_ok"], (it, out["check"])
    assert E.explain(pk, None, intent="stuck_reading")["footer"].endswith("live data.")
