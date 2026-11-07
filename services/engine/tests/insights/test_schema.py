"""The public shapes validate against packages/schema/insight.schema.json, and the schema's enums are the vocabulary's (REQ-9)."""
from __future__ import annotations

import json

import jsonschema
import pytest

from understudy_engine.insights import firm as F
from understudy_engine.insights import paths as P
from understudy_engine.insights import vocab as V
from understudy_engine.insights.service import InsightsService
from understudy_engine.insights.store import InsightsStore

SCHEMA = json.loads(P.schema_path().read_text())


def check(name: str, doc) -> None:
    jsonschema.validate(doc, {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}, cls=jsonschema.Draft202012Validator)


@pytest.fixture(scope="module")
def svc():
    snap = F.build_firm(0).snapshot
    return InsightsService(InsightsStore(), snapshot_provider=lambda s: snap, clock=lambda: snap.now), snap


def test_the_schema_is_valid_and_its_enums_are_the_vocabulary():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    d = SCHEMA["$defs"]
    assert d["kind"]["enum"] == list(V.KINDS) and d["polarity"]["enum"] == list(V.POLARITIES) and d["glyph"]["enum"] == list(V.GLYPHS)
    assert d["trend"]["enum"] == list(V.TREND_CLASSES) and d["reason"]["enum"] == list(V.REASONS) and d["status_worker"]["enum"] == list(V.STATUSES_WORKER)
    assert set(d["worker_pointer"]["properties"]["source"]["enum"]) == V.SOURCE_SET and d["admin_card"]["properties"]["statement"]["const"] == V.STATEMENT
    assert d["tenure_band"]["enum"] == list(V.TENURE_BANDS) and set(d["action"]["properties"]["id"]["enum"]) == set(V.ACTIONS)


def test_every_worker_response_in_the_firm_validates(svc):
    s, snap = svc
    for p in snap.people:
        check("worker_response", s.worker(p.id, "firm"))


def test_every_admin_card_every_user_row_and_every_drill_validates(svc):
    s, snap = svc
    ov = s.overview("firm")
    for c in ov["top"]:
        check("admin_card", c)
        check("drill", s.drill("firm", c["id"]))
    for g in s.firm("firm")["roles"]:
        for u in g["users"]:
            check("user_row", u)


def test_the_schema_refuses_a_worker_pointer_that_carries_statistics(svc):
    s, snap = svc
    pid = next(p.id for p in snap.people if s.worker(p.id, "firm")["pointers"])
    ptr = s.worker(pid, "firm")["pointers"][0]
    bad = dict(ptr, interval=[1, 2])
    with pytest.raises(jsonschema.ValidationError):
        check("worker_pointer", bad)
    with pytest.raises(jsonschema.ValidationError):
        check("worker_pointer", dict(ptr, kind="rank_the_people"))
    with pytest.raises(jsonschema.ValidationError):
        check("admin_card", dict(s.overview("firm")["top"][0], text="No coaching sentence."))
