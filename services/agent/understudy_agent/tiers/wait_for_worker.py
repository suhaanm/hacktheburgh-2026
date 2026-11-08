"""A browsing task that WAITS for the worker's click instead of ending (owner report, 8 Nov 2026).

Two stops used to end a typed browser task for good, and approving the item in "Needs you" did nothing, because the run was already over:

1. the control-reading gate failed closed on a control that trusted code could not read (a page built from custom elements, such as
   YouTube's search box and buttons): "Knack couldn't tell what that control does";
2. the model's own safety check (Gemini computer use answers a click on a consent banner with `require_confirmation`).

Now the run keeps its page open and asks, in plain words, with two buttons: Allow once and Not now. Only the worker's own click can answer: the
card is an item in the approval queue, and the queue accepts a decision only from its release route (the actor `worker` or `worker_approval`,
plus the per-boot token), which sets the item's origin; no code path in the agent, no model and no routine can approve one. The wait is
bounded (ten minutes), the budget clock does not run during it, and Stop, the kill file and a restart end it.

What the wait adds is small and fixed in code: wait for the click, then do THAT ONE action through the same gates as every other action. It does
not make any class of action approvable that was not already approvable. An action whose class is irreversible or outward (buy, send, submit,
delete, download, install, a form that posts to another site, credentials) is never offered this way: the gate's own classification decides, run
before a question is asked (`ComputerUse._waitable`). Every approval is for one action; the next stop asks again. Unattended runs never wait.

The wording of the card is written here from closed parts: the action's kind, the page's host (read by code), a few words the model gave for what
it wants to do (shown as the model's, redacted and cut), and for a safety check a closed topic word. Page text never reaches the card.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..models.port import Action
from ..queue import ApprovalQueue
from ..security.actions import action_signature
from ..security.killflag import is_killed
from .base import TierError

STOP_WAIT_S = 600.0                 # how long a run waits for the worker's click: ten minutes
POLL_S = 0.5
# Actions a waiting stop may be about. Whether the ACTION is fit to wait on is decided by the gate's own classification, not by this list.
WAIT_KINDS = ("click", "double_click", "type", "key", "goto", "back", "forward", "scroll", "move", "wait")
# What a model safety check may be about for the run to wait on it. A check about money, an account, a download or an irreversible step
# (topics payment, sign_in, download, submit) ends the run as it always did.
WAIT_TOPICS = ("cookies", "terms", "other")
WAIT_CHANGED_PIXELS = 4000          # of 256 000 grey pixels (640 x 400): how much of the picture may move while the worker decides

TOPIC_WORDS = {"cookies": "a cookie or consent choice", "terms": "terms or an agreement", "other": "a step on the page",
               "payment": "a payment", "sign_in": "a sign-in", "download": "a download", "submit": "something that sends or can't be undone"}
_VERB = {"click": "Click", "double_click": "Double-click", "type": "Type", "key": "Press", "goto": "Open a page", "back": "Go back",
         "forward": "Go forward", "scroll": "Scroll", "move": "Move the pointer", "wait": "Wait"}


class WorkerDeclined(TierError):
    """The run was WAITING for the worker's click on one step and the worker answered "Not now", or nobody answered in time (`why` is
    `declined` or `timeout`). It ends the run with a plain reason; nothing is done."""

    def __init__(self, why: str) -> None:
        super().__init__(f"the worker did not allow the step ({why})")
        self.why = why


@dataclass(frozen=True)
class StopAsk:
    """One question for the worker, asked while a browsing task WAITS with its page open. `kind` is `control` (trusted code could not tell
    what the control does) or `model_check` (the model's own safety check). Nothing here is page text: `host` is read by code, `label` is the
    model's own few words for what it wants to do, `topic` is a closed word."""

    kind: str
    queue_id: str
    action: str                # the typed action's kind (click, double_click, type, key, goto, ...)
    host: str
    label: str = ""
    topic: str = "other"


def question_signature(action: Action) -> str:
    """What a model-check approval is bound to: the one action it was raised for (an approval for a click is no use for another click)."""
    return "model_check|" + action_signature(action.kind, dict(action.args))


def _clean(text: Any, limit: int) -> str:
    from ..tasks.model import one_line

    return one_line(text, limit)


_LEAD_VERB = re.compile(r"^(?:double[- ]click|click|tap|press|select|choose)\s+(?:on\s+)?(?:the\s+)?", re.I)


def _what(label: Any, limit: int = 50) -> str:
    """The model's few words for what it wants to click, as a short label: its own leading verb is dropped (the card already says Click) and so
    is a closing full stop. Redacted and cut by code."""
    s = _clean(label, 120)
    s = _LEAD_VERB.sub("", s).strip().strip("“”\"'").rstrip(".!").strip()
    return _clean(s, limit)


def step_words(action: Action, host: str, label: str = "") -> str:
    """The step as the worker reads it: `Click “Search” on www.youtube.com`, `Type “python tutorial” on www.youtube.com`, `Press Enter on ...`."""
    verb = _VERB.get(action.kind, "Do one step")
    place = host or "this page"
    if action.kind in ("click", "double_click"):
        what = _what(label)
        return f"{verb} “{what}” on {place}" if what else f"{verb} on {place}"
    if action.kind == "type":
        text = _clean(action.args.get("text"), 40)
        return f"{verb} “{text}” on {place}" if text else f"{verb} on {place}"
    if action.kind == "key":
        keys = " + ".join(str(k).title() for k in (action.args.get("keys") or [])[:3])
        return f"{verb} {keys} on {place}" if keys else f"{verb} a key on {place}"
    if action.kind == "goto":
        return f"{verb} on {place}" if place != "this page" else verb
    return f"{verb} on {place}"


def card_words(kind: str, action: Action, host: str, label: str = "", topic: str = "other", *, unreadable: bool = False) -> tuple[str, str]:
    """(title, summary) for the card in Needs you. Both are written here from closed parts. `unreadable` is a model check on a control that
    trusted code also could not read: one card says both."""
    step = step_words(action, host, label)
    if kind == "model_check":
        topic_words = TOPIC_WORDS.get(topic, TOPIC_WORDS["other"])
        also = ", and Knack can't tell what this control does" if unreadable else ""
        return (f"The page asks to confirm: {topic_words}",
                f"Knack wants to do this: {step}. The page asked for a confirmation first{also}. Allow once, or choose Not now.")
    return (step, "Knack can't tell what this control does, so it is asking before it acts. Allow once, or choose Not now.")


class QueueWaiter:
    """The waiter a browser task hands to `ComputerUse`: it watches ONE approval-queue item until the worker decides. It can end the wait
    (Stop, the kill file, the time limit) but it cannot approve anything: it only reads the item's status, and the status changes only on the
    queue's release route. An approved item whose integrity tag does not verify counts as not approved."""

    def __init__(self, queue: ApprovalQueue, *, should_stop: Callable[[], bool], timeout_s: float = STOP_WAIT_S, poll_s: float = POLL_S,
                 status: Callable[[str], None] | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.queue, self.should_stop, self.timeout_s, self.poll_s = queue, should_stop, float(timeout_s), float(poll_s)
        self.status, self.clock, self.sleep = status, clock, sleep

    def _say(self, line: str) -> None:
        if self.status is not None:
            try:
                self.status(line)
            except Exception:  # noqa: BLE001 - a status line is a courtesy
                pass

    async def __call__(self, ask: StopAsk) -> str:
        self._say("Waiting for you in Needs you")
        end = self.clock() + self.timeout_s
        while True:
            if is_killed() or self.should_stop():
                self.queue.withdraw(ask.queue_id, "stopped")
                return "stopped"
            item = self.queue.get(ask.queue_id)
            if item is None:
                return "declined"
            st = item.get("status")
            if st == "approved":
                if self.queue.integrity(item) != "ok":
                    return "declined"
                self._say("Carrying on")
                return "approved"
            if st in ("rejected", "expired"):
                return "declined"
            if self.clock() >= end:
                self.queue.withdraw(ask.queue_id, "timeout")
                return "timeout"
            await self.sleep(self.poll_s)
