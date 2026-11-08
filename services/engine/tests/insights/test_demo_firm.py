"""The firm the Admin screens show on a built data directory (Track R, 8 Nov 2026).

The live Admin view was blank because the engine (mock off) read the device's own ledger, one person, so every comparison was withheld under the group-size rule of 5. The fix is data
and wiring, never a switch: a firm of 32 people is written into ``<data>/firm/`` by an idempotent top-up and the Admin routes read it. These tests keep that true: the firm has the
people it should, every Admin view has content from the real rules (k = 5 untouched), the same people add up on every screen, the seed is a top-up that touches nothing else, a damaged
firm is never served in part, a running engine notices a new firm, and the Worker routes never serve it."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import demo, http_guard
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.hitlist import routes as HR
from understudy_engine.insights import firm as F
from understudy_engine.insights import firmstore as FS
from understudy_engine.insights import routes as R
from understudy_engine.insights import service as SV
from understudy_engine.insights.names import NAMES
from understudy_engine.insights.params import DEFAULT
from understudy_engine.insights.service import InsightsService
from understudy_engine.insights.store import InsightsStore

NOW = float(datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc).timestamp())


@pytest.fixture()
def dd(tmp_path, monkeypatch) -> Path:
    """A demo data dir with the firm seeded, mock off (the live stack's setting)."""
    d = tmp_path / "demo-data"
    d.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(d))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "0")
    monkeypatch.setenv("UNDERSTUDY_X_INSIGHTS", "1")
    monkeypatch.setenv("UNDERSTUDY_X_HITLIST", "1")
    demo.seed_firm(d, datetime.fromtimestamp(NOW, timezone.utc), lambda m: None)
    return d


@pytest.fixture()
def client(dd):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.include_router(HR.router)
    app.state.insights = InsightsService(InsightsStore())
    http_guard.ensure_token()
    return TestClient(app)


def admin():
    return {"x-understudy-role": "admin", "x-understudy-token": http_guard.read_token()}


def strings(o, skip=("origin",)):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in skip:
                continue
            yield from strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v, skip)
    elif isinstance(o, str):
        yield o


# ------------------------------------------------------------------------------------------------ who is in it
def test_the_firm_is_32_people_in_three_roles_and_three_teams():
    snap = F.demo_firm(NOW).snapshot
    by_role: dict[str, list] = {}
    for p in snap.people:
        by_role.setdefault(p.role, []).append(p)
    assert {r: len(v) for r, v in by_role.items()} == {"benefits-processor": 12, "data-analyst": 10, "programmer": 10}
    assert {p.unit for p in snap.people} == {"claims_intake", "case_review", "data_tools"}
    teams = {u: sum(p.unit == u for p in snap.people) for u in ("claims_intake", "case_review", "data_tools")}
    assert teams == {"claims_intake": 11, "case_review": 11, "data_tools": 10}           # teams mix roles
    for role, (experts, juniors) in {"benefits-processor": (5, 7), "data-analyst": (5, 5), "programmer": (5, 5)}.items():
        assert sum(p.level == "expert" for p in by_role[role]) == experts and sum(p.level == "junior" for p in by_role[role]) == juniors     # at least 5 of each: k = 5 can be met
        for unit in {p.unit for p in by_role[role]}:
            assert sum(p.unit == unit for p in by_role[role]) >= 5                       # every role has teams of at least 5, so the per-team bands draw too
    assert len({p.id for p in snap.people}) == 32 and len({p.label for p in snap.people}) == 32
    assert all(p.origin == "synthetic" for p in snap.people)                  # the data enum stays: it drives the honesty logic, it is never shown
    assert len(snap.routines) >= 6 and len(snap.approvals) == 3 and len(snap.risk_events) == 3


def test_twelve_weeks_of_history_with_a_learning_curve_and_tenures():
    snap = F.demo_firm(NOW).snapshot
    first = min(r["t_hour"] for p in snap.people for r in p.rows)
    last = max(r["t_hour"] for p in snap.people for r in p.rows)
    assert first < "2026-08-20" and last <= "2026-11-08T01"                    # 12 weeks back from the clock, nothing after it
    experts = [p.tenure_weeks for p in snap.people if p.level == "expert"]
    juniors = [p.tenure_weeks for p in snap.people if p.level == "junior"]
    assert min(experts) >= 60 and max(juniors) <= 12 and min(juniors) >= 1
    bp_juniors = [p for p in snap.people if p.role == "benefits-processor" and p.level == "junior" and len(p.rows) > 60]
    assert bp_juniors

    def share(rows):
        a = [r for r in rows if r["stream"] == "assist"]
        return sum(1 for r in a if r["outcome"] == "clean" and not r["accepted"]) / max(1, len(a))

    early = sum(share(p.rows[:30]) for p in bp_juniors) / len(bp_juniors)
    late = sum(share(p.rows[-30:]) for p in bp_juniors) / len(bp_juniors)
    assert late > early + 0.15                                                 # the juniors finish more steps without help at the end than at the start


def test_the_firm_is_deterministic_and_moves_with_the_clock():
    a, b = F.demo_firm(NOW).snapshot, F.demo_firm(NOW + 120.0).snapshot        # inside the same hour: the same firm
    assert [p.rows for p in a.people] == [p.rows for p in b.people] and a.now == b.now
    c = F.demo_firm(NOW + 7200.0).snapshot
    assert c.now == NOW + 7200.0 and c.people[0].rows != a.people[0].rows


def test_the_legacy_firm_is_what_it_was():
    s = F.build_firm(0).snapshot
    assert len(s.people) == 60 and s.badge in ("synthetic firm", "made-up firm") and s.now == F.NOW0


# ------------------------------------------------------------------------------------------------ names
def test_every_person_has_a_distinct_name_from_the_list_and_never_a_code(dd):
    snap = FS.load_firm(dd)
    names = [p.name for p in snap.people]
    assert len(set(names)) == 32 and set(names) <= set(NAMES)
    assert all(re.fullmatch(r"[A-Z][\w'’.-]+(?: [A-Z][\w'’.-]+)+", n) for n in names)
    assert all(n != p.label for n, p in zip(names, snap.people, strict=True))


def test_the_people_list_carries_the_names_and_the_label_stays_the_sort_key(client):
    d = client.get("/insights/admin/firm", headers=admin()).json()["data"]
    rows = [u for g in d["roles"] for u in g["users"]]
    assert len(rows) == 32 and all(u["name"] for u in rows)
    for g in d["roles"]:
        assert [u["label"] for u in g["users"]] == sorted((u["label"] for u in g["users"]), key=lambda s: (s[:2], int(s[3:])))


# ------------------------------------------------------------------------------------------------ every admin view has content (k = 5 untouched)
def test_k_anonymity_is_untouched():
    assert DEFAULT.k_anon == 5


def test_every_admin_view_has_content_from_the_real_rules(client):
    h = admin()
    ov = client.get("/insights/admin/overview", headers=h).json()
    assert ov["meta"]["source"] == "firm" and ov["meta"]["badge"] == "firm" and ov["meta"]["n"] == 32
    d = ov["data"]
    assert d["firm"] == {"users": 32, "roles": 3, "label": "Firm"} and len(d["top"]) >= 5 and not d["nothing_stands_out"]
    assert {c["kind"] for c in d["top"]} >= {"role_gap", "automation_value", "risk_signal"}
    for role, juniors in (("benefits-processor", 6), ("data-analyst", 5), ("programmer", 5)):    # every role is compared: 5 experts against 5 or more juniors with enough data, k = 5 held
        r = next(x for x in d["role_comparison"] if x["role"] == role)
        assert r["enough"] and r["reason"] is None and r["n_expert"] == 5 and r["n_junior"] == juniors and r["gap"]["value"] > 5 and r["gap"]["ci"][0] > 0
    assert d["coverage"]["users"] == 32 and d["coverage"]["enough_data"] >= 28
    assert d["risk"]["open_approvals"] == 3 and d["risk"]["approval_backlog_age_h"]["max"] >= 24 and d["risk"]["injection_pauses_30d"] >= 1

    roles = client.get("/insights/admin/roles", headers=h).json()["data"]["roles"]
    assert len(roles) == 3
    for full in roles:
        assert not full.get("reason") and len(full["habits"]) == 4 and full["tenure"]
    firm = client.get("/insights/admin/firm", headers=h).json()["data"]
    assert firm["totals"] == {"users": 32, "enough_data": firm["coverage"]["enough_data"]} and not firm["privacy"]["merged_roles"]
    assert all(g["aggregate"] and g["units"] for g in firm["roles"])
    onb = client.get("/insights/admin/onboarding", headers=h).json()["data"]["roles"]
    assert {r["role"] for r in onb} == {"benefits-processor", "data-analyst", "programmer"} and all(r["curve"] and r["km"] and not r["reason"] for r in onb)
    hits = client.get("/hitlist/firm?window=7", headers=h).json()
    assert hits["data"]["total"]["people"] == 32 and len(hits["data"]["rows"]) >= 3 and hits["meta"]["firm_source"] == "roster"


def test_the_same_people_add_up_on_every_screen(client):
    h = admin()
    ov = client.get("/insights/admin/overview", headers=h).json()["data"]
    firm = client.get("/insights/admin/firm", headers=h).json()["data"]
    roles = client.get("/insights/admin/roles", headers=h).json()["data"]["roles"]
    onb = client.get("/insights/admin/onboarding", headers=h).json()["data"]["roles"]
    hits = client.get("/hitlist/firm?window=30", headers=h).json()["data"]
    want = {"benefits-processor": 12, "data-analyst": 10, "programmer": 10}
    assert ov["firm"]["users"] == firm["totals"]["users"] == ov["coverage"]["users"] == hits["total"]["people"] == hits["people"] == 32
    assert {g["role"]: len(g["users"]) for g in firm["roles"]} == want
    assert {r["role"]: r["users"] for r in ov["coverage"]["roles"]} == want
    assert {r["role"]: r["people"] for r in ov["role_comparison"]} == want
    assert {r["role"]: r["n_expert"] + r["n_junior"] for r in roles} == {"benefits-processor": 11, "data-analyst": 10, "programmer": 10}     # the new joiner has no comparison data yet: 11 of 12
    assert {r["role"]: r["enough_data"] for r in ov["coverage"]["roles"]} == {"benefits-processor": 11, "data-analyst": 10, "programmer": 10}   # and coverage agrees with Roles
    assert all(o["n"] <= want[o["role"]] for o in onb)
    for row in hits["rows"]:                                                    # a repeated action is repeated by at most the people of its role
        assert row["people"] <= want[row["role"]] and row["people"] >= 5
    assert hits["suppressed"] >= 1                                              # the weekly report is repeated by fewer than 5 people and is withheld


def test_the_built_firms_payloads_validate_against_the_public_schema(dd):
    import jsonschema

    from understudy_engine.insights import paths as P

    schema = json.loads(P.schema_path().read_text())

    def check(name, doc):
        jsonschema.validate(doc, {"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]}, cls=jsonschema.Draft202012Validator)

    snap = FS.load_firm(dd)
    svc = InsightsService(InsightsStore(), clock=lambda: snap.now)
    ov = svc.overview("firm")
    assert ov["badge"] == "firm" and svc.snapshot("firm").source == "firm"
    for c in ov["top"]:
        check("admin_card", c)
        check("drill", svc.drill("firm", c["id"]))
    for g in svc.firm("firm")["roles"]:
        for u in g["users"]:
            check("user_row", u)
    for p in snap.people:
        check("worker_response", svc.worker(p.id, "firm"))


def test_nothing_a_person_can_read_says_how_the_data_was_made(client):
    h = admin()
    bodies = [client.get(p, headers=h).json() for p in ("/insights/admin/overview", "/insights/admin/roles", "/insights/admin/firm", "/insights/admin/onboarding", "/hitlist/firm?window=7")]
    for c in bodies[0]["data"]["top"]:
        bodies.append(client.get("/insights/admin/drill", params={"insight": c["id"]}, headers=h).json())
    bad = re.compile(r"synthetic|simulated|made[- ]?up|\bdemo\b|sample data|example data|fake|pretend", re.I)
    offenders = [s for b in bodies for s in strings(b) if bad.search(s)]
    assert offenders == []


# ------------------------------------------------------------------------------------------------ the wiring
def test_a_running_engine_notices_a_firm_added_after_it_started(tmp_path, monkeypatch):
    d = tmp_path / "demo-data"
    d.mkdir()
    for k, v in (("UNDERSTUDY_DATA_DIR", str(d)), ("UNDERSTUDY_MOCK", "0"), ("UNDERSTUDY_X_INSIGHTS", "1")):
        monkeypatch.setenv(k, v)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.insights = InsightsService(InsightsStore())
    http_guard.ensure_token()
    c = TestClient(app)
    before = c.get("/insights/admin/overview", headers=admin()).json()
    assert before["meta"]["source"] == "local" and before["data"]["firm"]["users"] == 0           # the live stack's blank Admin view
    demo.seed_firm(d, datetime.fromtimestamp(NOW, timezone.utc), lambda m: None)
    after = c.get("/insights/admin/overview", headers=admin()).json()
    assert after["meta"]["source"] == "firm" and after["data"]["firm"]["users"] == 32 and after["data"]["top"]
    (d / "firm" / "roster.json").unlink()                                                          # removing it puts things back, still without a restart
    assert c.get("/insights/admin/overview", headers=admin()).json()["meta"]["source"] == "local"


def test_an_explicit_source_still_wins_for_the_admin(client):
    r = client.get("/insights/admin/overview?source=local", headers=admin()).json()
    assert r["meta"]["source"] == "local" and r["data"]["firm"]["users"] == 0


def test_the_worker_routes_never_serve_the_firm_outside_mock_mode(client, dd):
    pid = FS.load_firm(dd).people[0].id
    for url in (f"/insights/worker?person={pid}&source=firm", f"/insights/sharing?person={pid}&source=firm", f"/insights/worker?person={pid}"):
        r = client.get(url).json()
        assert r["meta"]["source"] == "local", url
        blob = json.dumps(r)
        assert not any(n in blob for n in NAMES) and "p_f_" not in blob.replace(pid, "")
    why = client.get(f"/insights/why?insight=i_x&person={pid}&source=firm").json()
    assert why.get("meta", {}).get("source", "local") == "local"


def test_the_worker_route_gives_a_worker_header_no_firm_either(client, dd):
    pid = FS.load_firm(dd).people[0].id
    r = client.get(f"/insights/worker?person={pid}&source=firm", headers={"x-understudy-role": "worker", "x-understudy-token": http_guard.read_token()}).json()
    assert r["meta"]["source"] == "local" and r["data"]["status"] == "no_data"


def test_the_firm_aggregate_of_repeated_work_is_admin_only(client):
    assert client.get("/hitlist/firm?window=7").status_code == 403
    assert client.get("/insights/admin/firm").status_code == 403


# ------------------------------------------------------------------------------------------------ the seed is an idempotent top-up
def test_the_seed_is_idempotent_and_touches_only_the_firm_folder(tmp_path, monkeypatch):
    d = tmp_path / "demo-data"
    for sub in ("queue", "runs", "routines", "assist"):
        (d / sub).mkdir(parents=True)
        (d / sub / "keep.txt").write_text(f"{sub} stays as it is")
    (d / "audit.jsonl").write_text('{"kind":"x"}\n')
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(d))
    outs: list[str] = []
    t = datetime.fromtimestamp(NOW, timezone.utc)
    first = demo.seed_firm(d, t, outs.append)
    assert first["firm_written"] and first["firm_people"] == 32 and "32 people" in outs[-1] and "benefits-processor" in outs[-1]
    snap1 = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in sorted((d / "firm").rglob("*")) if p.is_file()}
    assert len(snap1) == 33                                                                          # the roster and 32 ledger files
    time.sleep(0.02)
    second = demo.seed_firm(d, t, outs.append)
    assert second["firm_written"] is False and "already seeded" in outs[-1]
    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in sorted((d / "firm").rglob("*")) if p.is_file()} == snap1     # nothing changed, not even a timestamp
    for sub in ("queue", "runs", "routines", "assist"):
        assert (d / sub / "keep.txt").read_text() == f"{sub} stays as it is" and [x.name for x in (d / sub).iterdir()] == ["keep.txt"]
    assert (d / "audit.jsonl").read_text() == '{"kind":"x"}\n'
    refreshed = demo.seed_firm(d, datetime.fromtimestamp(NOW + 86400, timezone.utc), outs.append, refresh=True)
    assert refreshed["firm_written"] and FS.load_firm(d).now == NOW + 86400
    assert [p.id for p in FS.load_firm(d).people] == [p.id for p in F.demo_firm(NOW).snapshot.people]       # the same people, later history


def test_the_seed_refuses_a_data_dir_that_is_not_a_demo_one(tmp_path):
    d = tmp_path / "real-data"
    d.mkdir()
    out: list[str] = []
    assert demo.seed_firm(d, datetime.fromtimestamp(NOW, timezone.utc), out.append) == {"firm": False}
    assert not (d / "firm").exists() and "not a demo data dir" in out[0]
    (d / demo.DATA_MARKER).write_text("marked\n")
    assert demo.seed_firm(d, datetime.fromtimestamp(NOW, timezone.utc), out.append)["firm"] is True      # the marker is what live-data carries


def test_reset_removes_the_firm_with_the_rest_of_what_the_seed_made(tmp_path, monkeypatch):
    d = tmp_path / "demo-data"
    d.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(d))
    demo.seed_firm(d, datetime.fromtimestamp(NOW, timezone.utc), lambda m: None)
    demo.reset_data(d, lambda m: None)
    assert not (d / "firm").exists()


def test_a_damaged_firm_is_never_served_in_part(dd):
    assert FS.load_firm(dd) is not None
    victim = next((dd / "firm" / "ledger").iterdir())
    good = victim.read_text()
    victim.write_text(good + "\n")
    assert FS.load_firm(dd) is None                                                                  # the hash is over the bytes: any change at all is refused, not served in part
    victim.write_text(good)
    assert FS.load_firm(dd) is not None                                                              # put back, it reads clean again
    victim.write_text("")
    assert FS.load_firm(dd) is None
    (dd / "firm" / "roster.json").write_text("{not json")
    assert FS.load_firm(dd) is None and FS.describe(dd) is None


def test_the_rows_of_the_firm_are_ledger_shaped_and_labelled_with_the_enum(dd):
    snap = FS.load_firm(dd)
    keys = set(snap.people[0].rows[0])
    for p in snap.people:
        for r in p.rows[:50]:
            assert set(r) >= {"id", "person", "origin", "t_hour", "role", "stream", "outcome"} and r["person"] == p.id and r["origin"] == "synthetic"
    assert "skill" in keys


# ------------------------------------------------------------------------------------------------ a role change reaches the local snapshot
def test_the_local_role_follows_the_profile_after_a_role_change(monkeypatch):
    prof = {"person": "p1", "role": "programmer", "role_since": "2026-11-05T10:00:00Z", "history": [{"role": "benefits-processor", "since": "2026-10-01T00:00:00Z", "until": "2026-11-05T10:00:00Z"}]}
    from understudy_engine import routes_handoff as rh

    monkeypatch.setattr(rh, "_mem", lambda: SimpleNamespace(load_state=lambda: {"profile": prof}))
    assert SV._profile_role("p1") == ("programmer", None)          # no time cut: rows carry their role, so a returning worker finds that role's history, never another role's
    assert SV._profile_role("someone-else") == (None, None)
    prof["history"] = []
    assert SV._profile_role("p1") == ("programmer", None)
    monkeypatch.setattr(rh, "_mem", lambda: (_ for _ in ()).throw(RuntimeError("no store")))
    assert SV._profile_role("p1") == (None, None)                                                    # an unreadable profile is no profile
