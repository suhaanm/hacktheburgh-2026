"""Actions, prompts and the model participant, with a stub model port (no network, no model)."""
from __future__ import annotations

import json

import pytest

from evals.study_sim.budget import Budget, BudgetExhausted
from evals.study_sim.design import household_card, load_cases
from evals.study_sim.observe import is_submit_control, parse_actions, render_elements, url_allowed, url_parts
from evals.study_sim.participant import (DECIDE_SCHEMA, MAX_NOTE, FakeParticipant, ModelParticipant, StepContext, build_note_prompt, build_prompt,
                                         persona_text, cache_key)

URLS = {"gov": "http://127.0.0.1:7911/step/1", "quick": "http://127.0.0.1:7912/", "note": "http://127.0.0.1:7911/casenote"}
PORTS = {7911, 7912, 7913}


def test_parse_actions_validates_and_caps():
    acts = parse_actions({"actions": [{"kind": "click", "ref": 3}, {"kind": "fill", "ref": 4, "text": "56"}, {"kind": "teleport"}, "junk",
                                      {"kind": "wait", "seconds": 2}, {"kind": "finish"}, {"kind": "click", "ref": 9}]}, max_actions=4)
    assert [a.kind for a in acts] == ["click", "fill", "wait", "finish"]
    assert acts[1].text == "56" and acts[0].ref == 3 and acts[2].seconds == 2
    assert parse_actions({}) == [] and parse_actions({"actions": None}) == []
    assert parse_actions({"actions": [{"kind": "click", "ref": True}]})[0].ref is None


def test_url_rules():
    assert url_allowed("http://127.0.0.1:7911/step/1", PORTS) and url_allowed("http://127.0.0.1:7912/", PORTS)
    assert not url_allowed("http://127.0.0.1:7700/health", PORTS) and not url_allowed("https://example.com/", PORTS)
    assert not url_allowed("http://localhost:7911/", PORTS) and not url_allowed("", PORTS)
    assert url_parts("http://127.0.0.1:7911/casenote/CN-1234?x=1") == (7911, "/casenote/CN-1234")


def test_submit_control_detection():
    assert is_submit_control("Submit to claimant record", "") and is_submit_control("submit  to claimant record", "x")
    assert is_submit_control("", "submit-note") and is_submit_control("", "cn-submit")
    assert not is_submit_control("Save draft", "save-draft")


def test_render_elements_marks_the_ring_and_has_no_brackets():
    txt = render_elements([{"ref": 2, "tag": "button", "label": "Check cliff edges", "dom_id": "cliff-btn", "ringed": True},
                           {"ref": 3, "tag": "select", "label": "Tenure", "options": [{"value": "rent", "text": "Rent"}, {"value": "own", "text": "Own"}], "value": "own"},
                           {"ref": 4, "tag": "input", "type": "text", "label": "Your age", "value": "56"}])
    assert "ringed in orange" in txt and "currently: Own" in txt and 'value: "56"' in txt
    assert not any(ch in txt for ch in "[]<>{}|`")                      # the model port's sanitiser would rewrite these


def _ctx(spec, phase="practice", coach=None, note=None, ring=False):
    card = household_card(load_cases()[spec.blocks[0].practice_case])
    return StepContext(spec=spec, phase=phase, card=card, obs={"url": "http://x", "text": "Check what benefits you could get", "elements": []},
                       tabs=[{"index": 0, "url": "", "title": "", "active": True, "name": "blank page"}], history=[], used=3, cap=60, urls=URLS,
                       note_to_self=note, coach=coach, ring_found=ring)


def test_prompt_is_neutral_about_the_skills(specs):
    for s in specs[:8]:
        text = build_prompt(_ctx(s)).lower()
        note_prompt = build_note_prompt(s, "1. clicked something").lower()
        for banned in ("cliff", "reconcil", "capital", "tariff", "discrepan", "agree", "expert", "benefit knowledge"):
            assert banned not in text.replace("benefits work", "").replace("what benefits you", ""), banned
            assert banned not in note_prompt, banned
        assert s.pid in text and "participant code" in text
        assert "never press submit to claimant record" in text


def test_persona_text_varies_and_is_not_about_knowledge(specs):
    texts = {persona_text(s.persona) for s in specs}
    assert len(texts) > 6
    for t in texts:
        assert "no prior experience of benefits work" in t
        assert not any(w in t.lower() for w in ("expert", "knowledgeable", "trained"))


def test_post_test_shows_the_note_only_in_the_post_phase(specs):
    s = specs[0]
    assert "note you wrote to yourself" not in build_prompt(_ctx(s, "practice", note="do x")).lower()
    post = build_prompt(_ctx(s, "post", note="open the thing first"))
    assert "open the thing first" in post and "on your own" in post.lower()
    assert "On your own" not in build_prompt(_ctx(s, "practice"))


def test_coach_overlay_appears_in_the_prompt_only_when_up(specs):
    s = specs[0]
    assert "switched on on this computer" not in build_prompt(_ctx(s)).lower()
    up = build_prompt(_ctx(s, coach={"message": "Check cliff edges before you copy this result."}, ring=True))
    assert "Check cliff edges before you copy this result." in up and "orange ring" in up


class StubPort:
    """Stands in for the model port: records prompts, returns scripted JSON, keeps token stats like the OpenAI provider."""
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []
        self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def check(self, prompt, schema):
        self.prompts.append(prompt)
        self.stats["calls"] += 1
        self.stats["input_tokens"] += 1000
        self.stats["output_tokens"] += 50
        return self.replies.pop(0)


@pytest.mark.asyncio
async def test_model_participant_caches_by_prompt_and_charges(specs, tmp_path):
    port = StubPort([{"thought": "t", "actions": [{"kind": "click", "ref": 1}]}, {"note": "x" * 400}])
    b = Budget(ledger_path=tmp_path / "ledger.jsonl")
    mp = ModelParticipant(port, specs[0], b, "stub-model", cache_dir=tmp_path / "cache")
    ctx = _ctx(specs[0])
    a1 = await mp.decide(ctx)
    a2 = await mp.decide(ctx)                                       # identical prompt: from the cache
    assert [x.kind for x in a1] == [x.kind for x in a2] == ["click"] and len(port.prompts) == 1 and b.cache_hits == 1 and b.calls == 1
    note = await mp.write_note("1. did things")
    assert len(note) == MAX_NOTE and b.calls == 2
    assert (tmp_path / "ledger.jsonl").read_text().count("\n") == 2
    # a different participant has a different prompt hash even with the same persona and page
    k1 = cache_key("m", build_prompt(_ctx(specs[0])), DECIDE_SCHEMA)
    k2 = cache_key("m", build_prompt(_ctx(specs[1])), DECIDE_SCHEMA)
    assert k1 != k2


def test_budget_cap_and_start_rule(tmp_path):
    b = Budget(cap_usd=1.0)
    b.charge("p1", "decide", 100_000, 10_000)
    assert b.usd == pytest.approx(0.25 + 0.15)
    b.finished.add("p1")
    assert not b.can_start_participant(0)                           # 0.40 + 1.5 * 0.40 = 1.0 is above 95% of the cap: not enough room
    b2 = Budget(cap_usd=8.0)
    b2.charge("p1", "decide", 400_000, 40_000)
    b2.finished.add("p1")
    assert b2.can_start_participant(0) and not b2.can_start_participant(8)
    with pytest.raises(BudgetExhausted):
        Budget(cap_usd=0.01).charge("p", "decide", 100_000, 0)


def test_fake_participant_programs_differ_and_never_submit_by_default(specs):
    cases = load_cases()
    c = cases[specs[0].blocks[0].practice_case]
    skipper = FakeParticipant(specs[0], c["site_inputs"], "CASE-1", urls=URLS, style="skipper")
    thorough = FakeParticipant(specs[0], c["site_inputs"], "CASE-1", urls=URLS, style="thorough")
    skipper._start()
    thorough._start()
    flat = lambda p: json.dumps(p)  # noqa: E731
    assert "Check cliff edges" not in flat(skipper.program) and "Check cliff edges" in flat(thorough.program)
    assert "Submit to claimant" not in flat(skipper.program) and "Discrepancy" in flat(thorough.program)
    sub = FakeParticipant(specs[0], c["site_inputs"], "CASE-1", urls=URLS, style="skipper", submits=True)
    sub._start()
    assert "Submit to claimant" in flat(sub.program)


def test_schemas_survive_the_ports_strict_conversion():
    """The OpenAI strict mode needs every property required and nullable-if-optional; the port converts and then validates against OUR schema."""
    from understudy_agent.models.strict import to_strict_schema, validate_output

    from evals.study_sim.participant import NOTE_SCHEMA
    strict = to_strict_schema(DECIDE_SCHEMA)
    item = strict["properties"]["actions"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"kind", "ref", "text", "url", "seconds"}
    assert "null" in item["properties"]["ref"]["type"] and item["properties"]["kind"]["type"] == "string"
    out = validate_output({"thought": "t", "actions": [{"kind": "click", "ref": 3, "text": None, "url": None, "seconds": None}]}, DECIDE_SCHEMA)
    assert out["actions"][0] == {"kind": "click", "ref": 3}                       # optional nulls are dropped
    assert validate_output({"note": "x"}, NOTE_SCHEMA) == {"note": "x"}
    with pytest.raises(Exception):
        validate_output({"thought": "t", "actions": [{"kind": "click", "ref": "three"}]}, DECIDE_SCHEMA)


@pytest.mark.asyncio
async def test_transient_errors_are_retried_and_refusals_are_not(specs, tmp_path):
    class Flaky(StubPort):
        def check(self, prompt, schema):
            if not self.replies:
                raise RuntimeError("never reached")
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return super().check(prompt, schema) if False else self._ok(prompt, r)

        def _ok(self, prompt, r):
            self.prompts.append(prompt)
            self.stats["input_tokens"] += 10
            self.stats["output_tokens"] += 1
            return r

    class ProviderError(RuntimeError):
        pass

    class ModelRefusal(RuntimeError):
        pass

    port = Flaky([ProviderError("429"), ProviderError("timeout"), {"thought": "t", "actions": [{"kind": "finish"}]}])
    mp = ModelParticipant(port, specs[0], Budget(), "m", cache_dir=tmp_path / "c1")
    mp.retry_sleeps = (0, 0, 0)
    assert [a.kind for a in await mp.decide(_ctx(specs[0]))] == ["finish"] and mp.errors == 2
    refusing = Flaky([ModelRefusal("no")])
    mp2 = ModelParticipant(refusing, specs[1], Budget(), "m", cache_dir=tmp_path / "c2")
    mp2.retry_sleeps = (0, 0, 0)
    assert await mp2.decide(_ctx(specs[1])) == []
    always = Flaky([ProviderError("x")] * 4)
    mp3 = ModelParticipant(always, specs[2], Budget(), "m", cache_dir=tmp_path / "c3")
    mp3.retry_sleeps = (0, 0, 0)
    from evals.study_sim.participant import HarnessModelError
    with pytest.raises(HarnessModelError):
        await mp3.decide(_ctx(specs[2]))


def test_clean_typed_removes_only_structured_reply_artifacts():
    from evals.study_sim.observe import clean_typed
    seen = {"36},{": "36", "190.00},{": "190.00", "12000},{": "12000", "56},{": "56", "16000/": "16000", "12000.00?": "12000.00", "18000?": "18000",
            "45, 45?": "45, 45", "455.00?": "455.00", "12000.00/": "12000.00", "42 42 42 42 42 42": "42", "56 ": "56", "CASE-1004": "CASE-1004",
            "£801.14": "£801.14", "12000.00 GBP?": "12000.00 GBP?", "£0": "£0", "Match": "Match", "cliff edge?": "cliff edge?", "": "", "n/a": "n/a",
            'He said "no"': "He said"}
    for raw, want in seen.items():
        assert clean_typed(raw) == want, (raw, clean_typed(raw), want)
    assert clean_typed("12,000") == "12,000" and clean_typed("1 2 3") == "1 2 3" and clean_typed("a a a") == "a a a"      # human-like input is left alone
