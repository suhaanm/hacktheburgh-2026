"""Invented display names for the synthetic firm (REQ-9): the dashboard's list and rule, display only. The names never reach the selection, the thresholds or the evaluation."""
from __future__ import annotations

import json
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest

from understudy_engine.insights import firm as F
from understudy_engine.insights import names as N
from understudy_engine.insights import select as SEL
from understudy_engine.insights import views as VW
from understudy_engine.insights.params import DEFAULT
from understudy_engine.insights.service import InsightsService
from understudy_engine.insights.store import InsightsStore
from understudy_engine.insights.summary import AdminView

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "apps" / "dashboard" / "src" / "fixtures" / "firm-firm.json"
SCRIPT = ROOT / "apps" / "dashboard" / "scripts" / "name-fixtures.mjs"


@pytest.fixture(scope="module")
def snap():
    return F.build_firm(0).snapshot


def test_fnv1a_matches_the_published_32_bit_vectors():
    assert N.fnv1a("") == 0x811C9DC5 and N.fnv1a("a") == 0xE40C292C and N.fnv1a("foobar") == 0xBF9CF968


def test_natural_order_compares_digits_as_numbers_and_letters_without_case():
    assert sorted(["BP-10", "BP-9", "DA-01", "BP-01", "pg-02", "PG-01"], key=N.natural_key) == ["BP-01", "BP-9", "BP-10", "DA-01", "PG-01", "pg-02"]


def test_the_list_is_the_dashboards_list_verbatim():
    if not SCRIPT.exists():
        pytest.skip("the dashboard script is not in this checkout")
    block = re.search(r"export const NAMES = \[(.*?)\];", SCRIPT.read_text(), re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', block)) == N.NAMES
    assert len(N.NAMES) == 100 and len(set(N.NAMES)) == 100


def test_names_are_deterministic_never_reused_and_independent_of_input_order(snap):
    labels = [p.label for p in snap.people]
    a = N.assign_names(labels)
    shuffled = labels[:]
    random.Random(3).shuffle(shuffled)
    assert N.assign_names(shuffled) == a == N.assign_names(labels + labels)
    assert len(a) == 60 and len(set(a.values())) == 60 and set(a.values()) <= set(N.NAMES)
    assert N.assign_names(["BP-01"]) == {"BP-01": N.NAMES[N.fnv1a("BP-01") % 100]}


def test_a_firm_larger_than_the_list_names_the_first_hundred_and_leaves_the_rest_without():
    labels = [f"BP-{i:03d}" for i in range(1, 121)]
    out = N.assign_names(labels)
    assert len(out) == 100 and len(set(out.values())) == 100 and "BP-120" not in out and "BP-001" in out


def test_the_engine_names_equal_the_dashboard_fixture_names_for_the_built_in_firm(snap):
    if not FIXTURE.exists():
        pytest.skip("the dashboard fixture is not in this checkout")
    fx = json.loads(FIXTURE.read_text())
    want = {u["label"]: u["name"] for r in fx["data"]["roles"] for u in r["users"]}
    got = N.assign_names(p.label for p in snap.people)
    assert got == want
    rows = {u["label"]: u["name"] for g in VW.firm_payload(AdminView(snap))["roles"] for u in g["users"]}
    assert rows == want


def test_every_person_row_has_a_name_and_the_label_stays_the_key_and_the_sort(snap):
    firm = VW.firm_payload(AdminView(snap))
    users = [u for g in firm["roles"] for u in g["users"]]
    assert len(users) == 60 and all(isinstance(u["name"], str) and u["name"] for u in users) and len({u["name"] for u in users}) == 60
    for g in firm["roles"]:
        labels = [u["label"] for u in g["users"]]
        assert labels == sorted(labels)                                   # the order is by label, as before


def test_the_workers_preview_carries_the_same_name_as_the_admins_row(snap):
    svc = InsightsService(InsightsStore(), snapshot_provider=lambda s: snap, clock=lambda: snap.now)
    firm = {u["id"]: u for g in svc.firm("firm")["roles"] for u in g["users"]}
    for pid in ("p_f_bp06", "p_f_da03", "p_f_pg10"):
        prev = svc.sharing(pid, "firm")["preview"]
        assert prev["name"] == firm[pid]["name"] and prev["label"] == firm[pid]["label"]


def test_a_real_ledger_gets_no_invented_name():
    from .helpers import person, row, snap as mk_snap

    real = replace(mk_snap([person("p_real1", [row("p_real1", 1.0 + i, outcome="clean") for i in range(30)], label="p_real1")]), badge="live", origin="real", source="local")
    s = AdminView(real).sums["p_real1"]
    assert s.name is None and s.to_row()["name"] is None


def test_names_change_nothing_the_selection_can_see(snap, monkeypatch):
    """The selection is identical with and without names: the same ids, scores, order and reasons for every person and for the admin."""
    from understudy_engine.insights import admin as A
    from understudy_engine.insights.evaluate import worker_pass

    def everything():
        w = []
        for p in sorted(snap.people, key=lambda x: x.id):
            out, sel = worker_pass(p, snap.now, None, DEFAULT)
            w.append((p.id, out.status, [(s.cand.id, s.score, s.position, s.reason) for s in sel.selected], [(x.id, x.reason) for x in sel.suppressed]))
        view = AdminView(snap, DEFAULT)
        sel = SEL.select(A.admin_run(view), audience="admin", scope="firm", now=snap.now, params=DEFAULT)
        return w, [(s.cand.id, s.score, s.position, s.reason) for s in sel.selected], [(x.id, x.reason) for x in sel.suppressed]

    named = everything()
    monkeypatch.setattr(N, "assign_names", lambda labels: {})
    from understudy_engine.insights import summary as SUM

    monkeypatch.setattr(SUM, "assign_names", lambda labels: {})
    assert everything() == named
    assert not any(isinstance(v, str) and v in N.NAMES for v in json.dumps(named).split('"'))       # no name appears anywhere in the selection output
