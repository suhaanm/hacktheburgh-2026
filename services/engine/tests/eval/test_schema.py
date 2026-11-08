"""report.schema.json: the shape contract for evals/report.json, and the dashboard's reference fixture."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from understudy_engine.eval import schema_errors
from understudy_engine.eval.schema import load_schema, validate

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "apps" / "dashboard" / "src" / "fixtures" / "eval-report.json"

META = {"origin": "synthetic", "n": 4, "n_unit": "people", "split": "leave-one-person-out", "interval_level": 0.95, "note": None,
        "generated_at": "2026-11-07T15:00:00Z"}


def minimal() -> dict:
    return {
        "generated_at": "2026-11-07T15:00:00Z", "mock": True,
        "sections": {
            "deficit_recovery": {"meta": META, "rows": [{"deficit": "search_loop", "injected_price_s": 70.0, "recovered_price_s": 71.0, "ci": [60.0, 80.0],
                                                         "precision": 1.0, "recall": 0.9}], "overall": {"precision": 1.0, "recall": 0.9}},
            "null_placebo": {"meta": META, "real": {"gap_s": 230, "ci": [190, 270]}, "placebo": {"gap_s": 3, "ci": [-5, 11]}, "null": {"gap_s": 40, "ci": [-30, 110]}},
            "ope": {"meta": META, "true_value": 0.02, "estimators": [{"name": "dr", "value": 0.01, "ci": [-0.03, 0.05]}]},
            "redteam": {"status": "pending", "reason": "agent-safety not landed", "meta": META},
            "study": {"status": "not_run", "reason": "no results", "n": 4, "rows": [], "meta": META},
            "limitations": [{"id": "L1", "text": "All generated.", "severity": "high", "source": "engine-eval"}],
        },
    }


def test_schema_is_a_valid_json_schema():
    Draft202012Validator.check_schema(load_schema())


def test_every_contract_section_is_typed():
    props = load_schema()["properties"]["sections"]["properties"]
    for name in ("deficit_recovery", "null_placebo", "hazard", "ope", "routing", "ski_rental", "presence", "routines", "agent_claims",
                 "redteam", "study", "limitations"):
        assert name in props


def test_minimal_report_validates():
    assert schema_errors(minimal()) == []
    validate(minimal())


def test_stubs_need_status_reason_and_meta():
    r = minimal()
    del r["sections"]["redteam"]["reason"]
    assert any("reason" in e for e in schema_errors(r))
    r = minimal()
    r["sections"]["redteam"]["status"] = "unknown"
    assert schema_errors(r)


@pytest.mark.parametrize("mutate,needle", [
    (lambda r: r["sections"]["deficit_recovery"].pop("overall"), "overall"),
    (lambda r: r["sections"]["deficit_recovery"]["rows"][0].pop("recovered_price_s"), "recovered_price_s"),
    (lambda r: r["sections"]["null_placebo"].pop("null"), "null"),
    (lambda r: r["sections"]["ope"]["estimators"][0].update(name="Doubly robust"), "Doubly robust"),
    (lambda r: r["sections"]["deficit_recovery"]["meta"].pop("n_unit"), "n_unit"),
    (lambda r: r["sections"]["deficit_recovery"]["meta"].update(origin="made-up"), "made-up"),
    (lambda r: r["sections"]["deficit_recovery"]["rows"][0].update(ci=[1.0]), "ci"),
    (lambda r: r["sections"]["limitations"][0].update(severity="critical"), "critical"),
    (lambda r: r.pop("mock"), "mock"),
    (lambda r: r["sections"].update(unknown_section={"meta": META}), "unknown_section"),
])
def test_broken_shapes_are_rejected_with_a_useful_message(mutate, needle):
    r = copy.deepcopy(minimal())
    mutate(r)
    errs = schema_errors(r)
    assert errs and any(needle in e for e in errs), errs


def test_extra_keys_are_allowed_additive():
    r = minimal()
    r["sections"]["null_placebo"]["extra"] = {"anything": 1}
    r["sections"]["deficit_recovery"]["rows"][0]["label"] = "Searches in loops"
    assert schema_errors(r) == []


def test_nan_cannot_sneak_in():
    s = json.dumps(minimal())
    assert "NaN" not in s


# ---------------------------------------------------------------------------------------------- dashboard fixture
@pytest.fixture(scope="module")
def fixture_report() -> dict:
    return json.loads(FIXTURE.read_text())


def test_dashboard_fixture_has_the_envelope_and_every_meta(fixture_report):
    """The part both sides already agree on: top-level keys and AnalyticMeta on every section."""
    errs = [e for e in schema_errors(fixture_report) if "/meta" in e.split(":")[0] or e.startswith("(root)")]
    assert errs == []
    top = {k for k in fixture_report}
    assert {"generated_at", "mock", "sections"} <= top
    for name, sec in fixture_report["sections"].items():
        if name != "limitations":
            assert {"origin", "n", "n_unit", "split", "interval_level", "note", "generated_at"} <= set(sec["meta"]), name


def test_dashboard_fixture_matches_the_contract_shapes(fixture_report):
    """The dashboard's reference fixture is a copy of a generated report; it must keep validating as the schema and the generator move."""
    errs = schema_errors(fixture_report)
    assert errs == [], "dashboard fixture does not match report.schema.json:\n" + "\n".join(errs[:60])
