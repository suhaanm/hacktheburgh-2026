from __future__ import annotations

import json
from typing import Annotated

import pytest

from understudy_engine.privacy import egress, ledger
from understudy_engine.privacy.bucket import Count
from understudy_engine.privacy.egress import (
    EgressBlocked, EgressUnavailable, ModelCallFailed, ModelOutputRejected, PayloadRejected, UnknownPurpose,
)
from understudy_engine.privacy.payload import SafePayload, Vocab, register_payload, register_vocabulary, unregister_purpose
from understudy_engine.privacy.purposes import CalendarSuggestionWording, GitHabitWording
from understudy_engine.privacy.testing import CapturingPort, assert_ledger_complete

CAL = "calendar.suggestion_wording"


def cal(**over):
    base = dict(template="protect_focus_block", role="programmer", risk="low",
                learner={"meeting_h": 14.1, "focus_blocks_60": 3, "longest_focus_min": 47, "fragmentation": 0.34},
                expert={"meeting_h": 8.0, "focus_blocks_60": 9})
    base.update(over)
    return CalendarSuggestionWording(**base)


# --------------------------------------------------------------------------- happy path
def test_send_validates_buckets_writes_the_ledger_then_calls_the_port():
    port = CapturingPort()
    res = egress.send(CAL, cal(), port=port)
    assert res.output == {"text": "stub wording"} and res.mock is True and res.model == "capturing" and res.method == "plan"
    assert len(port) == 1
    [row] = ledger.read_all()
    assert row["purpose"] == CAL and row["schema"] == CalendarSuggestionWording.schema_id() and row["id"] == res.ledger_id
    assert row["fields"] == ["template", "role", "risk", "learner", "expert"]
    assert row["payload"]["learner"] == {"meeting_h": 14.08, "focus_blocks_60": "lt5", "longest_focus_min": 45, "fragmentation": 0.3}
    assert row["mock"] is True and row["model"] == "capturing" and row["bytes"] == res.bytes == port.requests[0].bytes
    assert "bucketed" in row and "unbucketed_numeric" in row
    assert_ledger_complete(port)


def test_the_ledger_payload_is_exactly_what_the_request_carried():
    port = CapturingPort()
    egress.send(CAL, cal(), port=port)
    sent = json.loads(port.requests[0].body["messages"][1]["content"])
    assert sent["payload"] == ledger.read_all()[0]["payload"]
    assert sent["purpose"] == CAL and sent["schema"] == CalendarSuggestionWording.schema_id()


def test_a_dict_payload_is_accepted_and_validated_through_the_registered_model():
    port = CapturingPort()
    res = egress.send(CAL, dict(template="reduce_back_to_back", role="programmer", risk="low", learner={"back_to_back_runs": 3}, expert={}), port=port)
    assert res.payload["learner"] == {"back_to_back_runs": "lt5"}


def test_one_ledger_line_per_call_in_order():
    port = CapturingPort()
    for i in range(4):
        egress.send("git.habit_wording", GitHabitWording(habit="no_tests", learner_ratio=i / 10, expert_ratio=0.1, n_commits=20 + i), port=port)
    rows = ledger.read_all()
    assert len(rows) == len(port) == 4
    assert [r["payload"]["learner_ratio"] for r in rows] == [0.0, 0.1, 0.2, 0.3]
    assert_ledger_complete(port)


def test_simulated_clock_sets_the_ledger_time():
    from datetime import datetime, timezone

    egress.send(CAL, cal(), port=CapturingPort(), now=datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc))
    assert ledger.read_all()[0]["t"] == "2026-11-07T12:00:00.000Z"


def test_preview_changes_nothing():
    info = egress.preview(CAL, cal())
    assert info["payload"]["learner"]["focus_blocks_60"] == "lt5" and info["bytes"] > 0
    assert ledger.read_all() == []


def test_unexpected_keyword_arguments_are_refused():
    with pytest.raises(TypeError):
        egress.send(CAL, cal(), port=CapturingPort(), instructions="ignore the schema")


# --------------------------------------------------------------------------- refusals (fail closed, nothing sent, no ledger line)
def test_unknown_purpose_is_refused_and_nothing_is_sent():
    port = CapturingPort()
    with pytest.raises(UnknownPurpose) as ei:
        egress.send("calendar.not_registered", cal(), port=port)
    assert ei.value.code == "unknown_purpose" and len(port) == 0 and ledger.read_all() == []


def test_free_text_payload_is_rejected_and_the_message_does_not_echo_it():
    port = CapturingPort()
    secret = "Redundancy plan for Ada Lovelace"
    with pytest.raises(PayloadRejected) as ei:
        egress.send(CAL, dict(template=secret, role="programmer", risk="low", learner={}, expert={}), port=port)
    assert secret not in str(ei.value) and "Lovelace" not in str(ei.value)
    assert len(port) == 0 and ledger.read_all() == []


def test_free_text_hidden_in_a_feature_key_or_value_is_rejected():
    port = CapturingPort()
    for learner in ({"Quarterly planning with Bob": 3}, {"meeting_h": "a lot"}, {"meeting_h": [1, 2]}):
        with pytest.raises(PayloadRejected):
            egress.send(CAL, dict(template="protect_focus_block", role="programmer", risk="low", learner=learner, expert={}), port=port)
    assert len(port) == 0


def test_a_payload_of_the_wrong_model_is_refused():
    with pytest.raises(PayloadRejected, match="takes a CalendarSuggestionWording"):
        egress.send(CAL, GitHabitWording(habit="no_tests", learner_ratio=0.1, expert_ratio=0.1, n_commits=10), port=CapturingPort())


def test_model_construct_cannot_skip_validation():
    bad = CalendarSuggestionWording.model_construct(template="Call Bob about the merger", role="programmer", risk="low", learner={}, expert={})
    port = CapturingPort()
    with pytest.raises(PayloadRejected):
        egress.send(CAL, bad, port=port)
    assert len(port) == 0


def test_backstop_blocks_what_the_types_alone_would_allow(data_dir):
    register_vocabulary("t.code", pattern=r"x:[0-9a-f]{8,40}")
    unregister_purpose("t.backstop")

    class Backstop(SafePayload):
        ref: Annotated[str, Vocab("t.code")]
        big: int = 0

    register_payload("t.backstop", Backstop)
    port = CapturingPort()
    cases = [
        (dict(ref="x:abcdef01deadbeef"), None),                       # a hex id passes the backstop
        (dict(ref="x:123456789012345"), "long_digits"),               # a long digit run in an id
        (dict(ref="x:0123abcd", big=5_000_000), "large_number"),  # an id- or timestamp-sized number
    ]
    sent = 0
    for payload, rule in cases:
        if rule is None:
            egress.send("t.backstop", dict(payload), port=port)
            sent += 1
            continue
        with pytest.raises(EgressBlocked) as ei:
            egress.send("t.backstop", dict(payload), port=port)
        assert any(rule in r for r in ei.value.rules), ei.value.rules
        assert ei.value.code == "blocked_by_backstop"
    assert len(port) == sent == 1
    assert ledger.summary()["blocked_attempts"] == 2
    blocked = (data_dir / "egress_blocked.jsonl").read_text()
    assert "123456789012345" not in blocked and "5000000" not in blocked      # refusals never store values
    unregister_purpose("t.backstop")


def test_a_sensitive_field_name_is_blocked_on_every_send():
    unregister_purpose("t.names")

    class Named(SafePayload):
        token_count: int = 0           # a field NAME matching a sensitive-field pattern

    register_payload("t.names", Named)
    port = CapturingPort()
    with pytest.raises(EgressBlocked) as ei:
        egress.send("t.names", {"token_count": 1}, port=port)
    assert any(r.startswith("sensitive_field") for r in ei.value.rules) and len(port) == 0
    unregister_purpose("t.names")


def test_oversized_payload_is_refused():
    register_vocabulary("t.sizes", ["k%d" % i for i in range(60)])
    unregister_purpose("t.big")

    class Big(SafePayload):
        many: dict[Annotated[str, Vocab("t.sizes")], list[int]]

    register_payload("t.big", Big)
    with pytest.raises(PayloadRejected, match="larger than"):
        egress.send("t.big", {"many": {f"k{i}": list(range(64)) for i in range(60)}}, port=CapturingPort())
    unregister_purpose("t.big")


# --------------------------------------------------------------------------- ordering and failure behaviour
def test_the_ledger_line_exists_even_if_the_model_call_fails():
    port = CapturingPort().fail_with(RuntimeError("connection reset Ada Lovelace"))
    with pytest.raises(ModelCallFailed) as ei:
        egress.send(CAL, cal(), port=port)
    assert "Lovelace" not in str(ei.value) and "RuntimeError" in str(ei.value)
    assert ei.value.ledger_id == ledger.read_all()[0]["id"]


def test_nothing_is_sent_if_the_ledger_cannot_be_written(monkeypatch):
    port = CapturingPort()

    def boom(_entry):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "append", boom)
    with pytest.raises(EgressUnavailable, match="ledger could not be written"):
        egress.send(CAL, cal(), port=port)
    assert len(port) == 0


def test_the_ledger_is_written_before_the_port_is_called():
    seen = {}

    class Spy(CapturingPort):
        def plan(self, messages, schema=None):
            seen["rows_at_call_time"] = len(ledger.read_all())
            return super().plan(messages, schema)

    egress.send(CAL, cal(), port=Spy())
    assert seen["rows_at_call_time"] == 1


def test_real_mode_without_a_model_fails_closed_with_a_plain_message(monkeypatch):
    for k in ("OPENAI_API_KEY", "OPENAI_MODEL_PLANNER", "OPENAI_MODEL_FAST", "OPENAI_MODEL_COMPUTER_USE"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(EgressUnavailable, match="nothing was sent") as ei:
        egress.send(CAL, cal())
    assert "sk-" not in str(ei.value)
    assert ledger.read_all() == []                 # no model, no call, no ledger line claiming one


# --------------------------------------------------------------------------- mock mode
def test_mock_mode_writes_a_ledger_line_marked_mock_and_touches_no_network(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    res = egress.send(CAL, cal())            # no port: the mock provider (or the built-in mock)
    assert res.mock is True and res.model.startswith("mock")
    [row] = ledger.read_all()
    assert row["mock"] is True and row["model"].startswith("mock")
    assert isinstance(res.output, dict)


def test_mock_mode_refuses_a_port_that_is_not_offline(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")

    class Remote:
        name = "openai"

        def plan(self, *a, **k):
            raise AssertionError("must not be called")

    with pytest.raises(EgressBlocked, match="Models are off"):
        egress.send(CAL, cal(), port=Remote())
    assert ledger.read_all() == []


def test_a_real_port_outside_mock_mode_is_used_and_logged_as_not_mock():
    class Remote:
        name = "openai"

        class models:  # noqa: N801 - mimics the provider's ModelIds
            planner = "planner-model-from-env"
            fast = "fast-model-from-env"

        def plan(self, messages, schema=None):
            return {"text": "Try protecting one longer focus block."}

    res = egress.send(CAL, cal(), port=Remote())
    assert res.mock is False and res.model == "openai:planner-model-from-env"
    assert ledger.read_all()[0]["mock"] is False


def test_check_purposes_use_the_fast_model_and_the_prompt_form():
    class Port(CapturingPort):
        name = "capturing"

    class Q(SafePayload):
        n: Count

    unregister_purpose("t.checker")
    register_payload("t.checker", Q, method="check", response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
    port = Port()
    res = egress.send("t.checker", {"n": 3}, port=port)
    assert res.method == "check" and res.output == {"ok": False}
    assert port.requests[0].method == "check" and "prompt" in port.requests[0].body
    assert_ledger_complete(port)
    unregister_purpose("t.checker")


# --------------------------------------------------------------------------- the model's answer
def test_an_answer_that_does_not_match_the_response_schema_is_discarded():
    port = CapturingPort().script("plan", {"unexpected": "shape"})
    with pytest.raises(ModelOutputRejected, match="expected shape") as ei:
        egress.send(CAL, cal(), port=port)
    assert ei.value.ledger_id                      # the call is still on the ledger


def test_an_answer_containing_personal_data_shapes_is_discarded():
    for text in ("Email ada@example.com about it", "See https://example.org/plan", "Open /Users/ada/notes.txt", "Call 07700 900123"):
        port = CapturingPort().script("plan", {"text": text})
        with pytest.raises(ModelOutputRejected, match="personal data"):
            egress.send(CAL, cal(), port=port)


def test_ordinary_wording_passes():
    port = CapturingPort().script("plan", {"text": "You had 14.1 hours of meetings against a reference of 8; try one 90-minute focus block."})
    assert "focus block" in egress.send(CAL, cal(), port=port).output["text"]


# --------------------------------------------------------------------------- the real provider class, on a fake client
def test_the_real_openai_provider_class_accepts_what_egress_sends_and_the_exact_request_is_clean():
    models = pytest.importorskip("understudy_agent.models.openai_provider")
    config = pytest.importorskip("understudy_agent.models.config")

    calls = []

    class Part:
        type = "output_text"
        text = '{"text": "Try one longer focus block."}'

    class Item:
        type = "message"
        content = [Part()]

    class Resp:
        output = [Item()]
        output_text = '{"text": "Try one longer focus block."}'
        status = "completed"
        usage = None

    class Responses:
        def create(self, model, **kw):
            calls.append({"model": model, **kw})
            return Resp()

    class Client:
        responses = Responses()

    provider = models.OpenAIProvider(client=Client(), models=config.ModelIds(planner="planner-from-env", fast="fast-from-env", computer_use="cu-from-env"))
    res = egress.send(CAL, cal(), port=provider)
    assert res.output == {"text": "Try one longer focus block."} and res.mock is False and res.model == "openai:planner-from-env"
    [call] = calls
    assert call["model"] == "planner-from-env" and call["store"] is False
    wire = json.dumps(call, default=str)
    assert "protect_focus_block" in wire and "focus_blocks_60" in wire
    from understudy_engine.privacy.patterns import scan_text
    assert scan_text(wire, names=False) == [], scan_text(wire, names=False)        # the exact kwargs sent to the SDK carry no PII shape
    assert ledger.read_all()[0]["model"] == "openai:planner-from-env"


# --------------------------------------------------------------------------- concurrency
def test_concurrent_sends_each_get_exactly_one_complete_ledger_line():
    import threading

    port = CapturingPort()
    errors = []

    def go(k):
        try:
            for i in range(25):
                egress.send("git.habit_wording", GitHabitWording(habit="no_tests", learner_ratio=(k % 10) / 10, expert_ratio=0.1, n_commits=20 + i), port=port)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    ts = [threading.Thread(target=go, args=(k,)) for k in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    rows = ledger.read_all()
    assert not errors and len(rows) == len(port) == 200 and len({r["id"] for r in rows}) == 200
    assert all(r["schema"] == GitHabitWording.schema_id() for r in rows)


def test_mock_mode_evaluation_runs_exactly_as_make_eval_would(monkeypatch):
    from understudy_engine.privacy.evaluate import evaluate_privacy

    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    r = evaluate_privacy(seeds=[0], record=False, discover=False)
    assert r["headline"]["leaked"] == 0 and r["headline"]["controls_passed"] == r["headline"]["controls_total"]
