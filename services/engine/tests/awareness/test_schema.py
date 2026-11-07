from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from understudy_engine.awareness import schema
from understudy_engine.privacy.image import closed_schema_problem

from .conftest import glance_event, window_event

REPO = Path(__file__).resolve().parents[4]
TS_TYPES = REPO / "apps" / "desktop" / "src" / "main" / "awareness" / "types.ts"


def ts_enum(name: str) -> tuple[str, ...]:
    text = TS_TYPES.read_text()
    m = re.search(rf"export const {name} = \[(.*?)\] as const", text, re.S)
    assert m, name
    return tuple(re.findall(r"'([a-z_0-9]+)'", m.group(1)))


def test_the_enums_come_from_the_schema_file_and_match_the_desktop_types():
    assert schema.APP_KINDS == ts_enum("APP_KINDS")
    assert schema.TASK_PHASES == ts_enum("TASK_PHASES")
    assert schema.BLOCKERS == ts_enum("BLOCKERS")
    assert schema.TRIGGER_REASONS == ts_enum("TRIGGER_REASONS")
    assert schema.APP_KINDS_OR_UNKNOWN == (*schema.APP_KINDS, "unknown")
    assert "none" in schema.NO_BLOCK and "unknown" in schema.NO_BLOCK


def test_valid_events_pass_and_the_schema_is_closed():
    assert schema.problem(window_event()) is None
    assert schema.problem(glance_event()) is None
    assert schema.problem(glance_event(glance={"app_kind": None, "task_phase": None, "blocker": "none", "confidence": 0.1, "box_2d": [1, 2, 30, 40]})) is None
    s = schema.schema()
    assert s["$defs"]["AwarenessEvent"]["additionalProperties"] is False
    assert s["$defs"]["CursorFeatures"]["additionalProperties"] is False
    assert s["$defs"]["GlanceResult"]["additionalProperties"] is False


@pytest.mark.parametrize("name,mutate", [
    ("unknown key", lambda e: e.update(title="Payroll")),
    ("coordinates in the cursor", lambda e: e["cursor"].update(x=10, y=20)),
    ("a missing cursor key", lambda e: e["cursor"].pop("wander")),
    ("bad app kind", lambda e: e.update(app_kind="martian")),
    ("bad zone", lambda e: e["cursor"].update(dwell_zone="Not A Zone")),
    ("wander below 1", lambda e: e["cursor"].update(wander=0.2)),
    ("dwell over 30", lambda e: e["cursor"].update(dwell_s=31)),
    ("fractional count", lambda e: e["cursor"].update(back_forth=1.5)),
    ("a glance on a window", lambda e: e.update(glance={"app_kind": None, "task_phase": None, "blocker": "none", "confidence": 0.1})),
    ("bad person", lambda e: e.update(person="alice")),
    ("bad time", lambda e: e.update(t="yesterday")),
    ("bad schema version", lambda e: e.update(schema=2)),
    ("bad type", lambda e: e.update(type="frame")),
])
def test_bad_window_events_are_refused(name, mutate):
    e = copy.deepcopy(window_event())
    mutate(e)
    assert schema.problem(e) is not None, name


@pytest.mark.parametrize("name,mutate", [
    ("free text in the glance", lambda e: e["glance"].update(description="a payroll sheet")),
    ("bad blocker", lambda e: e["glance"].update(blocker="boredom")),
    ("bad phase", lambda e: e["glance"].update(task_phase="dancing")),
    ("confidence over 1", lambda e: e["glance"].update(confidence=1.2)),
    ("box with three numbers", lambda e: e["glance"].update(box_2d=[1, 2, 3])),
    ("box out of range", lambda e: e["glance"].update(box_2d=[0, 0, 5, 1001])),
    ("no trigger", lambda e: e.pop("trigger")),
    ("bad trigger", lambda e: e.update(trigger="curiosity")),
    ("a cursor on a glance", lambda e: e.update(cursor=window_event()["cursor"])),
])
def test_bad_glance_events_are_refused(name, mutate):
    e = copy.deepcopy(glance_event())
    mutate(e)
    assert schema.problem(e) is not None, name


def test_a_reason_names_the_rule_and_the_path_and_never_a_value():
    secret = "Payroll-Q3-Alice-Smith"
    for e in (window_event(app_kind=secret), window_event(extra=secret), {**window_event(), "cursor": {**window_event()["cursor"], "dwell_zone": secret}},
              glance_event(trigger=secret)):
        why = schema.problem(e)
        assert why and secret not in why and "Alice" not in why, why
    assert schema.problem("not an object") == "not an object"
    assert schema.problem(None) == "not an object"


def test_a_naive_time_is_accepted_as_utc_and_garbage_is_not():
    assert schema.parse_time("2026-11-07T10:00:00") == schema.parse_time("2026-11-07T10:00:00Z")
    with pytest.raises(ValueError):
        schema.parse_time("nope")
    assert schema.iso(0) == "1970-01-01T00:00:00.000Z"


def test_the_glance_answer_schema_is_closed_enough_for_the_privacy_spine():
    s = schema.glance_response_schema()
    assert closed_schema_problem(s) is None
    assert set(s["required"]) == {"app_kind", "task_phase", "blocker", "confidence"}
    assert s["properties"]["blocker"]["enum"] == list(schema.BLOCKERS)
    assert "null" not in json.dumps(s)
