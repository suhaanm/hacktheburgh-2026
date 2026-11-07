from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from understudy_engine.cogs import cog_labeler, load_mapping, segment_episodes, to_cogs
from understudy_engine.core import BASE_COGS
from understudy_engine.personas import PERSONA_BY_SLUG, apprentices, simulate_persona
from understudy_engine.store import EventStore, validate_row

T0 = datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc)
_n = 0


def ev(dt: float, typ: str, zone: str | None = None, *, task="t_a1", person="p_hand", source="browser", role=None, **meta):
    global _n
    _n += 1
    row = {
        "schema": 1, "id": f"hand{_n:06d}", "t": (T0 + timedelta(seconds=dt)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "origin": "synthetic", "actor": "human", "person": person, "role": "benefits-processor", "source": source, "type": typ,
    }
    if task:
        row["task_id"] = task
    m = dict(meta)
    if zone:
        m["zone"] = zone
    if m:
        row["meta"] = m
    if role:
        row["target"] = {"role": role}
    return validate_row(row)


def ids(cogs):
    return [c.id for c in cogs]


def test_default_mapping_has_all_base_and_role_cogs():
    mp = load_mapping()
    assert set(BASE_COGS) <= set(mp.cogs)
    assert {"ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE"} <= set(mp.cogs)
    used = {r.cog for r in mp.rules if r.cog} | {r.reformulate_as for r in mp.rules if r.reformulate_as}
    assert used <= set(mp.cogs)


def test_hand_made_benefits_trace():
    evs = [
        ev(0, "task_start"),
        ev(1, "nav", "calc_site", site="calc1"),
        ev(7, "focus", "household_form"), ev(13, "click", "household_form"), ev(20, "focus", "household_form"),
        ev(26, "focus", "calc_result"), ev(32, "scroll", "calc_result", depth_bin=2),
        ev(33, "progress", kind="result_read"),
        ev(36, "focus", "cliff_panel"), ev(42, "click", "cliff_panel"),
        ev(46, "tab", "results_tabs"), ev(50, "click", "results_tabs"),
        ev(54, "copy", "calc_result"), ev(57, "tab", "case_note"), ev(60, "paste", "case_note"),
        ev(61, "task_end"),
    ]
    cogs = to_cogs(evs)
    assert ids(cogs) == ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE"]
    # contiguous segments: each starts where the previous one ended; dwell comes from the next start
    for a, b in zip(cogs, cogs[1:]):
        assert a.t1 == pytest.approx(b.t0)
    assert cogs[0].t0 == pytest.approx(T0.timestamp() + 1)
    assert cogs[1].dwell == pytest.approx(19.0)       # 7 -> 26
    assert cogs[-1].t1 == pytest.approx(T0.timestamp() + 66)    # last event + follow_s (6)


def test_t_end_clips_last_cog():
    evs = [ev(0, "scroll", "doc"), ev(5, "scroll", "doc")]
    assert to_cogs(evs)[-1].t1 == pytest.approx(T0.timestamp() + 11)
    assert to_cogs(evs, t_end=T0.timestamp() + 8)[-1].t1 == pytest.approx(T0.timestamp() + 8)


def test_starts_flag_keeps_repeated_reads_separate_and_plain_scrolls_merge():
    merged = to_cogs([ev(0, "focus", "calc_result"), ev(5, "scroll", "calc_result"), ev(10, "scroll", "calc_result")])
    assert ids(merged) == ["READ_RESULT"]
    split = to_cogs([ev(0, "focus", "calc_result"), ev(5, "scroll", "calc_result"), ev(9, "focus", "calc_result"), ev(14, "scroll", "calc_result")])
    assert ids(split) == ["READ_RESULT", "READ_RESULT"]
    assert split[0].t1 == pytest.approx(split[1].t0)


def test_search_then_reformulate_then_read():
    evs = [ev(0, "search", "search_box", len=12), ev(10, "scroll", "search_box"), ev(20, "search", "search_box", len=18),
           ev(24, "focus", "query_edit"), ev(30, "focus", "doc"), ev(38, "scroll", "doc")]
    assert ids(to_cogs(evs)) == ["SEARCH", "REFORMULATE", "READ"]
    # a search long after the previous one is a fresh SEARCH, not a reformulation
    far = to_cogs([ev(0, "search", len=5), ev(300, "search", len=7)])
    assert [c.id for c in far if c.id != "IDLE"] == ["SEARCH", "SEARCH"]


def test_idle_from_gap_and_from_os_idle_event():
    # a silence longer than gap_idle_s becomes an IDLE cog between the two
    gap = to_cogs([ev(0, "focus", "doc"), ev(4, "scroll", "doc"), ev(60, "click", "household_form")])
    assert ids(gap) == ["READ", "IDLE", "ENTER_HOUSEHOLD"]
    assert gap[0].t1 == pytest.approx(T0.timestamp() + 10)       # last event + follow_s
    assert gap[1].t0 == pytest.approx(gap[0].t1) and gap[1].t1 == pytest.approx(gap[2].t0)
    # an OS idle event says the machine was already idle for idle_s: the segment starts in the past
    os_idle = to_cogs([ev(0, "focus", "doc"), ev(3, "scroll", "doc"), ev(30, "idle", source="os", idle_s=20, task=None),
                       ev(55, "click", "household_form")])
    assert ids(os_idle) == ["READ", "IDLE", "ENTER_HOUSEHOLD"]
    assert os_idle[1].t0 == pytest.approx(T0.timestamp() + 9)   # 30 - 20 = 10 clamped to the end of READ (9) when extended back
    assert os_idle[1].t1 == pytest.approx(T0.timestamp() + 55)


def test_non_cog_events_are_skipped_and_undo_is_revert():
    evs = [ev(0, "task_start"), ev(1, "progress", kind="x"), ev(2, "undo", source="browser"), ev(3, "stuck", source="desk"), ev(4, "lock", source="os", task=None)]
    assert ids(to_cogs(evs)) == ["REVERT"]


def test_cliff_button_starts_a_check_and_panel_continues_it():
    one = to_cogs([ev(0, "click", "cliff_button"), ev(5, "scroll", "cliff_panel"), ev(9, "click", "cliff_panel")])
    assert ids(one) == ["CHECK_CLIFF"]
    two = to_cogs([ev(0, "click", "cliff_button"), ev(5, "scroll", "cliff_panel"), ev(12, "click", "cliff_button"), ev(16, "scroll", "cliff_panel")])
    assert ids(two) == ["CHECK_CLIFF", "CHECK_CLIFF"] and two[0].t1 == pytest.approx(two[1].t0)


def test_zoneless_link_tab_menuitem_clicks_navigate_but_zones_still_win():
    assert ids(to_cogs([ev(0, "click", role="link"), ev(8, "click", role="tab"), ev(16, "click", role="menuitem")])) == ["NAVIGATE"]
    assert ids(to_cogs([ev(0, "click", role="textbox")])) == ["ENTER"]
    assert ids(to_cogs([ev(0, "click", "household_form", role="link")])) == ["ENTER_HOUSEHOLD"]


def test_fallbacks_without_a_zone():
    evs = [ev(0, "nav"), ev(6, "scroll"), ev(12, "click"), ev(18, "copy"), ev(20, "paste")]
    assert ids(to_cogs(evs)) == ["NAVIGATE", "READ", "ENTER", "COPY", "PASTE"]


def test_to_cogs_rejects_two_people():
    with pytest.raises(ValueError):
        to_cogs([ev(0, "scroll", person="p_a"), ev(1, "scroll", person="p_b")])


def test_mapping_from_dict_and_yaml_file(tmp_path):
    doc = yaml.safe_load("""
version: 1
params: {follow_s: 2, gap_idle_s: 5}
rules:
  - { match: { type: click, zone: weird_zone }, cog: DECIDE }
  - { match: { type: [task_start, task_end] }, cog: null }
""")
    cogs = to_cogs([ev(0, "task_start"), ev(1, "click", "weird_zone")], doc)
    assert ids(cogs) == ["DECIDE"] and cogs[0].t1 == pytest.approx(cogs[0].t0 + 2)
    path = tmp_path / "mapping.yaml"
    path.write_text(yaml.safe_dump(doc))
    assert ids(to_cogs([ev(1, "click", "weird_zone")], path)) == ["DECIDE"]
    # a pack mapping that is the default file works the same way
    from understudy_engine.cogs import DEFAULT_MAPPING_PATH

    assert ids(to_cogs([ev(0, "scroll", "doc")], DEFAULT_MAPPING_PATH)) == ["READ"]
    with pytest.raises(ValueError):
        load_mapping({"role_rules": []})


def test_segment_episodes_by_task_with_progress_and_bounds():
    evs = [
        ev(0, "task_start", task="t_a1"), ev(2, "focus", "doc", task="t_a1"), ev(8, "scroll", "doc", task="t_a1"),
        ev(9, "progress", task="t_a1", kind="step_done"), ev(12, "task_end", task="t_a1"),
        ev(100, "task_start", task="t_a2"), ev(102, "click", "household_form", task="t_a2"), ev(110, "task_end", task="t_a2"),
        ev(50, "scroll", "doc", task=None),                       # background noise: ignored
    ]
    eps = segment_episodes(evs)
    assert [e.task_id for e in eps] == ["t_a1", "t_a2"]
    a, b = eps
    assert a.t0 == pytest.approx(T0.timestamp()) and a.t1 == pytest.approx(T0.timestamp() + 12)
    assert ids(a.cogs) == ["READ"] and a.cogs[0].t1 == pytest.approx(T0.timestamp() + 12)   # clipped by task_end
    assert a.progress_t == [pytest.approx(T0.timestamp() + 9)] and b.progress_t == []
    assert a.person == "p_hand" and a.origin == "synthetic" and a.role == "benefits-processor"
    assert ids(b.cogs) == ["ENTER_HOUSEHOLD"]


def test_untagged_events_split_on_idle_only_when_no_task_ids_exist():
    evs = [ev(0, "scroll", "doc", task=None), ev(10, "scroll", "doc", task=None), ev(200, "click", "household_form", task=None),
           ev(205, "click", "household_form", task=None)]
    eps = segment_episodes(evs, idle_s=60)
    assert len(eps) == 2 and ids(eps[0].cogs) == ["READ"] and ids(eps[1].cogs) == ["ENTER_HOUSEHOLD"]
    assert eps[0].task_id != eps[1].task_id
    tagged = evs + [ev(300, "task_start", task="t_x1"), ev(302, "scroll", "doc", task="t_x1")]
    assert [e.task_id for e in segment_episodes(tagged)] == ["t_x1"]
    assert len(segment_episodes(tagged, include_untagged=True)) == 3


def test_cog_labeler_counts_for_replay():
    lab = cog_labeler()
    assert lab(ev(0, "focus", "calc_result")) == "READ_RESULT"
    assert lab(ev(0, "progress")) is None


@pytest.fixture(scope="module")
def apprentice_data(tmp_path_factory):
    root = tmp_path_factory.mktemp("appr")
    apprentices.generate(root)
    truth = json.loads((root / "synthetic" / "apprentices" / "truth.json").read_text())
    return EventStore(root).read("synthetic"), truth


def test_mapper_recovers_every_planted_apprentice_cog_sequence(apprentice_data):
    evs, truth = apprentice_data
    planted = {t["task_id"]: t for t in truth["traces"]}
    eps = segment_episodes(evs)
    assert len(eps) == len(planted) == 48
    for ep in eps:
        t = planted[ep.task_id]
        assert ids(ep.cogs) == [c for c, _, _ in t["cogs"]], ep.task_id
        assert ep.duration == pytest.approx(t["duration_s"], abs=0.3)
        for c, (_, d, _) in zip(ep.cogs, t["cogs"]):
            assert c.dwell == pytest.approx(d, abs=8.0)
        total_err = sum(abs(c.dwell - d) for c, (_, d, _) in zip(ep.cogs, t["cogs"]))
        assert total_err / len(ep.cogs) < 1.0


def test_routine_instances_in_personas_map_to_the_expected_cogs():
    run = simulate_persona(PERSONA_BY_SLUG["nine-to-five"], with_mc=False)
    evs = [validate_row(r) for r in run.rows]
    eps = {e.task_id: e for e in segment_episodes(evs)}
    calc = next(r for r in run.truth["routines"] if r["name"] == "calc-entry-3x")
    hits = 0
    for inst in calc["instances"][:25]:
        seq = ids(eps[inst["task_id"]].cogs)
        assert "OPEN_CALCULATOR" in seq and "ENTER_HOUSEHOLD" in seq and "READ_RESULT" in seq
        hits += seq[0] == "OPEN_CALCULATOR"
    assert hits >= 20
    assert len(eps) >= run.truth["counts"]["tasks"] * 0.98
