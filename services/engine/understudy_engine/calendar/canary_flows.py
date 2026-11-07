"""Canary flows for the calendar layer (privacy contract): ``FLOWS`` lists what the privacy track plants canaries in and measures.

Each flow builds FRESH fixtures (a week of events with names, addresses, titles, places and a customer in the fields the code reads),
and ``run`` pushes them through the REAL read path: ICS text (or a Graph fake response) -> source plugin -> text-free blocks -> features ->
code-selected suggestions -> wording through ``egress.send`` against the capturing port. The harness plants unique tokens (mode ``append``
because titles are read for keywords such as "lunch"), runs the flow with several seeds and checks that no token reaches any request,
the ledger, a log record, or the audit, queue and ledger files, and that every call has exactly one ledger line.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..privacy.testing import CanaryFlow, CapturingPort
from . import suggest as sug
from .expert import load_template, template_reference
from .features import analyse_week
from .model import monday_of
from .normalize import to_blocks
from .synth import esc, fold

ROLE = "benefits-processor"


def _name(email: str) -> str:
    local = email.split("@", 1)[0]
    return " ".join(p.capitalize() for p in local.replace("_", ".").split(".") if p)


def make_fixtures() -> dict[str, Any]:
    """One fresh week of a calendar with fragmented, back-to-back days (so suggestions are selected), as nested dicts and lists."""
    from . import synth
    spec = next(s for s in synth.person_specs() if s.person == "p_nov05")
    _, cal, _, _, _ = synth.build_files(spec)
    events = []
    for r in cal["events"]:
        if not ("2026-10-19" <= r["start"][:10] <= "2026-10-23"):
            continue
        events.append({
            "title": r["title"], "start": r["start"], "end": r["end"], "location": r["location"],
            "organizer": {"name": _name(r["organizer"]), "email": r["organizer"]},
            "attendees": [{"name": _name(a), "email": a} for a in r["attendees"]],
            "customer": "Meridian Holdings" if r["online"] else "",
            "status": r["status"], "show_as": r["show_as"],
        })
    return {"owner": {"name": "Alex Doe", "email": "alex.doe@fenwickcouncil.example"}, "events": events}


def fixtures_to_ics(fix: dict[str, Any]) -> str:
    """ICS text from the fixtures (single events; names go in CN parameters, the customer in the description, as real exports do)."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Fenwick Council//Exchange Calendar 16.0//EN"]
    for i, e in enumerate(fix["events"]):
        s, t = e["start"][:19].replace("-", "").replace(":", ""), e["end"][:19].replace("-", "").replace(":", "")
        lines += ["BEGIN:VEVENT", f"UID:canary-flow-{i}@fenwickcouncil.example", "DTSTAMP:20261001T080000Z", f"DTSTART:{s}", f"DTEND:{t}",
                  f"SUMMARY:{esc(e['title'])}", f'ORGANIZER;CN="{e["organizer"]["name"]}":mailto:{e["organizer"]["email"]}']
        for a in e["attendees"]:
            lines.append(f'ATTENDEE;CN="{a["name"]}";PARTSTAT=ACCEPTED:mailto:{a["email"]}')
        if e["location"]:
            lines.append(f"LOCATION:{esc(e['location'])}")
        if e["customer"]:
            lines.append(f"DESCRIPTION:{esc('Customer: ' + e['customer'] + ' - see the ' + e['customer'] + ' file')}")
        lines.append("STATUS:CANCELLED" if e["status"] == "cancelled" else "STATUS:CONFIRMED")
        lines.append("X-MICROSOFT-CDO-BUSYSTATUS:" + {"free": "FREE", "tentative": "TENTATIVE"}.get(e["show_as"], "BUSY"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def run(fix: dict[str, Any], port: CapturingPort) -> dict[str, Any]:
    """The real flow: ICS -> blocks -> features -> suggestions -> wording through the egress guard."""
    from ..plugins.ics import ICSSource
    tpl = load_template(ROLE)
    src = ICSSource(fixtures_to_ics(fix), default_tz="UTC", self_email=fix["owner"]["email"])
    blocks, off, _stats = to_blocks(src.read(), tpl.work)
    wa = analyse_week(blocks, tpl.work, date(2026, 10, 19), off)
    ref = template_reference(ROLE)
    out = sug.suggest(wa.features, ref, tpl.targets, history=[wa.features], person="p_canary", week="2026-W43", days_expected=len(tpl.work.days))
    reworded = [sug.reword(s, ROLE, ref, wa.features, port=port, accept_mock=True) for s in out]
    return {"suggestions": len(out), "reworded": sum(1 for s in reworded if s["source"] == "reworded")}


FLOWS = [CanaryFlow(name="calendar.ics_to_suggestion_wording", make_fixtures=make_fixtures, run=run, layer="calendar", min_requests=1, mode="append")]
