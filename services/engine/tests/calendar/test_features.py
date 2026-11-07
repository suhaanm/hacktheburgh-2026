"""CAL-1: weekly features on hand-made blocks, normalisation rules, and the bucketing of what may leave."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from understudy_engine.calendar import features as F
from understudy_engine.calendar.model import Block, WorkConfig, attendee_bucket, monday_of, parse_week, week_label
from understudy_engine.calendar.normalize import classify, to_blocks
from understudy_engine.plugins.base import RawItem

UTC = timezone.utc
MON = date(2026, 11, 2)                      # a Monday, after the clock change


def blk(day_off, h0, m0, h1, m1, kind="meeting", tag="", n=3, rec=False, series="", ext=False, online=False, tz=UTC):
    d = MON + timedelta(days=day_off)
    s = datetime(d.year, d.month, d.day, h0, m0, tzinfo=tz).astimezone(UTC)
    e = datetime(d.year, d.month, d.day, h1, m1, tzinfo=tz).astimezone(UTC)
    return Block(s, e, kind, tag, n, rec, series, ext, online)


CFG = WorkConfig()                           # 09:00-17:30 Mon-Fri, peak 09:30-12:00, UTC


def week(blocks, cfg=CFG, off=frozenset()):
    return F.analyse_week(blocks, cfg, MON, off)


def test_empty_week_is_all_free():
    f = week([]).features
    assert f["meeting_h"] == 0 and f["focus_blocks_90"] == 5 and f["longest_focus_min"] == 510 and f["fragmentation"] == 0.0
    assert f["days_worked"] == 5 and f["back_to_back_runs"] == 0


def test_one_day_numbers_by_hand():
    # Mon: standup 09:00-09:15, meeting 10:00-11:00, meeting 11:05-11:35 (5 min gap = back to back), lunch 12:30-13:15, review 16:30-17:00
    bl = [blk(0, 9, 0, 9, 15, rec=True, series="s"), blk(0, 10, 0, 11, 0), blk(0, 11, 5, 11, 35), blk(0, 12, 30, 13, 15, "offscreen", n=1),
          blk(0, 16, 30, 17, 0, "focus", "review", n=1)]
    wa = week(bl)
    d = wa.days[0]
    assert d.segments == [(F.MEETING, 540, 555), (F.SLIVER, 555, 600), (F.MEETING, 600, 660), (F.MEETING, 665, 695), (F.SLIVER, 695, 750),
                          (F.OFFSCREEN, 750, 795), (F.FOCUS, 795, 990), (F.REVIEW, 990, 1020), (F.SLIVER, 1020, 1050)]
    assert d.metrics["meetings_n"] == 3 and d.metrics["meeting_min"] == 15 + 60 + 30
    assert d.metrics["b2b_runs"] == 1 and d.metrics["longest_b2b_min"] == 95
    assert d.metrics["review_slots"] == 1 and d.metrics["offscreen_min"] == 45
    # free runs: 09:15-10:00 (45), 11:35-12:30 (55), 13:15-17:30 (255; the review slot is free-like time); the 5 minutes between
    # 11:00 and 11:05 is a transition, not free time
    assert [e - s for s, e in d.free_runs] == [45, 55, 255]
    assert d.metrics["focus_60"] == 1 and d.metrics["focus_90"] == 1 and d.metrics["slivers"] == 2


def test_review_batch_and_off_screen_segments():
    bl = [blk(1, 9, 30, 11, 0, "focus", "batch", n=1), blk(1, 12, 30, 13, 15, "offscreen", n=1), blk(1, 16, 30, 17, 0, "focus", "review", n=1)]
    d = week(bl).days[1]
    assert [k for k, _, _ in d.segments] == [F.SLIVER, F.BATCH, F.FOCUS, F.OFFSCREEN, F.FOCUS, F.REVIEW, F.SLIVER]
    assert d.metrics["batch_windows"] == 1 and d.metrics["review_slots"] == 1


def test_fragmented_day_needs_four_meetings_and_no_hour_gap():
    frag = [blk(2, 9, 0, 9, 30), blk(2, 9, 50, 10, 20), blk(2, 10, 45, 11, 15), blk(2, 12, 0, 12, 30), blk(2, 13, 0, 13, 30), blk(2, 14, 0, 14, 30),
            blk(2, 14, 55, 15, 25), blk(2, 15, 50, 16, 20), blk(2, 16, 45, 17, 15)]
    # gaps: 09:00 start none; 20, 25, 45, 30, 30, 25, 25, 25, then 15 to 17:30 -> all under 60
    wa = week(frag)
    assert wa.features["fragmented_days"] == 1 and F.fragmented_day_indexes(wa) == [2]
    assert wa.days[2].metrics["fragmentation"] > 0.8
    busy_ok = [blk(3, 9, 15, 9, 45), blk(3, 10, 30, 11, 0), blk(3, 13, 0, 13, 30), blk(3, 14, 0, 14, 30)]       # 4 meetings, but 11:00-13:00 is free
    assert week(busy_ok).features["fragmented_days"] == 0
    three = frag[:3]
    assert week(three).features["fragmented_days"] == 0                                                         # fewer than four meetings


def test_fragmentation_index_extremes():
    one_block = week([blk(0, 9, 0, 9, 30)]).days[0].metrics["fragmentation"]
    many = week([blk(0, 9 + i, 0, 9 + i, 20) for i in range(8)]).days[0].metrics["fragmentation"]
    assert one_block < 0.15 < 0.8 < many <= 1.0
    full_day = week([blk(0, 9, 0, 17, 30)]).days[0].metrics["fragmentation"]
    assert full_day == 1.0                                                                                     # no usable time at all


def test_recurring_series_and_peak_window():
    rec = [blk(i, 10, 0, 10, 45, rec=True, series="alloc") for i in range(5)] + [blk(1, 14, 0, 14, 30, rec=True, series="one2one")]
    f = week(rec).features
    assert f["recurring_series"] == 2 and f["recurring_meeting_h"] == 4.25
    # peak is 09:30-12:00: five 45-minute recurring meetings inside it, the 14:00 one is outside
    assert f["recurring_in_peak_h"] == 3.75
    one_off = week([blk(0, 10, 0, 11, 0)]).features
    assert one_off["recurring_in_peak_h"] == 0 and one_off["recurring_series"] == 0


def test_external_unbuffered_only_when_the_gap_is_short():
    a = [blk(0, 14, 0, 14, 25), blk(0, 14, 32, 15, 15, ext=True)]               # 7 minutes: no buffer
    b = [blk(0, 14, 0, 14, 25), blk(0, 14, 40, 15, 15, ext=True)]               # 15 minutes: buffered
    c = [blk(0, 14, 0, 15, 0), blk(0, 14, 30, 15, 30, ext=True)]                # overlapping: unbuffered
    first = [blk(0, 9, 0, 9, 45, ext=True)]                                       # first of the day: fine
    assert week(a).features["external_unbuffered_n"] == 1
    assert week(b).features["external_unbuffered_n"] == 0
    assert week(c).features["external_unbuffered_n"] == 1
    assert week(first).features["external_unbuffered_n"] == 0


def test_outside_hours_work_span_off_computer_and_day_off():
    bl = [blk(0, 17, 45, 18, 45), blk(5, 10, 0, 11, 0), blk(1, 9, 0, 9, 30), blk(1, 16, 0, 16, 30), blk(2, 12, 0, 12, 45, "offscreen", n=1)]
    f = week(bl).features
    assert f["outside_hours_h"] == 2.0                                    # Monday evening hour plus the Saturday hour
    assert f["offscreen_h"] == 0.75
    assert f["work_span_h"] == pytest.approx(7.5, abs=0.01)               # only Tuesday has two commitments: 09:00 to 16:30
    f2 = week([blk(3, 9, 0, 17, 0)], off=frozenset({MON + timedelta(days=3)})).features
    assert f2["days_worked"] == 4 and f2["outside_hours_h"] == 8.0        # a meeting booked on a day off counts as outside hours


def test_meeting_over_midnight_is_split_by_local_day():
    d = week([Block(datetime(2026, 11, 2, 23, 0, tzinfo=UTC), datetime(2026, 11, 3, 1, 0, tzinfo=UTC), "meeting", "", 3, False, "", False, True)])
    assert d.days[0].metrics["meeting_min"] == 60 and d.days[1].metrics["meeting_min"] == 60


def test_wall_clock_survives_a_clock_change():
    lon = ZoneInfo("Europe/London")
    cfg = WorkConfig(tz=lon, tz_name="Europe/London")
    sun_change = date(2026, 10, 19)          # a Monday before the change (BST) and one after
    bst = Block(datetime(2026, 10, 19, 9, 0, tzinfo=lon).astimezone(UTC), datetime(2026, 10, 19, 10, 0, tzinfo=lon).astimezone(UTC), "meeting", "", 3, False, "", False, False)
    gmt = Block(datetime(2026, 11, 2, 9, 0, tzinfo=lon).astimezone(UTC), datetime(2026, 11, 2, 10, 0, tzinfo=lon).astimezone(UTC), "meeting", "", 3, False, "", False, False)
    assert bst.start.hour == 8 and gmt.start.hour == 9
    a = F.analyse_week([bst], cfg, sun_change).days[0].segments[0]
    b = F.analyse_week([gmt], cfg, MON).days[0].segments[0]
    assert a == b == (F.MEETING, 540, 600)


def test_week_labels():
    assert monday_of(date(2026, 11, 5)) == MON and week_label(MON) == "2026-W45"
    assert parse_week("2026-W45") == MON and parse_week("2026-11-06") == MON and parse_week(None) is None
    assert attendee_bucket(3) == "lt5" and attendee_bucket(7) == "5to9" and attendee_bucket(12) == "10plus"


# ---------------------------------------------------------------------------------------------------- normalisation
def item(title, n=3, show_as="busy", status="confirmed", response="none", all_day=False, online=False, minutes=45, recurring=False, series="",
         organizer="boss@fenwick.example", attendees=None):
    t0 = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    atts = attendees if attendees is not None else [f"p{i}@fenwick.example" for i in range(max(0, n - 1))]
    return RawItem("calendar_event", t0, t0 + timedelta(minutes=minutes), {
        "title": title, "organizer": organizer, "attendees": atts, "location": "", "series_id": series, "source_id": "x", "n_attendees": n,
        "all_day": all_day, "recurring": recurring, "online": online, "show_as": show_as, "status": status, "response": response,
        "provider": "teams" if online else "none", "sensitivity": "normal"})


@pytest.mark.parametrize("title,n,kind,tag", [
    ("Lunch", 1, "offscreen", ""), ("Walk with Sam", 1, "offscreen", ""), ("Dentist appointment", 1, "offscreen", ""),
    ("Coffee break", 1, "break", ""), ("Focus time: reports", 1, "focus", ""), ("Deep work", 1, "focus", ""),
    ("Batch: calculator entries", 1, "focus", "batch"), ("End-of-day queue review", 1, "focus", "review"),
    ("Prepare slides", 1, "focus", ""),                       # any other solo hold is the owner's own time
    ("Lunch with the audit team", 4, "meeting", ""),            # with others it is a meeting whatever the words
    ("Design review", 3, "meeting", ""), ("Review slot", 2, "meeting", ""),
])
def test_classification_rules(title, n, kind, tag):
    assert classify(title, n, "busy", False, 45) == (kind, tag)


def test_online_join_link_makes_it_a_meeting_and_oof_is_offscreen():
    assert classify("Focus time", 1, "busy", True, 45) == ("meeting", "")
    assert classify("Anything", 1, "oof", False, 45) == ("offscreen", "")


def test_normalisation_drops_cancelled_declined_free_and_all_day():
    items = [item("A meeting"), item("Cancelled", status="cancelled"), item("Declined", response="declined"), item("Placeholder", show_as="free"),
             item("Birthday", all_day=True, show_as="free", n=1), item("Annual leave", all_day=True, show_as="oof", n=1, minutes=1440)]
    blocks, off, stats = to_blocks(items)
    assert [b.kind for b in blocks] == ["meeting"]
    assert stats.cancelled == 1 and stats.declined == 1 and stats.free_skipped == 1 and stats.all_day_skipped == 1 and stats.days_off == 1
    assert off == frozenset({date(2026, 11, 3)})
    assert stats.as_dict()["by_kind"] == {"meeting": 1}


def test_external_means_a_domain_other_than_the_majority_one():
    ext = item("Supplier call", organizer="boss@fenwick.example", attendees=["a@fenwick.example", "b@fenwick.example", "vendor@kestrelcharity.example"], n=4)
    internal = item("Team sync")
    blocks, _, _ = to_blocks([internal, internal, ext])
    assert [b.external for b in blocks] == [False, False, True] or sorted(b.external for b in blocks) == [False, False, True]


def test_blocks_carry_no_text():
    fields = {f.name: f for f in dataclasses.fields(Block)}
    assert set(fields) == {"start", "end", "kind", "tag", "n_attendees", "recurring", "series", "external", "online"}
    blocks, _, _ = to_blocks([item("Secret merger with Zephyr Holdings", recurring=True, series="UID-ZEPHYR-1", online=True)])
    b = blocks[0]
    text = repr(b) + str(dataclasses.asdict(b))
    assert "Zephyr" not in text and "merger" not in text and "UID" not in text and "fenwick" not in text
    assert len(b.series) == 16 and all(c in "0123456789abcdef" for c in b.series)       # an opaque salted hash, never emitted


def test_series_key_is_not_stable_across_processes_but_stable_within_one():
    a, _, _ = to_blocks([item("x", recurring=True, series="S1")])
    b, _, _ = to_blocks([item("y", recurring=True, series="S1")])
    c, _, _ = to_blocks([item("x", recurring=True, series="S2")])
    assert a[0].series == b[0].series != c[0].series


# ---------------------------------------------------------------------------------------------------- what may leave
def test_safe_features_are_bucketed():
    f = {"meeting_h": 7.83, "focus_blocks_60": 3, "focus_blocks_90": 12, "longest_focus_min": 187, "fragmentation": 0.683, "back_to_back_runs": 4,
         "work_span_h": 8.07, "offscreen_h": 3.0}
    s = F.safe_features(f)
    assert s["focus_blocks_60"] == "lt5" and s["back_to_back_runs"] == "lt5" and s["focus_blocks_90"] == 12
    assert s["longest_focus_min"] % 5 == 0 and s["fragmentation"] == 0.7
    assert all(round(s[k] * 60) % 5 == 0 for k in ("meeting_h", "work_span_h", "offscreen_h"))


@pytest.mark.parametrize("n", range(0, 30))
def test_count_bucket_property(n):
    from understudy_engine.calendar.bucket import bucket_count
    assert bucket_count(n) == ("lt5" if n < 5 else n)


def test_features_contain_only_numbers():
    f = week([blk(0, 9, 0, 10, 0, rec=True, series="k")]).features
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in f.values())
    assert set(F.CONTRACT_KEYS) <= set(f) and set(f) == set(F.ALL_KEYS)
