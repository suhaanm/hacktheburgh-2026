"""AGENTIC-3 item 1: a goal check that fails to RUN is retried (the check, never the action), a bounded number of times with a
fixed backoff, and the error class is recorded as an enum. All offline: a scripted fake port, an injected clock and sleeper, so
nothing waits and nothing depends on a model. After the retries the layer still fails closed.

What these tests pin down
  * each error class (rate_limit, timeout, invalid_answer, transport, other) is classified from the exception type, its HTTP status or
    kind, its cause chain, or the class-name prefix the OpenAI provider writes; never from the text of a message;
  * transient failures are retried up to 2 times; a refusal and a permanent 4xx are not; an answer of 'not on goal' is final and is
    never asked for again; the total time is bounded by an injected clock;
  * the pipeline records the class in the audit line (tokens only) and in the decision the gate-stop row is built from, and the
    action itself is authorised once: only `check` is ever called more than once.
"""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.errors import ConfigError, ModelRefusal, ProviderError, SchemaViolation
from understudy_agent.models.gemini_http import GeminiHTTPError
from understudy_agent.models.port import Action
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.config import SecurityConfig
from understudy_agent.security.detector import PageObservation
from understudy_agent.security.drift import (
    CHECK_BACKOFF_S, CHECK_ERROR_CLASSES, CHECK_RETRIES, DriftChecker, ProposedStep, classify_check_error,
)
from understudy_agent.security.gates import RoutineContext, TargetInfo
from understudy_agent.security.pipeline import SafetyPipeline


# ----------------------------------------------------------------------------- doubles
class RateLimitError(Exception):
    """Same NAME as openai.RateLimitError: classification is by type name, so the tests need no SDK objects."""


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class HTTPStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("status")
        self.status_code = status_code


def provider_error_from(cause: Exception, label: str | None = None) -> ProviderError:
    """The OpenAI provider's shape: ProviderError(f'{ClassName}: message') raised from the SDK error."""
    try:
        raise ProviderError(f"{label or type(cause).__name__}: some provider message") from cause
    except ProviderError as exc:
        return exc


OK_ON = {"serves_goal": True, "reason": "fine"}
OK_OFF = {"serves_goal": False, "reason": "unrelated"}


class Clock:
    """A fake monotonic clock that only moves when somebody sleeps or a call 'takes' time."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s


class ScriptedPort:
    """`check` returns or raises the next scripted item; the other port methods must never be reached from the drift layer."""

    name = "scripted"

    def __init__(self, *outcomes, clock: Clock | None = None, takes_s: float = 0.0) -> None:
        self.outcomes, self.calls, self.clock, self.takes_s = list(outcomes), [], clock, takes_s

    def check(self, prompt, schema):
        self.calls.append("check")
        if self.clock is not None:
            self.clock.now += self.takes_s
        item = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item

    def plan(self, *a, **k):
        self.calls.append("plan")
        raise AssertionError("the drift layer must only ever call check")

    read = vision = computer_step = plan


def checker(port, clock: Clock | None = None, **kw) -> tuple[DriftChecker, Clock]:
    clock = clock or Clock()
    return DriftChecker(port, clock=clock, sleep=clock.sleep, **kw), clock


STEP = ProposedStep("click", "on 'Calculate'")


# ----------------------------------------------------------------------------- classification (one per class, and the shapes it must read)
@pytest.mark.parametrize("exc, expected", [
    (provider_error_from(RateLimitError()), "rate_limit"),
    (ProviderError("RateLimitError: slow down"), "rate_limit"),                                  # class-name prefix, no cause object
    (provider_error_from(HTTPStatusError(429), label="APIStatusError"), "rate_limit"),
    (GeminiHTTPError("rate_limit", "x", 429), "rate_limit"),
    (provider_error_from(APITimeoutError()), "timeout"),
    (ProviderError("APITimeoutError: Request timed out."), "timeout"),
    (TimeoutError("t"), "timeout"),
    (provider_error_from(HTTPStatusError(504), label="APIStatusError"), "timeout"),
    (GeminiHTTPError("timeout", "x"), "timeout"),
    (SchemaViolation("model output does not match schema"), "invalid_answer"),
    (ValueError("not json"), "invalid_answer"),
    (ModelRefusal("no"), "invalid_answer"),
    (ProviderError("response incomplete (output token limit); raise max_output_tokens"), "invalid_answer"),
    (GeminiHTTPError("empty", "x"), "invalid_answer"),
    (provider_error_from(APIConnectionError()), "transport"),
    (ConnectionResetError("reset"), "transport"),
    (provider_error_from(HTTPStatusError(503), label="APIStatusError"), "transport"),
    (GeminiHTTPError("network", "x"), "transport"),
    (ProviderError("something nobody planned for"), "other"),
    (provider_error_from(HTTPStatusError(401), label="APIStatusError"), "other"),
    (GeminiHTTPError("auth", "x", 401), "other"),
])
def test_each_error_class_is_recognised(exc, expected):
    assert classify_check_error(exc) == expected and expected in CHECK_ERROR_CLASSES


def test_the_class_set_is_the_documented_enum():
    assert CHECK_ERROR_CLASSES == ("rate_limit", "timeout", "invalid_answer", "transport", "other")
    assert CHECK_RETRIES == 2 and CHECK_BACKOFF_S == (0.5, 1.5)


def test_classification_never_depends_on_what_a_message_says():
    """A message that talks about rate limits does not make an unknown error a rate limit unless it carries the class-name prefix."""
    assert classify_check_error(ProviderError("the 429 rate limit timeout connection schema story")) == "other"


# ----------------------------------------------------------------------------- the retry itself
@pytest.mark.parametrize("exc, cls", [
    (provider_error_from(RateLimitError()), "rate_limit"),
    (provider_error_from(APITimeoutError()), "timeout"),
    (SchemaViolation("bad shape"), "invalid_answer"),
    (provider_error_from(APIConnectionError()), "transport"),
    (ProviderError("unclassified hiccup"), "other"),
])
def test_one_transient_failure_of_each_class_is_retried_and_then_answers(exc, cls):
    port = ScriptedPort(exc, OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert v.on_goal and v.source == "model" and v.attempts == 2 and v.error_class == cls
    assert port.calls == ["check", "check"] and clock.slept == [0.5]


def test_two_failures_then_an_answer_still_counts_and_waits_the_fixed_backoff():
    port = ScriptedPort(ProviderError("RateLimitError: x"), ProviderError("APITimeoutError: y"), OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert v.on_goal and v.attempts == 3 and v.error_class == "timeout"        # the class of the LAST failure
    assert port.calls == ["check"] * 3 and clock.slept == [0.5, 1.5]


@pytest.mark.parametrize("exc, cls", [
    (provider_error_from(RateLimitError()), "rate_limit"),
    (provider_error_from(APITimeoutError()), "timeout"),
    (SchemaViolation("bad shape"), "invalid_answer"),
    (provider_error_from(APIConnectionError()), "transport"),
    (ProviderError("unclassified hiccup"), "other"),
])
def test_when_every_try_fails_the_layer_fails_closed_with_the_class_recorded(exc, cls):
    port = ScriptedPort(exc)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert not v.on_goal and v.source == "unavailable" and v.error_class == cls
    assert v.attempts == 3 and port.calls == ["check"] * 3 and clock.slept == [0.5, 1.5]    # 1 try plus 2 retries, never more
    assert "could not run" in v.reason and "pausing to be safe" in v.reason


def test_the_reason_keeps_the_exception_class_name_but_never_its_message():
    chk, _ = checker(ScriptedPort(SchemaViolation("SECRET-MESSAGE-TEXT")))
    v = chk.check("g", STEP)
    assert "SchemaViolation" in v.reason and "SECRET-MESSAGE-TEXT" not in v.reason


def test_a_verdict_of_not_on_goal_is_final_and_is_never_asked_again():
    port = ScriptedPort(OK_OFF, OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert not v.on_goal and v.source == "model" and v.attempts == 1 and v.error_class is None
    assert port.calls == ["check"] and clock.slept == []


def test_a_refusal_is_not_retried():
    port = ScriptedPort(ModelRefusal("declined"), OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert not v.on_goal and v.source == "unavailable" and v.error_class == "invalid_answer" and v.attempts == 1
    assert port.calls == ["check"] and clock.slept == []


@pytest.mark.parametrize("exc", [provider_error_from(HTTPStatusError(401), label="APIStatusError"),
                                 provider_error_from(HTTPStatusError(400), label="APIStatusError"),
                                 GeminiHTTPError("auth", "x", 403), GeminiHTTPError("blocked", "x")])
def test_a_permanent_failure_is_not_retried(exc):
    port = ScriptedPort(exc, OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert not v.on_goal and v.source == "unavailable" and v.attempts == 1 and port.calls == ["check"]


@pytest.mark.parametrize("answer", [{}, {"reason": "no verdict"}, {"serves_goal": "yes", "reason": "string, not a boolean"}, None, ["x"]])
def test_an_answer_the_layer_cannot_use_is_an_invalid_answer_and_is_retried(answer):
    port = ScriptedPort(answer, OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP)
    assert v.on_goal and v.attempts == 2 and v.error_class == "invalid_answer" and clock.slept == [0.5]


def test_an_unusable_answer_every_time_is_unavailable_not_off_goal():
    port = ScriptedPort({"reason": "no verdict"})
    chk, _ = checker(port)
    v = chk.check("goal", STEP)
    assert v.source == "unavailable" and not v.on_goal and v.error_class == "invalid_answer" and v.attempts == 3


def test_the_total_time_is_bounded_by_the_injected_clock():
    clock = Clock()
    port = ScriptedPort(provider_error_from(APITimeoutError()), OK_ON, clock=clock, takes_s=50.0)   # one slow failure uses the budget
    chk, _ = checker(port, clock=clock)
    v = chk.check("goal", STEP)
    assert not v.on_goal and v.source == "unavailable" and v.error_class == "timeout" and v.attempts == 1
    assert port.calls == ["check"] and clock.slept == []


def test_the_budget_allows_retries_while_calls_are_quick():
    clock = Clock()
    port = ScriptedPort(ProviderError("RateLimitError: x"), ProviderError("RateLimitError: x"), OK_ON, clock=clock, takes_s=2.0)
    chk, _ = checker(port, clock=clock, total_budget_s=45.0)
    assert chk.check("goal", STEP).attempts == 3


def test_a_stop_signal_ends_the_retries_before_the_next_try():
    stops = iter([False, True])                      # the kill flag is set while the first backoff is being waited out
    port = ScriptedPort(ProviderError("APITimeoutError: x"), OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP, should_stop=lambda: next(stops, True))
    assert not v.on_goal and v.source == "unavailable" and port.calls == ["check"]


def test_a_stop_signal_that_is_already_set_means_no_retry_and_no_wait():
    port = ScriptedPort(ProviderError("APITimeoutError: x"), OK_ON)
    chk, clock = checker(port)
    v = chk.check("goal", STEP, should_stop=lambda: True)
    assert not v.on_goal and port.calls == ["check"] and clock.slept == []


def test_an_error_that_is_not_a_provider_or_value_error_is_not_swallowed_or_retried():
    port = ScriptedPort(ConfigError("no key"), OK_ON)           # a configuration error is a bug, not a transient failure
    chk, clock = checker(port)
    with pytest.raises(ConfigError):
        chk.check("goal", STEP)
    assert port.calls == ["check"] and clock.slept == []


def test_a_disabled_layer_makes_no_call_and_a_clean_answer_makes_exactly_one():
    port = ScriptedPort(OK_ON)
    off, _ = checker(port, enabled=False)
    assert off.check("goal", STEP).source == "off" and port.calls == []
    on, _ = checker(port)
    v = on.check("goal", STEP)
    assert v.on_goal and v.attempts == 1 and v.error_class is None and port.calls == ["check"]


def test_a_reason_of_any_length_is_accepted_and_the_stored_text_is_capped():
    """The patch from the diagnosis: the 200-character cap is applied to the STORED text, not as a validation rule."""
    port = ScriptedPort({"serves_goal": True, "reason": "x" * 400})
    chk, _ = checker(port)
    v = chk.check("goal", STEP)
    assert v.on_goal and v.source == "model" and len(v.reason) <= 200


def test_counters_say_how_often_a_check_was_retried_recovered_or_failed():
    chk, _ = checker(ScriptedPort(ProviderError("APITimeoutError: x"), OK_ON, ProviderError("RateLimitError: y")))
    chk.check("g", STEP)                          # try 1 fails (timeout), try 2 answers
    chk.port = ScriptedPort(ProviderError("RateLimitError: y"))
    chk.check("g", STEP)                          # three failures: unavailable
    s = chk.stats()
    assert s["checks"] == 2 and s["retried"] == 2 and s["recovered"] == 1 and s["failed"] == 1
    assert s["by_class"] == {"timeout": 1, "rate_limit": 3}


# ----------------------------------------------------------------------------- through the pipeline
GOAL = "Enter the household in calculator A and read the result"
PAGE = "http://localhost:7801/calc"
HOSTS = frozenset({"localhost:7801"})
CLEAN = PageObservation(text="Calculator A\nEntitlement: 812.40", url=PAGE, title="Calc A")
SCHEMA = {"title": "calc_result", "type": "object", "required": ["entitlement"], "properties": {"entitlement": {"type": "number"}}}


def make_pipe(tmp_path, port, clock):
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    routine = RoutineContext(routine_id="r", run_id="r_t", mode="model_driven", rung="A2", recorded_hosts=HOSTS)
    pipe = SafetyPipeline(port, SecurityConfig(), audit=audit, queue=queue, routine=routine, goal=GOAL, clock=clock, sleep=clock.sleep)
    return pipe, audit, queue


def click(pipe, label="Calculate"):
    obs = pipe.observe(CLEAN, None)
    return pipe.authorise(Action("click", {"x": 10, "y": 10}), observation=obs,
                          target=TargetInfo(label=label, role="button", url=PAGE, structure=("submit_control",)))


def test_a_transient_check_failure_does_not_pause_the_run_and_the_action_is_authorised_once(tmp_path):
    clock = Clock()
    port = ScriptedPort(ProviderError("APITimeoutError: x"), ProviderError("RateLimitError: y"), OK_ON)
    pipe, audit, queue = make_pipe(tmp_path, port, clock)
    d = click(pipe)
    assert d.verdict == "allow" and d.check_error is None            # a recovered check is not a stop
    assert port.calls == ["check"] * 3                                # only the CHECK was repeated: no plan, read, vision or computer_step
    assert pipe.budget.steps == 1                                     # one action authorised, one step spent
    assert pipe.drift.stats()["recovered"] == 1 and queue.list("all") == []
    rows = audit.read(limit=0)
    line = [r for r in rows if r["kind"] == "drift_check"]
    assert len(line) == 1 and line[0]["outcome"] == "recovered" and line[0]["meta"] == {"attempts": 3, "error_class": "rate_limit"}
    assert sum(1 for r in rows if r["kind"] == "step" and r.get("outcome", "").startswith("allowed")) == 1


def test_when_all_tries_fail_the_step_pauses_with_the_class_in_the_decision_and_the_audit(tmp_path):
    clock = Clock()
    port = ScriptedPort(ProviderError("APITimeoutError: x"))
    pipe, audit, queue = make_pipe(tmp_path, port, clock)
    d = click(pipe)
    assert d.verdict == "needs_human" and d.layer == "drift" and d.codes == ["drift:off_goal_unavailable"]
    assert d.check_error == "timeout" and d.check_attempts == 3        # what the gate-stop row is built from
    assert port.calls == ["check"] * 3 and pipe.budget.steps == 0     # nothing was authorised, nothing spent
    rows = audit.read(limit=0)
    pause = [r for r in rows if r["kind"] == "drift_pause"]
    assert len(pause) == 1 and pause[0]["note"] == "drift:unavailable"
    assert pause[0]["meta"] == {"check_error": "timeout", "attempts": 3}
    fail = [r for r in rows if r["kind"] == "drift_check"]
    assert len(fail) == 1 and fail[0]["outcome"] == "failed" and fail[0]["meta"] == {"attempts": 3, "error_class": "timeout"}
    assert len(queue.list("pending")) == 1


def test_a_model_verdict_of_off_goal_is_one_call_and_carries_no_error_class(tmp_path):
    clock = Clock()
    port = ScriptedPort(OK_OFF)
    pipe, audit, _ = make_pipe(tmp_path, port, clock)
    d = click(pipe)
    assert d.verdict == "needs_human" and d.codes == ["drift:off_goal_model"] and d.check_error is None
    assert port.calls == ["check"] and clock.slept == []
    assert all(r["kind"] != "drift_check" for r in audit.read(limit=0))


def test_the_kill_flag_is_checked_between_tries_and_stops_the_retries(tmp_path):
    from understudy_agent.security.killflag import clear_kill, set_kill

    clock = Clock()

    class KillsDuringTheFirstFailure(ScriptedPort):
        def check(self, prompt, schema):
            set_kill()                                   # the worker presses the kill switch while the first check is failing
            return super().check(prompt, schema)

    port = KillsDuringTheFirstFailure(ProviderError("APITimeoutError: x"), OK_ON)
    pipe, audit, _ = make_pipe(tmp_path, port, clock)
    try:
        d = click(pipe)
        assert d.verdict == "needs_human" and d.check_error == "timeout" and d.check_attempts == 1
        assert port.calls == ["check"] and clock.slept == []
    finally:
        clear_kill()


def test_the_audit_lines_hold_tokens_only_no_text(tmp_path):
    clock = Clock()
    port = ScriptedPort(SchemaViolation("PRIVATE page text that must not be logged"))
    pipe, audit, _ = make_pipe(tmp_path, port, clock)
    click(pipe)
    raw = (tmp_path / "audit.jsonl").read_text()
    assert "PRIVATE" not in raw and audit.verify_chain()


def test_the_gate_stop_row_carries_the_class_and_the_attempt_count(tmp_path):
    """instrument_guard builds the `gate_stops` rows of a live round: a drift stop that was 'could not run' says which class, and how many tries."""
    from understudy_agent.orchestrator import instrument_guard
    from understudy_agent.tiers.safety import Guard

    clock = Clock()
    port = ScriptedPort(provider_error_from(RateLimitError()))
    audit = AuditLog(tmp_path / "audit.jsonl")
    guard = Guard(port, run_id="r_row", mode="model_driven", audit=audit, queue=ApprovalQueue(tmp_path / "q", audit=audit),
                  recorded_hosts=frozenset({"localhost:7801"}))
    guard.pipe.drift._sleep, guard.pipe.drift._clock = clock.sleep, clock
    rows: list[dict] = []
    instrument_guard(guard, "nav-c", rows, frozenset({"localhost:7801"}))
    seen = guard.observe_screen()
    dec = guard.authorise(Action("key", {"keys": ["tab"]}), seen, label="Show my results", role="combobox", url=PAGE, structure=())
    assert dec.verdict == "needs_human" and len(rows) == 1
    row = rows[0]
    assert row["layer"] == "drift" and row["codes"] == ["drift:off_goal_unavailable"]
    assert row["check_error"] == "rate_limit" and row["check_attempts"] == 3
    assert port.calls == ["check"] * 3 and clock.slept == [0.5, 1.5]


def test_a_gate_stop_that_is_not_a_failed_check_has_no_error_class(tmp_path):
    from understudy_agent.orchestrator import instrument_guard
    from understudy_agent.tiers.safety import Guard

    port = ScriptedPort(OK_OFF)
    audit = AuditLog(tmp_path / "audit.jsonl")
    guard = Guard(port, run_id="r_row2", mode="model_driven", audit=audit, queue=ApprovalQueue(tmp_path / "q", audit=audit),
                  recorded_hosts=frozenset({"localhost:7801"}))
    rows: list[dict] = []
    instrument_guard(guard, "nav-c", rows, frozenset({"localhost:7801"}))
    dec = guard.authorise(Action("click", {"x": 5, "y": 5}), guard.observe_screen(), label="Calculate", role="button", url=PAGE,
                          structure=("submit_control",))
    assert dec.verdict == "needs_human" and rows[0]["codes"] == ["drift:off_goal_model"]
    assert rows[0]["check_error"] is None and rows[0]["check_attempts"] == 0
