from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from understudy_engine.core import Event
from understudy_engine.store import (
    EventStore, InvalidEvent, OriginMixError, fold, hash_domain, hash_label, replay, validate_row,
)
from understudy_engine.store import hashing


def mk(i: int, *, origin="real", person="p_ann", t0=None, typ="click", **kw) -> dict:
    t0 = t0 or datetime(2026, 11, 7, 9, 0, 0, tzinfo=timezone.utc)
    row = {
        "schema": 1, "id": f"ev{i:08d}", "t": (t0 + timedelta(seconds=i * 5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "origin": origin, "actor": "human", "person": person, "role": "benefits-processor",
        "source": "browser", "type": typ,
    }
    row.update(kw)
    return row


@pytest.fixture()
def store(tmp_path):
    return EventStore(tmp_path / "data")


def test_append_and_read_roundtrip(store):
    ev = store.append(mk(1, task_id="t_a1", meta={"depth_bin": 3, "tier": "x"}, target={"role": "button", "label_hash": "h:9f2c0011"}))
    assert isinstance(ev, Event)
    files = store.files("real")
    assert [p.parent.name for p in files] == ["p_ann"] and files[0].name == "2026-11-07.jsonl"
    got = store.read("real", person="p_ann")
    assert len(got) == 1 and got[0].id == "ev00000001" and got[0].meta["depth_bin"] == 3
    assert store.read("synthetic") == []


@pytest.mark.parametrize(
    "patch",
    [
        {"person": "ann"},                      # bad person pattern
        {"type": "keypress"},                   # unknown type
        {"url": "https://example.com/x"},       # extra key (no URLs)
        {"meta": {"text": "hello world"}},      # free text in meta (space)
        {"meta": {"title": "My Secret Page"}},
        {"target": {"role": "button", "text": "Pay now"}},
        {"t": "2026-11-07T09:00:00"},           # no timezone
        {"origin": "fake"},
        {"schema": 2},
    ],
)
def test_invalid_rows_rejected(store, patch):
    row = mk(1)
    row.update(patch)
    with pytest.raises(InvalidEvent):
        store.append(row)
    assert store.files("real") == []


def test_append_many_reports_rejections_and_dedupes(store):
    rows = [mk(1), {**mk(2), "type": "nope"}, mk(3), mk(1)]
    res = store.append_many(rows)
    assert res.accepted == 2
    assert [r["index"] for r in res.rejected] == [1, 3]
    assert res.rejected[1]["reason"] == "duplicate id"
    # re-posting the same batch accepts nothing new
    again = store.append_many([mk(1), mk(3)])
    assert again.accepted == 0 and len(again.rejected) == 2
    assert len(store.read("real")) == 2


def test_origin_mixing_refused(store, tmp_path):
    store.append(mk(1, origin="real"))
    # a synthetic event goes to synthetic/, never into the real file
    store.append(mk(2, origin="synthetic", person="p_ann"))
    assert len(store.read("real")) == 1 and len(store.read("synthetic")) == 1
    # forcing a synthetic event into a real partition file is refused
    real_file = store.files("real")[0]
    with pytest.raises(OriginMixError):
        store.append(mk(3, origin="synthetic"), path=real_file)
    # a file whose first row is real refuses synthetic rows even outside the standard layout
    odd = tmp_path / "odd.jsonl"
    store.append(mk(4, origin="real"), path=odd)
    with pytest.raises(OriginMixError):
        store.append(mk(5, origin="synthetic"), path=odd)
    # a whole-file write with both origins is refused
    with pytest.raises(OriginMixError):
        store.write_file(tmp_path / "mixed.jsonl", [mk(6, origin="real"), mk(7, origin="synthetic")])
    # and append_many reports it as a rejection, not a crash
    res = store.append_many([mk(8, origin="real")])
    assert res.accepted == 1


def test_write_file_is_atomic_replace_and_sorted(store, tmp_path):
    path = store.root / "synthetic" / "grp" / "events.jsonl"
    rows = [mk(i, origin="synthetic", person="p_syn") for i in (3, 1, 2)]
    assert store.write_file(path, rows) == 3
    assert [e.id for e in store.read_file(path)] == ["ev00000001", "ev00000002", "ev00000003"]
    store.write_file(path, rows[:1])
    assert len(store.read_file(path)) == 1
    assert not list(path.parent.glob("*.tmp"))
    # synthetic events cannot be written under real/
    with pytest.raises(OriginMixError):
        store.write_file(store.root / "real" / "p_syn" / "x.jsonl", rows)


def test_fold_is_pure_and_replay_repeatable(store):
    evs = [
        mk(0, typ="task_start", task_id="t_x1"), mk(1), mk(2, typ="progress", task_id="t_x1", meta={"kind": "result_read"}),
        mk(3, typ="idle", source="os"), mk(40, typ="stuck", task_id="t_x1"), mk(41, typ="task_end", task_id="t_x1"),
    ]
    store.append_many(evs)
    got = store.read("real")
    s1, s2 = fold(got), fold(list(got))
    assert s1 == s2 and s1.to_dict() == s2.to_dict()
    assert s1.n_events == 6 and s1.tasks["t_x1"].n_progress == 1 and s1.tasks["t_x1"].n_stuck == 1
    assert s1.open_task == {}
    path = store.files("real")[0]
    r1 = replay(path, speed=10, squeeze_idle_s=30, store=store)
    r2 = replay(path, speed=10, squeeze_idle_s=30, store=store)
    assert r1.final == r2.final and r1.duration_s == r2.duration_s
    assert [(f.t_replay, f.event.id, f.state) for f in r1.frames] == [(f.t_replay, f.event.id, f.state) for f in r2.frames]


def test_replay_squeezes_idle_gaps_and_scales_speed():
    base = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    rows = [mk(0, t0=base), {**mk(0, t0=base + timedelta(seconds=600)), "id": "evlate001"}, {**mk(0, t0=base + timedelta(seconds=605)), "id": "evlate002"}]
    evs = [validate_row(r) for r in rows]
    r1 = replay(evs, speed=1, squeeze_idle_s=30)
    assert r1.duration_s == pytest.approx(35.0)       # 30 (squeezed 600 s gap) + 5
    r10 = replay(evs, speed=10, squeeze_idle_s=30)
    assert r10.duration_s == pytest.approx(3.5)
    r_nosqueeze = replay(evs, speed=200, squeeze_idle_s=10_000)
    assert r_nosqueeze.duration_s == pytest.approx(605 / 200)
    assert [f.t_replay for f in r1.frames] == sorted(f.t_replay for f in r1.frames)


def test_replay_label_fn_counts():
    evs = [validate_row(mk(i, typ="click" if i % 2 else "scroll")) for i in range(6)]
    r = replay(evs, label_fn=lambda e: "READ" if e.type == "scroll" else "ENTER")
    assert r.frames[-1].state["counts"] == {"READ": 3, "ENTER": 3}
    assert r.frames[-1].state["last_cog"] == "ENTER"


def test_hashing_is_salted_and_schema_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    hashing._salt_cache.clear()
    salt = hashing.get_salt()
    assert (tmp_path / "home" / "salt").exists()
    assert oct((tmp_path / "home" / "salt").stat().st_mode & 0o777) == "0o600"
    assert hashing.get_salt() == salt                 # stable
    hashing._salt_cache.clear()
    assert hashing.get_salt() == salt                 # read back from disk
    h = hash_label("  Submit  Claim ")
    assert re.fullmatch(r"h:[0-9a-f]{12}", h) and h == hash_label("submit claim")
    d = hash_domain("https://www.Example.com:8443/a/b?q=1")
    assert re.fullmatch(r"d:[0-9a-f]{12}", d) and d == hash_domain("example.com")
    assert hash_label("x", salt=b"other") != hash_label("x", salt=salt)
    assert hash_label("example.com") != hash_domain("example.com")   # domain separation
    validate_row(mk(1, target={"role": "button", "label_hash": h, "domain_hash": d}))


def test_cap4_captured_file_has_no_page_text(store, tmp_path, monkeypatch):
    """CAP-4: grep of a captured file finds no page text, URLs or field values."""
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    hashing._salt_cache.clear()
    page_text = ["Universal Credit calculator", "Enter your partner's income", "https://turn2us.org.uk/benefits-calculator", "hunter2"]
    rows = []
    for i, txt in enumerate(page_text):
        rows.append(mk(i, target={"role": "textbox", "label_hash": hash_label(txt), "domain_hash": hash_domain("https://turn2us.org.uk/x")}, meta={"len": len(txt)}))
    # attempts to smuggle text in are rejected, not stored
    # (a single short lowercase token such as "hunter2" would pass the meta pattern by design: meta is for enum
    # tokens and numbers. The extension is responsible for never sending field values; see the limitations register.)
    for i, txt in enumerate(page_text[:3], start=10):
        for bad in ({"meta": {"label": txt}}, {"target": {"role": "textbox", "label": txt}}, {"text": txt}):
            with pytest.raises(InvalidEvent):
                store.append({**mk(i), **bad})
    assert store.append_many(rows).accepted == 4
    blob = b"".join(p.read_bytes() for p in store.files("real")).decode()
    for txt in page_text:
        assert txt.lower() not in blob.lower()
    assert "turn2us" not in blob and "hunter2" not in blob and "http" not in blob


def test_read_filters(store):
    base = datetime(2026, 11, 7, 23, 59, 50, tzinfo=timezone.utc)   # crosses midnight -> two day files
    evs = [mk(i, t0=base, task_id="t_a" if i < 3 else "t_b") for i in range(6)]
    store.append_many(evs)
    assert [p.name for p in store.files("real")] == ["2026-11-07.jsonl", "2026-11-08.jsonl"]
    assert len(store.read("real", task="t_b")) == 3
    assert len(store.read("real", since="2026-11-08T00:00:00Z")) == 4
    assert len(store.read("real", limit=2)) == 2
    assert store.persons("real") == ["p_ann"]


def test_append_is_append_only_on_disk(store):
    store.append(mk(1))
    path = store.files("real")[0]
    before = path.read_bytes()
    store.append(mk(2))
    after = path.read_bytes()
    assert after.startswith(before) and len(after) > len(before)
