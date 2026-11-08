"""The synthetic firm (REQ-9, D43): deterministic, badged, about 60 users, planted situations recorded for the evaluation only."""
from __future__ import annotations

import collections

import pytest
from understudy_engine.cue import ledger as L
from understudy_engine.insights import firm as F
from understudy_engine.insights.summary import AdminView


@pytest.fixture(scope="module")
def firm():
    return F.build_firm(0)


def test_sixty_users_across_three_roles_with_experts_and_juniors(firm):
    s = firm.snapshot
    assert len(s.people) == 60 and s.badge == "made-up firm" and s.origin == "synthetic" and s.source == "firm"
    c = collections.Counter((p.role, p.level) for p in s.people)
    assert c[("benefits-processor", "expert")] == 7 and c[("benefits-processor", "junior")] == 23
    assert c[("data-analyst", "expert")] == 5 and c[("programmer", "expert")] == 3
    assert {p.unit for p in s.people} == {"unit_a", "unit_b", "unit_c", "unit_d", "prog_infra", "prog_web"}
    assert len({p.id for p in s.people}) == 60 and len({p.label for p in s.people}) == 60


def test_the_same_seed_gives_the_same_firm_byte_for_byte(firm):
    again = F.build_firm(0)
    assert [(p.id, len(p.rows), p.rows[-1]["id"] if p.rows else None) for p in again.snapshot.people] == [(p.id, len(p.rows), p.rows[-1]["id"] if p.rows else None) for p in firm.snapshot.people]
    assert all(a.rows == b.rows for a, b in zip(again.snapshot.people, firm.snapshot.people))
    assert F.build_firm(1).snapshot.people[0].rows != firm.snapshot.people[0].rows


def test_rows_are_schema_valid_ledger_rows_and_carry_the_synthetic_origin(firm):
    n = 0
    for p in firm.snapshot.people:
        for r in p.rows[::9]:
            L.validate_row(r)
            assert r["origin"] == "synthetic" and r["person"] == p.id
            n += 1
    assert n > 500


def test_no_row_holds_text_or_a_name(firm):
    for p in firm.snapshot.people:
        for r in p.rows[::31]:
            for k, v in r.items():
                assert not isinstance(v, str) or len(v) < 60, (k, v)


def test_planted_situations_are_all_present_and_recorded(firm):
    pl = firm.truth["planted"]
    sp = pl["specials"]
    by = {p.id: p for p in firm.snapshot.people}
    assert len(sp["no_data"]) == 1 and by[sp["no_data"][0]].rows == ()
    assert len(sp["stale"]) == 1 and len(sp["new_joiner"]) == 1 and len(sp["holiday"]) == 1 and len(sp["role_change"]) == 1
    rc = by[sp["role_change"][0]]
    assert {r["role"] for r in rc.rows} == {"data-analyst", "programmer"} and rc.role == "programmer" and rc.role_since_t is not None
    assert pl["no_expert_reference"] == ["programmer"] and pl["small_team"] == ["prog_infra"]
    streams = {r["stream"] for p in firm.snapshot.people for r in p.rows}
    assert streams == {"assist", "delegated", "automation"}
    assert firm.snapshot.approvals and firm.snapshot.risk_events and firm.snapshot.routines


def test_the_holiday_user_has_a_three_week_gap_and_the_stale_user_stops_early(firm):
    s = firm.snapshot
    by = {p.id: p for p in s.people}
    hol = by[firm.truth["planted"]["specials"]["holiday"][0]]
    from understudy_engine.insights.rows import row_t

    ts = sorted(row_t(r) for r in hol.rows if r["stream"] == "assist")
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert max(gaps) >= 17 * 86400
    stale = by[firm.truth["planted"]["specials"]["stale"][0]]
    assert s.now - max(row_t(r) for r in stale.rows) > 21 * 86400


def test_the_null_firm_has_nothing_planted():
    n = F.build_firm(0, scenario="null")
    pl = n.truth["planted"]
    assert pl["improving_units"] == [] and pl["role_gap"] == {} and pl["no_expert_reference"] == [] and pl["risk"] == {}
    assert not n.snapshot.routines and not n.snapshot.approvals and not n.snapshot.risk_events
    streams = {r["stream"] for p in n.snapshot.people for r in p.rows}
    assert streams == {"assist"}
    assert all(p.rows for p in n.snapshot.people)


def test_the_expert_reference_is_centred_on_zero_and_juniors_lose_time(firm):
    import numpy as np

    lost = collections.defaultdict(list)
    for p in firm.snapshot.people:
        if p.role != "benefits-processor":
            continue
        for r in p.rows:
            if r["stream"] == "assist" and r.get("lost_s") is not None:
                lost[(p.level, r["skill"])].append(r["lost_s"])
    assert abs(np.median(lost[("expert", "check-the-cliff")])) < 3                      # the reference is a median: the heavy tail does not move it
    assert np.median(lost[("junior", "check-the-cliff")]) > 8
    assert np.median(lost[("junior", "enter-household-once")]) < np.median(lost[("junior", "check-the-cliff")])


def test_the_skill_ids_exist_in_the_role_packs():
    from understudy_engine.packs import load_pack

    for role, skills in F.SKILLS.items():
        cur = load_pack(role).file("curriculum")
        ids = {s["id"] for s in cur["skills"]}
        assert set(skills) <= ids, (role, set(skills) - ids)


def test_the_view_counts_every_person_including_the_one_with_no_data(firm):
    v = AdminView(firm.snapshot)
    cov = v.coverage()
    assert cov["users"] == 60 and cov["by_status"]["no_data"] == 1 and cov["by_status"]["stale"] >= 1 and cov["by_status"]["onboarding"] >= 1
