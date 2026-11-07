from __future__ import annotations

import json

import numpy as np
import pytest

from understudy_engine.cue import ledger as L
from understudy_engine.cue import simlearn as SL
from understudy_engine.cue.ledger import Ledger, LedgerError

T = 1_790_000_000.0


def mk(i=0, **kw):
    base = dict(person="p_a", role="benefits-processor", skill="check-the-cliff", step="cliff_a", t=T + i * 3600, outcome="clean", serial=i)
    base.update(kw)
    return L.make_row(**base)


def test_rows_are_enums_numbers_and_ids_only_and_hour_bucketed():
    r = mk(trigger="auto", tier=2, p_stuck=0.7, seconds_to_progress=11.26, lost_s=12.34, accepted=True, outcome="assisted")
    assert r["t_hour"] == "2027-01-15T08" or len(r["t_hour"]) == 13
    assert r["seconds_to_progress"] == 11.3 and r["stuck_bucket"] == "p60_79"
    for k, v in r.items():
        assert isinstance(v, (bool, int, float, type(None), str)), k
    strings = {k: v for k, v in r.items() if isinstance(v, str)}
    assert set(strings) <= {"id", "person", "origin", "t_hour", "role", "skill", "step", "stream", "trigger", "stuck_bucket", "outcome"}


def test_free_text_and_unknown_fields_are_refused_without_echoing_the_value():
    for bad in ({"person": "Alice Smith"}, {"skill": "Check the cliff edges!"}, {"role": "Benefits Processor"}, {"step": "https://x.example/a"}):
        with pytest.raises(LedgerError) as e:
            mk(**bad)
        for v in bad.values():
            assert v not in str(e.value)
    r = mk()
    for extra in ({"note": "hello"}, {"title": "meeting"}, {"screenshot": "a.png"}):
        with pytest.raises(LedgerError):
            Ledger.append(Ledger("/nonexistent/x.jsonl"), {**r, **extra})


def test_append_only_view_newest_first_and_stream_filter(tmp_path):
    lg = Ledger(tmp_path / "assist" / "ledger.jsonl")
    for i in range(5):
        lg.append(mk(i))
    lg.append(L.make_row(person="p_a", role="benefits-processor", skill=None, t=T, outcome="clean", stream="automation", routine="calc-entry-3x", minutes=9.0,
                         offload_outcome="done", serial=99))
    assert [r["t_hour"] for r in lg.rows("p_a", "assist", newest_first=True)] == sorted((r["t_hour"] for r in lg.rows("p_a", "assist")), reverse=True)
    assert lg.counts("p_a") == {"assist": 5, "delegated": 0, "automation": 1}
    assert len(lg.rows("p_a", "automation")) == 1 and lg.rows("p_b") == []
    assert len(lg.rows("p_a", limit=2)) == 2
    lines = (tmp_path / "assist" / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 6 and all(json.loads(x)["id"].startswith("a_") for x in lines)


def test_same_hour_rows_keep_the_later_one_first_when_newest_first(tmp_path):
    lg = Ledger(tmp_path / "l.jsonl")
    lg.append(mk(0, t=T))
    lg.append(mk(1, t=T + 60, outcome="assisted", accepted=True))
    assert lg.rows("p_a", newest_first=True)[0]["outcome"] == "assisted"


def test_export_is_one_json_document_with_counts(tmp_path):
    lg = Ledger(tmp_path / "l.jsonl")
    lg.extend(mk(i) for i in range(3))
    doc = lg.export("p_a")
    assert doc["schema"] == "assist_ledger.schema.json" and doc["counts"]["assist"] == 3 and len(doc["rows"]) == 3
    json.dumps(doc)


def test_hard_delete_removes_rows_and_leaves_one_audit_line_with_counts_only(tmp_path, data_dir):
    lg = Ledger(tmp_path / "l.jsonl")
    lg.extend([mk(0), mk(1, person="p_b"), mk(2)])
    gone = lg.delete("p_a")
    assert gone == {"assist": 2, "delegated": 0, "automation": 0}
    assert [r["person"] for r in lg.rows()] == ["p_b"]
    raw = (tmp_path / "l.jsonl").read_text()
    assert "p_a" not in raw
    audit = [json.loads(x) for x in (data_dir / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1 and audit[0]["kind"] == "assist_ledger_deleted" and audit[0]["note"] == "rows removed: assist=2, delegated=0, automation=0"
    flat = json.dumps(audit[0])
    assert "p_a" not in flat and "cliff" not in flat and "benefits" not in flat
    lg.delete(None)
    assert lg.rows() == []


def test_a_torn_line_is_skipped_never_echoed(tmp_path):
    p = tmp_path / "l.jsonl"
    lg = Ledger(p)
    lg.append(mk(0))
    with open(p, "a") as fh:
        fh.write('{"id": "a_000000000000", "person": "p_a", "outcome": "cl')
    assert len(lg.rows()) == 1


def test_outcome_classification_follows_the_guards():
    c = L.classify_outcome
    assert c(completed=True) == "clean"
    assert c(completed=True, accepted=True) == "assisted" and c(completed=True, answered=True) == "assisted"
    assert c(completed=True, followed_within_s=9.9) == "assisted" and c(completed=True, followed_within_s=10.1) == "clean"
    assert c(completed=False) == "abandoned" and c(completed=False, accepted=True) == "abandoned"
    assert c(completed=True, error=True, accepted=True) == "error"


def test_simulated_ledgers_hold_no_text_at_all():
    rows, _ = SL.simulate_learner(SL.preset("improving"), np.random.default_rng(0), person="p_sim", n_per_skill=12)
    allowed_values = set()
    for r in rows:
        L.validate_row(r)
        for k, v in r.items():
            if isinstance(v, str):
                allowed_values.add(k)
    assert allowed_values <= {"id", "person", "origin", "origin_detail", "t_hour", "role", "skill", "step", "stream", "trigger", "stuck_bucket", "outcome"}


def test_schema_file_forbids_additional_properties_and_names_every_field():
    import jsonschema

    from understudy_engine.cue import paths

    schema = json.loads(paths.schema_path().read_text())
    assert schema["additionalProperties"] is False
    jsonschema.Draft202012Validator.check_schema(schema)
    row = mk()
    assert set(row) <= set(schema["properties"])
