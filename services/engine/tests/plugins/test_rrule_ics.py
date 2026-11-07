"""ICS parsing and recurrence expansion on hand-written, real-looking calendar text."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


from understudy_engine.plugins.base import RawItem
from understudy_engine.plugins.ics import ICSSource, parse_duration, parse_line, unfold, unescape

UTC = timezone.utc
FIX = Path(__file__).parent / "fixtures"


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def read(text, **kw):
    return list(ICSSource(text, **kw).read())


def wrap(*events, tz=""):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n" + tz + "".join(events) + "END:VCALENDAR\r\n"


def vev(*lines):
    return "BEGIN:VEVENT\r\n" + "".join(l + "\r\n" for l in lines) + "END:VEVENT\r\n"


def test_unfold_and_params_and_escapes():
    assert unfold("DESCRIPTION:aaa\r\n bbb\r\n\tccc\r\nX:1") == ["DESCRIPTION:aaabbbccc", "X:1"]
    p = parse_line('ATTENDEE;CN="Last\\, First: Dr";PARTSTAT=ACCEPTED:mailto:a@x.example')
    assert p.name == "ATTENDEE" and p.params["CN"] == "Last\\, First: Dr" and p.value == "mailto:a@x.example"
    bs = chr(92)
    assert unescape("a" + bs + ", b" + bs + "; c" + bs + "nline2" + bs + bs) == "a, b; c\nline2" + bs
    assert parse_duration("PT1H30M").total_seconds() == 5400
    assert parse_duration("P1DT2H").total_seconds() == 26 * 3600
    assert parse_duration("nonsense") is None


def test_outlook_export_fixture_end_to_end():
    src = ICSSource(path=FIX / "outlook_export.ics", default_tz="Europe/London", self_email="me@fenwick.example")
    items = list(src.read())
    titles = [(i.t0, i.fields["title"]) for i in items]
    # series: Mon 19 Oct BST 09:00 -> 08:00Z; Wed 21 Oct moved to 10:00 BST -> 09:00Z; Mon 26 Oct is EXDATE; Wed 28 Oct GMT 09:00 -> 09:00Z;
    # Mon 2 Nov, Wed 4 Nov, Mon 9 Nov, Wed 11 Nov in GMT; UNTIL 11 Nov 23:59:59Z keeps the 11th
    huddle = sorted(i.t0 for i in items if i.fields["recurring"])
    assert huddle == [utc(2026, 10, 19, 8), utc(2026, 10, 21, 9), utc(2026, 10, 28, 9), utc(2026, 11, 2, 9), utc(2026, 11, 4, 9),
                      utc(2026, 11, 9, 9), utc(2026, 11, 11, 9)]
    moved = next(i for i in items if i.t0 == utc(2026, 10, 21, 9))
    assert moved.fields["title"] == "Casework huddle (moved)"
    first = next(i for i in items if i.t0 == utc(2026, 10, 19, 8))
    assert first.duration_s == 1800 and first.fields["title"] == "Casework huddle, Monday and Wednesday"
    assert first.fields["provider"] == "teams" and first.fields["online"] is True
    assert first.fields["n_attendees"] == 3                      # organiser + two attendees, distinct
    # the declined workshop is reported as declined for the owner; DURATION gives the end
    ws = next(i for i in items if i.fields["title"] == "Quarter planning workshop")
    assert ws.fields["response"] == "declined" and ws.duration_s == 5400
    assert ws.t0 == utc(2026, 10, 22, 13)
    # cancelled stays visible as status cancelled (normalisation drops it)
    assert next(i for i in items if i.fields["title"] == "Supplier call").fields["status"] == "cancelled"
    # all-day out of office
    ooo = next(i for i in items if i.fields["title"] == "Annual leave")
    assert ooo.fields["all_day"] is True and ooo.fields["show_as"] == "oof" and ooo.duration_s == 86400
    # floating time uses the default zone (London on 26 Oct is GMT) and the VALARM description is not read as the event's
    lunch = next(i for i in items if i.fields["title"] == "Lunch")
    assert lunch.t0 == utc(2026, 10, 26, 12) and lunch.fields["location"] == ""
    assert "Tamsin" not in repr(lunch.fields["title"]) and all("Reminder" not in str(v) for v in lunch.fields.values())
    # a description is scanned for a join link and never kept
    assert not any("allocation of the new" in str(v) for it in items for v in it.fields.values())
    assert [t for _, t in titles][0]                                  # sorted by start
    assert [i.t0 for i in items] == sorted(i.t0 for i in items)
    assert src.stats["events_read"] == len(items)


def test_dst_changes_on_25_october_for_a_london_series():
    text = wrap(vev("UID:s1", "DTSTART;TZID=Europe/London:20261022T093000", "DTEND;TZID=Europe/London:20261022T100000",
                    "RRULE:FREQ=DAILY;COUNT=6", "SUMMARY:Stand-up"))
    got = [i.t0 for i in read(text)]
    assert got[0] == utc(2026, 10, 22, 8, 30)          # BST
    assert got[2] == utc(2026, 10, 24, 8, 30)          # Saturday, still BST
    assert got[3] == utc(2026, 10, 25, 9, 30)          # clock change: 25 Oct 01:00 UTC; wall time stays 09:30
    assert got[5] == utc(2026, 10, 27, 9, 30)


def test_weekly_byday_count_interval_until():
    t = lambda rr: wrap(vev("UID:a", "DTSTART:20261012T090000Z", "DTEND:20261012T091500Z", f"RRULE:{rr}", "SUMMARY:x"))
    assert [i.t0.day for i in read(t("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=7"))] == [12, 14, 16, 19, 21, 23, 26]
    assert [i.t0.day for i in read(t("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;COUNT=3"))] == [12, 26, 9]       # 9 Nov
    assert [i.t0.day for i in read(t("FREQ=DAILY;UNTIL=20261015T090000Z"))] == [12, 13, 14, 15]
    assert [i.t0.day for i in read(t("FREQ=DAILY;UNTIL=20261014"))] == [12, 13, 14]                   # bare-date UNTIL


def test_monthly_rules_and_setpos():
    t = lambda start, rr: wrap(vev("UID:m", f"DTSTART:{start}", "DURATION:PT1H", f"RRULE:{rr}", "SUMMARY:x"))
    last_fri = [i.t0 for i in read(t("20261030T150000Z", "FREQ=MONTHLY;BYDAY=-1FR;COUNT=4"))]
    assert [(d.month, d.day) for d in last_fri] == [(10, 30), (11, 27), (12, 25), (1, 29)]
    second_tue = [i.t0 for i in read(t("20261013T100000Z", "FREQ=MONTHLY;BYDAY=2TU;COUNT=3"))]
    assert [(d.month, d.day) for d in second_tue] == [(10, 13), (11, 10), (12, 8)]
    d31 = [i.t0 for i in read(t("20261031T090000Z", "FREQ=MONTHLY;BYMONTHDAY=31;COUNT=3"))]
    assert [(d.month, d.day) for d in d31] == [(10, 31), (12, 31), (1, 31)]                          # months without a 31st are skipped
    last_weekday = [i.t0 for i in read(t("20261030T090000Z", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=3"))]
    assert [(d.month, d.day) for d in last_weekday] == [(10, 30), (11, 30), (12, 31)]
    yearly = [i.t0 for i in read(t("20261105T090000Z", "FREQ=YEARLY;COUNT=3"))]
    assert [d.year for d in yearly] == [2026, 2027, 2028]


def test_exdate_rdate_override_and_cancelled_exception():
    master = vev("UID:u1", "DTSTART:20261012T090000Z", "DTEND:20261012T093000Z", "RRULE:FREQ=DAILY;COUNT=5",
                 "EXDATE:20261013T090000Z", "RDATE:20261020T090000Z", "SUMMARY:Series")
    moved = vev("UID:u1", "RECURRENCE-ID:20261014T090000Z", "DTSTART:20261014T150000Z", "DTEND:20261014T153000Z", "SUMMARY:Moved")
    cancelled = vev("UID:u1", "RECURRENCE-ID:20261015T090000Z", "DTSTART:20261015T090000Z", "DTEND:20261015T093000Z",
                    "STATUS:CANCELLED", "SUMMARY:Gone")
    items = read(wrap(master, moved, cancelled))
    starts = [(i.t0.day, i.t0.hour, i.fields["status"]) for i in items]
    assert (13, 9, "confirmed") not in starts                       # EXDATE removed it
    assert (14, 15, "confirmed") in starts and (14, 9, "confirmed") not in starts
    assert (15, 9, "cancelled") in starts                           # a cancelled exception is kept as cancelled (normalisation counts and drops it)
    assert (20, 9, "confirmed") in starts                           # RDATE added
    assert (12, 9, "confirmed") in starts and (16, 9, "confirmed") in starts


def test_unsupported_rule_degrades_to_one_event_and_is_counted():
    src = ICSSource(wrap(vev("UID:x", "DTSTART:20261012T090000Z", "DTEND:20261012T093000Z", "RRULE:FREQ=HOURLY;COUNT=4", "SUMMARY:x")))
    assert len(list(src.read())) == 1 and src.stats["rrule_unsupported_single_event"] == 1


def test_since_until_window_and_open_ended_series():
    text = wrap(vev("UID:w", "DTSTART:20261012T090000Z", "DTEND:20261012T093000Z", "RRULE:FREQ=WEEKLY;BYDAY=MO", "SUMMARY:x"))
    got = [i.t0.day for i in read(text, horizon_days=60)]
    assert got[:3] == [12, 19, 26] and len(got) >= 8                        # open-ended: bounded by the horizon
    some = [i.t0 for i in ICSSource(text, horizon_days=60).read(since=utc(2026, 10, 20), until=utc(2026, 11, 3))]
    assert some == [utc(2026, 10, 26, 9), utc(2026, 11, 2, 9)]


def test_all_day_and_timezone_fallbacks():
    odd = wrap(vev("UID:z", "DTSTART;TZID=Made Up Standard Time:20261012T090000", "DTEND;TZID=Made Up Standard Time:20261012T100000", "SUMMARY:x"))
    src = ICSSource(odd, default_tz="Europe/London")
    assert [i.t0 for i in src.read()] == [utc(2026, 10, 12, 8)]               # default zone used, counted
    assert src.stats["tz_unknown_default_used"] >= 1
    mozilla = wrap(vev("UID:z", "DTSTART;TZID=/mozilla.org/20050126_1/Europe/London:20261012T090000", "DTEND;TZID=/mozilla.org/20050126_1/Europe/London:20261012T100000", "SUMMARY:x"))
    assert [i.t0 for i in read(mozilla)] == [utc(2026, 10, 12, 8)]
    vtz = ("BEGIN:VTIMEZONE\r\nTZID:Custom Zone\r\nBEGIN:STANDARD\r\nDTSTART:16010101T000000\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0200\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n")
    custom = wrap(vev("UID:z", "DTSTART;TZID=Custom Zone:20261012T090000", "DTEND;TZID=Custom Zone:20261012T100000", "SUMMARY:x"), tz=vtz)
    cs = ICSSource(custom)
    assert [i.t0 for i in cs.read()] == [utc(2026, 10, 12, 7)] and cs.stats["tz_vtimezone_used"] >= 1


def test_bad_input_never_raises_and_never_echoes_content():
    garbage = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:g\r\nDTSTART:not-a-date SECRET-TITLE\r\nSUMMARY:SECRET-TITLE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    src = ICSSource(garbage)
    assert list(src.read()) == []
    assert all("SECRET" not in k for k in src.stats)
    assert list(ICSSource("").read()) == []
    assert list(ICSSource("not a calendar at all").read()) == []


def test_item_repr_hides_fields():
    it = read(wrap(vev("UID:r", "DTSTART:20261012T090000Z", "DTEND:20261012T093000Z", "SUMMARY:Top secret merger", "LOCATION:Vault")))[0]
    assert isinstance(it, RawItem)
    assert "secret" not in repr(it) and "secret" not in str(it) and "Vault" not in repr(it) and "withheld" in repr(it)
    assert it.fields["title"] == "Top secret merger"


def test_outlook_display_name_zone_follows_its_vtimezone_rules_across_the_clock_change():
    """Outlook desktop exports name a zone by its display text; only the file's VTIMEZONE says what it is. The rules (last Sunday of March and
    October) must be followed, so 09:00 stays 09:00 local before and after 25 Oct 2026."""
    tzid = "(UTC+00:00) Dublin, Edinburgh, Lisbon, London"
    vtz = ("BEGIN:VTIMEZONE\r\nTZID:" + tzid + "\r\nBEGIN:STANDARD\r\nDTSTART:16011028T020000\r\nRRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10\r\n"
           "TZOFFSETFROM:+0100\r\nTZOFFSETTO:+0000\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:16010325T010000\r\nRRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3\r\n"
           "TZOFFSETFROM:+0000\r\nTZOFFSETTO:+0100\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\n")
    text = wrap(vev("UID:d", "DTSTART;TZID=\"" + tzid + "\":20261022T090000", "DTEND;TZID=\"" + tzid + "\":20261022T100000", "RRULE:FREQ=DAILY;COUNT=6", "SUMMARY:x"), tz=vtz)
    src = ICSSource(text)
    got = [i.t0 for i in src.read()]
    assert got[:3] == [utc(2026, 10, 22, 8), utc(2026, 10, 23, 8), utc(2026, 10, 24, 8)]            # still summer time
    assert got[3:] == [utc(2026, 10, 25, 9), utc(2026, 10, 26, 9), utc(2026, 10, 27, 9)]            # clock change on the 25th
    assert src.stats["tz_vtimezone_used"] >= 1
    spring = wrap(vev("UID:s", "DTSTART;TZID=\"" + tzid + "\":20270401T090000", "DTEND;TZID=\"" + tzid + "\":20270401T100000", "SUMMARY:x"), tz=vtz)
    assert [i.t0 for i in read(spring)] == [utc(2027, 4, 1, 8)]
