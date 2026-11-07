"""The Cue response schemas (cue_decision, cue_growth, cue_ledger) say what the engine really returns.

Three kinds of check. The schema files are valid and closed, and every enum and copied definition in them is the engine's own list
(a change to the code that is not mirrored in the schema fails here). The generated examples validate and are registered in the
pack validator (``packages/packs/validate.py`` ``EXAMPLE_SCHEMAS``). And live output validates: GET /cue/next over every mock fixture
and a set of flag variants, the pure gate over a cue ladder, a question, an offer and a withheld step, GET /growth for ledgers of every
kind (empty, too few, improving, flat, declining, with offloaded work, filtered by skill) and GET /cue/ledger.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys

import jsonschema
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.api.errors import install_error_handlers
from understudy_engine.cue import fixtures as FX
from understudy_engine.cue import paths, score as S, simlearn as SL, vocab as V
from understudy_engine.cue import routes as R
from understudy_engine.cue.ledger import Ledger
from understudy_engine.cue.live import LiveCue
from understudy_engine.cue.params import DEFAULT
from understudy_engine.cue.types import KINDS, REASONS, SOURCES, STREAMS, CueDecision

from .helpers import CLOSE, Run

SCHEMA_DIR = paths.repo_root() / "packages" / "schema"
META_OK = {"origin": "synthetic", "n": 0, "n_unit": "occurrences", "split": None, "interval_level": 0.95, "note": None, "generated_at": "2026-11-07T12:00:00Z"}


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validator(name: str, ref: str) -> jsonschema.Draft202012Validator:
    """A validator for one definition of a schema file (the same way ``packages/packs/validate.py`` does it)."""
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{ref}", "$defs": load(name)["$defs"]})


def problems(v: jsonschema.Draft202012Validator, doc) -> list[str]:
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message[:160]}" for e in sorted(v.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))]


DECISION = validator("cue_decision.schema.json", "CueDecision")
ENVELOPE = validator("cue_decision.schema.json", "CueEnvelope")
GROWTH = validator("cue_growth.schema.json", "GrowthEnvelope")
LEDGER = validator("cue_ledger.schema.json", "LedgerEnvelope")
SCHEMAS = ("cue_decision.schema.json", "cue_growth.schema.json", "cue_ledger.schema.json", "cue_step.schema.json")


# ------------------------------------------------------------------------------------------------ the files
def _unclosed(node, path="$") -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        if "properties" in node and node.get("type") == "object" and node.get("additionalProperties") is not False:
            out.append(path)
        for k, v in node.items():
            out += _unclosed(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _unclosed(v, f"{path}[{i}]")
    return out


@pytest.mark.parametrize("name", SCHEMAS)
def test_the_schema_is_valid_and_every_object_in_it_is_closed(name):
    doc = load(name)
    jsonschema.Draft202012Validator.check_schema(doc)
    assert doc["$id"].endswith("/" + name)
    assert _unclosed(doc) == []


def test_every_enum_is_the_engines_own_list():
    d = load("cue_decision.schema.json")["$defs"]["CueDecision"]["properties"]
    assert d["kind"]["enum"] == list(KINDS)
    assert d["target"]["anyOf"][1]["properties"]["source"]["enum"] == list(SOURCES)
    assert d["why"]["properties"]["reasons"]["items"]["enum"] == list(REASONS)
    q = d["question"]["anyOf"][1]["properties"]
    assert q["type"]["enum"] == list(V.QUESTIONS) and q["text"]["enum"] == list(V.QUESTIONS.values())
    assert set(d) == {f.name for f in dataclasses.fields(CueDecision)}                              # every key of to_dict(), no more
    assert set(load("cue_decision.schema.json")["$defs"]["CueDecision"]["required"]) == set(d)         # all always present
    g = load("cue_growth.schema.json")["$defs"]
    assert set(g["Weights"]["properties"]) == set(S.WEIGHTS)
    assert g["GrowthData"]["properties"]["components"]["properties"]["mastery"]["properties"]["variant"]["enum"] == list(S.MASTERY_VARIANTS)
    assert g["GrowthData"]["properties"]["origin_detail"]["enum"] == load("assist_ledger.schema.json")["properties"]["origin_detail"]["enum"]
    ledger_counts = load("cue_ledger.schema.json")["$defs"]["LedgerData"]["properties"]["counts"]["properties"]
    assert set(ledger_counts) == set(STREAMS)


def test_copied_definitions_equal_their_sources():
    step = load("cue_step.schema.json")["$defs"]
    dec = load("cue_decision.schema.json")["$defs"]
    assert dec["CueStep"] == step["CueStep"] and dec["CueStepTarget"] == step["CueStepTarget"]
    metas = [load(n)["$defs"]["Meta"] for n in ("cue_decision.schema.json", "cue_growth.schema.json", "cue_ledger.schema.json")]
    assert metas[0] == metas[1] == metas[2]
    row = load("assist_ledger.schema.json")
    for k in ("$schema", "$id", "title", "description"):
        row.pop(k)
    copy = dict(load("cue_ledger.schema.json")["$defs"]["LedgerRow"])
    copy.pop("description")
    assert copy == row
    poll = dict(dec["Poll"]["properties"])
    assert poll.pop("t")["type"] == "number" and poll == dec["CueDecision"]["properties"]                # a poll is a decision plus the fixture clock
    assert dec["Poll"]["required"] == ["t", *dec["CueDecision"]["required"]]


# ------------------------------------------------------------------------------------------------ the examples
def _pack_validator_module():
    spec = importlib.util.spec_from_file_location("packs_validate_under_test", paths.repo_root() / "packages" / "packs" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        spec.loader.exec_module(mod)            # it puts its own folder on sys.path to import refmap
    finally:
        sys.path[:] = saved
    return mod


def test_the_cue_examples_are_registered_with_the_pack_validator_and_validate():
    mod = _pack_validator_module()
    files = sorted((SCHEMA_DIR / "examples").glob("cue.*.example.json"))
    assert {f.name for f in files} == {"cue.decisions.example.json", "cue.growth.example.json", "cue.growth_skill.example.json", "cue.ledger.example.json"}
    for f in files:
        prefix = next((k for k in mod.EXAMPLE_SCHEMAS if f.name.startswith(k)), None)
        assert prefix is not None, f.name
        schema = load(mod.EXAMPLE_SCHEMAS[prefix])
        assert mod.schema_errors(jsonschema.Draft202012Validator(schema), json.loads(f.read_text(encoding="utf-8")), f.name) == []
    assert mod.EXAMPLE_SCHEMAS["cue.decisions."] == "cue_decision.schema.json" and mod.EXAMPLE_SCHEMAS["cue.ledger."] == "cue_ledger.schema.json"
    assert mod.EXAMPLE_SCHEMAS["cue.growth."] == mod.EXAMPLE_SCHEMAS["cue.growth_skill."] == "cue_growth.schema.json"


def test_the_schemas_refuse_what_is_outside_the_vocabulary():
    ok = {"meta": dict(META_OK), "data": None}
    walk = json.loads((SCHEMA_DIR / "examples" / "cue.decisions.example.json").read_text(encoding="utf-8"))["stuck_after_result"]["polls"][-1]
    d = {k: v for k, v in walk.items() if k != "t"}
    assert problems(DECISION, d) == []
    assert problems(DECISION, {**d, "page_text": "x"})                                                  # closed
    assert problems(DECISION, {**d, "kind": "shout"})
    assert problems(DECISION, {**d, "why": {**d["why"], "reasons": ["because_i_said_so"]}})             # a reason id outside the table
    assert problems(DECISION, {**d, "episode_id": "episode 1"})
    assert problems(DECISION, {**d, "target": {**d["target"], "box_2d": [0, 0, 10]}})
    assert problems(DECISION, {**d, "say": {"chip": "x" * 41, "whisper": None, "whisper_id": None}})
    assert problems(DECISION, {**d, "question": {"type": "close_call", "text": "Free text from a model?"}})
    assert problems(DECISION, {k: v for k, v in d.items() if k != "stale"})                              # all keys always present
    assert ok["data"] is None and problems(ENVELOPE, ok)                                                 # data is a decision, never null


# ------------------------------------------------------------------------------------------------ the gate
def _gate_decisions() -> list[dict]:
    """Decisions of the pure gate over a ladder to the whisper, a question and an offer, and a withheld step, with the real pack vocabulary."""
    v = V.get_vocab("benefits-processor")
    assert v is not None
    kw = {"reason_text": v.text_of, "step_target": v.target}
    out = []
    ladder = Run(voice_ok=True, level=1)
    ladder.decide_kw = kw
    out += [ladder.poll(t).decision for t in (0, 2.5, 27.5, 52.5, 77.5)]
    asking = Run(cands=CLOSE)
    asking.decide_kw = kw
    out += [asking.poll(5.0 * k).decision for k in range(40)]
    held = Run(retrieval_due=True, start_stall=30)
    held.decide_kw = kw
    out.append(held.poll(0).decision)
    return [{**d.to_dict(), "meta": dict(META_OK)} for d in out]


def test_pure_gate_decisions_of_every_kind_match_the_decision_schema():
    ds = _gate_decisions()
    assert {d["kind"] for d in ds} >= {"none", "confirm", "cue", "ask", "offer"}
    assert any((d["say"] or {}).get("whisper") for d in ds)                                              # the whisper shape too
    for d in ds:
        assert problems(DECISION, d) == [], (d["kind"], d["why"]["reasons"])


# ------------------------------------------------------------------------------------------------ the routes
@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    ledger = Ledger(tmp_path / "assist" / "ledger.jsonl")
    app.state.cue_live = LiveCue(params=DEFAULT, ledger=ledger)
    return TestClient(app), ledger


def _get(c: TestClient, url: str, **params) -> dict:
    r = c.get(url, params=params)
    assert r.status_code == 200, (url, params, r.text)
    return r.json()


def test_cue_next_matches_the_envelope_schema_for_every_fixture_and_flag_variant(api):
    c, _ = api
    kinds: set[str] = set()
    for name in FX.NAMES:                                              # 0 to 150 s in 2.5 s steps: wait, cue, escalate, cap, silence, offer
        for k in range(61):
            body = _get(c, "/cue/next", person=f"p_{name}", fixture=name, t=2.5 * k)
            assert problems(ENVELOPE, body) == [], (name, 2.5 * k)
            assert "t" not in body["data"]
            kinds.add(body["data"]["kind"])
    assert kinds >= {"none", "confirm", "cue", "ask"}
    variants = ({"asked": "1"}, {"asked": "1", "voice_ok": "1"}, {"denied": "1"}, {"consent": "0"}, {"away": "1"}, {"dry": "1"},
                {"proactivity": "eager"}, {"proactivity": "quiet"}, {"quiet_s": "0.5"}, {"typing": "1"})
    for i, extra in enumerate(variants):
        for name in ("stuck_after_result", "close_call", "screen_disagrees", "ungrounded"):
            for t in (0, 60, 85, 87.5, 90, 112.5, 120, 150):
                body = _get(c, "/cue/next", person=f"p_{name}_v{i}", fixture=name, t=t, **extra)
                assert problems(ENVELOPE, body) == [], (name, t, extra)


def test_cue_next_with_no_context_is_a_silent_decision_that_matches_the_schema(api):
    c, _ = api
    body = _get(c, "/cue/next", person="p_nobody")
    assert problems(ENVELOPE, body) == []
    assert body["data"]["kind"] == "none" and body["data"]["why"]["reasons"] == ["no_context"] and body["data"]["step"] is None


def _seed(ledger: Ledger, kind: str, person: str, n_per_skill: int, seed: int) -> None:
    rows, _ = SL.simulate_learner(SL.preset(kind), np.random.default_rng(seed), person=person, n_per_skill=n_per_skill)
    ledger.extend(rows)


def test_growth_matches_the_schema_for_every_kind_of_ledger(api):
    c, ledger = api
    _seed(ledger, "improving", "p_few", 1, 1)                                  # 3 occurrences: too early for everything
    _seed(ledger, "improving", "p_mid", 12, 2)
    _seed(ledger, "improving", "p_improving", 30, 3)
    _seed(ledger, "flat", "p_flat", 15, 4)
    _seed(ledger, "declining", "p_declining", 15, 5)
    for i, stream in enumerate(("delegated", "automation")):                   # offloaded work: listed, never scored
        r = c.post("/cue/offloaded", json={"person": "p_improving", "role": "benefits-processor", "stream": stream, "routine": "calc-entry-3x",
                                           "outcome": "done", "minutes": 12.5, "skill": "enter-household-once", "origin": "synthetic"})
        assert r.status_code == 200, r.text
    seen_directions: set[str] = set()
    for person in ("p_nobody", "p_few", "p_mid", "p_improving", "p_flat", "p_declining"):
        body = _get(c, "/growth", person=person)
        assert problems(GROWTH, body) == [], person
        seen_directions |= {s["direction"] for s in body["data"]["by_skill"]} | {body["data"]["trend"]["direction"]}
    assert "too_early" in seen_directions and len(seen_directions) >= 2
    for skill in ("check-the-cliff", "overall", "no-such-skill"):
        body = _get(c, "/growth", person="p_improving", skill=skill)
        assert problems(GROWTH, body) == [], skill
        assert body["data"]["skill"] == (None if skill == "overall" else skill)
    full = _get(c, "/growth", person="p_improving")["data"]
    assert full["readiness"]["ready"] and full["offloaded"]["delegated"] == 1 and full["offloaded"]["automation"] == 1 and full["curve"]


def test_the_ledger_matches_the_schema_with_assist_and_offloaded_rows(api):
    c, ledger = api
    _seed(ledger, "improving", "p_led", 5, 7)
    for stream in ("delegated", "automation"):
        r = c.post("/cue/offloaded", json={"person": "p_led", "role": "benefits-processor", "stream": stream, "routine": "calc-entry-3x",
                                           "outcome": "done", "minutes": 9.0, "origin": "synthetic"})
        assert r.status_code == 200, r.text
    for params in ({"person": "p_led"}, {"person": "p_led", "stream": "assist"}, {"person": "p_led", "stream": "delegated"}, {"person": "p_led", "limit": 3},
                   {"person": "p_nobody"}):
        body = _get(c, "/cue/ledger", **params)
        assert problems(LEDGER, body) == [], params
    both = _get(c, "/cue/ledger", person="p_led")["data"]
    assert both["counts"] == {"assist": 15, "delegated": 1, "automation": 1}
    assert any(r["stream"] == "delegated" and r["routine"] == "calc-entry-3x" and r["offload_outcome"] == "done" for r in both["rows"])
    assert _get(c, "/cue/ledger", person="p_nobody")["data"] == {"rows": [], "counts": {"assist": 0, "delegated": 0, "automation": 0}}
