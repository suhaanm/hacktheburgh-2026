from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from understudy_engine.privacy import ledger


def test_append_read_newest_first_and_limit():
    for i in range(5):
        ledger.append({"purpose": f"t.p{i}", "schema": "S#1", "fields": ["a"], "payload": {"a": i}, "model": "m", "bytes": 10 + i, "mock": True})
    rows = ledger.read(3)
    assert [r["purpose"] for r in rows] == ["t.p4", "t.p3", "t.p2"]
    assert all({"id", "t", "purpose", "schema", "fields", "payload", "model", "bytes"} <= set(r) for r in rows)
    assert ledger.count() == 5 and len(ledger.read(None)) == 5


def test_file_is_append_only_jsonl_mode_600(data_dir):
    ledger.append({"purpose": "t.a", "payload": {}})
    ledger.append({"purpose": "t.b", "payload": {}})
    p = data_dir / "egress_ledger.jsonl"
    lines = p.read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(x) for x in lines)
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    ledger.append({"purpose": "t.c", "payload": {}})
    assert p.read_text().splitlines()[:2] == lines          # earlier lines untouched


def test_corrupt_lines_are_skipped_not_fatal(data_dir):
    ledger.append({"purpose": "t.a", "payload": {}})
    with open(data_dir / "egress_ledger.jsonl", "a") as f:
        f.write("{not json\n\n[1,2]\n")
    ledger.append({"purpose": "t.b", "payload": {}})
    assert [r["purpose"] for r in ledger.read_all()] == ["t.a", "t.b"]


def test_time_is_utc_iso_and_can_be_set():
    e = ledger.append({"purpose": "t.a", "payload": {}, "t": ledger.now_iso(datetime(2026, 11, 7, 9, 30, tzinfo=timezone.utc))})
    assert e["t"] == "2026-11-07T09:30:00.000Z"


def test_concurrent_appends_do_not_interleave():
    def go(k):
        for i in range(40):
            ledger.append({"purpose": "t.c", "payload": {"k": k, "i": i}})

    ts = [threading.Thread(target=go, args=(k,)) for k in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    rows = ledger.read_all()
    assert len(rows) == 240 and len({r["id"] for r in rows}) == 240


def test_summary_counts_by_purpose_mock_direct_blocked_and_is_honest():
    ledger.append({"purpose": "t.a", "payload": {}, "mock": True, "model": "capturing", "bytes": 5})
    ledger.append({"purpose": "t.a", "payload": {}, "mock": False, "model": "openai:x", "bytes": 7})
    ledger.append({"purpose": "t.b", "payload": {}, "mock": False, "model": "openai:x", "bytes": 9})
    ledger.record_direct(method="plan", model="openai:x", bytes_sent=123)
    ledger.log_blocked("t.a", "backstop", ["email"], ["x"])
    s = ledger.summary()
    assert s["calls"] == 4 and s["by_purpose"] == {"t.a": 2, "t.b": 1, "worker_requested": 1}
    assert s["mock_calls"] == 1 and s["worker_requested_calls"] == 1 and s["blocked_attempts"] == 1
    assert s["last_call"]["purpose"] == "worker_requested"
    note = s["local_only_note"].lower()
    assert "does not claim that nothing else leaves" in note and "asked for" in note
    assert "nothing leaves this laptop" not in note


def test_direct_calls_carry_no_content():
    row = ledger.record_direct(method="plan", model="m", bytes_sent=42, note="agent step")
    assert row["payload"] is None and row["content_logged"] is False and row["fields"] == []


def test_blocked_lines_hold_rule_and_field_names_only(data_dir):
    ledger.log_blocked("t.a", "backstop", ["email", "path"], ["learner.x"])
    raw = (data_dir / "egress_blocked.jsonl").read_text()
    row = json.loads(raw)
    assert row["rules"] == ["email", "path"] and row["fields"] == ["learner.x"] and "payload" not in row


def test_clear_removes_lines_but_remembers_that_it_happened(data_dir):
    for _ in range(3):
        ledger.append({"purpose": "t.a", "payload": {}})
    ledger.log_blocked("t.a", "backstop", ["email"], [])
    out = ledger.clear()
    assert out["cleared"] == 3 and out["blocked_cleared"] == 1
    assert ledger.read_all() == [] and not (data_dir / "egress_ledger.jsonl").exists()
    s = ledger.summary()
    assert s["calls"] == 0 and s["cleared"]["times"] == 1 and s["cleared"]["calls_removed"] == 3 and s["cleared"]["last_cleared_at"]
    ledger.append({"purpose": "t.a", "payload": {}})
    ledger.clear()
    assert ledger.summary()["cleared"] == {"times": 2, "calls_removed": 4, "last_cleared_at": ledger.summary()["cleared"]["last_cleared_at"]}


def test_clear_on_empty_ledger_is_fine():
    assert ledger.clear()["cleared"] == 0


def test_export_is_the_jsonl_text():
    ledger.append({"purpose": "t.a", "payload": {"a": 1}})
    txt = ledger.export_jsonl()
    assert json.loads(txt.splitlines()[0])["payload"] == {"a": 1}
    ledger.clear()
    assert ledger.export_jsonl() == ""


def test_canary_summary_defaults_to_zero():
    assert ledger.canary_summary()["runs"] == 0
    assert ledger.summary()["canary"] == {"runs": 0, "planted": 0, "leaked": 0, "last_run": None}
