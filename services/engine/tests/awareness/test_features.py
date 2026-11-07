from __future__ import annotations

import math

from understudy_engine.awareness import schema
from understudy_engine.awareness.features import AWARENESS_COLUMNS, awareness_features, awareness_vector, features_by_bin, zeros

from .conftest import glance_event, window_event

T0 = schema.parse_time("2026-11-07T10:00:00.000Z")


def win(i, off, **cursor_over):
    e = window_event(i, t=schema.iso(T0 + off))
    e["cursor"] = {**e["cursor"], **cursor_over}
    return e


def test_the_columns_are_named_unique_and_always_all_present():
    assert len(AWARENESS_COLUMNS) == len(set(AWARENESS_COLUMNS)) == 25
    assert all(c.startswith("aw_") for c in AWARENESS_COLUMNS)
    for window in ([], [window_event(1)], [glance_event(1)], [{"junk": 1}, None, "x"]):
        f = awareness_features(window)
        assert tuple(f) == AWARENESS_COLUMNS
        assert all(isinstance(v, float) and math.isfinite(v) for v in f.values())
    assert awareness_vector([]) == [0.0] * len(AWARENESS_COLUMNS)


def test_an_empty_window_is_all_zeros_with_zero_coverage():
    assert awareness_features([]) == zeros()


def test_coverage_and_the_cursor_columns():
    ws = [win(1, 0, dwell_s=1.9, wander=1.0, idle_gap_s=1.9), win(2, 2, dwell_s=0.0, wander=math.e ** 2, back_forth=2, speed_bursts=3, idle_gap_s=0.3)]
    f = awareness_features(ws, span_s=30)
    assert f["aw_coverage"] == 4 / 30
    assert f["aw_dwell_share"] == 0.5 and f["aw_dwell_s_max"] == 1.9
    assert abs(f["aw_wander_mean_log"] - 1.0) < 1e-9 and abs(f["aw_wander_max_log"] - 2.0) < 1e-9
    assert f["aw_back_forth_sum"] == 2 and f["aw_speed_bursts_sum"] == 3 and f["aw_idle_gap_max_s"] == 1.9
    assert abs(f["aw_sys_idle_mean_log"] - math.log1p(0.4)) < 1e-9


def test_coverage_is_capped_at_one():
    ws = [win(i, 2 * i) for i in range(40)]
    assert awareness_features(ws, span_s=30)["aw_coverage"] == 1.0


def test_input_rhythm_without_a_permission_a_still_cursor_with_recent_input_means_keys_or_a_click():
    typing = win(1, 0, idle_gap_s=1.95)
    typing["sys_idle_s"] = 0.3
    away = win(2, 2, idle_gap_s=1.95)
    away["sys_idle_s"] = 40.0
    moving = win(3, 4, idle_gap_s=0.2)
    moving["sys_idle_s"] = 0.1
    unknown = win(4, 6, idle_gap_s=1.95)
    unknown.pop("sys_idle_s")
    f = awareness_features([typing, away, moving, unknown])
    assert f["aw_input_active_share"] == 0.25


def test_app_kind_shares_and_switches():
    ws = [window_event(1, t=schema.iso(T0), app_kind="browser"), window_event(2, t=schema.iso(T0 + 2), app_kind="spreadsheet"),
          window_event(3, t=schema.iso(T0 + 4), app_kind="browser"), window_event(4, t=schema.iso(T0 + 6), app_kind="browser")]
    f = awareness_features(ws)
    assert f["aw_app_browser"] == 0.75 and f["aw_app_spreadsheet"] == 0.25 and f["aw_app_switches"] == 2
    assert abs(sum(f[c] for c in AWARENESS_COLUMNS if c.startswith("aw_app_") and c != "aw_app_switches") - 1.0) < 1e-9


def test_zone_alternation_flag():
    assert awareness_features([win(1, 0, zone_a="case_note", zone_b="results_tabs", back_forth=2)])["aw_zone_alternation"] == 1.0
    assert awareness_features([win(1, 0)])["aw_zone_alternation"] == 0.0


def test_glance_columns_a_blocker_counts_none_and_unknown_do_not():
    none = glance_event(1, glance={"app_kind": "browser", "task_phase": "reading", "blocker": "none", "confidence": 0.9})
    unknown = glance_event(2, glance={"app_kind": "browser", "task_phase": "reading", "blocker": "unknown", "confidence": 0.9})
    blocked = glance_event(3, trigger="hotkey", glance={"app_kind": "browser", "task_phase": "reading", "blocker": "error_message", "confidence": 0.7})
    f = awareness_features([none, unknown])
    assert (f["aw_glance_any"], f["aw_glance_blocked"], f["aw_glance_conf"]) == (1.0, 0.0, 0.0)
    f = awareness_features([none, blocked])
    assert (f["aw_glance_any"], f["aw_glance_blocked"], f["aw_glance_conf"], f["aw_trigger_hotkey"], f["aw_trigger_loop"]) == (1.0, 1.0, 0.7, 1.0, 0.0)
    assert awareness_features([glance_event(4, trigger="loop")])["aw_trigger_loop"] == 1.0


def test_the_stuck_trigger_is_not_a_feature_so_the_model_is_not_fed_its_own_prediction():
    stuck = glance_event(1, trigger="stuck")
    f = awareness_features([stuck])
    assert f["aw_glance_any"] == 1.0 and f["aw_trigger_hotkey"] == 0.0 and f["aw_trigger_loop"] == 0.0
    assert not any("stuck" in c for c in AWARENESS_COLUMNS)


def test_malformed_events_are_skipped_not_raised_on():
    bad = [{"type": "window", "cursor": "nope"}, {"type": "window", "cursor": {"dwell_s": "x", "wander": None}}, {"type": "glance", "glance": []}, 5]
    f = awareness_features(bad)
    assert tuple(f) == AWARENESS_COLUMNS and all(math.isfinite(v) for v in f.values())


def test_features_by_bin_use_only_events_that_finished_before_the_bin_starts():
    events = [win(i, 2 * i, dwell_s=1.9) for i in range(0, 30)]          # windows over 60 s
    events.append(glance_event(1, t=schema.iso(T0 + 50)))
    bins = [T0 + 10, T0 + 40, T0 + 70]
    out = features_by_bin(events, bins, span_s=30)
    # bin at +10: windows that ended by +10 and after -20: 5 windows (0..8), coverage 10/30
    assert abs(out[0]["aw_coverage"] - 10 / 30) < 1e-9 and out[0]["aw_glance_any"] == 0.0
    # the glance at +50 is after the bin at +40: it must not leak into it
    assert out[1]["aw_glance_any"] == 0.0 and out[1]["aw_coverage"] == 1.0
    assert out[2]["aw_glance_any"] == 1.0
    # a window that ends after the bin start is not used
    straddle = [win(1, 9)]                                              # runs 9 to 11
    assert features_by_bin(straddle, [T0 + 10], span_s=30)[0]["aw_coverage"] == 0.0
    assert features_by_bin(straddle, [T0 + 11], span_s=30)[0]["aw_coverage"] == 2 / 30


def test_features_by_bin_are_independent_of_event_order_and_skip_bad_times():
    events = [win(i, 2 * i, dwell_s=1.9 if i % 2 else 0.0) for i in range(10)] + [{"type": "window", "t": "garbage"}]
    a = features_by_bin(events, [T0 + 20])
    b = features_by_bin(list(reversed(events)), [T0 + 20])
    assert a == b
