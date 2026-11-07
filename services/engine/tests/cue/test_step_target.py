"""A Cue step says where its control is (``step.target``), from the pack's own mapping through the coach's helper (CUE-ENGINE-2).

The desktop's DOM tracker can only follow a ring that moved if the step carries a zone it can ask the extension for. The coach has
always answered that question (``coach.messages.target_for``); Cue shares the helper, so these tests check: a step with a zone, a step
without one, the pack's override, that nothing is copied from the coach's rules, the closed schema and the generated examples, that every
step of every shipped pack has a reason text, and that every kind of decision that names a step carries the field.
"""
from __future__ import annotations

import json

import jsonschema
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.api.errors import install_error_handlers
from understudy_engine.coach import Step, target_for
from understudy_engine.cogs.mapper import load_mapping
from understudy_engine.cue import make_examples, paths, vocab as V
from understudy_engine.cue import routes as R
from understudy_engine.cue.gate import _step_dict
from understudy_engine.cue.live import LiveCue
from understudy_engine.cue.params import DEFAULT
from understudy_engine.cue.target import LABEL_MAX, step_target
from understudy_engine.cue.types import Candidate
from understudy_engine.packs import load_pack

from .helpers import CLOSE, Run

ROLES = ("benefits-processor", "programmer", "data-analyst")
EXAMPLES = paths.repo_root() / "packages" / "schema" / "examples" / "cue.decisions.example.json"
CLIFF_TARGET = {"zone": "cliff_button", "label_hint": "Check cliff edges", "role_hint": "button"}


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(paths.step_schema_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema):
    return jsonschema.Draft202012Validator(schema)


def problems(validator, doc) -> list[str]:
    return [e.message for e in validator.iter_errors(doc)]


def standing_in(sid: str) -> dict:
    """A stand-in for ``vocab.target`` so the gate tests do not depend on a pack."""
    return {"zone": f"zone_{sid}", "label_hint": f"Label {sid}", "role_hint": "button"}


# ------------------------------------------------------------------------------------------------ the pure part
def test_a_step_with_a_zone_gets_the_coach_helpers_answer():
    v = V.get_vocab("benefits-processor")
    assert v is not None
    assert v.target("cliff_a") == CLIFF_TARGET
    assert v.target("reconcile") == {"zone": "reconcile_control", "label_hint": "How do they compare", "role_hint": "select"}   # no site, no fallback_zones
    assert v.target("calc_b")["zone"] == "calc_site"
    assert v.target("no_such_step") is None


def test_a_step_without_a_zone_gets_none():
    m = load_mapping(None)
    s = Step(id="x", label="Do the thing", cogs=("NO_SUCH_COG",))
    assert target_for(s, m)["zone"] is None                  # the coach's helper has no zone for it
    assert step_target(s, m) is None                         # so the cue is text only
    assert step_target(Step(id="y", label="No cogs", cogs=()), m) is None
    assert step_target(None, m) is None
    assert step_target(Step(id="z", label="Z", cogs=("READ",)), None) is None


def test_a_pack_override_is_used_and_stays_closed():
    m = load_mapping(None)
    base = dict(id="s", label="Press Go on the form", cogs=("READ",))
    ok = Step(**base, coach={"target": {"zone": "go_button", "label_hint": "Go", "role_hint": "button"}})
    assert step_target(ok, m) == {"zone": "go_button", "label_hint": "Go", "role_hint": "button"}
    assert step_target(Step(**base, coach={"target": {"zone": "Go Button!", "label_hint": "Go"}}), m) is None          # not a zone id
    odd_role = Step(**base, coach={"target": {"zone": "go_button", "label_hint": "Go", "role_hint": "Big <b>"}})
    assert step_target(odd_role, m)["role_hint"] == "region"
    long = "word " * 40
    t = step_target(Step(**base, coach={"target": {"zone": "go_button", "label_hint": long}}), m)
    assert len(t["label_hint"]) <= LABEL_MAX and long.startswith(t["label_hint"]) and not t["label_hint"].endswith(" ")


def test_the_target_is_the_coach_helpers_answer_for_every_step_not_a_copy_of_its_rules():
    for role in ROLES:
        v = V.get_vocab(role)
        assert v is not None and v.mapping == load_pack(role).cog_mapping()        # the same mapping the coach reads
        for sid, s in v.policy.steps.items():
            raw = target_for(s, v.mapping)
            got = v.target(sid)
            assert got == {"zone": raw["zone"], "label_hint": raw["label_hint"], "role_hint": raw["role_hint"]}, (role, sid)   # every shipped step has a zone


# ------------------------------------------------------------------------------------------------ reason text for every step
@pytest.mark.parametrize("role", ROLES)
def test_every_candidate_step_of_a_shipped_pack_has_a_reason_text_and_a_closed_target(role, validator):
    v = V.get_vocab(role)
    assert v is not None and len(v.policy.order) >= 3
    for sid in v.policy.order:
        c = Candidate(id=sid, group=v.group(sid), label=v.label(sid), p=0.5, skill=v.skill(sid), reason_id=v.reason_id(sid), cogs=v.cogs(sid))
        d = _step_dict(c, v.text_of, v.target)
        assert d["reason_text"] and len(d["reason_text"].split()) <= 12, (role, sid)
        assert d["reason_id"] != "why.generic", (role, sid)             # a reason about this step, not the fallback line
        assert set(d["target"]) == {"zone", "label_hint", "role_hint"}, (role, sid)
        assert problems(validator, d) == [], (role, sid, d)


DANGLING = {"a", "an", "the", "of", "to", "and", "or", "with", "you", "your", "on", "in", "for", "by", "than", "that", "before", "after", "when", "if", "at", "from"}


@pytest.mark.parametrize("role", ROLES)
def test_every_short_label_is_written_by_hand_fits_and_is_not_a_clipped_long_label(role):
    """The chip and the ask options show the short label. It must be a whole phrase in the pack's words, never the long label cut at 32 characters:
    not cut inside a word and not ending on a dangling word ("before", "the", "a"). (``short()`` can still coincide with a hand-written label that is a
    whole phrase, such as "Reconcile the three results", so equality with it is not the test.)"""
    v = V.get_vocab(role)
    assert v is not None
    assert set(V.SHORT_LABELS[role]) == set(v.policy.steps)              # no step falls back to clipping the pack's long label
    for sid, step in v.policy.steps.items():
        label, long = v.label(sid), " ".join(step.label.split())
        assert 0 < len(label) <= V.LABEL_MAX, (role, sid, label)
        assert len(V.chip_text(label)) <= V.CHIP_MAX and len(V.whisper_text(label).split()) <= V.WHISPER_WORDS, (role, sid, label)
        if long.startswith(label) and len(long) > len(label):              # a prefix of the long label is fine only as a whole phrase:
            assert not long[len(label)].isalnum(), (role, sid, label)      # not cut inside a word
        last = label.split()[-1]
        assert last.strip(",.") not in DANGLING, (role, sid, label)        # never ends on "before", "the", "a" (case-sensitive: "calculator A" is a name)
        assert label == label.strip() and "  " not in label and label[0].isupper(), (role, sid, label)


def test_a_step_dict_without_a_reason_table_or_a_target_source_still_has_every_key():
    c = Candidate(id="cliff_a", group="cliff_a", label="Check cliff edges (A)", p=0.9, skill="check-the-cliff", reason_id="why.cliff")
    assert _step_dict(c, None) == {"id": "cliff_a", "label": "Check cliff edges (A)", "reason_id": "why.cliff", "reason_text": None, "target": None}


# ------------------------------------------------------------------------------------------------ the closed schema
def test_the_schema_file_is_valid_and_closed(schema):
    jsonschema.Draft202012Validator.check_schema(schema)
    for name in ("CueStep", "CueStepTarget"):
        assert schema["$defs"][name]["additionalProperties"] is False
    assert set(schema["$defs"]["CueStepTarget"]["properties"]) == {"zone", "label_hint", "role_hint"}
    assert set(schema["$defs"]["CueStep"]["required"]) == set(schema["$defs"]["CueStep"]["properties"])


def test_the_schema_refuses_anything_outside_the_closed_vocabulary(validator):
    good = {"id": "cliff_a", "label": "Check cliff edges (A)", "reason_id": "why.cliff", "reason_text": "A figure near a limit can flip the answer.", "target": dict(CLIFF_TARGET)}
    assert problems(validator, good) == []
    assert problems(validator, {**good, "target": None}) == []

    def with_target(**kw):
        return {**good, "target": {**CLIFF_TARGET, **kw}}

    assert problems(validator, with_target(extra="x"))                               # closed: no extra key in the target
    assert problems(validator, {**good, "page_text": "x"})                           # closed: no extra key in the step
    assert problems(validator, with_target(zone="Cliff Button"))                     # a zone is an id, not a selector or a phrase
    assert problems(validator, with_target(zone="#cliff > button"))
    assert problems(validator, with_target(label_hint="x" * (LABEL_MAX + 1)))
    assert problems(validator, with_target(label_hint=""))
    assert problems(validator, with_target(role_hint="Big Button"))
    assert problems(validator, {k: v for k, v in good.items() if k != "target"})     # the key is always present: null, never missing
    assert problems(validator, {**good, "target": {"zone": "cliff_button"}})         # all three words, always


def test_the_generated_examples_match_the_schema_and_carry_a_target(validator):
    doc = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    steps = [p["step"] for walk in doc.values() for p in walk["polls"] if p.get("step")]
    assert len(steps) >= 5
    for s in steps:
        assert problems(validator, s) == [], s
    assert all(s["target"] == CLIFF_TARGET for s in steps if s["id"] == "cliff_a")
    assert {s["id"] for s in steps} >= {"cliff_a"}


def _kinds_and_steps(doc: dict) -> dict:
    return {name: [(p["t"], p["kind"], p.get("step")) for p in walk["polls"]] for name, walk in doc.items()}


def test_the_decision_examples_have_the_kinds_and_steps_make_examples_writes_now():
    """Regenerate with ``python -m understudy_engine.cue.make_examples decisions`` when the step shape changes. Only the kinds and the steps are compared: the
    path-prior numbers depend on whether data/synthetic/apprentices exists on the machine that wrote the file (this test runs without it)."""
    on_disk = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    now = json.loads(json.dumps(make_examples.build_decisions()))
    assert _kinds_and_steps(now) == _kinds_and_steps(on_disk)


# ------------------------------------------------------------------------------------------------ every decision that names a step
def drive(run: Run, n: int = 40, dt: float = 5.0) -> list:
    return [run.poll(dt * k).decision for k in range(n)]


def test_cue_and_its_persisting_polls_carry_the_step_target(validator):
    run = Run()
    run.decide_kw = {"reason_text": V.REASONS.get, "step_target": standing_in}
    cues = [d for d in drive(run, 6, 2.5) if d.kind == "cue"]
    assert len(cues) >= 2 and cues[0].new and not cues[1].new           # the new cue, then the same cue persisting
    for d in cues:
        assert d.step["target"] == standing_in("cliff_a")
        assert problems(validator, d.step) == []


def test_ask_and_offer_carry_the_step_target():
    run = Run(cands=CLOSE)
    run.decide_kw = {"reason_text": V.REASONS.get, "step_target": standing_in}
    decisions = drive(run, 40)
    kinds = {d.kind for d in decisions}
    assert {"ask", "offer"} <= kinds
    named = [d for d in decisions if d.step is not None]
    assert named and all(d.step["target"] == standing_in(d.step["id"]) for d in named)


def test_confirm_carries_the_step_target():
    run = Run(retrieval_due=True, start_stall=30)
    run.decide_kw = {"reason_text": V.REASONS.get, "step_target": standing_in}
    d = run.poll(0).decision
    assert d.kind == "confirm" and d.step["target"] == standing_in("cliff_a")


def test_without_a_target_source_the_key_is_there_and_null():
    run = Run()
    d = [x for x in drive(run, 6, 2.5) if x.kind == "cue"][0]
    assert "target" in d.step and d.step["target"] is None
    # the decision's own target (the ring box) is a different field and is unchanged
    assert set(d.target) == {"box_2d", "source", "confidence"}


def test_a_silent_decision_names_no_step():
    assert Run().poll(0, p=0.1, stall=5).decision.step is None


# ------------------------------------------------------------------------------------------------ the route
@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_CUE", "1")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(R.router)
    app.state.cue_live = LiveCue(params=DEFAULT)
    return TestClient(app)


def test_get_cue_next_returns_the_step_target_for_every_fixture_kind(client, validator):
    seen: dict[str, dict] = {}
    for name, ts in (("stuck_after_result", (0, 60, 85, 87.5, 90, 105, 120)), ("close_call", (0, 60, 85, 87.5)), ("retrieval", (0, 60))):
        for t in ts:
            r = client.get("/cue/next", params={"person": f"p_{name}", "fixture": name, "t": t})
            assert r.status_code == 200, r.text
            d = r.json()["data"]
            if d["step"] is not None:
                assert problems(validator, d["step"]) == [], (name, t, d["step"])
                seen[d["kind"]] = d
    assert {"cue", "ask", "confirm"} <= set(seen)
    assert seen["cue"]["step"]["target"] == CLIFF_TARGET
    assert seen["ask"]["step"]["target"] == CLIFF_TARGET and seen["confirm"]["step"]["target"] == CLIFF_TARGET
    assert seen["cue"]["target"]["source"] == "dom"                      # the ring box is a different field and is unchanged
