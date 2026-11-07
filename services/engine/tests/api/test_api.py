from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("understudy_agent", reason="run with: uv run --package understudy-agent pytest services/engine/tests/api")

from understudy_agent.audit import AuditLog  # noqa: E402
from understudy_agent.queue import ApprovalQueue  # noqa: E402


def ev(i: int, *, person="p_ann", origin="real", typ="click", t0=None, **kw):
    t0 = t0 or datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    row = {"schema": 1, "id": f"api{i:07d}", "t": (t0 + timedelta(seconds=5 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "origin": origin,
           "actor": "human", "person": person, "role": "benefits-processor", "source": "browser", "type": typ}
    row.update(kw)
    return row


def assert_error(r, status, code=None):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"} and body["error"]["message"]
    if code:
        assert body["error"]["code"] == code


# ------------------------------------------------------------------ health, routing, cors
def test_health_shape_and_mock_flag(client):
    h = client.get("/health").json()
    assert h["ok"] is True and h["mock"] is True and h["version"]
    assert set(h["models"]) == {"planner", "fast", "computer_use"} and set(h["services"]) == {"engine", "agent"}
    assert h["services"]["engine"] is True and h["services"]["agent"] is False


def test_models_come_from_environment_never_hard_coded(client, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_PLANNER", "planner-from-env")
    models = client.get("/health").json()["models"]
    assert models["planner"] == "planner-from-env" and models["fast"] == "mock"      # unset in mock mode reads "mock"
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.delenv("OPENAI_MODEL_FAST", raising=False)
    assert client.get("/health").json()["models"]["fast"] == "(not set)"


def test_unknown_route_and_wrong_method_use_the_error_shape(client):
    assert_error(client.get("/nope"), 404, "not_found")
    assert_error(client.put("/health"), 405, "method_not_allowed")
    assert_error(client.get("/replay?speed=500"), 422, "invalid_request")


def test_cors_allows_the_dashboard_origin_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    ok = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "http://evil.example"}).headers
    pre = client.options("/events", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 200


def test_optional_routers_are_reported(env):
    from understudy_engine.api.app import create_app

    app = create_app(env)
    assert app.state.router_status["routes_data"] == "included"
    assert app.state.router_status["routes_analytics"] in ("included", "absent") or app.state.router_status["routes_analytics"].startswith("import failed")


# ------------------------------------------------------------------ events
def test_post_events_accepts_valid_and_reports_rejections(fresh):
    client, root = fresh
    r = client.post("/events", json=[ev(1), {**ev(2), "type": "keypress"}, ev(3), {**ev(4), "url": "https://x.example"}, ev(1)])
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 2 and [x["index"] for x in body["rejected"]] == [1, 3, 4]
    assert all(set(x) == {"index", "reason"} and x["reason"] for x in body["rejected"])
    assert body["rejected"][2]["reason"] == "duplicate id"
    assert client.post("/events", json=ev(9)).json() == {"accepted": 1, "rejected": []}          # one bare event
    assert client.post("/events", json={"events": [ev(10)]}).json()["accepted"] == 1             # wrapped
    assert_error(client.post("/events", content=b"not json", headers={"content-type": "application/json"}), 400, "bad_json")
    assert (root / "real" / "p_ann" / "2026-11-07.jsonl").exists()


def test_get_events_filters(fresh):
    client, _ = fresh
    client.post("/events", json=[ev(i) for i in range(6)] + [ev(10 + i, person="p_bob") for i in range(3)] + [ev(20, origin="synthetic", person="p_syn")])
    assert len(client.get("/events").json()["events"]) == 9                                         # default partition: real
    assert len(client.get("/events?person=p_bob").json()["events"]) == 3
    assert len(client.get("/events?partition=synthetic").json()["events"]) == 1
    assert len(client.get("/events?limit=2").json()["events"]) == 2
    since = (datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc) + timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert len(client.get(f"/events?person=p_ann&since={since}").json()["events"]) == 2
    assert_error(client.get("/events?since=yesterday"), 422, "bad_since")
    assert_error(client.get("/events?partition=other"), 422)
    row = client.get("/events?person=p_bob&limit=1").json()["events"][0]
    assert row["schema"] == 1 and row["t"].endswith("Z") and "meta" not in row


# ------------------------------------------------------------------ replay, packs
def test_replay_shape_speed_squeeze_and_filters(client):
    r = client.get("/replay?person=p_nov03&task=t_nov03a&speed=1&squeeze_idle_s=30").json()
    assert set(r) >= {"duration_s", "frames"} and r["frames"] and r["total_frames"] == len(r["frames"])
    f = r["frames"][5]
    assert set(f) == {"t_replay", "event", "state"} and set(f["state"]) == {"task", "last_cog", "counts"}
    assert f["event"]["task_id"] == "t_nov03a" and all(isinstance(v, int) for v in f["state"]["counts"].values())
    times = [x["t_replay"] for x in r["frames"]]
    assert times == sorted(times) and r["frames"][-1]["state"]["counts"].get("REVERT", 0) >= 0
    fast = client.get("/replay?person=p_nov03&task=t_nov03a&speed=50").json()
    assert fast["duration_s"] == pytest.approx(r["duration_s"] / 50, rel=1e-3)
    assert client.get("/replay?person=p_nov03&task=t_nov03a&speed=1&squeeze_idle_s=0").json()["duration_s"] == 0
    assert r["frames"][-1]["state"]["counts"] == fast["frames"][-1]["state"]["counts"]            # same state at any speed
    again = client.get("/replay?person=p_nov03&task=t_nov03a&speed=1&squeeze_idle_s=30").json()
    assert again == r                                                                             # deterministic
    paged = client.get("/replay?person=p_irregular&limit=50&offset=10").json()
    assert len(paged["frames"]) == 50 and paged["truncated"] is True and paged["total_frames"] > 1000
    assert_error(client.get("/replay?person=p_nobody"), 404, "no_events")


def test_replay_default_is_a_novice_case(client):
    r = client.get("/replay").json()
    assert r["frames"][0]["event"]["person"].startswith("p_nov") and r["partition"] == "synthetic"


def test_packs_list_matches_contract(client):
    rows = client.get("/packs").json()
    assert {"benefits-processor", "data-analyst", "programmer"} <= {r["id"] for r in rows}
    assert all(set(r) == {"id", "name", "summary", "depth"} and r["depth"] in ("deep", "thin") for r in rows)


# ------------------------------------------------------------------ genome, transitions
def test_genome_envelope_and_shape(client):
    r = client.get("/genome/benefits-household-entry?person=p_nov04")
    assert r.status_code == 200
    body = r.json()
    meta, data = body["meta"], body["data"]
    assert meta["origin"] == "synthetic" and meta["n"] == 24 and meta["n_unit"] == "people" and meta["split"] and meta["interval_level"] == 0.95
    assert meta["generated_at"]
    for k in ("task", "person", "expert_person", "expert", "novice", "alignment", "waterfall", "total_gap_s", "total_gap_ci", "controls"):
        assert k in data, k
    assert data["person"] == "p_nov04" and data["controls"]["placebo"]["ci"] and data["controls"]["null"]["ci"]
    assert all(isinstance(w["ci"], list) and len(w["ci"]) == 2 for w in data["waterfall"])
    assert data["total_gap_ci"][0] < data["total_gap_s"] < data["total_gap_ci"][1]
    ops = {a["op"] for a in data["alignment"]}
    assert ops <= {"match", "mismatch", "gap_expert", "gap_novice"}
    for a in data["alignment"]:                                                  # the dashboard reads a gap from i or j being null
        assert (a["i"] is None) == (a["op"] == "gap_expert") and (a["j"] is None) == (a["op"] == "gap_novice")
        assert isinstance(a["seconds"], (int, float))
    # dashboard default task id and consensus reference
    assert client.get("/genome/t_entitlement_check").status_code == 200
    cons = client.get("/genome/benefits?reference=consensus&person=p_nov04").json()["data"]
    assert cons["expert_person"] is None
    first = client.get("/genome/benefits?person=p_nov04").json()["data"]
    assert first == client.get("/genome/benefits?person=p_nov04").json()["data"]                  # deterministic


def test_genome_errors_are_plain(client):
    assert_error(client.get("/genome/nope"), 404, "unknown_task")
    assert_error(client.get("/genome/benefits?person=p_exp01"), 422, "not_a_novice")
    assert_error(client.get("/genome/benefits?person=p_zzz"), 404, "unknown_person")
    assert_error(client.get("/genome/benefits?reference=magic"), 422, "invalid_request")


def test_genome_without_cohort_is_a_clear_404(fresh):
    client, _ = fresh
    assert_error(client.get("/genome/benefits"), 404, "no_cohort")
    assert_error(client.get("/graph/transitions"), 404, "no_cohort")


def test_transitions_shape(client):
    body = client.get("/graph/transitions?task=benefits").json()
    assert body["meta"]["origin"] == "synthetic"
    d = body["data"]
    assert d["nodes"] and set(d["nodes"][0]) == {"id", "cog", "expert_dwell_s", "novice_dwell_s"}
    e = d["edges"][0]
    assert {"from", "to", "expert_freq", "novice_freq", "missing_for_novice", "planted"} <= set(e)
    flagged = [x for x in d["edges"] if x["missing_for_novice"]]
    assert flagged and all(x["planted"] is True for x in flagged)
    assert all(x["planted"] is None for x in d["edges"] if not x["missing_for_novice"])


# ------------------------------------------------------------------ queue and audit
def _enqueue(tmp_path, **kw):
    q = ApprovalQueue()
    return q.enqueue(kind=kw.pop("kind", "irreversible_step"), title=kw.pop("title", "Submit case note CN-2041"), summary="One line, plain.",
                     risk_class=kw.pop("risk_class", "irreversible"), routine_id="calc-entry-3x", run_id="r_01", **kw)


def test_queue_list_and_status_filter(fresh):
    client, root = fresh
    a, b = _enqueue(root), _enqueue(root, title="Send letter")
    body = client.get("/queue").json()
    assert body["meta"]["n"] == 2 and [i["id"] for i in body["data"]] == [a["id"], b["id"]]
    item = body["data"][0]
    assert {"id", "created_at", "routine_id", "run_id", "kind", "title", "summary", "risk_class", "evidence", "status", "decided_at", "decided_by"} <= set(item)
    assert set(item["evidence"]) >= {"screenshots", "extracted", "expected", "diff", "tier_log"}
    client.post(f"/queue/{a['id']}/approve")
    assert [i["id"] for i in client.get("/queue?status=pending").json()["data"]] == [b["id"]]
    assert len(client.get("/queue?status=all").json()["data"]) == 2
    assert [i["id"] for i in client.get("/queue?status=approved").json()["data"]] == [a["id"]]
    assert_error(client.get("/queue?status=bogus"), 422)


def test_approve_records_worker_and_auth_in_item_and_audit(fresh):
    client, root = fresh
    item = _enqueue(root)
    r = client.post(f"/queue/{item['id']}/approve", json={"auth": {"method": "auth0_stepup", "sub_hash": "0a1b2c3d4e5f"}})
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "approved" and out["decided_by"] == "worker" and out["auth_method"] == "auth0_stepup" and out["sub_hash"] == "0a1b2c3d4e5f"
    assert out["decided_at"]
    on_disk = json.loads((root / "queue" / f"{item['id']}.json").read_text())
    assert on_disk["auth_method"] == "auth0_stepup" and on_disk["decided_by"] == "worker"
    rows = client.get("/audit?limit=10").json()["data"]
    line = [x for x in rows if x["kind"] == "queue_decided"][-1]
    assert line["actor"] == "human" and line["outcome"] == "approved" and line["meta"]["auth_method"] == "auth0_stepup" and line["meta"]["sub_hash"] == "0a1b2c3d4e5f"
    assert AuditLog().verify_chain() is True


def test_reject_without_body_defaults_to_local(fresh):
    client, root = fresh
    item = _enqueue(root)
    out = client.post(f"/queue/{item['id']}/reject").json()
    assert out["status"] == "rejected" and out["decided_by"] == "worker" and out["auth_method"] == "local" and "sub_hash" not in out


def test_decision_body_rejects_unknown_keys_and_non_hash_subjects(fresh):
    client, root = fresh
    item = _enqueue(root)
    for bad in ({"auth": {"method": "local", "email": "a@b.example"}}, {"auth": {"method": "local", "name": "Ann"}}, {"who": "ann"},
                {"auth": {"method": "password"}}, {"auth": {"method": "auth0_stepup", "sub_hash": "ann@example.com"}},
                {"auth": {"method": "auth0_stepup", "sub_hash": "eyJhbGciOi.token"}},
                {"auth": {"method": "auth0_stepup", "sub_hash": "h:0a1b2c3d4e5f"}}, {"auth": {"method": "auth0_stepup", "sub_hash": "0A1B2C3D4E5F"}},
                {"auth": {"method": "auth0_stepup", "sub_hash": "0a1b2c3d4e"}}):
        assert_error(client.post(f"/queue/{item['id']}/approve", json=bad), 422)
    assert client.get("/queue?status=pending").json()["data"][0]["status"] == "pending"            # nothing changed


def test_queue_errors(fresh):
    client, root = fresh
    item = _enqueue(root)
    assert_error(client.post("/queue/q_missing/approve"), 404, "no_such_item")
    assert_error(client.post("/queue/..%2Fx/approve"), 404)
    assert client.post(f"/queue/{item['id']}/reject").status_code == 200
    assert_error(client.post(f"/queue/{item['id']}/approve"), 409, "already_decided")


def test_audit_is_redacted_rows_and_limited(fresh):
    client, root = fresh
    log = AuditLog()
    for i in range(7):
        log.append("agent", "step", routine="calc-entry-3x", run_id="r_01", tier=1, outcome="ok", note=f"page said: click here {i}")
    body = client.get("/audit?limit=3").json()
    assert body["meta"]["n"] == 3 and len(body["data"]) == 3
    row = body["data"][0]
    assert {"t", "actor", "kind", "routine", "run_id", "tier", "outcome", "note"} <= set(row)
    assert "page said" not in json.dumps(body)                                                    # no page text, a hash and a length only
    assert_error(client.get("/audit?limit=0"), 422)
    assert client.get("/audit").json()["data"][0]["kind"] == "step"


def test_empty_queue_and_audit(fresh):
    client, _ = fresh
    assert client.get("/queue").json()["data"] == [] and client.get("/audit").json()["data"] == []


# ------------------------------------------------------------------ kill
def test_kill_flag_roundtrip(fresh):
    client, root = fresh
    assert client.get("/kill").json() == {"killed": False, "at": None}
    r = client.post("/kill").json()
    assert r["killed"] is True and r["agent_notified"] is False and datetime.fromisoformat(r["at"])
    assert (root / "KILL").exists()
    assert client.get("/kill").json() == {"killed": True, "at": r["at"]}
    assert client.post("/kill/clear").json() == {"killed": False, "at": None}
    assert not (root / "KILL").exists() and client.get("/kill").json()["killed"] is False
    assert client.post("/kill/clear").json()["killed"] is False                                    # clearing twice is fine


# ------------------------------------------------------------------ run evidence
def test_run_evidence_served_safely(fresh):
    client, root = fresh
    run = root / "runs" / "r_01"
    run.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    (run / "s3.png").write_bytes(png)
    (run / "evidence.json").write_text('{"ok": true}')
    (run / "notes.txt").write_text("secret")
    (run / ".hidden.png").write_bytes(png)
    outside = root / "outside.png"
    outside.write_bytes(png)
    (run / "link.png").symlink_to(outside)
    (root / "runs" / "linked").symlink_to(run, target_is_directory=True)
    r = client.get("/runs/r_01/s3.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == png
    assert client.get("/runs/r_01/evidence.json").json() == {"ok": True}
    for run_id, file in (("r_01", "notes.txt"), ("r_01", ".hidden.png"), ("r_01", "link.png"), ("linked", "s3.png"), ("r_01", "missing.png"),
                         ("r_99", "s3.png"), ("..", "outside.png"), ("r_01", "..%2Foutside.png"), ("r_01%2F..", "s3.png"), ("r_01", "s3.png%00.png"),
                         ("r_01", "s3.PNG"), ("r_01", "s3.png.exe")):
        assert client.get(f"/runs/{run_id}/{file}").status_code == 404, (run_id, file)
    assert client.get("/runs/r_01/").status_code in (404, 405)


# ------------------------------------------------------------------ eval report
def test_eval_report_404_then_served(fresh, monkeypatch, tmp_path):
    client, _ = fresh
    monkeypatch.setenv("UNDERSTUDY_EVAL_REPORT", str(tmp_path / "evals" / "report.json"))
    assert_error(client.get("/eval/report"), 404, "no_report")
    (tmp_path / "evals").mkdir()
    doc = {"generated_at": "2026-11-07T14:00:00Z", "mock": True, "sections": {"limitations": [{"id": "l1", "text": "n = 4", "severity": "high"}]}}
    (tmp_path / "evals" / "report.json").write_text(json.dumps(doc))
    assert client.get("/eval/report").json() == doc
    (tmp_path / "evals" / "report.json").write_text("{broken")
    assert_error(client.get("/eval/report"), 500, "bad_report")


# ------------------------------------------------------------------ E3: conformance, warm-up, speed, concurrency
OWNED = {
    ("get", "/health"), ("post", "/events"), ("get", "/events"), ("get", "/replay"), ("get", "/packs"), ("get", "/genome/{task}"),
    ("get", "/graph/transitions"), ("get", "/queue"), ("post", "/queue/{item_id}/approve"), ("post", "/queue/{item_id}/reject"),
    ("get", "/audit"), ("get", "/kill"), ("post", "/kill"), ("post", "/kill/clear"), ("get", "/eval/report"), ("get", "/runs/{run_id}/{file}"),
}


def test_every_owned_endpoint_is_in_the_openapi_document(client):
    paths = client.get("/openapi.json").json()["paths"]
    have = {(m, p) for p, ops in paths.items() for m in ops}
    assert OWNED <= have, OWNED - have


def test_every_owned_endpoint_in_the_contract_table_exists(client):
    """The contract table is the source of truth: each engine-data row must be routable (not 404/405 for the route itself)."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[4] / "docs" / "API_CONTRACT.md").read_text()
    mine = ["/health", "/events", "/replay", "/packs", "/genome/", "/graph/transitions", "/queue", "/audit", "/kill", "/eval/report"]
    for needle in mine:
        assert f"`GET {needle}" in doc or f"`POST {needle}" in doc or f"{needle}" in doc, needle
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {"/health", "/events", "/replay", "/packs", "/genome/{task}", "/graph/transitions", "/queue", "/audit", "/kill", "/eval/report"} <= paths


def test_health_lists_routers_and_warm_state(client):
    h = client.get("/health").json()
    assert set(h["routers"]) == {"data", "analytics", "handoff"} and h["routers"]["data"] is True
    assert all(isinstance(v, bool) for v in h["routers"].values()) and isinstance(h["warm"], dict)


def test_warm_up_fills_the_genome_cache(env):
    import time

    from fastapi.testclient import TestClient

    from understudy_engine.api.app import create_app

    app = create_app(env, warm=True)
    with TestClient(app) as c:
        t0 = time.time()
        while "seconds" not in app.state.warm and time.time() - t0 < 60:
            time.sleep(0.1)
        assert app.state.warm.get("genome") is True
        t = time.time()
        assert c.get("/genome/benefits").status_code == 200
        assert time.time() - t < 0.5                                   # served from the warm cache
        assert c.get("/health").json()["warm"]["genome"] is True


def test_warm_up_without_data_is_harmless(fresh):
    import time

    from fastapi.testclient import TestClient

    from understudy_engine.api.app import create_app

    _, root = fresh
    app = create_app(root, warm=True)
    with TestClient(app):
        t0 = time.time()
        while "seconds" not in app.state.warm and time.time() - t0 < 30:
            time.sleep(0.1)
        assert app.state.warm.get("genome") is False


def test_replay_of_a_21_day_persona_is_fast(client):
    import time

    t = time.time()
    r = client.get("/replay?person=p_irregular&speed=200&limit=4000")
    assert r.status_code == 200 and r.json()["total_frames"] > 10000
    assert time.time() - t < 2.0


def test_concurrent_decisions_have_exactly_one_winner(fresh):
    import threading

    from understudy_engine.api import files
    from understudy_engine.api.errors import ApiError

    _, root = fresh
    item = _enqueue(root)
    results = []

    def go(action):
        try:
            results.append(files.queue_decide(item["id"], action, None)["status"])
        except ApiError as exc:
            results.append(exc.code)

    threads = [threading.Thread(target=go, args=(a,)) for a in ("approve", "reject", "approve", "reject", "approve")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results).count("already_decided") == 4 and len([r for r in results if r in ("approved", "rejected")]) == 1
    assert not list((root / "queue").glob("*.tmp")) and AuditLog().verify_chain() is True
    assert len([r for r in AuditLog().read(100) if r["kind"] == "queue_decided"]) == 1


def test_kill_writes_are_atomic_and_idempotent(fresh):
    client, root = fresh
    for _ in range(3):
        assert client.post("/kill").json()["killed"] is True
    assert (root / "KILL").read_text().splitlines()[0] and not list(root.glob("KILL*.tmp")) and not list(root.glob("*.tmp"))
    for _ in range(2):
        client.post("/kill/clear")
    assert not list(root.glob("KILL*"))


def test_mock_mode_answers_every_get_without_a_network(client, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    for path in ("/health", "/packs", "/events?partition=synthetic&limit=5", "/replay?person=p_nov02&task=t_nov02a", "/genome/benefits",
                 "/graph/transitions", "/queue", "/audit", "/kill"):
        assert client.get(path).status_code == 200, path
    assert client.get("/eval/report").status_code in (200, 404)
