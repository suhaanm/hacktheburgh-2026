"""The handoff routes share one PersonSource per data root, so a worker's parsed events are read once per data version, not once per request.

What is pinned:
* ``shared_source`` hands out the same object for the same root and another for another root, bounded;
* a second ``load`` is the very same object (no re-read), and a third after the person's file changed is a new one (the cache refreshes);
* the cached answer equals a cold one: the same events, role and episodes;
* the route handler's helper ``_src()`` is the shared one.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from understudy_engine.routines import sources
from understudy_engine.routines.sources import PersonSource, shared_source

PERSON = "p_cache01"


def _write_day(root, day: str, n: int, role: str = "benefits-processor", start: int = 0) -> None:
    d = root / "real" / PERSON
    d.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 7, 9, 0, 0, tzinfo=timezone.utc)
    with (d / f"{day}.jsonl").open("a") as fh:
        for i in range(start, start + n):
            fh.write(json.dumps({"schema": 1, "id": f"ev{i:08d}", "t": (t0 + timedelta(seconds=5 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "origin": "real",
                                 "actor": "human", "person": PERSON, "role": role, "source": "browser", "type": "click"}) + "\n")


def test_same_root_same_object_other_root_other_object_and_bounded(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert shared_source(a) is shared_source(a) and shared_source(a) is not shared_source(b)
    for i in range(sources._SHARED_MAX + 3):
        shared_source(tmp_path / f"r{i}")
    assert len(sources._SHARED) <= sources._SHARED_MAX


def test_a_second_load_is_the_same_object_and_a_changed_file_refreshes_it(tmp_path):
    _write_day(tmp_path, "2026-11-07", 6)
    src = shared_source(tmp_path)
    first = src.load(PERSON)
    assert first is not None and len(first.events) == 6
    assert src.load(PERSON) is first                                     # no re-read: the parsed events are kept
    assert shared_source(tmp_path).load(PERSON) is first                  # another caller, same root: same data
    _write_day(tmp_path, "2026-11-07", 3, start=6)                         # the capture appended to the day file: size and mtime change
    fresh = src.load(PERSON)
    assert fresh is not first and len(fresh.events) == 9
    _write_day(tmp_path, "2026-11-08", 2, start=9)                         # a new day file
    assert len(src.load(PERSON).events) == 11


def test_cached_result_equals_a_cold_one(tmp_path):
    _write_day(tmp_path, "2026-11-07", 12)
    warm = shared_source(tmp_path)
    warm.load(PERSON)
    cached = warm.load(PERSON)
    cold = PersonSource(tmp_path).load(PERSON)                            # a source that has never seen the files
    assert [e.id for e in cached.events] == [e.id for e in cold.events]
    assert (cached.role, cached.origin, cached.person) == (cold.role, cold.origin, cold.person)
    assert len(warm.episodes(cached)) == len(PersonSource(tmp_path).episodes(cold))
    assert warm.episodes(cached) is warm.episodes(cached)                  # episodes are kept too


def test_a_role_switch_is_picked_up(tmp_path):
    _write_day(tmp_path, "2026-11-07", 4, role="benefits-processor")
    src = shared_source(tmp_path)
    assert src.load(PERSON).role == "benefits-processor"
    _write_day(tmp_path, "2026-11-07", 3, role="programmer", start=4)
    pd = src.load(PERSON)
    assert pd.role == "programmer" and len(pd.events) == 3 and len(pd.earlier_events) == 4


def test_the_routes_use_the_shared_source(tmp_path, monkeypatch):
    from understudy_engine import routes_handoff as rh

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    assert rh._src() is rh._src() and rh._src() is shared_source(tmp_path)
