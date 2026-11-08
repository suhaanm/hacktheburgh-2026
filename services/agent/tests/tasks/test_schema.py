"""packages/schema/task_row.schema.json is the closed shape of the Tasks API. Every row the service produces, in every state it can be in, must
validate; and the schema must refuse the shapes that would leak or break a consumer."""
from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from understudy_agent.security.paths import repo_root
from understudy_agent.tasks.model import Task

from .conftest import claude_text, wait_for
from .test_manager import done

SCHEMA = json.loads((repo_root() / "packages" / "schema" / "task_row.schema.json").read_text())


def validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


ROW = validator("TaskRow")
DETAIL = validator("TaskDetail")


def check_row(row):
    errs = sorted(ROW.iter_errors(row), key=lambda e: list(e.path))
    assert not errs, [(list(e.path), e.message[:120]) for e in errs[:3]]


def check_detail(d):
    errs = sorted(DETAIL.iter_errors(d), key=lambda e: list(e.path))
    assert not errs, [(list(e.path), e.message[:120]) for e in errs[:3]]


def test_the_schema_itself_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_every_state_a_task_reaches_validates(make_manager, port):
    m = make_manager()
    seen_states: set[str] = set()
    rows = []

    def collect(*tids):
        for tid in tids:
            d = m.detail(tid)
            check_detail(d)
            check_row({k: v for k, v in d.items() if k not in ("steps", "answer")})
            seen_states.add(d["state"])
            rows.append(d)

    q = m.create("sort this out for me", "typed")["task_id"]                         # waiting_consent with a question
    c = m.create(claude_text("ok"), "typed")["task_id"]                              # waiting_consent with a claude card
    b = m.create("go to https://example.com and read the news online", "typed")["task_id"]    # waiting_consent with a browser card
    collect(q, c, b)
    m.consent(c, "allow")
    collect(c)                                                                       # running (or already done)
    a = m.create("What is the capital of Scotland?", "typed")["task_id"]
    done(m, a)
    done(m, c)
    f = m.create(claude_text("exit3"), "typed")["task_id"]
    m.consent(f, "allow")
    done(m, f)
    s = m.create(claude_text("hang"), "typed")["task_id"]
    m.consent(s, "allow")
    assert wait_for(lambda: m.get(s).pid, 10)
    m.stop(s)
    m.consent(b, "decline")
    de = m.create("click the Save button in Excel", "typed")["task_id"]
    done(m, de)
    collect(a, c, f, s, b, de, q)
    assert {"done", "failed", "stopped", "waiting_consent"} <= seen_states               # every end state, and both kinds of card
    for _, name, row in m.events_since(0):                                           # and every SSE row too
        check_row(row)
    for row in m.list_rows():
        check_row(row)


def test_the_planning_row_validates(make_manager):
    t = Task(task_id="tk_00000001", text="x", title="x")
    t.latest = "Working out what to do"
    check_row(t.row())


def _good():
    return {"task_id": "tk_8f3a1c2e", "title": "Summarise the csv", "route": "claude_agent", "source": "typed", "state": "done", "attended": True,
            "latest": None, "steps_done": 3, "result": "Wrote summary.md.", "reason": None, "started": "2026-11-08T01:00:00.000Z",
            "finished": "2026-11-08T01:01:00.000Z", "open": {"kind": "folder", "path": "/Users/x/Knack/work/a"}, "needs_consent": None, "question": None}


def test_the_schema_refuses_shapes_that_would_leak_or_break_consumers():
    check_row(_good())
    bad = []

    def mutate(fn):
        row = copy.deepcopy(_good())
        fn(row)
        bad.append(row)

    mutate(lambda r: r.update(text="the whole prompt"))                                  # a prompt body can never ride in a row
    mutate(lambda r: r.update(output="full agent output"))
    mutate(lambda r: r.update(title="x" * 61))
    mutate(lambda r: r.update(result="x" * 141))
    mutate(lambda r: r.update(state="paused"))
    mutate(lambda r: r.update(route="shell"))
    mutate(lambda r: r.pop("question"))
    mutate(lambda r: r.update(finished=None))                                            # done without a finish time
    mutate(lambda r: r.update(state="running", finished="2026-11-08T01:01:00.000Z"))
    mutate(lambda r: r.update(started="2026-11-08T01:00:00Z"))                           # no milliseconds
    mutate(lambda r: r.update(open={"kind": "script", "path": "/x"}))
    mutate(lambda r: r.update(task_id="tk_XYZ"))
    mutate(lambda r: r.update(state="running", finished=None, question={"text": "?", "options": [{"id": "answer", "label": "a"}] * 2}))
    for row in bad:
        assert not ROW.is_valid(row), row
    card = {"kind": "claude_agent", "scope_text": "s", "can": [], "cannot": [], "folder": None, "command_hash": "0123456789ab", "cost_note": None,
            "max_minutes": 30, "buttons": {"allow": "Allow for this task", "decline": "Not now", "more": []}}
    ok = {**_good(), "state": "waiting_consent", "finished": None, "needs_consent": card}
    check_row(ok)
    for tweak in ({"command_hash": "XYZ"}, {"max_minutes": 0}, {"kind": "shell"}, {"extra": 1},
                  {"buttons": {"allow": "Yes", "decline": "Not now", "more": []}},
                  {"buttons": {"allow": "Allow for this task", "decline": "Not now", "more": [{"id": "x", "label": "y"}]}}):
        assert not ROW.is_valid({**ok, "needs_consent": {**card, **tweak}}), tweak
    assert not ROW.is_valid({**ok, "needs_consent": None})                               # waiting with neither a card nor a question
    assert not ROW.is_valid({**ok, "question": {"text": "?", "options": [{"id": "answer", "label": "a"}, {"id": "desktop", "label": "d"}]}})
    assert not DETAIL.is_valid(_good())                                                  # a detail needs steps and answer
    assert DETAIL.is_valid({**_good(), "steps": ["Reading a.csv"], "answer": None})
    assert not DETAIL.is_valid({**_good(), "steps": [], "answer": None, "text": "x"})
