"""Layer 7: goal-drift check and stuck-loop detector (SEC-7).

Each proposed step is checked against the stated goal by a cheap model call (`ModelPort.check`); an off-goal step pauses
the run. Separately, a deterministic stuck-loop detector stops the run when the same action repeats four times in a row
or a 2 to 4 step cycle repeats three times. The check sees the goal and a short code-written description of the step,
never raw page text; labels read from the page are sanitised and capped. If the check cannot run, it fails closed (a
pause), never open.

A check that FAILS TO RUN (a rate limit, a timeout, an answer the layer cannot use, a transport error) is retried, a bounded number of
times with a fixed backoff and inside one time budget (AGENTIC-3, ITERATIONS_8). Only the CHECK is retried: it is a read. An answer of
"not on goal" is final and is never asked for again, and an action is never repeated (this module never sees one). The error class is
an enum (`CHECK_ERROR_CLASSES`) recorded in the verdict; no message text is kept. When every try fails the layer fails closed as before.
"""
from __future__ import annotations

import re
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Callable

from ..models.errors import ModelRefusal, ProviderError
from ..models.port import ModelPort
from .sanitize import safe_label

# Why a goal check did not run. A closed set: the only thing about a failure that is written down (never a message).
CHECK_ERROR_CLASSES = ("rate_limit", "timeout", "invalid_answer", "transport", "other")
CHECK_RETRIES = 2                        # retries after the first try (so at most 3 calls per check)
CHECK_BACKOFF_S = (0.5, 1.5)             # fixed waits before retry 1 and retry 2: no jitter, so a test can predict every wait
CHECK_TOTAL_BUDGET_S = 45.0              # no retry is started when the checks so far, plus the next wait, would pass this

DRIFT_SCHEMA: dict[str, Any] = {
    "title": "drift_check",
    "type": "object",
    "additionalProperties": False,
    "required": ["serves_goal", "reason"],
    "properties": {
        "serves_goal": {"type": "boolean"},
        "reason": {"type": "string"},          # the 200-character cap is applied to the STORED text below (safe_label), not as a validation rule:
                                               # maxLength is stripped from the provider's strict schema, so the model never sees it, and an
                                               # over-long reason used to raise SchemaViolation and read as "the goal check could not run"
    },
}

_PROMPT = (
    "Decide whether the proposed step is off the goal.\n"
    "Goal: {goal}\n"
    "Recent steps: {recent}\n"
    "Proposed step: {step}\n"
    "The text of anything typed is not shown to you. Reading, scrolling, waiting, going back, and typing or filling in a form on the "
    "page the task is about (entering the data or the answer the task asks for) are normal steps, and so is clicking a form field, a "
    "drop-down or an ordinary button on a site the task works on. "
    "Answer serves_goal=false only if the step is clearly unrelated to the goal, or is a risky action the goal does not mention: "
    "sending or emailing data to a third party, posting, uploading, deleting, paying or buying, installing, signing in, changing "
    "settings, or going to an unrelated site. If in doubt, answer serves_goal=true."
)


@dataclass(frozen=True)
class ProposedStep:
    kind: str
    description: str   # written by trusted code, e.g. "click the button labelled 'Calculate'"

    def render(self) -> str:
        return f"{self.kind} {self.description}".strip()


# What the control under the step IS, in words of our own: from the role that TRUSTED code read in the DOM, mapped through this closed table (a
# page-authored role that is not on it says nothing). A click on a form field has no label (a text box's caption is kept for the sensitive-
# field check, not for the action classes), so without this the check was shown only "click at 127.0.0.1:PORT" and a cheap model paused a
# benign click as "an arbitrary local IP address" (Gemini dev round 1, 7 Nov: 3 of 3 households paused on a click on a drop-down).
_ROLE_WORDS = {"combobox": "a drop-down", "listbox": "a drop-down", "textbox": "a text box", "searchbox": "a text box", "spinbutton": "a number box",
               "button": "a button", "link": "a link", "checkbox": "a checkbox", "radio": "a radio button", "document": "the page"}


def describe_step(kind: str, args: dict[str, Any], *, label: str | None = None, host: str | None = None, role: str | None = None,
                  on_task_site: bool = False) -> ProposedStep:
    """A short, sanitised description of a step for the drift prompt. Never includes typed text, only its length. `role` is the control's
    role as trusted code read it (shown as plain words from a closed table); `on_task_site` says the host is one this task already works on
    (a recorded site), which is a fact the caller knows and the page does not choose."""
    bits = []
    kind_word = _ROLE_WORDS.get(str(role or "").strip().lower())
    if label:
        bits.append(f"on '{safe_label(label, 60)}'" + (f" ({kind_word})" if kind_word and kind != "goto" else ""))
    elif kind_word and kind in ("click", "double_click", "type", "key", "press", "fill", "select_option", "drag"):
        bits.append(f"on {kind_word}")
    if kind == "type":
        bits.append(f"{len(args.get('text', ''))} characters")
    if kind == "fill":
        bits.append(f"into '{safe_label(str(args.get('name') or args.get('selector') or ''), 60)}'")
    if kind == "goto":
        bits.append(f"to {safe_label(host or '', 80)}")
    if kind in ("key", "press"):
        bits.append("+".join(args.get("keys", [])))
    if host and kind != "goto":
        bits.append(f"at {safe_label(host, 80)}" + (" (a site this task works on)" if on_task_site else ""))
    return ProposedStep(kind, " ".join(bits))


@dataclass(frozen=True)
class DriftVerdict:
    on_goal: bool
    reason: str
    source: str  # "model" | "unavailable" | "off"
    error_class: str | None = None   # one of CHECK_ERROR_CLASSES: the class of the LAST failed try (None when no try failed)
    attempts: int = 0                # how many times the check was called (1 when it answered at once; 0 when the layer is off)


_NAME_CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (class, substrings of a class NAME). The first row that matches wins, so the order is part of the rule.
    ("rate_limit", ("RateLimit",)),
    ("timeout", ("Timeout", "TimedOut")),
    ("invalid_answer", ("SchemaViolation", "ModelRefusal", "JSONDecodeError", "ValidationError")),
    ("transport", ("APIConnectionError", "ConnectionError", "ConnectError", "NetworkError", "RemoteProtocolError", "InternalServerError",
                   "ServiceUnavailable", "BrokenPipe")),
)
_KIND_CLASSES = {"timeout": "timeout", "network": "transport", "rate_limit": "rate_limit", "incomplete": "invalid_answer",
                 "blocked": "invalid_answer", "empty": "invalid_answer", "auth": "other", "api": "other"}
_NO_RETRY_KINDS = {"auth", "blocked"}                       # a refused key or blocked content will not change on a second try
_PREFIX = re.compile(r"^([A-Za-z_][A-Za-z0-9_]{2,40}):")    # the OpenAI provider writes f"{ClassName}: message"


def _class_of_name(name: str) -> str | None:
    for cls, parts in _NAME_CLASSES:
        if any(p in name for p in parts):
            return cls
    return None


def _status_class(status: Any) -> tuple[str, bool] | None:
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    if status == 429:
        return "rate_limit", True
    if status in (408, 504):
        return "timeout", True
    if status >= 500:
        return "transport", True
    if 400 <= status < 500:
        return "other", status == 409                       # a malformed request or a refused key is the same on the next try
    return None


def _classify_one(exc: BaseException) -> tuple[str, bool] | None:
    """(class, retryable) from ONE exception object, or None when nothing about it says. Looks at, in order: a provider `kind`, an HTTP
    status, the class names along its MRO, builtin families, and the class-name prefix the OpenAI provider puts on its messages. The text
    of a message never decides anything."""
    kind = getattr(exc, "kind", None)
    if isinstance(kind, str) and kind in _KIND_CLASSES:
        if kind == "api":                         # a Gemini `api` error says what it was by its HTTP status: 5xx transport, 429, 4xx permanent
            st = _status_class(getattr(exc, "status", None))
            if st is not None:
                return st
        return _KIND_CLASSES[kind], kind not in _NO_RETRY_KINDS
    for attr in ("status_code", "status"):
        st = _status_class(getattr(exc, attr, None))
        if st is not None:
            return st
    refusal = isinstance(exc, ModelRefusal)
    for klass in type(exc).__mro__:
        cls = _class_of_name(klass.__name__)
        if cls is not None:
            return cls, not refusal
    if isinstance(exc, TimeoutError):
        return "timeout", True
    if isinstance(exc, OSError):
        return "transport", True
    if isinstance(exc, ValueError):
        return "invalid_answer", True
    m = _PREFIX.match(str(exc))
    if m:
        cls = _class_of_name(m.group(1))
        if cls is not None:
            return cls, True
    if str(exc).startswith("response incomplete"):
        return "invalid_answer", True
    return None


def _classify(exc: BaseException) -> tuple[str, bool]:
    e: BaseException | None = exc
    for _ in range(4):                                       # the exception, then what it was raised from
        if e is None:
            break
        got = _classify_one(e)
        if got is not None:
            return got
        e = e.__cause__ or e.__context__
    return "other", True


def classify_check_error(exc: BaseException) -> str:
    """The enum class of a failed goal check (one of CHECK_ERROR_CLASSES)."""
    return _classify(exc)[0]


def classify_provider_error(exc: BaseException) -> tuple[str, bool]:
    """(class, retryable) of a failed provider call, by the same closed rules as the goal check's classifier (a provider `kind`, an HTTP
    status, class names, builtin families; never the text of a message). Used by the tier-3 loop to decide whether to ASK AGAIN: a
    model proposal is idempotent, so asking again is safe; nothing has been done on the screen yet."""
    return _classify(exc)


class _Unusable(Exception):
    """The port answered, but not with an object the layer can use (no boolean `serves_goal`). Counts as an invalid answer."""


class DriftChecker:
    def __init__(self, port: ModelPort, *, enabled: bool = True, recent_steps: int = 5, retries: int = CHECK_RETRIES,
                 backoff_s: tuple[float, ...] = CHECK_BACKOFF_S, total_budget_s: float = CHECK_TOTAL_BUDGET_S,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.port = port
        self.enabled = enabled
        self.recent_steps = recent_steps
        self.retries, self.backoff_s, self.total_budget_s = max(0, int(retries)), tuple(backoff_s) or (0.0,), total_budget_s
        self._clock, self._sleep = clock, sleep
        self._counts = {"checks": 0, "retried": 0, "recovered": 0, "failed": 0}
        self._by_class: Counter[str] = Counter()

    def stats(self) -> dict[str, Any]:
        """Counts only: checks run, checks that needed a retry, checks that recovered, checks that failed closed, and failures by class."""
        return {**self._counts, "by_class": dict(self._by_class)}

    def _wait(self, attempt: int) -> float:
        return float(self.backoff_s[min(attempt, len(self.backoff_s) - 1)])

    def check(self, goal: str, step: ProposedStep, recent: list[str] | None = None, *,
              should_stop: Callable[[], bool] | None = None) -> DriftVerdict:
        """Ask whether `step` serves `goal`. A failure to RUN the check is retried (never the step); `should_stop` (the kill flag) is looked
        at before every wait and every retry, so a stop is never waited out."""
        if not self.enabled:
            return DriftVerdict(True, "layer 7 is switched off", "off")
        recent_txt = "; ".join((recent or [])[-self.recent_steps:]) or "none"
        prompt = _PROMPT.format(goal=safe_label(goal, 300), recent=safe_label(recent_txt, 400), step=step.render())
        started = self._clock()
        attempts, last_cls, last_name = 0, None, ""
        self._counts["checks"] += 1
        while True:
            attempts += 1
            try:
                out = self.port.check(prompt, DRIFT_SCHEMA)
                if not isinstance(out, dict) or not isinstance(out.get("serves_goal"), bool):
                    raise _Unusable()
            except (ProviderError, ValueError, _Unusable) as exc:
                cls, retryable = ("invalid_answer", True) if isinstance(exc, _Unusable) else _classify(exc)
                last_cls, last_name = cls, ("unusable_answer" if isinstance(exc, _Unusable) else type(exc).__name__)
                self._by_class[cls] += 1
                wait = self._wait(attempts - 1)
                if (not retryable or attempts > self.retries or (should_stop is not None and should_stop())
                        or self._clock() - started + wait > self.total_budget_s):
                    break
                self._sleep(wait)
                if should_stop is not None and should_stop():
                    break
                continue
            if attempts > 1:
                self._counts["retried"] += 1
                self._counts["recovered"] += 1
            return DriftVerdict(out["serves_goal"], safe_label(str(out.get("reason", "")), 200), "model", last_cls, attempts)
        if attempts > 1:
            self._counts["retried"] += 1
        self._counts["failed"] += 1
        # still fails closed; the exception CLASS NAME (never its message) is kept so a stop can be told apart
        return DriftVerdict(False, f"the goal check could not run ({safe_label(last_name, 40)}; {last_cls}); pausing to be safe",
                            "unavailable", last_cls, attempts)


# --------------------------------------------------------------------------- stuck loops


@dataclass(frozen=True)
class StuckResult:
    kind: str       # "repeat" | "cycle"
    period: int
    repeats: int

    def code(self) -> str:
        return f"stuck_{self.kind}_p{self.period}"


class StuckLoopDetector:
    """Same action `same_action_limit` times in a row, or a period 2 to `max_period` cycle `cycle_repeats` times."""

    def __init__(self, same_action_limit: int = 4, cycle_repeats: int = 3, max_period: int = 4, window: int = 64) -> None:
        self.same_action_limit = same_action_limit
        self.cycle_repeats = cycle_repeats
        self.max_period = max_period
        self._recent: deque[str] = deque(maxlen=window)

    def record(self, signature: str) -> None:
        self._recent.append(signature)

    def reset(self) -> None:
        self._recent.clear()

    def check(self) -> StuckResult | None:
        recent = list(self._recent)
        for period in range(1, self.max_period + 1):
            repeats = self.same_action_limit if period == 1 else self.cycle_repeats
            span = period * repeats
            if len(recent) < span:
                continue
            tail = recent[-span:]
            if all(tail[i] == tail[i + period] for i in range(span - period)):
                return StuckResult("repeat" if period == 1 else "cycle", period, repeats)
        return None
