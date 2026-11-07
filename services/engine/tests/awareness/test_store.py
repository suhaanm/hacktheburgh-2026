from __future__ import annotations

import json
import os
import stat

import pytest

from understudy_engine.awareness import schema
from understudy_engine.awareness.store import AwarenessStore, merge_windows

from .conftest import glance_event, window_event


@pytest.fixture()
def store(tmp_path):
    return AwarenessStore(tmp_path / "aw")


def test_valid_events_are_appended_to_one_file_per_person_and_origin(store):
    res = store.append([window_event(1), window_event(2, t="2026-11-07T10:00:02.000Z"), window_event(3, person="p_other", origin="synthetic")])
    assert (res.accepted, res.duplicates, res.rejected) == (3, 0, [])
    assert store.people("real") == ["p_demo01"] and store.people("synthetic") == ["p_other"]
    assert len(store.events("p_demo01")) == 2
    assert store.events("p_demo01", "synthetic") == []                       # origins never mix
    path = store.path("p_demo01", "real")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_invalid_events_are_rejected_with_a_reason_and_the_rest_are_kept(store):
    bad = window_event(2)
    bad["cursor"]["x"] = 5
    res = store.append([window_event(1), bad, "junk", glance_event(3)])
    assert res.accepted == 2
    assert [i for i, _ in res.rejected] == [1, 2]
    assert all(isinstance(why, str) and "5" not in why for _, why in res.rejected)
    assert len(store.events("p_demo01")) == 2


def test_a_retried_batch_is_not_stored_twice_even_after_a_restart(store, tmp_path):
    batch = [window_event(1), window_event(2, t="2026-11-07T10:00:02.000Z")]
    assert store.append(batch).accepted == 2
    again = store.append(batch)
    assert (again.accepted, again.duplicates) == (0, 2)
    fresh = AwarenessStore(tmp_path / "aw")                                  # a new process: the ids are read back from the file
    assert fresh.append(batch).duplicates == 2
    assert len(fresh.events("p_demo01")) == 2


def test_nothing_that_could_be_a_coordinate_or_text_is_on_disk(store):
    store.append([window_event(1), glance_event(2)])
    text = store.path("p_demo01").read_text()
    for key in ('"x":', '"y":', '"title"', '"url"', '"text"', '"image"', '"frame"', "sha"):
        assert key not in text
    for line in text.splitlines():
        assert schema.problem(json.loads(line)) is None


def test_a_batch_over_the_limit_rejects_the_overflow(store):
    events = [window_event(i, t=f"2026-11-07T10:{i // 60:02d}:{i % 60:02d}.000Z") for i in range(1, 504)]
    res = store.append(events)
    assert res.accepted == 500 and len(res.rejected) == 3


def test_time_filters_and_limit_keep_the_newest(store):
    store.append([window_event(i, t=f"2026-11-07T10:00:{2 * i:02d}.000Z") for i in range(1, 6)])
    t = schema.parse_time("2026-11-07T10:00:05.000Z")
    got = store.events("p_demo01", since=t)
    assert [e["id"] for e in got] == ["evt-win-00003", "evt-win-00004", "evt-win-00005"]
    assert [e["id"] for e in store.events("p_demo01", until=t)] == ["evt-win-00001", "evt-win-00002"]
    assert [e["id"] for e in store.events("p_demo01", limit=2)] == ["evt-win-00004", "evt-win-00005"]


def test_a_glance_attaches_to_the_window_that_contains_it_and_a_stray_one_is_loose():
    inside = glance_event(1, t="2026-11-07T10:00:01.000Z")
    outside = glance_event(2, t="2026-11-07T10:05:00.000Z")
    wins, loose = merge_windows([window_event(1), inside, outside])
    assert len(wins) == 1 and [g.trigger for g in wins[0].glances] == ["stuck"]
    assert wins[0].glances[0].blocker == "cannot_find_control" and wins[0].glances[0].confidence == 0.8
    assert len(loose) == 1
    assert merge_windows([{"junk": 1}, window_event(1)])[0][0].app_kind == "browser"          # malformed events are skipped


def test_summary_has_counts_and_means_only(store):
    store.append([window_event(1), window_event(2, t="2026-11-07T10:00:02.000Z", app_kind="spreadsheet"), glance_event(3)])
    s = store.summary("p_demo01")
    assert s["windows"] == 2 and s["glances"] == 1 and s["window_seconds"] == 4.0
    assert s["by_app_kind"] == {"browser": 1, "spreadsheet": 1}
    assert s["glances_by_trigger"] == {"stuck": 1} and s["glances_by_blocker"] == {"cannot_find_control": 1}
    assert s["cursor_mean"]["dwell_s"] == 1.9 and s["clicks_known"] is False
    assert AwarenessStore(store.root).summary("p_nobody")["windows"] == 0


def test_clear_removes_one_person_or_everything(store):
    store.append([window_event(1), window_event(2, person="p_other")])
    assert store.clear("p_other") == 1
    assert store.people() == ["p_demo01"]
    assert store.clear() == 1
    assert store.people() == []
    assert store.append([window_event(1)]).duplicates == 0                      # the id cache was dropped with the file


def test_person_ids_cannot_escape_the_directory(store):
    for bad in ("../etc/passwd", "p_", "alice", "p_UPPER", "p_a/b"):
        with pytest.raises(ValueError):
            store.path(bad)
    with pytest.raises(ValueError):
        store.path("p_demo01", "elsewhere")
