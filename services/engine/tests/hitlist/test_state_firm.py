"""The worker's hide and reset marks, and the firm aggregate: privacy by construction (groups under 5 are not listed, no person named)."""
from __future__ import annotations

import hashlib
import json

import pytest

from understudy_engine.hitlist import firm as F
from understudy_engine.hitlist.state import HitState, audit


# ------------------------------------------------------------------------------------------------ state
def test_hide_unhide_and_reset_persist_for_one_person_only(tmp_path):
    st = HitState(tmp_path)
    assert st.get("p_a") == {"reset_at": None, "hidden": {}}
    st.hide("p_a", "calc-entry-3x", 12, ["OPEN", "ENTER"])
    st.hide("p_b", "case-note-copy", 5, [])
    assert st.get("p_a")["hidden"] == {"calc-entry-3x": {"count": 12, "signature": ["OPEN", "ENTER"]}}
    assert HitState(tmp_path).get("p_b")["hidden"]["case-note-copy"]["count"] == 5          # a new instance reads the same file
    assert st.unhide("p_a", "calc-entry-3x") is True and st.unhide("p_a", "calc-entry-3x") is False
    st.hide("p_a", "x", 3, [])
    assert st.reset("p_a", 1234.5) == 1
    assert st.get("p_a") == {"reset_at": 1234.5, "hidden": {}}
    assert st.get("p_b")["hidden"]                                                              # the other person is untouched


def test_a_damaged_state_file_reads_as_empty_not_as_an_error(tmp_path):
    (tmp_path / "hitlist_state.json").write_text("{not json")
    assert HitState(tmp_path).get("p")["hidden"] == {}
    (tmp_path / "hitlist_state.json").write_text(json.dumps({"people": {"p": {"hidden": {"a": "bad"}, "reset_at": "soon"}}}))
    assert HitState(tmp_path).get("p") == {"reset_at": None, "hidden": {}}


def test_reset_writes_only_the_hit_list_file(tmp_path):
    tmp_path = tmp_path / "state"
    tmp_path.mkdir()
    other = {n: tmp_path / n for n in ("memory.md", "routines_state.json", "memory_state.json", "events.jsonl")}
    for n, p in other.items():
        p.write_text(f"content of {n}")
    before = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in other.items()}
    st = HitState(tmp_path)
    st.hide("p", "a", 3, [])
    st.reset("p", 99.0)
    assert {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in other.items()} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([*other, "hitlist_state.json"])


def test_the_audit_line_carries_counts_and_no_content(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    audit("hitlist_reset", "cleared 4 counters and 1 hidden marks")
    (line,) = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert line["kind"] == "hitlist_reset" and line["actor"] == "worker" and line["outcome"] == "ok"
    assert line["routine"] is None and line["run_id"] is None and line["note"] == "cleared 4 counters and 1 hidden marks"


# ------------------------------------------------------------------------------------------------ firm
def person(i, role, rows):
    return {"person": f"secret_person_{i}", "role": role, "rows": rows}


def row(rid="calc-entry-3x", count=10, pt=20.0, half=5.0, stops="submit"):
    return {"id": rid, "label": "Enter the household into three calculators", "key": "household", "family": "enter", "count": count,
            "minutes_per_week": {"point": pt, "lo": pt - half, "hi": pt + half}, "stops_before": stops}


def test_combine_adds_points_and_widths_in_quadrature():
    pt, lo, hi = F.combine([(10.0, 8.0, 12.0), (20.0, 16.0, 24.0)])
    assert pt == 30.0 and (hi - lo) / 2 == pytest.approx((2 ** 2 + 4 ** 2) ** 0.5)
    assert F.combine([]) == (0.0, 0.0, 0.0)
    assert F.combine([(1.0, 0.0, 2.0)])[1] == 0.0                                           # never below zero


def test_a_group_under_five_people_is_not_listed_and_is_counted():
    ppl = [person(i, "benefits-processor", [row()]) for i in range(5)] + [person(10 + i, "benefits-processor", [row("weekly-report", 4, 3.0, 1.0)]) for i in range(4)]
    d = F.aggregate(ppl, 7)
    assert [r["id"] for r in d["rows"]] == ["calc-entry-3x"] and d["suppressed"] == 1
    r = d["rows"][0]
    assert r["people"] == 5 and r["count"] == 50 and r["minutes_per_week"]["point"] == 100.0 and r["hours_per_week"]["point"] == 1.67
    assert d["people"] == 9 and d["min_group"] == 5
    assert d["total"] == {"actions": 1, "people": 9, "hours_per_week": r["hours_per_week"]}
    five = F.aggregate([person(i, "r", [row()]) for i in range(4)], 7)
    assert five["rows"] == [] and five["suppressed"] == 1 and five["total"]["hours_per_week"]["point"] == 0


def test_no_person_is_named_ranked_or_scored():
    ppl = [person(i, "benefits-processor", [row(count=10 + i, pt=20.0 + i)]) for i in range(8)]
    blob = json.dumps(F.aggregate(ppl, 30))
    assert "secret_person" not in blob and '"person"' not in blob and "rank" not in blob and "score" not in blob


def test_roles_are_separate_rows_and_the_role_filter_narrows_the_cohort():
    ppl = [person(i, "benefits-processor", [row()]) for i in range(6)] + [person(20 + i, "data-analyst", [row()]) for i in range(5)]
    both = F.aggregate(ppl, 7)
    assert sorted((r["role"], r["people"]) for r in both["rows"]) == [("benefits-processor", 6), ("data-analyst", 5)] and both["people"] == 11
    only = F.aggregate(ppl, 7, role="data-analyst")
    assert [r["role"] for r in only["rows"]] == ["data-analyst"] and only["people"] == 5


def test_the_firm_list_is_sorted_by_minutes_then_people_then_id_and_capped():
    ppl = [person(i, "r", [row(f"a{k:02d}", 10, 10.0 + k) for k in range(13)]) for i in range(6)]
    d = F.aggregate(ppl, 7)
    assert len(d["rows"]) == 10 and d["not_shown"] == 3
    pts = [r["minutes_per_week"]["point"] for r in d["rows"]]
    assert pts == sorted(pts, reverse=True)


def test_the_built_in_firm_is_sixty_people_in_three_roles_and_deterministic():
    a, b = F.tiny_firm(7), F.tiny_firm(7)
    assert a == b and len(a) == 60
    assert {p["role"] for p in a} == {"benefits-processor", "data-analyst", "programmer"}
    d, source = F.firm_hitlist(7)
    assert source in ("built-in", "insights") and d["people"] == 60
    assert d["rows"] and all(r["people"] >= 5 for r in d["rows"])
    assert F.firm_hitlist(7)[0] == d
    thirty = F.firm_hitlist(30)[0]
    assert thirty["window_days"] == 30 and thirty["rows"]
    assert thirty["suppressed"] >= 1 and all(r["id"] != "weekly-report" for r in thirty["rows"])    # a handful of people do the weekly report: not listed
    for r in d["rows"]:
        lo, pt, hi = (r["minutes_per_week"][k] for k in ("lo", "point", "hi"))
        assert 0 <= lo <= pt <= hi


def test_the_firm_uses_the_insights_firm_when_it_offers_the_right_shape(monkeypatch):
    import sys
    import types

    mod = types.ModuleType("understudy_engine.insights.firm")
    mod.repeat_people = lambda w: [person(i, "benefits-processor", [row()]) for i in range(7)]
    pkg = types.ModuleType("understudy_engine.insights")
    pkg.firm = mod
    monkeypatch.setitem(sys.modules, "understudy_engine.insights", pkg)
    monkeypatch.setitem(sys.modules, "understudy_engine.insights.firm", mod)
    d, source = F.firm_hitlist(7)
    assert source == "insights" and d["people"] == 7 and d["rows"][0]["people"] == 7
    mod.repeat_people = lambda w: "nonsense"
    assert F.firm_hitlist(7)[1] == "built-in"
