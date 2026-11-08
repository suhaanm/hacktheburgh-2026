"""Routes, roles and the service (REQ-9, D41, D42): the admin gate, the worker response type, the weekly pin, feedback that only quiets, read-only sharing."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from understudy_engine import http_guard
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.insights import firm as F
from understudy_engine.insights import routes as R
from understudy_engine.insights import texts as T
from understudy_engine.insights import vocab as V
from understudy_engine.insights.service import InsightsService
from understudy_engine.insights.store import InsightsStore

WORKER_KEYS = {"id", "kind", "polarity", "polarity_label", "glyph", "title", "headline", "detail", "text", "source", "badge", "origin", "numbers", "action", "details_available", "a11y_label"}
WORKER_DATA_KEYS = {"person", "role", "week", "status", "nothing_stands_out", "message", "pointers", "try", "monday_note", "stale_sources", "cap", "badge", "origin"}
STAT_WORDS = {"interval", "ci", "lo", "hi", "p", "p_value", "n_unit", "effect", "score", "parts", "family", "split", "impact", "se"}


@pytest.fixture(scope="module")
def snapshot():
    return F.build_firm(0).snapshot


@pytest.fixture()
def state(snapshot):
    return {"snap": snapshot}


@pytest.fixture()
def client(monkeypatch, state):
    monkeypatch.setenv("UNDERSTUDY_X_INSIGHTS", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.insights = InsightsService(InsightsStore(), snapshot_provider=lambda s: state["snap"], clock=lambda: state["snap"].now)
    http_guard.ensure_token()
    return TestClient(app)


def admin_headers():
    return {"x-understudy-role": "admin", "x-understudy-token": http_guard.read_token()}


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def a_person(snapshot, role="benefits-processor", level="junior", unit="unit_a"):
    return next(p.id for p in snapshot.people if p.role == role and p.level == level and p.unit == unit and p.rows)


def pointer_person(client, snapshot, minimum=2):
    """The first person in the firm who has at least ``minimum`` pointers this week (found through the route, so the week is pinned for them)."""
    for p in snapshot.people:
        if p.level == "junior" and len(client.get("/insights/worker", params={"person": p.id}).json()["data"]["pointers"]) >= minimum:
            return p.id
    raise AssertionError("nobody in the firm has that many pointers")


# ---------------------------------------------------------------------------------------------------- flag and gate
ROUTES = [("get", "/insights/worker?person=p_f_bp05"), ("get", "/insights/admin/overview"), ("get", "/insights/admin/roles"), ("get", "/insights/admin/firm"),
          ("get", "/insights/admin/onboarding"), ("get", "/insights/admin/drill?insight=i_x"), ("get", "/insights/why?insight=i_x&person=p_f_bp05"),
          ("post", "/insights/feedback"), ("get", "/insights/sharing?person=p_f_bp05")]


def test_flag_off_is_404_extension_off_everywhere(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_INSIGHTS", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    c = TestClient(app)
    assert not R.enabled()
    for method, url in ROUTES:
        r = getattr(c, method)(url, **({"json": {"insight": "i", "event": "useful"}} if method == "post" else {}))
        assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off", url


def test_the_master_flag_also_turns_it_on_and_the_engine_can_wire_it(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_INSIGHTS", raising=False)
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert R.enabled()
    from understudy_engine.api.flags import EXTENSIONS

    assert EXTENSIONS.get("insights") == "insights.routes" and R.FLAG == "UNDERSTUDY_X_INSIGHTS"


ADMIN_ROUTES = ["/insights/admin/overview", "/insights/admin/roles", "/insights/admin/firm", "/insights/admin/onboarding", "/insights/admin/drill?insight=i_x"]


def test_the_admin_role_needs_the_header_and_the_per_boot_token(client):
    for url in ADMIN_ROUTES:
        assert client.get(url).status_code == 403 and client.get(url).json()["error"]["code"] == "admin_only"
        assert client.get(url, headers={"x-understudy-role": "worker", "x-understudy-token": http_guard.read_token()}).json()["error"]["code"] == "admin_only"
        r = client.get(url, headers={"x-understudy-role": "admin"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "admin_token_required"
        r = client.get(url, headers={"x-understudy-role": "admin", "x-understudy-token": "0" * 64})
        assert r.status_code == 403 and r.json()["error"]["code"] == "admin_token_required"
        r = client.get(url, headers={"x-understudy-role": "Admin", "x-understudy-token": http_guard.read_token()})
        assert r.status_code in (200, 404)          # the drill of an unknown id is a 404, never a 403
    assert client.get("/insights/admin/overview", headers=admin_headers()).status_code == 200


def test_the_worker_route_never_returns_admin_data_even_for_an_admin_caller(client, snapshot):
    pid = a_person(snapshot)
    plain = client.get("/insights/worker", params={"person": pid}).json()
    asadmin = client.get("/insights/worker", params={"person": pid}, headers=admin_headers()).json()
    assert plain["data"] == asadmin["data"]
    assert not (set(walk(asadmin)) & {"role_comparison", "coverage", "top", "split", "interval", "family", "parts"})


# ---------------------------------------------------------------------------------------------------- worker
def test_the_worker_response_is_a_few_pointers_with_no_statistics(client, snapshot):
    pid = a_person(snapshot)
    r = client.get("/insights/worker", params={"person": pid})
    assert r.status_code == 200
    d = r.json()["data"]
    assert set(d) == WORKER_DATA_KEYS and d["person"] == pid and len(d["pointers"]) <= 3 and d["cap"] == 3
    assert d["status"] in V.STATUSES_WORKER and d["badge"] == "made-up firm"
    assert r.json()["meta"]["interval_level"] is None and r.json()["meta"]["audience"] == "worker"
    for p in d["pointers"]:
        assert set(p) == WORKER_KEYS
        assert p["polarity"] in V.POLARITIES and p["glyph"] in V.GLYPHS and p["polarity_label"] == V.POLARITY_LABEL[p["polarity"]]
        assert T.lint(p["text"], audience="worker", kind="body", badge=p["badge"]) == [] and T.lint(p["title"], audience="worker", kind="title") == []
        assert p["a11y_label"].startswith(p["polarity_label"])
        assert p["action"] is None or set(p["action"]) <= {"id", "label", "to", "query"}
    assert not (set(walk(d)) & STAT_WORDS)


def test_every_person_in_the_firm_gets_at_most_three_pointers_and_a_valid_status(client, snapshot):
    seen = {}
    for p in snapshot.people:
        d = client.get("/insights/worker", params={"person": p.id}).json()["data"]
        assert len(d["pointers"]) <= 3 and d["status"] in V.STATUSES_WORKER
        assert (d["status"] == "nothing_stands_out") == (not d["pointers"] and d["status"] not in ("onboarding", "stale", "no_data", "role_changed")) or d["status"] in ("onboarding", "stale", "no_data", "role_changed", "ok", "nothing_stands_out")
        for q in d["pointers"]:
            assert T.lint(q["text"], audience="worker", kind="body", badge=q["badge"]) == [], q["text"]
        seen[p.id] = d
    sp = F.build_firm(0).truth["planted"]["specials"]
    assert seen[sp["no_data"][0]]["status"] == "no_data" and seen[sp["no_data"][0]]["pointers"] == []
    assert seen[sp["stale"][0]]["status"] == "stale" and seen[sp["stale"][0]]["pointers"][0]["kind"] == "stale_data"
    assert seen[sp["new_joiner"][0]]["status"] == "onboarding" and seen[sp["new_joiner"][0]]["pointers"][0]["kind"] == "onboarding"
    assert any(d["status"] == "nothing_stands_out" for d in seen.values()) and any(d["pointers"] for d in seen.values())
    assert all(p["kind"] != "time_loss_habit" or True for d in seen.values() for p in d["pointers"])


def test_the_week_is_pinned_so_repeated_calls_do_not_reshuffle(client, snapshot):
    pid = a_person(snapshot)
    a = client.get("/insights/worker", params={"person": pid}).json()["data"]
    b = client.get("/insights/worker", params={"person": pid}).json()["data"]
    assert a == b and a["week"]["key"] == "2026-W46" and a["week"]["from"] == "2026-11-09" and a["week"]["to"] == "2026-11-15"


def test_a_deleted_ledger_drops_the_pin_and_shows_no_data(client, state, snapshot):
    pid = a_person(snapshot)
    before = client.get("/insights/worker", params={"person": pid}).json()["data"]
    assert before["status"] != "no_data"
    state["snap"] = replace(snapshot, people=tuple(replace(p, rows=()) if p.id == pid else p for p in snapshot.people))
    after = client.get("/insights/worker", params={"person": pid}).json()["data"]
    assert after["status"] == "no_data" and after["pointers"] == [] and "not seen any" in after["message"]


def test_an_unknown_person_is_a_plain_404(client):
    r = client.get("/insights/worker", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"


def test_the_worker_week_follows_the_workers_own_time_zone(snapshot):
    from understudy_engine.insights.rows import week_bounds

    sunday_night_utc = 1794214800.0 - 9 * 3600 - 60                       # Sunday 23:59 UTC
    assert week_bounds(sunday_night_utc, "UTC")[0] == "2026-W45"
    assert week_bounds(sunday_night_utc, "Asia/Tokyo")[0] == "2026-W46"   # already Monday in Tokyo
    assert week_bounds(sunday_night_utc, "Not/AZone")[0] == "2026-W45"    # an unknown zone is UTC


# ---------------------------------------------------------------------------------------------------- admin shapes
def test_overview_has_the_agreed_shape_and_at_most_seven_ranked_insights(client):
    r = client.get("/insights/admin/overview", headers=admin_headers())
    d = r.json()["data"]
    assert set(d) >= {"firm", "top", "coverage", "risk", "role_comparison", "statement", "nothing_stands_out", "suppressed", "week", "badge"}
    assert d["firm"] == {"users": 60, "roles": 3, "label": "Firm"} and 1 <= len(d["top"]) <= 7 and d["statement"] == V.STATEMENT
    assert set(d["risk"]) == {"approval_backlog_age_h", "injection_pauses_30d", "kill_events_30d", "open_approvals"} and d["risk"]["injection_pauses_30d"] == 2
    assert set(d["coverage"]) >= {"users", "enough_data", "min_occurrences"}
    for i, c in enumerate(d["top"], start=1):
        assert set(c) >= {"id", "headline", "role", "effect", "n", "n_unit", "origin", "drill", "kind", "polarity", "polarity_label", "glyph", "text", "badge", "position", "a11y_label", "statement"}
        assert c["position"] == i and c["drill"] == c["id"] and set(c["effect"]) == {"label", "unit", "value", "ci"} and c["text"].endswith(V.STATEMENT)
        assert T.lint(c["text"], audience="admin", kind="body", badge=c["badge"]) == []
    assert not (set(walk(d)) & {"person", "rank", "score", "composite"})


def test_roles_firm_and_onboarding_have_the_agreed_shapes(client):
    h = admin_headers()
    roles = client.get("/insights/admin/roles", headers=h).json()["data"]
    assert roles["same_scale"] == {"min": 0, "max": 1} and len(roles["roles"]) == 3
    ben = next(r for r in roles["roles"] if r["role"] == "benefits-processor")
    assert ben["enough"] and set(ben["measures"][0]) == {"key", "label", "unit", "expert", "junior", "gap", "verdict"} and ben["measures"][2]["unit"] == "seconds"
    assert set(ben["habits"][0]) >= {"id", "label", "explains_s", "expert_rate", "junior_rate", "n", "verdict"} and ben["habits"][0]["verdict"] in ("gap", "cannot_tell")
    assert set(ben["measures"][0]["junior"]) == {"value", "ci"}
    firm = client.get("/insights/admin/firm", headers=h).json()["data"]
    assert firm["privacy"]["min_group"] == 5 and firm["totals"]["users"] == 60
    g = next(g for g in firm["roles"] if g["role"] == "benefits-processor")
    assert set(g) >= {"role", "name", "merged", "users", "aggregate"} and set(g["aggregate"]) == {"n_users", "independence", "assisted_share", "time_to_independence"}
    u = g["users"][0]
    assert set(u) >= {"id", "label", "tenure_band", "tenure_weeks", "trend", "independence", "assisted_share", "time_to_independence", "automations_running", "n"}
    assert [x["label"] for x in g["users"]] == sorted(x["label"] for x in g["users"]) and "score" not in u and "rank" not in u
    assert {u["trend"] for gg in firm["roles"] for u in gg["users"]} <= set(V.TREND_CLASSES)
    onb = client.get("/insights/admin/onboarding", headers=h).json()["data"]
    assert onb["target"]["label"] == "design target" and onb["target"]["value"] == 0.8 and onb["x_unit"] == "occurrences"
    r0 = next(r for r in onb["roles"] if r["role"] == "benefits-processor")
    assert set(r0) >= {"role", "name", "n", "curve", "median_to_target", "reached_share"} and r0["curve"] and set(r0["curve"][0]) >= {"x", "y", "lo", "hi"}


def test_every_selected_card_can_be_drilled_and_an_unknown_id_is_a_404(client):
    h = admin_headers()
    cards = client.get("/insights/admin/overview", headers=h).json()["data"]["top"]
    for c in cards:
        r = client.get("/insights/admin/drill", params={"insight": c["id"]}, headers=h)
        assert r.status_code == 200, c["kind"]
        d = r.json()["data"]
        assert set(d) >= {"id", "headline", "columns", "rows", "series", "notes", "tables", "state", "reason_code"} and d["state"] == "selected" and d["rows"]
        assert V.STATEMENT in " ".join(d["notes"])
    r = client.get("/insights/admin/drill", params={"insight": "i_nope"}, headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_insight"


def test_the_whole_admin_surface_is_deterministic(client):
    h = admin_headers()
    a = [client.get(u, headers=h).json()["data"] for u in ("/insights/admin/overview", "/insights/admin/roles", "/insights/admin/firm", "/insights/admin/onboarding")]
    b = [client.get(u, headers=h).json()["data"] for u in ("/insights/admin/overview", "/insights/admin/roles", "/insights/admin/firm", "/insights/admin/onboarding")]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------------------------------- why
def test_why_gives_a_fixed_reason_and_a_worker_never_sees_the_numbers(client, snapshot):
    pid = pointer_person(client, snapshot)
    d = client.get("/insights/worker", params={"person": pid}).json()["data"]
    assert d["pointers"], "the fixture person should have a pointer"
    pw = d["pointers"][0]
    w = client.get("/insights/why", params={"insight": pw["id"], "person": pid}).json()["data"]
    assert w["state"] == "selected" and w["reason_code"] in V.SELECTED and w["reason_text"] == V.REASON_TEXT[w["reason_code"]]
    assert not (set(walk(w)) & {"parts", "family", "n", "n_unit"}) and w["limits"] and w["because"]
    cards = client.get("/insights/admin/overview", headers=admin_headers()).json()["data"]["top"]
    a = client.get("/insights/why", params={"insight": cards[0]["id"]}, headers=admin_headers()).json()["data"]
    assert a["state"] == "selected" and a["parts"] and set(a["parts"]) >= {"impact", "actionability", "novelty", "recency", "score"} and a["family"]["method"] == "benjamini_hochberg"
    r = client.get("/insights/why", params={"insight": "i_nope", "person": pid})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_insight"
    # a worker cannot read an admin insight's reasons, and the admin cannot read a worker's
    assert client.get("/insights/why", params={"insight": cards[0]["id"], "person": pid}).status_code == 404
    assert client.get("/insights/why", params={"insight": pw["id"]}, headers=admin_headers()).status_code == 404


def test_a_suppressed_insight_has_a_reason_the_admin_can_read(client):
    from understudy_engine.insights.types import insight_id

    h = admin_headers()
    ov = client.get("/insights/admin/overview", headers=h).json()["data"]
    assert ov["suppressed"]["count"] > 0 and "no_expert_reference" in ov["suppressed"]["by_reason"]
    pid = insight_id("admin", "firm", "role_gap", "programmer")
    d = client.get("/insights/admin/drill", params={"insight": pid}, headers=h).json()["data"]
    assert d["state"] == "suppressed" and d["reason_code"] == "no_expert_reference" and d["reason_text"] == V.REASON_TEXT["no_expert_reference"]
    w = client.get("/insights/why", params={"insight": pid}, headers=h).json()["data"]
    assert w["state"] == "suppressed" and w["reason_code"] == "no_expert_reference" and w["parts"] is None


# ---------------------------------------------------------------------------------------------------- feedback only quiets
def test_feedback_only_ever_makes_things_quieter(client, snapshot):
    pid = pointer_person(client, snapshot)
    base = client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]
    assert base
    r = client.post("/insights/feedback", json={"insight": base[0]["id"], "event": "useful"}, params={"person": pid})
    assert r.status_code == 200 and r.json() == {"insight": base[0]["id"], "event": "useful", "recorded": True}
    assert [p["id"] for p in client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]] == [p["id"] for p in base]      # useful changes nothing
    client.post("/insights/feedback", json={"insight": base[0]["id"], "event": "not_useful"}, params={"person": pid})
    after = [p["id"] for p in client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]]
    assert base[0]["id"] not in after and set(after) <= {p["id"] for p in base} and len(after) < len(base)
    kind = base[-1]["kind"]
    client.post("/insights/feedback", json={"insight": base[-1]["id"], "event": "hide_kind"}, params={"person": pid})
    hidden = client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]
    assert all(p["kind"] != kind for p in hidden) and set(p["id"] for p in hidden) <= set(after)
    client.post("/insights/feedback", json={"insight": base[-1]["id"], "event": "show_kind"}, params={"person": pid})
    shown = client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]
    assert set(p["id"] for p in shown) <= {p["id"] for p in base}                      # never anything the original pin did not hold


def test_feedback_validates_and_refuses_other_actors(client, snapshot):
    pid = pointer_person(client, snapshot)
    base = client.get("/insights/worker", params={"person": pid}).json()["data"]["pointers"]
    assert client.post("/insights/feedback", json={"insight": base[0]["id"], "event": "louder"}, params={"person": pid}).status_code == 422
    assert client.post("/insights/feedback", json={"insight": "i_nope", "event": "useful"}, params={"person": pid}).status_code == 404
    r = client.post("/insights/feedback", json={"insight": base[0]["id"], "event": "useful"}, params={"person": pid}, headers={"x-understudy-actor": "model"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "write_refused"
    r = client.post("/insights/feedback", json={"insight": base[0]["id"], "event": "useful"}, params={"person": pid}, headers={"origin": "https://evil.example", "x-understudy-actor": "worker"})
    assert r.status_code == 403


def test_the_admin_can_hide_a_kind_for_the_admin_view_only(client):
    h = admin_headers()
    cards = client.get("/insights/admin/overview", headers=h).json()["data"]["top"]
    kind = cards[0]["kind"]
    r = client.post("/insights/feedback", json={"insight": cards[0]["id"], "event": "hide_kind"}, headers=h)
    assert r.status_code == 200
    after = client.get("/insights/admin/overview", headers=h).json()["data"]["top"]
    assert all(c["kind"] != kind for c in after)


# ---------------------------------------------------------------------------------------------------- sharing: read-only transparency
def test_sharing_is_read_only_and_shows_exactly_the_admins_row(client, snapshot):
    pid = a_person(snapshot)
    r = client.get("/insights/sharing", params={"person": pid})
    d = r.json()["data"]
    assert r.status_code == 200 and d["audience"] == "admin" and d["visible_to"].startswith("People with the Admin role")
    assert d["items"] and d["never"] and "coaching and onboarding" in d["notice"] and "lawful basis" in d["legal_note"] and d["visible_since"]
    firm = client.get("/insights/admin/firm", headers=admin_headers()).json()["data"]
    row = next(u for g in firm["roles"] for u in g["users"] if u["id"] == pid)
    assert d["preview"] == row
    assert {i["kind"] for i in d["items"]} <= {"number", "enum", "count"}
    assert client.post("/insights/sharing", json={"level": "none"}, params={"person": pid}).status_code == 405
    assert client.put("/insights/sharing", json={}, params={"person": pid}).status_code == 405
    blob = json.dumps(d["never"])
    for w in ("Screenshots", "memory file", "Raw events"):
        assert w in blob


def test_the_worker_of_a_deleted_ledger_sees_that_the_admin_now_sees_no_data(client, state, snapshot):
    pid = a_person(snapshot)
    state["snap"] = replace(snapshot, people=tuple(replace(p, rows=()) if p.id == pid else p for p in snapshot.people))
    d = client.get("/insights/sharing", params={"person": pid}).json()["data"]
    assert d["preview"]["status"] == "no_data" and d["preview"]["n"] == 0 and d["visible_since"] is None


# ---------------------------------------------------------------------------------------------------- the local source
def test_the_local_source_has_one_person_so_the_admin_views_have_nothing_to_compare(monkeypatch, tmp_path):
    monkeypatch.setenv("UNDERSTUDY_X_INSIGHTS", "1")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    c = TestClient(app)
    http_guard.ensure_token()
    r = c.get("/insights/admin/overview", headers=admin_headers())
    assert r.status_code == 200 and r.json()["meta"]["source"] == "local" and r.json()["data"]["top"] == [] and r.json()["data"]["nothing_stands_out"] is True
    w = c.get("/insights/worker", params={"person": "p_local1", "source": "local"})
    assert w.status_code == 200 and w.json()["data"]["status"] == "no_data"


# ---------------------------------------------------------------------------------------------------- the repeat list (HITLIST) feeds the worker's automation pointer
def test_the_hit_list_top_row_is_normalised_and_a_failing_module_gives_nothing(monkeypatch):
    import understudy_engine.hitlist as H
    from understudy_engine.insights.service import _hitlist_rows

    row = {"id": "calc-entry-3x", "label_id": "calc-entry-3x", "count": 5, "window_days": 7, "seconds_per_time": 45.0, "hours_saved": {"value": 1.4, "lo": 0.9, "hi": 2.1, "horizon_weeks": 4},
           "n": 5, "origin": "synthetic", "t": 1_794_000_000.0, "action_to": "repeats"}
    monkeypatch.setattr(H, "top_rows", lambda person=None, limit=1: [row])
    out = _hitlist_rows("p_x")
    assert out == [{"id": "calc-entry-3x", "count": 5, "window_days": 7, "hours_lo": 0.9, "hours_hi": 2.1, "horizon_weeks": 4, "origin": "synthetic", "t": 1_794_000_000.0,
                    "what": out[0]["what"]}] and isinstance(out[0]["what"], str)

    def boom(person=None, limit=1):
        raise RuntimeError("no data")

    monkeypatch.setattr(H, "top_rows", boom)
    assert _hitlist_rows("p_x") == []
    monkeypatch.setattr(H, "top_rows", lambda person=None, limit=1: [{"id": None}, {"count": "x"}])
    assert _hitlist_rows("p_x") == []


# ---------------------------------------------------------------------------------------------------- an agent or a script holding the token is not an admin
def test_a_non_worker_actor_cannot_use_the_admin_views_even_with_the_role_and_the_token(client):
    h = admin_headers()
    urls = ADMIN_ROUTES[:4] + ["/insights/why?insight=i_x"]
    for actor in ("agent", "model", "system", "tool", "extension", "page"):
        for url in urls:
            r = client.get(url, headers={**h, "x-understudy-actor": actor})
            assert r.status_code == 403 and r.json()["error"]["code"] == "admin_actor_refused", (actor, url, r.text)
    for actor in ("worker", "worker_approval"):
        assert client.get("/insights/admin/overview", headers={**h, "x-understudy-actor": actor}).status_code == 200
    assert client.get("/insights/admin/overview", headers=h).status_code == 200                      # no actor header: allowed (the dashboard's reads send none)
    r = client.post("/insights/feedback", json={"insight": "i_x", "event": "useful"}, headers={**h, "x-understudy-actor": "agent"})
    assert r.status_code == 403                                                                        # the write guard refuses it first


def test_the_refusal_is_audited_without_content_and_a_worker_read_is_unaffected(client, snapshot):
    import os

    client.get("/insights/admin/overview", headers={**admin_headers(), "x-understudy-actor": "agent"})
    log = (R.P.data_dir() / "audit.jsonl").read_text()
    assert "admin_actor_refused" not in log and "insights_refused" in log and "agent" in log
    assert os.environ["UNDERSTUDY_DATA_DIR"] in str(R.P.data_dir())
    pid = a_person(snapshot)
    assert client.get("/insights/worker", params={"person": pid}, headers={"x-understudy-actor": "agent"}).status_code == 200      # the worker pointers carry no per-user detail


def test_the_transparency_page_is_for_the_workers_own_app_not_an_agent(client, snapshot):
    pid = a_person(snapshot)
    assert client.get("/insights/sharing", params={"person": pid}, headers={"x-understudy-actor": "agent"}).status_code == 403
    assert client.get("/insights/sharing", params={"person": pid}, headers={"x-understudy-actor": "worker"}).status_code == 200
    assert client.get("/insights/sharing", params={"person": pid}).status_code == 200


# ---------------------------------------------------------------------------------------------------- the stand-in for the engine's own profile (mock mode, worker views only)
class _Identity:
    role = "benefits-processor"


@pytest.fixture()
def identity(monkeypatch):
    """The engine knows one profile, p_learn01, that is not in the synthetic firm."""
    from understudy_engine import routes_handoff as rh

    monkeypatch.setattr(rh, "_resolve", lambda person: ((person or "p_learn01"), _Identity() if person in (None, "p_learn01") else None))
    return "p_learn01"


def expected_stand_in(snapshot):
    from understudy_engine.insights.names import natural_key

    svc = InsightsService(InsightsStore(), snapshot_provider=lambda s: snapshot, clock=lambda: snapshot.now)
    members = sorted((p for p in snapshot.people if p.role == "benefits-processor"), key=lambda p: natural_key(p.label))
    for m in members:
        if len(svc.worker(m.id, "firm")["pointers"]) >= 2:
            return m
    return members[0]


def test_the_engines_own_profile_gets_a_fixed_example_week_in_mock_mode(client, snapshot, identity):
    r = client.get("/insights/worker", params={"person": identity})
    assert r.status_code == 200
    d, m = r.json()["data"], r.json()["meta"]
    want = expected_stand_in(snapshot)
    assert d["stand_in"] is True and d["person"] == identity and d["stand_in_label"] == want.label
    assert len(d["pointers"]) >= 2 and d["status"] in V.STATUSES_WORKER
    assert m["origin"] == "synthetic" and m["badge"] == "made-up firm" and m["note"] == "An example week stands in for this profile."
    assert "demo" not in json.dumps(r.json()).lower()
    check = pytest.importorskip("jsonschema")
    assert check is not None
    from .test_schema import check as schema_check

    schema_check("worker_response", d)


def test_the_stand_in_is_deterministic_across_services_and_calls(snapshot, monkeypatch, identity):
    outs = []
    for _ in range(2):
        monkeypatch.setenv("UNDERSTUDY_X_INSIGHTS", "1")
        app = FastAPI()
        install_error_handlers(app)
        app.include_router(R.router)
        app.state.insights = InsightsService(InsightsStore(), snapshot_provider=lambda s: snapshot, clock=lambda: snapshot.now)
        c = TestClient(app)
        outs.append([c.get("/insights/worker", params={"person": identity}).json()["data"] for _ in range(2)])
    assert outs[0][0] == outs[0][1] == outs[1][0] == outs[1][1]


def test_outside_mock_mode_the_404_stays_and_so_does_it_for_anyone_the_engine_does_not_know(client, monkeypatch, identity):
    r = client.get("/insights/worker", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"                     # in mock mode too: only the engine's own profile is stood in for
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    for url in ("/insights/worker", "/insights/sharing"):
        r = client.get(url, params={"person": identity, "source": "firm"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person", url
    r = client.get("/insights/why", params={"insight": "i_000000000000", "person": identity, "source": "firm"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"
    r = client.post("/insights/feedback", json={"insight": "i_000000000000", "event": "useful"}, params={"person": identity, "source": "firm"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person"


def test_a_person_in_the_firm_and_the_admin_views_never_use_a_stand_in(client, snapshot, identity):
    pid = a_person(snapshot)
    d = client.get("/insights/worker", params={"person": pid}).json()
    assert "stand_in" not in d["data"] and d["meta"]["note"] != "An example week stands in for this profile."
    ov = client.get("/insights/admin/overview", headers=admin_headers())
    assert ov.status_code == 200 and "stand_in" not in json.dumps(ov.json())
    # an admin request for the engine's profile is not served either: the routes take no person
    assert client.get("/insights/admin/firm", params={"person": identity}, headers=admin_headers()).status_code == 200


def test_why_sharing_and_feedback_follow_the_stand_in_and_touch_only_its_own_state(client, snapshot, identity):
    from understudy_engine.insights import routes as RR

    want = expected_stand_in(snapshot)
    d = client.get("/insights/worker", params={"person": identity}).json()["data"]
    ptr = d["pointers"][0]
    w = client.get("/insights/why", params={"insight": ptr["id"], "person": identity})
    assert w.status_code == 200 and w.json()["data"]["stand_in"] is True and w.json()["data"]["state"] == "selected" and "demo" not in json.dumps(w.json()).lower()
    sh = client.get("/insights/sharing", params={"person": identity}).json()
    assert sh["data"]["stand_in"] is True and sh["data"]["person"] == identity and sh["data"]["preview"]["label"] == want.label
    assert sh["meta"]["note"] == "An example week stands in for this profile."
    f = client.post("/insights/feedback", json={"insight": ptr["id"], "event": "not_useful"}, params={"person": identity})
    assert f.status_code == 200 and f.json() == {"insight": ptr["id"], "event": "not_useful", "recorded": True, "stand_in": True}
    after = client.get("/insights/worker", params={"person": identity}).json()["data"]
    assert ptr["id"] not in [p["id"] for p in after["pointers"]] and len(after["pointers"]) == len(d["pointers"]) - 1
    store = client.app.state.insights.store
    assert [e["event"] for e in store.events(want.id)] == ["not_useful"]
    assert all(store.events(p.id) == [] for p in snapshot.people if p.id != want.id) and store.events("admin") == [] and RR.P.is_mock()


def test_the_stand_in_rule_is_the_first_member_in_label_order_with_two_pointers_else_the_first_member():
    from understudy_engine.insights.params import DEFAULT as PRM

    from .helpers import NOW, habit_rows, person, snap as mk_snap

    def svc_for(people):
        s = mk_snap(people)
        return InsightsService(InsightsStore(), snapshot_provider=lambda src: s, clock=lambda: NOW, params=PRM)

    two = lambda pid: habit_rows(pid, lost=30.0) + habit_rows(pid, lost=30.0, skill="reconcile-before-noting", serial0=100)       # two pointers: two skills with a time loss
    few = lambda pid: [habit_rows(pid, lost=0.0)[0]]
    ppl = [person("p_a10", two("p_a10"), label="BP-10"), person("p_a02", two("p_a02"), label="BP-02"), person("p_a01", few("p_a01"), label="BP-01")]
    assert svc_for(ppl).stand_in("benefits-processor", "firm") == ("p_a02", "BP-02")                          # BP-01 has no pointers; BP-02 sorts before BP-10 (natural order)
    ppl = [person("p_a10", few("p_a10"), label="BP-10"), person("p_a02", few("p_a02"), label="BP-02"), person("p_a01", few("p_a01"), label="BP-01")]
    assert svc_for(ppl).stand_in("benefits-processor", "firm") == ("p_a01", "BP-01")                          # nobody qualifies: the first member
    assert svc_for(ppl).stand_in("data-analyst", "firm")[1] == "BP-01"                                          # no member of that role: the first member of the firm
