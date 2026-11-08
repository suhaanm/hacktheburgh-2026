"""Growth after a role change: the worker's work under an earlier role stays readable (``?role=``) and is never mixed into the current role's score.

The rule (cue/routes.py ``_role_scope``): Growth is computed from the CURRENT role's assist rows. The current role is the profile's once a role change was
recorded for that person, otherwise the role of the person's newest assist row. ``?role=`` reads another role. ``data.role_scope`` says which role is shown and
lists every role the person has work under, so the screen can offer the earlier work.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_handoff as rh
from understudy_engine.api.errors import install_error_handlers
from understudy_engine.cue import routes as R
from understudy_engine.cue.ledger import Ledger, make_row
from understudy_engine.cue.live import LiveCue
from understudy_engine.cue.params import DEFAULT

T0 = 1_790_000_000.0
BP, DA, PR = "benefits-processor", "data-analyst", "programmer"
P = "p_wk01"


def _rows(role: str, skills: tuple[str, str], n: int, t0: float, *, clean_every: int) -> list[dict]:
    out = []
    for i in range(n):
        clean = i % clean_every != 0
        out.append(make_row(person=P, role=role, skill=skills[i % 2], t=t0 + i * 3600.0, outcome="clean" if clean else "assisted", accepted=not clean,
                            trigger="auto" if not clean else "none", tier=1 if not clean else 0, origin="real", serial=i))
    return out


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.include_router(rh.router)
    ledger = Ledger(tmp_path / "assist" / "ledger.jsonl")
    app.state.cue_live = LiveCue(params=DEFAULT, ledger=ledger)
    rh._cache.clear()
    return TestClient(app), ledger


def _growth(c, **q):
    r = c.get("/growth", params={"person": P, **q})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_without_a_profile_the_newest_roles_work_is_the_score_and_the_earlier_role_is_one_query_away(api):
    c, ledger = api
    ledger.extend(_rows(BP, ("reads-error-first", "check-the-cliff"), 40, T0, clean_every=2))                          # 40 occurrences under the first role
    ledger.extend(_rows(PR, ("smallest-change", "confirm-the-fix"), 14, T0 + 100 * 3600.0, clean_every=3))              # then 14 under the second
    now = _growth(c)
    assert now["role"] == PR and now["occurrences"]["total"] == 14 and {s["skill"] for s in now["by_skill"]} == {"smallest-change", "confirm-the-fix"}
    assert now["role_scope"]["current"] == PR and now["role_scope"]["viewing_earlier"] is False
    assert [(r["role"], r["n"]) for r in now["role_scope"]["roles"]] == [(PR, 14), (BP, 40)]                                 # newest first
    old = _growth(c, role=BP)
    assert old["role"] == BP and old["occurrences"]["total"] == 40 and {s["skill"] for s in old["by_skill"]} == {"reads-error-first", "check-the-cliff"}
    assert old["role_scope"]["viewing_earlier"] is True and old["role_scope"]["current"] == PR
    # the current role's independence is its own, not a blend: the two roles were built with different shares of unaided work
    assert now["components"]["independence"]["k"] != old["components"]["independence"]["k"] or now["occurrences"]["total"] != old["occurrences"]["total"]
    assert _growth(c, role="astronaut")["occurrences"]["total"] == 0                                                          # an unknown role has no work, not an error


def test_after_a_recorded_role_change_growth_starts_clean_for_the_new_role_and_keeps_the_old_one_readable(api):
    c, ledger = api
    ledger.extend(_rows(BP, ("reads-error-first", "check-the-cliff"), 40, T0, clean_every=2))
    assert c.post("/onboarding", json={"role": BP, "person": P, "answers": {}}).status_code == 200
    before = _growth(c)
    assert before["role"] == BP and before["occurrences"]["total"] == 40 and before["readiness"]["ready"] is True
    assert c.post("/profile", json={"role": DA}).status_code == 200                                                           # the worker switches; no work under the new role yet
    fresh = _growth(c)
    assert fresh["role"] == DA and fresh["occurrences"]["total"] == 0 and fresh["readiness"]["ready"] is False and fresh["curve"] == []
    assert fresh["role_scope"]["current"] == DA and [(r["role"], r["n"]) for r in fresh["role_scope"]["roles"]] == [(BP, 40)]
    earlier = _growth(c, role=BP)
    assert earlier["occurrences"]["total"] == 40 and earlier["role_scope"]["viewing_earlier"] is True
    assert earlier["components"]["independence"] == before["components"]["independence"]                                    # the old role's score did not move
    ledger.extend(_rows(DA, ("profile-before-querying", "inspect-before-trusting"), 12, T0 + 200 * 3600.0, clean_every=4))
    grown = _growth(c)
    assert grown["role"] == DA and grown["occurrences"]["total"] == 12 and grown["readiness"]["ready"] is True
    assert _growth(c, role=BP)["occurrences"]["total"] == 40
    assert c.post("/profile", json={"role": BP}).status_code == 200                                                           # back to the first role: its work is the score again
    back = _growth(c)
    assert back["role"] == BP and back["occurrences"]["total"] == 40


def test_one_role_only_reads_exactly_as_before(api):
    c, ledger = api
    ledger.extend(_rows(BP, ("reads-error-first", "check-the-cliff"), 30, T0, clean_every=3))
    d = _growth(c)
    assert d["role"] == BP and d["occurrences"]["total"] == 30 and d["role_scope"] == {"role": BP, "current": BP, "viewing_earlier": False,
                                                                                        "roles": [{"role": BP, "n": 30, "last": d["role_scope"]["roles"][0]["last"]}]}


def test_a_person_with_no_rows_has_no_scope_and_no_error(api):
    c, _ = api
    d = _growth(c)
    assert d["role"] is None and d["occurrences"]["total"] == 0 and d["role_scope"] == {"role": None, "current": None, "viewing_earlier": False, "roles": []}


def test_offloaded_work_follows_the_role_too(api):
    c, ledger = api
    ledger.extend(_rows(BP, ("reads-error-first", "check-the-cliff"), 12, T0, clean_every=2))
    ledger.append(make_row(person=P, role=BP, skill="reads-error-first", t=T0 + 50 * 3600.0, outcome="clean", stream="automation", routine="calc-entry-3x", minutes=12.0,
                           offload_outcome="done", origin="real"))
    ledger.extend(_rows(PR, ("smallest-change", "confirm-the-fix"), 12, T0 + 100 * 3600.0, clean_every=2))
    assert _growth(c)["offloaded"]["automation"] == 0                                                                         # the old role's routine run is not this role's
    assert _growth(c, role=BP)["offloaded"]["automation"] == 1
