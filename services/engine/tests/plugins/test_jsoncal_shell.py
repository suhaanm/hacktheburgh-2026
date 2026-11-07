"""JSON calendar and shell-history adapters."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from understudy_engine.plugins.base import SourceError
from understudy_engine.plugins.jsoncal import JSONCalendarSource
from understudy_engine.plugins.shell_times import ShellTimesSource

UTC = timezone.utc


def test_json_calendar_shapes_zones_and_defaults():
    data = {"format": "understudy.calendar.v1", "tz": "Europe/London", "events": [
        {"id": "a", "start": "2026-10-19T09:00:00", "end": "2026-10-19T09:30:00", "title": "Huddle", "organizer": "Priya@Fenwick.example",
         "attendees": ["tom@fenwick.example"], "recurring": True, "series": "S-1", "online": True},
        {"start": "2026-11-02T09:00:00+00:00", "end": "2026-11-02T10:00:00+00:00", "title": "1:1", "n_attendees": 2},
        {"start": "2026-11-03T00:00:00", "all_day": True, "title": "Leave", "show_as": "oof"},
        {"start": "garbage", "end": "x"}, "not an object",
        {"start": "2026-11-04T10:00:00", "end": "2026-11-04T09:00:00", "title": "Backwards"},
    ]}
    src = JSONCalendarSource(data)
    items = list(src.read())
    first = items[0]
    assert first.t0 == datetime(2026, 10, 19, 8, tzinfo=UTC)                       # BST
    assert first.fields["organizer"] == "priya@fenwick.example" and first.fields["n_attendees"] == 2
    assert first.fields["recurring"] is True and first.fields["series_id"] == "S-1" and first.fields["provider"] == "teams"
    assert next(i for i in items if i.fields["title"] == "1:1").fields["n_attendees"] == 2
    leave = next(i for i in items if i.fields["title"] == "Leave")
    assert leave.fields["all_day"] is True and leave.duration_s == 86400 and leave.fields["show_as"] == "oof"
    assert next(i for i in items if i.fields["title"] == "Backwards").duration_s == 0
    assert src.stats["bad_datetime"] == 1 and src.stats["event_not_object"] == 1 and src.stats["end_before_start"] == 1
    assert [i.t0 for i in items] == sorted(i.t0 for i in items)


def test_json_calendar_list_text_path_and_errors(tmp_path):
    ev = [{"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T09:30:00Z", "title": "x"}]
    assert len(list(JSONCalendarSource(ev).read())) == 1
    assert len(list(JSONCalendarSource(json.dumps(ev)).read())) == 1
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"events": ev}))
    assert len(list(JSONCalendarSource(path=p).read())) == 1
    with pytest.raises(SourceError) as e:
        JSONCalendarSource("{not json")
    assert e.value.code == "bad_json"
    with pytest.raises(SourceError):
        list(JSONCalendarSource({"format": "other.v9", "events": []}).read())
    with pytest.raises(SourceError):
        list(JSONCalendarSource({"events": "nope"}).read())
    got = list(JSONCalendarSource(ev).read(since=datetime(2026, 11, 3, tzinfo=UTC)))
    assert got == []


ZSH = ": 1730000000:12;git commit -m 'SECRET-DEAL-NAME'\n: 1730000500:0;ssh admin@payroll.internal\n: 1730001000:3;ls ~/Documents/zephyr-merger\n"
BASH = "#1730000000\ncat /Users/me/secret-plans.txt\n#1730000100\necho hunter2\nplain line without time\n"
FISH = "- cmd: curl https://internal.example/api?token=abc123\n  when: 1730000000\n- cmd: rm -rf secret-dir\n  when: 1730000200\n"


@pytest.mark.parametrize("text,shell,n", [(ZSH, "zsh", 3), (BASH, "bash", 2), (FISH, "fish", 2)])
def test_shell_times_only(text, shell, n):
    src = ShellTimesSource(text)
    items = list(src.read())
    assert len(items) == n and all(i.fields["shell"] == shell for i in items)
    blob = " ".join(repr(i) + json.dumps(i.fields, default=str) + str(i.fields) for i in items) + json.dumps(src.describe())
    for secret in ("SECRET", "payroll", "zephyr", "hunter2", "secret-plans", "token", "abc123", "secret-dir", "internal"):
        assert secret not in blob
    assert set(items[0].fields) == {"shell", "duration_s"}
    assert items[0].t0 == datetime.fromtimestamp(1730000000, UTC)


def test_shell_times_duration_window_and_untimed_lines(tmp_path):
    src = ShellTimesSource(ZSH)
    items = list(src.read(since=datetime.fromtimestamp(1730000400, UTC), until=datetime.fromtimestamp(1730000800, UTC)))
    assert [i.fields["duration_s"] for i in items] == [0]
    assert list(ShellTimesSource("ls\npwd\n").read()) == []
    p = tmp_path / ".zsh_history"
    p.write_text(ZSH)
    assert len(list(ShellTimesSource(path=p).read())) == 3
    with pytest.raises(ValueError):
        ShellTimesSource()
