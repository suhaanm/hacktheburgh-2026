"""PLG-2: Microsoft Graph adapters on recorded fake responses. No network, no real account, no MSAL."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from understudy_engine.calendar.normalize import to_blocks
from understudy_engine.plugins.base import SourceError
from understudy_engine.plugins.graph_common import GraphHTTPError, default_fetch, parse_graph_dt
from understudy_engine.plugins.graph_outlook import OutlookGraphSource
from understudy_engine.plugins.graph_teams import TeamsMeetingsSource

UTC = timezone.utc
FIX = Path(__file__).parent / "fixtures"
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.FAKE-TEST-TOKEN-ONLY.sig"
SINCE, UNTIL = datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)


def fx(name):
    return json.loads((FIX / name).read_text())


class FakeGraph:
    """Records every call (url and headers) and answers from recorded files, in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def outlook(fake, **kw):
    return OutlookGraphSource(lambda: TOKEN, fake, sleep=lambda s: None, **kw)


def test_request_shape_paging_and_read_only_headers():
    fake = FakeGraph(fx("outlook_calendarview_page1.json"), fx("outlook_calendarview_page2.json"))
    src = outlook(fake)
    items = list(src.read(SINCE, UNTIL))
    assert len(fake.calls) == 2 and src.stats["pages"] == 2
    q = parse_qs(urlparse(fake.calls[0][0]).query)
    assert urlparse(fake.calls[0][0]).path == "/v1.0/me/calendarView" and urlparse(fake.calls[0][0]).hostname == "graph.microsoft.com"
    assert q["startDateTime"] == ["2026-11-02T00:00:00Z"] and q["endDateTime"] == ["2026-11-09T00:00:00Z"] and q["$top"] == ["50"]
    assert "attendees" in q["$select"][0] and "body" not in q["$select"][0]            # no message bodies are requested
    assert fake.calls[0][1]["Authorization"] == f"Bearer {TOKEN}" and fake.calls[0][1]["Prefer"] == 'outlook.timezone="UTC"'
    assert fake.calls[1][0].endswith("$skip=6")                                         # followed the next link
    assert len(items) == 9 and [i.t0 for i in items] == sorted(i.t0 for i in items)


def test_event_mapping_zones_and_enums():
    fake = FakeGraph(fx("outlook_calendarview_page1.json"), fx("outlook_calendarview_page2.json"))
    src = outlook(fake)
    items = {i.fields["title"]: i for i in src.read(SINCE, UNTIL)}
    huddle = items["Casework huddle"]
    assert huddle.t0 == datetime(2026, 11, 2, 9, tzinfo=UTC)                           # GMT Standard Time in November is UTC
    assert huddle.fields["provider"] == "teams" and huddle.fields["online"] is True and huddle.fields["n_attendees"] == 4
    assert huddle.fields["location"] == "Microsoft Teams Meeting" and huddle.fields["recurring"] is False
    series = items["Weekly planning (series)"]
    assert series.fields["recurring"] is True and series.fields["series_id"] == "AAMkAGI2Master01="
    assert items["Client workshop"].t0 == datetime(2026, 11, 3, 17, tzinfo=UTC)         # Pacific Standard Time, UTC-8 after 1 Nov
    odd = items["Odd zone meeting"]
    assert odd.t0 == datetime(2026, 11, 3, 13, tzinfo=UTC) and src.stats["tz_unknown_default_used"] == 1
    assert items["Annual leave"].fields["all_day"] is True and items["Annual leave"].fields["show_as"] == "oof"
    assert items["Hold: training"].fields["show_as"] == "tentative" and items["Hold: training"].fields["response"] == "tentative"
    assert items["Quarter planning workshop"].fields["response"] == "declined"
    assert items["Lunch"].fields["response"] == "organizer" and items["Possible catch-up"].fields["show_as"] == "free"
    assert "Supplier call: housing association" not in items and src.stats["cancelled_skipped"] == 1


def test_graph_items_flow_through_normalisation():
    fake = FakeGraph(fx("outlook_calendarview_page1.json"), fx("outlook_calendarview_page2.json"))
    blocks, off, stats = to_blocks(outlook(fake).read(SINCE, UNTIL))
    assert stats.declined == 1 and stats.free_skipped == 1 and stats.days_off == 1 and off
    kinds = sorted(b.kind for b in blocks)
    # the huddle, the series occurrence and the client workshop have other people; the odd-zone entry and the training hold are solo (the
    # owner's own time); lunch is off-screen
    assert kinds == ["focus", "focus", "meeting", "meeting", "meeting", "offscreen"]
    assert any(b.external for b in blocks)                                              # the charity and agency attendees are other domains


def test_token_is_never_stored_or_echoed():
    fake = FakeGraph(GraphHTTPError(401))
    src = outlook(fake)
    with pytest.raises(SourceError) as e:
        list(src.read(SINCE, UNTIL))
    assert e.value.code == "graph_unauthorized" and TOKEN not in str(e.value) and TOKEN not in repr(src.stats) and "FAKE-TEST" not in repr(src.describe())
    items = list(outlook(FakeGraph(fx("outlook_calendarview_page1.json"), fx("outlook_calendarview_page2.json"))).read(SINCE, UNTIL))
    assert all(TOKEN not in json.dumps(i.fields, default=str) for i in items)


def test_error_bodies_are_not_echoed():
    secret_body = {"error": {"code": "InvalidAuthenticationToken", "message": "Zephyr merger leaked in an error body"}}
    with pytest.raises(SourceError) as e:
        list(outlook(FakeGraph(secret_body)).read(SINCE, UNTIL))
    assert "Zephyr" not in str(e.value) and e.value.code == "graph_error_response"
    with pytest.raises(SourceError) as e:
        list(outlook(FakeGraph(GraphHTTPError(500))).read(SINCE, UNTIL))
    assert e.value.code == "graph_http_500"
    with pytest.raises(SourceError):
        list(outlook(FakeGraph(["not", "a", "dict"])).read(SINCE, UNTIL))


def test_throttling_is_retried_with_the_given_wait_then_gives_up():
    sleeps = []
    fake = FakeGraph(GraphHTTPError(429, 3.0), GraphHTTPError(503), fx("outlook_calendarview_page2.json"))
    src = OutlookGraphSource(lambda: TOKEN, fake, sleep=sleeps.append)
    assert len(list(src.read(SINCE, UNTIL))) == 4 and sleeps == [3.0, 4.0] and len(fake.calls) == 3
    always = FakeGraph(GraphHTTPError(429, 1.0))
    with pytest.raises(SourceError) as e:
        list(OutlookGraphSource(lambda: TOKEN, always, sleep=lambda s: None).read(SINCE, UNTIL))
    assert e.value.code == "graph_http_429" and len(always.calls) == 4                     # first try plus three retries


def test_a_next_link_on_another_host_is_refused():
    evil = {"value": [], "@odata.nextLink": "https://evil.example/v1.0/me/calendarView?x=1"}
    fake = FakeGraph(evil)
    with pytest.raises(SourceError) as e:
        list(outlook(fake).read(SINCE, UNTIL))
    assert e.value.code == "graph_url_refused" and len(fake.calls) == 1                    # the token was never sent to the other host
    http = {"value": [], "@odata.nextLink": "http://graph.microsoft.com/v1.0/me/calendarView"}
    with pytest.raises(SourceError):
        list(outlook(FakeGraph(http)).read(SINCE, UNTIL))


def test_runaway_paging_is_capped():
    endless = {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?n=1"}
    with pytest.raises(SourceError) as e:
        list(OutlookGraphSource(lambda: TOKEN, FakeGraph(endless), max_pages=5, sleep=lambda s: None).read(SINCE, UNTIL))
    assert e.value.code == "graph_too_many_pages"


def test_default_fetch_is_get_only_and_graph_only(monkeypatch):
    for bad in ("https://evil.example/v1.0/me", "http://graph.microsoft.com/v1.0/me", "https://graph.microsoft.com.evil.example/x", "file:///etc/passwd"):
        with pytest.raises(SourceError) as e:
            default_fetch(bad, {"Authorization": "Bearer x"})
        assert e.value.code == "graph_url_refused"
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"value": []}'

    def fake_urlopen(req, timeout=0):
        seen["method"], seen["url"], seen["data"] = req.get_method(), req.full_url, req.data
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert default_fetch("https://graph.microsoft.com/v1.0/me/calendarView", {"Authorization": "Bearer x"}) == {"value": []}
    assert seen["method"] == "GET" and seen["data"] is None


def test_parse_graph_dt_variants():
    assert parse_graph_dt({"dateTime": "2026-11-02T09:00:00.0000000", "timeZone": "UTC"}) == datetime(2026, 11, 2, 9, tzinfo=UTC)
    assert parse_graph_dt({"dateTime": "2026-07-01T09:00:00.1234567", "timeZone": "GMT Standard Time"}) == datetime(2026, 7, 1, 8, 0, 0, 123456, tzinfo=UTC)
    assert parse_graph_dt({"dateTime": "2026-07-01T09:00:00", "timeZone": "Europe/London"}) == datetime(2026, 7, 1, 8, tzinfo=UTC)
    assert parse_graph_dt({"dateTime": "bad"}) is None and parse_graph_dt(None) is None and parse_graph_dt({"timeZone": "UTC"}) is None


# ---------------------------------------------------------------------------------------------------- Teams
def teams(fake, **kw):
    return TeamsMeetingsSource(lambda: TOKEN, fake, sleep=lambda s: None, self_address="me@fenwick.example", **kw)


def test_teams_meeting_metadata():
    fake = FakeGraph(fx("teams_online_meetings.json"))
    items = list(teams(fake).read(SINCE, UNTIL))
    assert len(items) == 2 and all(i.fields["provider"] == "teams" and i.fields["online"] for i in items)
    first = items[0]
    assert first.t0 == datetime(2026, 11, 2, 10, tzinfo=UTC) and first.duration_s == 3600 and first.fields["n_attendees"] == 3
    assert first.fields["response"] == "none" and items[1].fields["response"] == "organizer" and items[1].fields["n_attendees"] == 2
    q = parse_qs(urlparse(fake.calls[0][0]).query)
    assert urlparse(fake.calls[0][0]).path == "/v1.0/me/onlineMeetings" and "startDateTime ge 2026-11-02T00:00:00Z" in q["$filter"][0]


def test_teams_attendance_reports_give_the_owners_own_time():
    fake = FakeGraph(fx("teams_online_meetings.json"), fx("teams_attendance_1.json"), fx("teams_attendance_2.json"))
    items = list(teams(fake, with_attendance=True).read(SINCE, UNTIL))
    assert items[0].fields["attended_s"] == 2700                                           # the owner's own record, not the meeting length
    assert items[1].fields["attended_s"] == 1800                                           # no report: falls back to the scheduled length
    assert any("attendanceReports" in u for u, _ in fake.calls)
    assert all(h["Authorization"].startswith("Bearer ") for _, h in fake.calls)


def test_teams_items_become_meetings_and_hold_no_text_after_normalisation():
    items = list(teams(FakeGraph(fx("teams_online_meetings.json"))).read(SINCE, UNTIL))
    blocks, _, _ = to_blocks(items)
    assert [b.kind for b in blocks] == ["meeting", "meeting"] and all(b.online for b in blocks)
    assert "Zephyr" not in repr(blocks) and "fenwick" not in repr(blocks)
