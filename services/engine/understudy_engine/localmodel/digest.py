"""The digest pipeline (LOC-2): raw items in memory in, fixed-vocabulary digests out.

    commit_digest(items) -> list[dict]   {category, size_bucket, touches_tests, risk, message_quality}
    event_digest(items)  -> list[dict]   {category, recurring, duration_bucket, attendee_bucket, needs_prep}

Per item: the facts that are functions of the input (size, tests touched, duration, attendees, recurrence) are computed by
code; the local model, constrained to a JSON schema of enums and booleans, decides the rest; the reply is checked by the
guards (strict schema, no verbatim span, PII backstop) and any failure falls back to the rules answer for that item and is
counted. In mock mode, with the flag off, with no model or no binary, every item takes the rules path and no server starts.

Raw items exist only as arguments and local variables here. They are never logged, stored, or put in an exception message.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import config, policy, prompts, rules
from .client import ClientError, LocalClient
from .guards import GuardError, guard_digest, guard_model_reply
from .schemas import (
    COMMIT_KEYS,
    EVENT_KEYS,
    CommitItem,
    DigestBatch,
    EventItem,
    normalise_commit,
    normalise_event,
    schema_for,
)
from .server import LocalServer, get_server

_model_lock = threading.Lock()          # one slot: calls are serialised
_MAX_CONSECUTIVE_TRANSPORT_ERRORS = 3


@dataclass
class _Totals:
    items: int = 0
    model_ok: int = 0
    fallbacks: dict[str, int] = field(default_factory=dict)
    model_seconds: float = 0.0
    completion_tokens: int = 0
    last: dict[str, Any] = field(default_factory=dict)


_totals = _Totals()
_stats_lock = threading.Lock()


def _record(task: str, batch: DigestBatch, tokens: int, model_seconds: float, model_ok: int) -> None:
    with _stats_lock:
        _totals.items += len(batch.digests)
        _totals.model_ok += model_ok
        _totals.model_seconds += model_seconds
        _totals.completion_tokens += tokens
        for k, v in batch.fallbacks.items():
            _totals.fallbacks[k] = _totals.fallbacks.get(k, 0) + v
        _totals.last = {"task": task, "n": len(batch.digests), "source": batch.source, "fallbacks": dict(batch.fallbacks),
                        "seconds": round(batch.seconds, 3), "model_ok": model_ok}


def last_run() -> dict[str, Any]:
    """Counters of the most recent call: task, n, source (model/rules/mixed), fallbacks by reason, seconds. No content."""
    with _stats_lock:
        return dict(_totals.last)


def totals() -> dict[str, Any]:
    with _stats_lock:
        return {"items": _totals.items, "model_ok": _totals.model_ok, "fallbacks": dict(_totals.fallbacks),
                "model_seconds": round(_totals.model_seconds, 3), "completion_tokens": _totals.completion_tokens}


def reset_stats() -> None:
    global _totals
    with _stats_lock:
        _totals = _Totals()


# ------------------------------------------------------------------------------------------------------- model plumbing
def _ready_client() -> LocalClient | None:
    """A client for a healthy local server (starting it on first use), or None when the rules path applies."""
    srv = get_server()
    if srv.unavailable_reason() is not None:
        return None
    if not srv.running() and not srv.start():
        return None
    return srv.client()


def _source_text_commit(c: CommitItem) -> str:
    return c.message + "\n" + "\n".join(c.paths)


def _source_text_event(e: EventItem) -> str:
    return e.title + "\n" + e.description + "\n" + e.location


@dataclass(frozen=True)
class _Task:
    name: str
    keys: tuple[str, ...]
    normalise: Callable[[Any], Any]
    rules: Callable[[Any], dict[str, Any]]
    messages: Callable[[Any, tuple[str, ...]], list[dict[str, str]]]
    source_text: Callable[[Any], str]


_COMMIT = _Task("commit_digest", COMMIT_KEYS, normalise_commit, rules.digest_commit, prompts.commit_messages, _source_text_commit)
_EVENT = _Task("event_digest", EVENT_KEYS, normalise_event, rules.digest_event, prompts.event_messages, _source_text_event)


def _run(task: _Task, items: Sequence[Any], *, force_rules: bool = False, client: LocalClient | None = None,
         model_fields: tuple[str, ...] | None = None) -> DigestBatch:
    t0 = time.perf_counter()
    norm = [task.normalise(i) for i in items]          # a bad item type is the caller's bug: TypeError, no content in it
    fields = policy.model_fields(task.name) if model_fields is None else tuple(model_fields)
    schema = schema_for(task.name, fields) if fields else {}
    own_client = client is None
    cl: LocalClient | None = None if (force_rules or not fields) else (client or _ready_client())
    digests: list[dict[str, Any]] = []
    sources: list[str] = []
    fallbacks: dict[str, int] = {}
    tokens = prompt_tokens = model_ok = transport_errors = 0
    model_seconds = 0.0

    def fall(reason: str) -> None:
        fallbacks[reason] = fallbacks.get(reason, 0) + 1

    try:
        for item in norm:
            ans = task.rules(item)                       # always computed: the facts, and the fallback answer
            if cl is None:
                digests.append(ans)
                sources.append("rules")
                continue
            try:
                with _model_lock:
                    res = cl.chat_json(task.messages(item, fields), schema, name=task.name)
                src = task.source_text(item)
                reply = guard_model_reply(task.name, res.obj, src, fields)
                merged = {k: (reply[k] if k in fields else ans[k]) for k in task.keys}
                digests.append(guard_digest(task.name, merged, src))
                sources.append("model")
                model_ok += 1
                tokens += res.completion_tokens
                prompt_tokens += res.prompt_tokens
                model_seconds += res.seconds
                transport_errors = 0
            except GuardError as exc:
                fall(f"guard:{exc.code}")
                digests.append(ans)
                sources.append("rules")
            except ClientError as exc:
                fall(f"client:{exc.kind}")
                digests.append(ans)
                sources.append("rules")
                if exc.kind in ("timeout", "transport", "server_error"):
                    transport_errors += 1
                    if transport_errors >= _MAX_CONSECUTIVE_TRANSPORT_ERRORS:
                        get_server()._remember_failure("model_unresponsive")  # noqa: SLF001
                        cl = None                        # the rest of the batch takes the rules path
                elif exc.kind == "unauthorised":
                    cl = None
    finally:
        if own_client and cl is not None:
            cl.close()
    batch = DigestBatch(digests=digests, per_item_source=sources, fallbacks=fallbacks, seconds=time.perf_counter() - t0,
                        model_seconds=model_seconds, completion_tokens=tokens, prompt_tokens=prompt_tokens, model_fields=fields)
    _record(task.name, batch, tokens, model_seconds, model_ok)
    return batch


# ------------------------------------------------------------------------------------------------------------ public API
def commit_digest(items: Sequence[Any]) -> list[dict[str, Any]]:
    """One digest per commit, in order. Items: a message string, or a dict with ``message`` and a diffstat (``files`` as paths
    or dicts with ``path``/``additions``/``deletions``, or ``numstat`` text, or ``additions``/``deletions``/``files_changed``)."""
    return _run(_COMMIT, items).digests


def event_digest(items: Sequence[Any]) -> list[dict[str, Any]]:
    """One digest per calendar entry, in order. Items: a title string, or a dict with ``title``/``subject``, ``start`` and
    ``end`` (or ``duration_min``), ``attendees`` (list or count), ``recurring``/``rrule``, ``description``, ``location``."""
    return _run(_EVENT, items).digests


def commit_digest_ex(items: Sequence[Any], *, force_rules: bool = False, client: LocalClient | None = None,
                     model_fields: tuple[str, ...] | None = None) -> DigestBatch:
    """Like ``commit_digest`` but returns the batch with the per-item source and the fallback counts. ``model_fields`` overrides
    the policy (the evaluation uses it to run the model on every field)."""
    return _run(_COMMIT, items, force_rules=force_rules, client=client, model_fields=model_fields)


def event_digest_ex(items: Sequence[Any], *, force_rules: bool = False, client: LocalClient | None = None,
                    model_fields: tuple[str, ...] | None = None) -> DigestBatch:
    return _run(_EVENT, items, force_rules=force_rules, client=client, model_fields=model_fields)


# ------------------------------------------------------------------------------------------------------------ benchmark
_BENCH_ITEM = {"message": "Add retry with backoff to the upload client", "files": [{"path": "client/upload.py", "additions": 28, "deletions": 3}]}


def benchmark_once(srv: LocalServer) -> float | None:
    """One fixed synthetic commit through the real constrained path. Returns generation tokens per second, or None."""
    if not srv.running():
        return None
    c = srv.client()
    try:
        item = normalise_commit(_BENCH_ITEM)
        with _model_lock:
            f = policy.ALL_MODEL_FIELDS["commit_digest"]
            res = c.chat_json(prompts.commit_messages(item, f), schema_for("commit_digest", f), name="bench")
        if res.tokens_per_s:
            return res.tokens_per_s
        return res.completion_tokens / res.seconds if res.seconds > 0 and res.completion_tokens else None
    except (ClientError, GuardError):
        return None
    finally:
        c.close()
