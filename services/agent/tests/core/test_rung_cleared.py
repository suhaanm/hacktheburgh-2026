"""The rung record written by the supervised R1 check and read by Knack's `do_it_for_me` (apps/desktop/src/main/wake/rung.ts)."""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone

from understudy_agent.tiers.mac_check import write_rung_cleared

# The same vector is asserted in apps/desktop/src/main/wake/rung.test.ts: the two digests must agree.
AT = datetime(2026, 11, 8, 9, 0, 0, tzinfo=timezone.utc).timestamp()
VECTOR = "f187022018575d6ed61f6b2939192a888f2635c8098aa8c1621f50b9760cad46"
PASSED = {"ok": True, "real": True, "postcondition": "passed"}


def test_a_passing_real_run_writes_the_record_with_the_shared_digest(tmp_path):
    p = write_rung_cleared(PASSED, "TextEdit", root=tmp_path, now=AT)
    assert p == tmp_path / "rung_cleared.json"
    rec = json.loads(p.read_text())
    assert rec == {"schema": 1, "rung": "R1", "at": "2026-11-08T09:00:00Z", "targets": ["TextEdit"], "postcondition": "passed", "real": True, "digest": VECTOR}
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_nothing_is_written_for_a_dry_run_a_failed_read_back_or_an_unproven_one(tmp_path):
    for out in (
        {"ok": True, "real": False, "postcondition": "passed"},          # a dry run on the fake backend
        {"ok": False, "real": True, "postcondition": "failed"},          # the document did not match
        {"ok": False, "real": True, "postcondition": "unavailable"},     # nothing proven
        {"ok": True, "real": True, "postcondition": "unavailable"},      # ok without a read-back can never clear a rung
        {"ok": True, "real": True},
        {},
    ):
        assert write_rung_cleared(out, "TextEdit", root=tmp_path, now=AT) is None
    assert not (tmp_path / "rung_cleared.json").exists()


def test_the_record_holds_enums_and_a_time_only(tmp_path):
    rec = json.loads(write_rung_cleared(PASSED, "Calculator", root=tmp_path, now=AT).read_text())
    assert set(rec) == {"schema", "rung", "at", "targets", "postcondition", "real", "digest"}
    assert rec["targets"] == ["Calculator"]
