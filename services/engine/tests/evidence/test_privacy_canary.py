"""Privacy: planted names, emails and paths never reach a packet, a request, a reply or a log; vocabularies and the static guard are clean."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from understudy_engine.evidence import canary_flows as CF
from understudy_engine.evidence import explain as E
from understudy_engine.evidence import packet as P
from understudy_engine.privacy import canary, guard
from understudy_engine.privacy.testing import CanaryFlow, CapturingPort, assert_vocabularies_clean, canary_flow, run_flow

PKG = Path(P.__file__).parent


def test_the_flows_are_registered_the_way_the_privacy_track_expects():
    assert len(CF.FLOWS) == 1
    f = CF.FLOWS[0]
    assert isinstance(f, CanaryFlow) and f.layer == "evidence" and f.min_requests >= 1
    assert f.make_fixtures() is not f.make_fixtures()


@pytest.mark.parametrize("seed", range(8))
def test_the_real_flow_leaks_nothing_across_seeds(seed):
    r = run_flow(CF.FLOWS[0], seed=seed)
    assert r.error is None, r.error
    assert r.requests >= 1 and r.planted >= 15
    assert r.leaked == 0 and r.leaked_kinds == []
    assert r.ledger_complete and r.ledger_lines == r.ledger_expected == r.requests, r.note
    assert r.artifact_leaked == 0
    assert {"person_name", "email", "meeting_title", "file_path", "commit_message", "customer_name"} <= set(r.by_kind)


def test_the_strict_one_call_kit_agrees():
    rep = canary_flow("evidence.explain_cloud", CF.make_fixtures, CF.run, min_requests=1, record=False)
    assert rep.ok and rep.planted >= 15


def _planted_run(seed: int):
    fx = CF.make_fixtures()
    planted = canary.plant(fx, seed=seed)
    return fx, planted


def test_planted_text_reaches_neither_the_packet_nor_the_reply_nor_the_local_model():
    sent: list[str] = []

    class Client:
        def chat_json(self, messages, schema, **kw):
            sent.append(json.dumps(messages))
            draft = json.loads(messages[1]["content"])["draft"]

            class R:
                obj = {"sections": [{"kind": "answer", "sentences": [{"text": "In short: " + s["text"], "uses": s["uses"]} for s in draft[:5]]}],
                       "coach_actions": []}

            return R()

    for seed in range(4):
        fx, planted = _planted_run(seed)
        g = fx["genome"]
        pk = P.from_genome(g["data"], g["meta"])
        pk = P.combine(pk, hazard=P.from_hazard(fx["hazard"]), coach=P.from_coach(fx["coach"])[0], routines=P.from_routines(fx["routines"]))
        out = E.explain(pk, "why did this case take 14 minutes?", backends=E.Backends(local=E.LocalBackend(client=Client())))
        assert out["source"] == "local" and out["check"]["ok"], out["attempts"]
        for name, blob in (("packet", json.dumps(pk.to_wire())), ("response", json.dumps(out)), ("local request", sent[-1])):
            rep = canary.scan([blob], planted)
            assert rep.ok, f"{name}: {rep.summary()}"


def test_the_packet_endpoint_and_the_explain_endpoint_never_echo_source_text(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from understudy_engine.evidence import routes as R
    from understudy_engine.evidence.sources import Sources

    monkeypatch.setenv("UNDERSTUDY_X_EVIDENCE", "1")
    fx, planted = _planted_run(5)
    g = fx["genome"]
    src = Sources(genome=lambda p, c: (g["data"], g["meta"]), hazard=lambda p: {"meta": g["meta"], "data": fx["hazard"]},
                  coach=lambda p: fx["coach"], routines=lambda p: {"meta": g["meta"], "data": fx["routines"]})
    app = FastAPI()
    app.include_router(R.router)
    app.state.evidence_sources = src
    c = TestClient(app)
    r1 = c.get("/evidence/packet", params={"person": "p_x"})
    r2 = c.post("/evidence/explain", json={"person": "p_x", "include_packet": True, "question": "why did Ada Lovelace take so long"})
    assert r1.status_code == r2.status_code == 200
    for r in (r1, r2):
        rep = canary.scan([r.text], planted)
        assert rep.ok, rep.summary()
    assert "Ada Lovelace" not in r2.text


def test_the_cloud_request_is_the_packet_and_nothing_else():
    fx, planted = _planted_run(1)
    g = fx["genome"]
    pk = P.from_genome(g["data"], g["meta"])
    port = CapturingPort()
    E.explain(pk, "mail ada.lovelace@example.test about /Users/ada/ledger.py", backends=E.Backends(cloud=E.CloudBackend(port=port)))
    assert len(port) == 1
    body = json.dumps(port.requests[0].body)
    assert canary.scan(port, planted).ok
    assert "ada.lovelace" not in body and "/Users" not in body and "ledger" not in body.lower()
    from understudy_engine.privacy.testing import _wire_from_request

    wire = _wire_from_request(port.requests[0])
    assert wire["purpose"] == E.PURPOSE and wire["payload"]["question"] == {"intent": "unsupported"}


def test_vocabularies_instructions_and_field_names_pass_the_backstop():
    E.ensure_registered()
    assert_vocabularies_clean()


def test_every_packet_passes_the_backstop_as_a_request_and_is_one_ledger_line(packets):
    from understudy_engine.privacy import egress

    E.ensure_registered()
    for pk in packets[:12]:
        info = egress.preview(E.PURPOSE, E.build_request(pk, None))
        assert info["bytes"] < 8192 and set(info["payload"]) == {"packet", "question", "menu"}


def test_this_package_obeys_the_static_egress_guard():
    """No model client, no ModelPort, no network import, no .plan/.check call: the package asks for a reply only through
    ``egress.send`` (cloud) or the local-model server's loopback client (local), exactly as the other layers do."""
    bad = []
    for f in sorted(PKG.glob("*.py")):
        viol = guard.scan_source(f.read_text(encoding="utf-8"), f"evidence/{f.name}")[0]
        bad += [f"{f.name}:{v.line} {v.rule} {v.detail}" for v in viol]
    routes = guard.scan_source((PKG / "routes.py").read_text(encoding="utf-8"), "routes_evidence.py")[0]
    assert not bad and not routes, bad
