"""HTTP routes (docs/API_CONTRACT.md Extensions API, BGA): flag-gated, worker-only writes, the contract's shapes."""
from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_agent.runtime import routes
from understudy_agent.runtime.sandbox import sandbox_available
from understudy_agent.security.killflag import clear_kill, set_kill

from .helpers import register_test_kinds, wait_for

pytestmark = pytest.mark.skipif(not sandbox_available(), reason="needs macOS sandbox-exec")
W = {"X-Understudy-Actor": "worker"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_AGENTS", "1")
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_everything_is_off_without_the_flag(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_AGENTS", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    for r in (c.get("/agents/runs"), c.get("/agents/kinds"), c.post("/agents/spawn", json={"kind": "data.profile"}, headers=W)):
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_disabled"
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert c.get("/agents/runs").status_code == 200


def test_spawn_list_get_follow_the_contract(client):
    assert client.get("/agents/runs").json() == []
    r = client.post("/agents/spawn", json={"kind": "data.profile", "params": {}, "mode": "foreground"}, headers=W)
    assert r.status_code == 200
    rid = r.json()["run_id"]
    assert wait_for(lambda: client.get(f"/agents/runs/{rid}").json()["state"] in ("done", "failed", "partial"), 60)
    one = client.get(f"/agents/runs/{rid}").json()
    assert one["state"] == "done" and one["kind"] == "data.profile" and one["mode"] == "foreground"
    assert set(one["parent"]) == {"id", "role", "state", "budget", "spent"}
    child = one["children"][0]
    assert {"id", "role", "state", "budget", "spent", "lease", "result_ref"} <= set(child)
    assert {"ttl_s", "remaining_s", "steps_left", "tools", "revoked"} <= set(child["lease"])
    assert one["artifacts"] and {"name", "kind", "path_ref"} <= set(one["artifacts"][0])
    assert one["result"]["all_verified"] is True
    assert all(s["check"] in ("verified", "uncertain", "failed") for s in one["result"]["children"]["c1"]["steps"])
    lst = client.get("/agents/runs").json()
    assert [x["run_id"] for x in lst] == [rid] and "artifacts" not in lst[0]
    art = client.get(f"/agents/runs/{rid}/artifacts/c1/profile.json")
    assert art.status_code == 200 and art.json()["n_rows"] == 240
    assert client.get(f"/agents/runs/{rid}/artifacts/c1/..%2Fx").status_code == 404
    assert client.get(f"/agents/runs/{rid}/artifacts/c9/profile.json").status_code == 404


def test_writes_need_the_worker_actor(client):
    body = {"kind": "data.profile"}
    for actor in ("agent", "page", "model", "tool"):
        r = client.post("/agents/spawn", json=body, headers={"X-Understudy-Actor": actor})
        assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    assert client.post("/agents/spawn", json=body, headers={"Origin": "https://evil.example", "X-Understudy-Actor": "worker", **{"Content-Type": "application/json"}}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/stop", headers={"X-Understudy-Actor": "page"}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/children/c1/revoke", headers={"X-Understudy-Actor": "model"}).status_code == 403


def test_bad_requests_get_plain_errors(client):
    assert client.post("/agents/spawn", json={"kind": "nope"}, headers=W).json()["error"]["code"] == "unknown_kind"
    assert client.post("/agents/spawn", json={"kind": "data.profile", "mode": "x"}, headers=W).status_code == 422
    assert client.post("/agents/spawn", json={"kind": "data.profile", "params": 5}, headers=W).status_code == 422
    assert client.post("/agents/spawn", content=b"not json", headers={**W, "Content-Type": "application/json"}).status_code == 422
    assert client.post("/agents/spawn", content=b'{"kind": "data.profile"}', headers={"Origin": "http://localhost:5173", **W}).status_code == 415
    assert client.post("/agents/spawn", json={"kind": "data.profile", "params": {"csv_path": "/nonexistent.csv"}},
                       headers=W).status_code in (200, 422)
    assert client.get("/agents/runs/r_nothere00").status_code == 404
    assert client.post("/agents/runs/r_nothere00/stop", headers=W).status_code == 404
    assert client.get("/agents/runs/..%2F..%2Fetc").status_code in (404, 422)


def test_spawn_refuses_while_the_kill_switch_is_set(client):
    set_kill("test")
    try:
        r = client.post("/agents/spawn", json={"kind": "data.profile"}, headers=W)
    finally:
        clear_kill()
    assert r.status_code == 423


def test_stop_and_revoke_endpoints_work_on_a_running_child(client):
    register_test_kinds()
    rid = client.post("/agents/spawn", json={"kind": "test.nap", "params": {"template": "nap_long"}}, headers=W).json()["run_id"]
    assert wait_for(lambda: (d := client.get(f"/agents/runs/{rid}").json()) and d["children"]
                    and d["children"][0]["spent"]["steps"] >= 1, 20)
    time.sleep(0.4)
    assert client.post(f"/agents/runs/{rid}/children/c9/revoke", headers=W).status_code == 404
    t0 = time.monotonic()
    assert client.post(f"/agents/runs/{rid}/children/c1/revoke", headers=W).json() == {"revoked": True, "child_id": "c1"}
    assert wait_for(lambda: client.get(f"/agents/runs/{rid}").json()["state"] not in ("running", "planning"), 2)
    assert time.monotonic() - t0 < 2
    child = client.get(f"/agents/runs/{rid}").json()["children"][0]
    assert child["state"] == "revoked" and child["lease"]["revoked"] is True
    rid2 = client.post("/agents/spawn", json={"kind": "test.nap", "params": {"template": "nap_long"}}, headers=W).json()["run_id"]
    assert wait_for(lambda: (d := client.get(f"/agents/runs/{rid2}").json()) and d["children"] and d["children"][0]["spent"]["steps"] >= 1, 20)
    t0 = time.monotonic()
    out = client.post(f"/agents/runs/{rid2}/stop", headers=W).json()
    assert out["stopped"] is True
    assert wait_for(lambda: client.get(f"/agents/runs/{rid2}").json()["state"] == "stopped", 1.0)
    assert time.monotonic() - t0 < 1.0


# ---------------------------------------------------------------------------------------------- the write guard (REVIEW-PRIVACY P3)
# The shared guard (understudy_engine.http_guard) decides Origin, content type, Host, actor and token; the routes call it on every write.
HOSTILE_ORIGINS = ["http://localhost.evil.example", "http://127.0.0.1.evil.example", "https://localhost.evil.example", "null",
                   "http://evil.example", "http://localhost:8080", "http://localhost:5173.evil.example", "http://localhost:5173@evil.example",
                   "http://user:pw@localhost:5173", "ftp://localhost:5173", "http://localhost", "http://[::1]:9999", "HTTP://LOCALHOST.EVIL.EXAMPLE",
                   "http://localhost:5173/", "http://LOCALHOST:5173"]
GOOD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
JSON = {"Content-Type": "application/json"}
WORKER = {"X-Understudy-Actor": "worker"}


@pytest.mark.parametrize("origin", HOSTILE_ORIGINS)
def test_a_hostile_or_prefix_origin_never_writes(client, origin):
    body = json.dumps({"kind": "data.profile", "mode": "foreground", "params": {}})
    for headers in ({"Origin": origin, **JSON}, {"Origin": origin, **WORKER, **JSON}):
        r = client.post("/agents/spawn", content=body, headers=headers)
        assert r.status_code == 403 and r.json()["error"]["code"] == "origin_refused", (origin, headers, r.text)
    assert client.post("/agents/runs/r_abcdef12/stop", headers={"Origin": origin, **WORKER, **JSON}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/resume", headers={"Origin": origin, **WORKER, **JSON}).status_code == 403
    assert client.post("/agents/runs/r_abcdef12/children/c1/revoke", headers={"Origin": origin, **WORKER, **JSON}).status_code == 403
    assert client.get("/agents/runs").json() == []                       # nothing started


def test_the_reproducer_a_text_plain_cross_site_post_with_raw_ok_is_refused(client):
    r = client.post("/agents/spawn", content=json.dumps({"kind": "data.profile", "mode": "foreground", "params": {"raw_ok": True}}),
                    headers={"Origin": "http://localhost.evil.example", "Content-Type": "text/plain;charset=UTF-8"})
    assert r.status_code == 403
    assert client.get("/agents/runs").json() == []


@pytest.mark.parametrize("ctype", ["text/plain", "text/plain;charset=UTF-8", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", ""])
def test_a_body_that_is_not_json_is_refused_even_from_a_good_origin(client, ctype):
    headers = {"Origin": "http://localhost:5173", **WORKER}
    if ctype:
        headers["Content-Type"] = ctype
    r = client.post("/agents/spawn", content=json.dumps({"kind": "data.profile"}), headers=headers)
    assert r.status_code == 415 and r.json()["error"]["code"] == "json_required"
    assert client.get("/agents/runs").json() == []


@pytest.mark.parametrize("origin", GOOD_ORIGINS)
def test_the_workers_own_dashboard_can_write_with_the_explicit_header_and_json(client, origin):
    r = client.post("/agents/spawn", content=json.dumps({"kind": "data.profile", "mode": "foreground"}),
                    headers={"Origin": origin, **WORKER, **JSON})
    assert r.status_code == 200, r.text
    client.post(f"/agents/runs/{r.json()['run_id']}/stop", headers={"Origin": origin, **WORKER, **JSON})


def test_the_allow_list_can_be_extended_only_with_canonical_origins(client, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_ALLOWED_ORIGINS", "app://understudy,http://localhost:9000/evil,HTTP://X.EXAMPLE")
    ok = {"Origin": "app://understudy", **WORKER, **JSON}
    r = client.post("/agents/spawn", json={"kind": "data.profile"}, headers=ok)
    assert r.status_code == 200
    client.post(f"/agents/runs/{r.json()['run_id']}/stop", headers=ok)
    for bad in ("http://localhost:9000", "http://x.example", "http://localhost:9000/evil"):
        assert client.post("/agents/spawn", json={"kind": "data.profile"}, headers={"Origin": bad, **WORKER}).status_code == 403


def test_a_browser_write_without_the_explicit_actor_header_is_refused(client):
    r = client.post("/agents/spawn", content=json.dumps({"kind": "data.profile"}), headers={"Origin": "http://localhost:5173", **JSON})
    assert r.status_code == 403 and r.json()["error"]["code"] == "actor_required"
    assert client.post("/agents/runs/r_abcdef12/stop", headers={"Origin": "http://localhost:5173", **JSON}).status_code == 403


def test_a_non_browser_local_client_needs_no_origin_and_no_actor_header_under_test_but_never_names_another_actor(client):
    r = client.post("/agents/spawn", json={"kind": "data.profile"})        # no Origin: curl, the engine, the app's main process
    assert r.status_code == 200
    client.post(f"/agents/runs/{r.json()['run_id']}/stop")
    assert client.post("/agents/spawn", json={"kind": "data.profile"}, headers={"X-Understudy-Actor": "model"}).status_code == 403


def test_cross_site_fetch_metadata_and_a_foreign_host_header_are_refused(client):
    base = {**WORKER, **JSON}
    assert client.post("/agents/spawn", json={"kind": "data.profile"}, headers={**base, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    r = client.post("/agents/spawn", json={"kind": "data.profile"}, headers={**base, "Host": "rebind.evil.example"})
    assert r.status_code == 421 and r.json()["error"]["code"] == "host_refused"
    ok = client.post("/agents/spawn", json={"kind": "data.profile"}, headers={**base, "Host": "localhost:7710", "Sec-Fetch-Site": "same-site"})
    assert ok.status_code == 200
    client.post(f"/agents/runs/{ok.json()['run_id']}/stop", headers=base)


def test_raw_ok_needs_a_top_level_flag_the_explicit_header_a_foreground_run_and_a_file_the_worker_named(client, tmp_path):
    from understudy_agent.runtime.exemplars.data import make_sales_csv

    csv = tmp_path / "d.csv"
    make_sales_csv(csv)
    worker = {**WORKER, **JSON}
    r = client.post("/agents/spawn", json={"kind": "data.profile", "params": {"csv_path": str(csv), "raw_ok": True}}, headers=worker)
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_params"                     # inside params: refused outright
    r = client.post("/agents/spawn", json={"kind": "data.profile", "raw_ok": True}, headers=worker)
    assert r.status_code == 422 and r.json()["error"]["code"] == "raw_not_allowed"                # no named file
    r = client.post("/agents/spawn", json={"kind": "data.profile", "raw_ok": True, "params": {"csv_path": str(csv)}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "raw_not_allowed"                # no explicit worker header
    r = client.post("/agents/spawn", json={"kind": "data.profile", "raw_ok": True, "mode": "nightly", "params": {"csv_path": str(csv)}}, headers=worker)
    assert r.status_code == 422 and r.json()["error"]["code"] == "raw_not_allowed"                # not foreground
    r = client.post("/agents/spawn", json={"kind": "data.profile", "raw_ok": True, "params": {"csv_path": str(csv)}}, headers=worker)
    assert r.status_code == 200, r.text
    from understudy_agent.runtime.run import get_run

    assert get_run(r.json()["run_id"]).raw_ok is True
    client.post(f"/agents/runs/{r.json()['run_id']}/stop", headers=worker)


@pytest.fixture
def strict(client, monkeypatch):
    """Production behaviour of the guard: JSON, an explicit actor, the real Host, and the per-boot token for release actions."""
    from understudy_engine import http_guard as hg

    monkeypatch.setenv("UNDERSTUDY_GUARD_STRICT", "1")
    token = hg.ensure_token()
    app = FastAPI()
    app.include_router(routes.router)
    loopback = TestClient(app, client=("127.0.0.1", 50000))              # a local client, as a real server would see it
    base = {"Host": "127.0.0.1:7710", **WORKER, **JSON}
    return loopback, base, {**base, "X-Understudy-Token": token}


def test_in_production_mode_a_caller_with_no_origin_must_still_send_json_and_the_actor(strict):
    c, base, tok = strict
    assert c.post("/agents/spawn", content=json.dumps({"kind": "data.profile"}), headers={"Host": "127.0.0.1:7710"}).status_code == 415
    assert c.post("/agents/spawn", content=json.dumps({"kind": "data.profile"}), headers={"Host": "127.0.0.1:7710", **WORKER}).status_code == 415
    r = c.post("/agents/spawn", json={"kind": "data.profile"}, headers=base)
    assert r.status_code == 200
    c.post(f"/agents/runs/{r.json()['run_id']}/stop", headers=base)               # stopping never needs the token


def test_resume_and_raw_ok_are_release_actions_and_need_the_per_boot_token(strict, tmp_path):
    from understudy_agent.runtime.exemplars.data import make_sales_csv

    c, base, tok = strict
    r = c.post("/agents/runs/r_abcdef12/resume", headers=base)
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_required"
    r = c.post("/agents/runs/r_abcdef12/resume", headers={**base, "X-Understudy-Token": "0" * 64})
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_invalid"
    assert c.post("/agents/runs/r_abcdef12/resume", headers=tok).status_code == 404                # past the guard: no such run
    csv = tmp_path / "d.csv"
    make_sales_csv(csv)
    body = {"kind": "data.profile", "raw_ok": True, "params": {"csv_path": str(csv)}}
    r = c.post("/agents/spawn", json=body, headers=base)
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_required"                 # file text to a model needs the token
    r = c.post("/agents/spawn", json=body, headers=tok)
    assert r.status_code == 200
    c.post(f"/agents/runs/{r.json()['run_id']}/stop", headers=base)


def test_a_browser_origin_cannot_use_the_token_it_cannot_read(strict):
    """A page on the dashboard origin could send the header, but a page on any other origin is refused before the token matters."""
    c, base, tok = strict
    for origin in HOSTILE_ORIGINS[:4]:
        r = c.post("/agents/runs/r_abcdef12/resume", headers={**tok, "Origin": origin})
        assert r.status_code == 403 and r.json()["error"]["code"] == "origin_refused"
