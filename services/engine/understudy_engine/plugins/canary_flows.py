"""Canary flows for the source plugins (privacy contract): the ICS, JSON and Graph (Outlook and Teams, on fake responses) adapters.

Fresh fixtures carry names, addresses, titles, places and a customer in the shapes each adapter reads (ICS text, the JSON export, a Graph
``calendarView`` page, a Teams ``onlineMeetings`` page). ``run`` reads each through its real adapter, reduces the items to text-free
blocks, computes the week's features and sends one wording request per adapter through ``egress.send`` against the capturing port. Planted
tokens must not appear in any request, ledger line, log record or file; every call has exactly one ledger line. A shell-history file
whose commands carry planted paths is parsed too: only times may come out.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ..privacy.testing import CanaryFlow, CapturingPort

ROLE = "benefits-processor"
UTC = timezone.utc


def make_fixtures() -> dict[str, Any]:
    from ..calendar.canary_flows import make_fixtures as calendar_fixtures
    base = calendar_fixtures()
    ev = base["events"]
    graph = {"value": [{
        "id": f"AAMk{i}", "iCalUId": f"uid{i}", "subject": e["title"], "isAllDay": False, "isCancelled": False, "showAs": "busy", "type": "singleInstance",
        "isOnlineMeeting": bool(e["customer"]), "onlineMeetingProvider": "teamsForBusiness" if e["customer"] else "unknown",
        "start": {"dateTime": e["start"][:19] + ".0000000", "timeZone": "UTC"}, "end": {"dateTime": e["end"][:19] + ".0000000", "timeZone": "UTC"},
        "location": {"displayName": e["location"]},
        "organizer": {"emailAddress": {"name": e["organizer"]["name"], "address": e["organizer"]["email"]}},
        "attendees": [{"emailAddress": {"name": a["name"], "address": a["email"]}, "status": {"response": "accepted"}} for a in e["attendees"]],
        "responseStatus": {"response": "accepted"}} for i, e in enumerate(ev)]}
    teams = {"value": [{
        "id": f"MSpk{i}", "subject": e["title"], "startDateTime": e["start"][:19] + "Z", "endDateTime": e["end"][:19] + "Z",
        "participants": {"organizer": {"upn": e["organizer"]["email"], "role": "presenter"},
                         "attendees": [{"upn": a["email"], "role": "attendee"} for a in e["attendees"]]}} for i, e in enumerate(ev) if e["customer"]]}
    json_cal = {"format": "understudy.calendar.v1", "tz": "UTC", "events": [{
        "id": f"j{i}", "start": e["start"], "end": e["end"], "title": e["title"], "organizer": e["organizer"]["email"],
        "attendees": [a["email"] for a in e["attendees"]], "location": e["location"], "online": bool(e["customer"])} for i, e in enumerate(ev)]}
    shell = {"history": [{"path": "/Users/alex/Projects/meridian-payroll/run.sh", "message": "deploy meridian payroll fixes"}]}
    return {**base, "graph": graph, "teams": teams, "json_calendar": json_cal, "shell": shell}


def run(fix: dict[str, Any], port: CapturingPort) -> dict[str, Any]:
    from ..calendar import suggest as sug
    from ..calendar.canary_flows import fixtures_to_ics
    from ..calendar.expert import load_template, template_reference
    from ..calendar.features import analyse_week
    from ..calendar.normalize import to_blocks
    from .graph_outlook import OutlookGraphSource
    from .graph_teams import TeamsMeetingsSource
    from .ics import ICSSource
    from .jsoncal import JSONCalendarSource
    from .shell_times import ShellTimesSource

    tpl = load_template(ROLE)
    ref = template_reference(ROLE)
    owner = fix["owner"]["email"]
    since, until = datetime(2026, 10, 19, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC)
    pages = iter([fix["graph"]])
    tpages = iter([fix["teams"]])
    sources = {
        "ics": ICSSource(fixtures_to_ics(fix), self_email=owner),
        "json": JSONCalendarSource(fix["json_calendar"]),
        "graph_outlook": OutlookGraphSource(lambda: "test-token", lambda url, headers: next(pages, {"value": []})),
        "graph_teams": TeamsMeetingsSource(lambda: "test-token", lambda url, headers: next(tpages, {"value": []}), self_address=owner),
    }
    sent = 0
    for name, src in sources.items():
        blocks, off, _ = to_blocks(src.read(since, until), tpl.work)
        wa = analyse_week(blocks, tpl.work, date(2026, 10, 19), off)
        picks = sug.suggest(wa.features, ref, tpl.targets, person=f"p_{name}", week="2026-W43", days_expected=len(tpl.work.days), max_n=1)
        for s in picks:
            sug.reword(s, ROLE, ref, wa.features, port=port, accept_mock=True)
            sent += 1
    # shell history: only times may come out of it
    text = "".join(f": {1729000000 + i * 60}:0;{h['message']} {h['path']}\n" for i, h in enumerate(fix["shell"]["history"]))
    times = [i.t0 for i in ShellTimesSource(text).read()]
    return {"sources": len(sources), "wording_requests": sent, "shell_times": len(times)}


FLOWS = [CanaryFlow(name="plugins.adapters_to_suggestion_wording", make_fixtures=make_fixtures, run=run, layer="plugins", min_requests=1, mode="append")]
