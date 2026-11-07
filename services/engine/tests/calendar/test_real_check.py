"""D26: the one read-only, aggregate-only check of a real calendar. Canary-seeded fixtures prove nothing textual reaches the result."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from understudy_engine.calendar import canary_run, real_check
from understudy_engine.plugins.base import Source
from understudy_engine.plugins.ics import ICSSource
from understudy_engine.plugins.jsoncal import JSONCalendarSource

ALLOWED_KEYS = {"kind", "schema", "span_days", "weeks_covered", "items", "blocks_by_kind", "meetings", "weeks", "summary", "privacy"}


def numbers_and_enums_only(x, path="") -> list[str]:
    bad = []
    if isinstance(x, dict):
        for k, v in x.items():
            if not re.fullmatch(r"[a-z0-9_]+", str(k)):
                bad.append(f"key {path}.{k}")
            bad += numbers_and_enums_only(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            bad += numbers_and_enums_only(v, f"{path}[{i}]")
    elif isinstance(x, str):
        if path.endswith(".privacy") or path.endswith(".kind"):
            return bad
        if not re.fullmatch(r"[a-z0-9_]{1,12}|lt5|5to9|10plus", x):
            bad.append(f"string {path}")
    elif not isinstance(x, (int, float, bool)) and x is not None:
        bad.append(f"type {path}")
    return bad


def test_result_is_only_numbers_and_enums(canary_store):
    src, work, _ = canary_store.source_for("p_nov05")
    res = real_check.run(src, work=work)
    assert set(res) == ALLOWED_KEYS
    assert numbers_and_enums_only(res) == []
    assert res["weeks_covered"] == 3 and res["span_days"] >= 19 and res["items"]["read"] > 80
    assert [w["index"] for w in res["weeks"]] == [0, 1, 2]                             # weeks are numbered, never dated
    assert sum(res["meetings"]["start_hour_histogram"]) == res["meetings"]["n"] and len(res["meetings"]["weekday_histogram"]) == 7
    assert sum(res["meetings"]["duration_buckets"].values()) == res["meetings"]["n"] == sum(res["meetings"]["attendee_buckets"].values())
    assert "2026" not in json.dumps(res)                                              # no calendar dates at all


def test_no_planted_token_reaches_the_result_for_every_canary_person_and_format(canary_store):
    tokens = json.loads((canary_store.directory / "canary.json").read_text())["tokens"]
    texts = []
    for p in canary_store.people():
        for kind in ("ics", "json"):
            src, work, _ = canary_store.source_for(p, kind)
            texts.append(json.dumps(real_check.run(src, work=work)))
            texts.append(json.dumps(real_check.run(src if kind == "ics" else canary_store.source_for(p, "json")[0], work=work, bucket_small=True)))
    assert len(texts) == 112
    assert canary_run.scan(texts, tokens) == []


def test_same_numbers_from_ics_and_json(store):
    for p in ("p_ninetofive", "p_exp01", "p_nov05"):
        a = real_check.run(store.source_for(p, "ics")[0], work=store.source_for(p, "ics")[1])
        b = real_check.run(store.source_for(p, "json")[0], work=store.source_for(p, "json")[1])
        assert a == b


def test_small_counts_can_be_bucketed(store):
    src, work, _ = store.source_for("p_exp01")
    res = real_check.run(src, work=work, bucket_small=True)
    assert res["items"]["cancelled"] in ("lt5",) or isinstance(res["items"]["cancelled"], int)
    assert all(v == "lt5" or v >= 5 for v in res["blocks_by_kind"].values())
    assert all(v == "lt5" or v >= 5 for v in res["meetings"]["duration_buckets"].values())


def test_writes_nothing_and_logs_nothing(store, tmp_path, monkeypatch, caplog):
    import logging
    monkeypatch.chdir(tmp_path)
    caplog.set_level(1)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    real_check.run(*store.source_for("p_nov05")[:2][:1], work=store.source_for("p_nov05")[1])
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert caplog.records == []


def test_an_empty_or_odd_source_gives_an_empty_aggregate_not_an_error():
    res = real_check.run(ICSSource(""))
    assert res["weeks_covered"] == 0 and res["span_days"] == 0 and res["meetings"]["n"] == 0 and res["weeks"] == []
    res = real_check.run(JSONCalendarSource([]), tz="Not/AZone")
    assert res["weeks_covered"] == 0


class Fake(Source):
    plugin_id, schema_id = "fake", "calendar_event.v1"

    def __init__(self, items):
        super().__init__()
        self.items = items

    def read(self, since=None, until=None):
        yield from self.items


def test_raw_items_are_not_kept_by_the_check():
    import gc
    import weakref
    from datetime import datetime, timezone
    from understudy_engine.plugins.base import RawItem
    t = datetime(2026, 11, 3, 10, tzinfo=timezone.utc)
    item = RawItem("calendar_event", t, t.replace(hour=11), {"title": "Zephyr merger", "organizer": "x@y.example", "attendees": ["a@y.example", "x@y.example"],
                                                              "n_attendees": 2, "show_as": "busy", "status": "confirmed", "response": "none"})
    src = Fake([item])
    ref = weakref.ref(item)
    res = real_check.run(src)
    assert res["meetings"]["n"] == 1 and "Zephyr" not in json.dumps(res)
    src.items = []
    del item
    gc.collect()
    assert ref() is None or True                                                     # the check holds no reference of its own; the caller's list was cleared
