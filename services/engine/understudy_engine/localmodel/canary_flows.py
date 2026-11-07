"""Canary flows for the privacy layer's evaluation (PRV-1, PRV-4): the REAL digest pipeline on fixtures seeded with names, emails,
paths, meeting titles, commit messages and customer names, forwarding only the digests through ``egress.send("digest.meta")``.

``privacy.evaluate`` discovers ``FLOWS`` and runs each over several seeds against a capturing port. What is checked there: zero
planted tokens in the captured request bodies, in this layer's local-server log and other artifacts, in log records, and one
ledger line per request. The pipeline runs as configured: the local model when it is available and the flag is on, the rules
otherwise (mock mode, no model, flag off); both are covered by the same assertions.

The third flow is a control: a stand-in model that tries to echo the input into its answer. The guards must reject every such
reply, so the digests and the forwarded payload still hold nothing but vocabulary values.
"""
from __future__ import annotations

from typing import Any

from understudy_engine.privacy import egress
from understudy_engine.privacy.testing import CanaryFlow, CapturingPort

from .bridge import meta_payload
from .digest import commit_digest, commit_digest_ex, event_digest, event_digest_ex
from .evaluate import FakeLeakyClient

# fresh on every call; the privacy kit plants canaries into the keys it recognises (message, files/path, title, description,
# location, attendees, name, email, customer) and ``mode="append"`` keeps the original wording so the keyword rules still read it
_COMMITS = [
    ("Fix payroll rounding for the Acme account", ["billing/payroll.py", "tests/test_payroll.py"]),
    ("Add CSV export to the monthly report", ["reports/export.py"]),
    ("Refactor the importer into smaller functions", ["ingest/importer.py", "ingest/parse.py"]),
    ("Revert \"Switch checkout to async payments\"", ["payments/checkout.py"]),
    ("Update the README with setup steps", ["README.md"]),
    ("wip", ["src/app.py"]),
    ("Bump requests from 2.30.0 to 2.31.0", ["pyproject.toml", "uv.lock"]),
    ("Disable the signature check on the webhook handler while we debug", ["hooks/verify.py"]),
]
_EVENTS = [
    ("1:1 with the new starter", 2, 30), ("Daily standup", 8, 15), ("Design review: checkout redesign", 6, 60),
    ("Focus time", 1, 120), ("Team lunch", 10, 60), ("Submit expenses", 1, 30), ("Call with the customer", 4, 45),
    ("Train to the client site", 1, 180),
]


def make_fixtures() -> dict[str, Any]:
    return {
        "commits": [{"message": m, "author": "A Developer", "committer": "A Developer",
                     "files": [{"path": p, "additions": 5 + 7 * i, "deletions": 2 + i} for i, p in enumerate(paths)]}
                    for m, paths in _COMMITS],
        "events": [{"title": t, "organizer": "An Organiser", "location": "Room 4", "description": f"Agenda for {t}",
                    "start": "2026-11-02T10:00:00+00:00", "end": f"2026-11-02T{10 + mins // 60:02d}:{mins % 60:02d}:00+00:00",
                    "attendees": [{"name": f"Colleague {i}", "email": f"person{i}@example.test"} for i in range(n)]}
                   for t, n, mins in _EVENTS],
    }


def _forward(commit_digests: list[dict[str, Any]], event_digests: list[dict[str, Any]], port: CapturingPort) -> None:
    if commit_digests:
        egress.send("digest.meta", meta_payload("commit", commit_digests), port=port)
    if event_digests:
        egress.send("digest.meta", meta_payload("event", event_digests), port=port)


def run(fixtures: dict[str, Any], port: CapturingPort) -> None:
    """The real pipeline (model or rules, as configured), then only the digests go out."""
    _forward(commit_digest(fixtures["commits"]), event_digest(fixtures["events"]), port)


def run_with_leaky_model(fixtures: dict[str, Any], port: CapturingPort) -> None:
    """Control: a stand-in model that echoes the input text into its answer. The guards must replace every such reply."""
    cd = commit_digest_ex(fixtures["commits"], client=FakeLeakyClient("echo_input_in_field"))
    ed = event_digest_ex(fixtures["events"], client=FakeLeakyClient("extra_key_with_input"))
    assert all(s == "rules" for s in cd.per_item_source + ed.per_item_source), "a leaking reply was accepted"
    _forward(cd.digests, ed.digests, port)


FLOWS = [
    CanaryFlow("localmodel.digest_pipeline", make_fixtures, run, layer="localmodel", min_requests=2, mode="append"),
    CanaryFlow("localmodel.digest_pipeline_leaky_model", make_fixtures, run_with_leaky_model, layer="localmodel", min_requests=2, mode="append"),
]
