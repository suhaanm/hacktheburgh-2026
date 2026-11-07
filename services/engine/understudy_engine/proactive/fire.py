"""Fire: the worker's press, and nothing else, makes anything happen.

``fire`` is called only from ``POST /briefing/{id}/fire`` with the worker as the actor. Nothing in this package calls it
on a timer, from a model or from another route; the evaluation counts calls to the queue and to the agent service across
every replay and asserts zero without a press.

What a press does, by the card's ``fire.type``:

* ``queue``: enqueue one item in the approval queue (``data/queue``) carrying the card's prepared content verbatim. It is
  *pending*: a second, separate approval by the worker is still needed before anything acts. Never an auto-approve.
* ``draft``: the same, plus the prepared content saved as a local draft file (``data/briefing/drafts/<card>.json``). Nothing is
  written to any calendar; that stays behind the queue approval.
* ``agent``: start one background agent run through ``POST <agent service>/agents/spawn`` (agent-runtime track), read-only kinds
  only. A card whose risk class is ``irreversible`` can never start a run: it can only enter the queue, where it needs its own
  approval.

One press makes exactly one thing: a queue item *or* a run, never both. The prepared content is passed exactly as the worker
left it, with its hash, so what fired is checkable against what was shown. The card is re-verified just before it fires; a
stale card is dropped instead. The kill flag stops everything.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidates import Candidate, Ctx, collect
from .cards import Card, iso
from .judge import COOLDOWN_DAYS
from .paths import agent_url, data_dir
from .sources import Readers
from .store import BriefingStore
from .verify import verify_one

QueuePort = Callable[..., dict[str, Any]]
Spawner = Callable[[str, dict[str, Any], str], dict[str, Any]]

#: the queue's own kinds (agent-safety track); chosen by the card's risk class. Used when the queue module cannot be asked.
KIND_FOR_RISK = {"irreversible": "irreversible_step", "outward": "outward_step", "normal": "batch_result"}
READ_ONLY_AGENT_KINDS = ("programming.commit_analyst", "programming.test_gap", "programming.refactor_suggest", "data.profile", "data.chart",
                         "creative.weekly_summary")


class FireError(Exception):
    status = 400
    code = "fire_error"

    def __init__(self, message: str, code_hint: str | None = None, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra
        if code_hint:
            self.code = code_hint


class NotFound(FireError):
    status, code = 404, "no_such_card"


class Refused(FireError):
    status, code = 403, "write_refused"


class NotReady(FireError):
    status, code = 409, "not_ready"


class Stale(FireError):
    status, code = 409, "stale"


class Killed(FireError):
    status, code = 409, "killed"


class Unavailable(FireError):
    status, code = 503, "unavailable"


# --------------------------------------------------------------------------------------------- ports
def default_queue_port() -> QueuePort:
    """The agent package's approval queue. Without it a press cannot enqueue, and says so plainly."""
    try:
        from understudy_agent.audit import AuditLog
        from understudy_agent.queue import ApprovalQueue
    except Exception as exc:
        raise Unavailable("The approval queue is not available (the agent package is not installed here), so nothing was started.") from exc
    return ApprovalQueue(audit=AuditLog()).enqueue


def queue_kinds() -> tuple[str, ...]:
    try:
        from understudy_agent.queue import KINDS

        return tuple(KINDS)
    except Exception:
        return tuple(KIND_FOR_RISK.values())


def default_spawner(*, url: str | None = None, timeout: float = 5.0, transport: Any = None) -> Spawner:
    """``POST <agent service>/agents/spawn {kind, params, mode}`` -> ``{run_id}``."""

    def spawn(kind: str, params: dict[str, Any], mode: str) -> dict[str, Any]:
        import httpx

        try:
            with httpx.Client(timeout=timeout, transport=transport) as c:
                r = c.post(f"{url or agent_url()}/agents/spawn", json={"kind": kind, "params": params, "mode": mode})
        except httpx.HTTPError as exc:
            raise Unavailable("The agent service is not running, so the analysis could not start. Nothing was done.") from exc
        if r.status_code != 200:
            raise Unavailable(f"The agent service refused to start the run (HTTP {r.status_code}). Nothing was done.")
        try:
            body = r.json()
        except ValueError as exc:
            raise Unavailable("The agent service answered with something unreadable. Nothing was done.") from exc
        rid = (body.get("data") or body).get("run_id") if isinstance(body, dict) else None
        if not isinstance(rid, str) or not rid:
            raise Unavailable("The agent service did not return a run id. Nothing was done.")
        return {"run_id": rid}

    return spawn


# --------------------------------------------------------------------------------------------- helpers
def kill_flag_set() -> bool:
    return (data_dir() / "KILL").exists()


def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, indent=1, sort_keys=True))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _summary(why: str) -> str:
    s = why.split(". ")[0].strip()
    return (s if s.endswith(".") else s + ".")[:230]


def _audit(kind: str, card: Card, outcome: str) -> None:
    """One redacted line in the shared audit log (the agent package's hash-chained writer). Best effort."""
    try:
        from understudy_agent.audit import AuditLog

        AuditLog().append("human", kind, outcome=outcome, note_code=f"briefing:{card.kind}",
                          meta={"fire_type": card.fire_type, "risk": card.risk_class, "card": card.id})
    except Exception:
        pass


def queue_kwargs(card: Card, *, kinds: tuple[str, ...] | None = None, draft_ref: str | None = None) -> dict[str, Any]:
    """Exactly what is enqueued for a card: the prepared content (verbatim), its hash and a pointer to the action. No source text."""
    ref = card.fire.get("payload_ref", {})
    allowed = kinds or queue_kinds()
    kind = "briefing_action" if "briefing_action" in allowed else (ref.get("queue_kind") if ref.get("queue_kind") in allowed else KIND_FOR_RISK[card.risk_class])
    # the queue's kind says what the item is; for irreversible cards it must say so, whatever the template asked for
    if card.risk_class == "irreversible" and "irreversible_step" in allowed:
        kind = "irreversible_step"
    extracted: dict[str, Any] = {"briefing_card": card.id, "card_kind": card.kind, "action": ref.get("action", ""),
                                 "prepared": {k: card.prepared[k] for k in ("text", "steps", "artifact_ref") if k in card.prepared},
                                 "prepared_hash": card.prepared_hash}
    for k in ("routine_id", "skill_id", "run_id", "requested_mode", "template"):
        if k in ref:
            extracted[k] = ref[k]
    if draft_ref:
        extracted["draft_ref"] = draft_ref
    return {"kind": kind, "title": card.title, "summary": _summary(card.why), "risk_class": card.risk_class,
            "routine_id": ref.get("routine_id"), "run_id": ref.get("run_id") if card.kind == "agent_result" else None,
            "evidence": {"extracted": extracted, "expected": {}, "diff": [], "tier_log": []},
            "signature": f"briefing:{card.id}:{card.prepared_hash}", "dedupe_key": f"briefing:{card.id}"}


# --------------------------------------------------------------------------------------------- the press
def fire(card_id: str, *, actor: str, store: BriefingStore, readers: Readers, now: datetime | None = None,
         queue: QueuePort | None = None, spawn: Spawner | None = None, allow_http: bool = False) -> dict[str, Any]:
    """The worker pressed the button on a card. Returns ``{queue_id}`` or ``{run_id}`` (one, never both) plus the card.

    Raises ``Refused`` (not the worker), ``NotFound``, ``NotReady`` (already fired, dismissed or stale), ``Killed``,
    ``Stale`` (the card stopped being true; it is marked stale) or ``Unavailable`` (the queue or the agent service cannot be
    reached; the card stays ready so the worker can press again)."""
    if actor != "worker":
        raise Refused(f"Only the worker can press a card; the actor {actor[:24]!r} cannot.")
    card = store.find(card_id)
    if card is None:
        raise NotFound(f"There is no card {card_id[:40]}.")
    if card.status != "ready":
        extra = {k: v for k, v in (card.fired or {}).items() if k in ("queue_id", "run_id")}
        raise NotReady(f"Nothing changed: the card is already {card.status}.", **extra)
    if kill_flag_set():
        raise Killed("The kill switch is on, so nothing can be started. Clear it first if you want to go on.")
    now = now or datetime.now(timezone.utc)
    ctx = Ctx(person=card.person, now=now, allow_http=allow_http)
    cand = Candidate.from_dict(card.candidate)
    verdict = verify_one(cand, collect(ctx, readers), ctx, in_flight=readers.in_flight, card=card)
    if verdict.verdict == "stale":
        store.update_card(card_id, lambda c: _mark(c, "stale", verdict.note, now))
        raise Stale(f"This card is out of date, so nothing was started. {verdict.note}")

    result: dict[str, Any] = {}
    ftype = card.fire_type
    if ftype in ("queue", "draft"):
        port = queue or default_queue_port()
        draft_ref = None
        if ftype == "draft":
            draft_ref = f"briefing/drafts/{card.id}.json"
            _atomic_json(data_dir() / draft_ref, {"card": card.id, "kind": card.kind, "prepared": card.prepared,
                                                  "prepared_hash": card.prepared_hash, "created_at": iso(now),
                                                  "note": "A local draft. Nothing has been written anywhere else."})
        item = port(**queue_kwargs(card, draft_ref=draft_ref))
        result["queue_id"] = item["id"]
    elif ftype == "agent":
        if card.risk_class != "normal":
            raise Refused("Only a read-only card can start a background run; this one needs its own approval in the queue.")
        ref = card.fire.get("payload_ref", {})
        kind = ref.get("agent_kind", "")
        if kind not in READ_ONLY_AGENT_KINDS:
            raise Refused(f"The run kind {str(kind)[:40]!r} is not one a card may start.")
        sp = spawn or default_spawner()
        params = {"card_id": card.id, "person": card.person, "prepared": {k: card.prepared[k] for k in ("text", "steps") if k in card.prepared},
                  "prepared_hash": card.prepared_hash, **({"habit": ref["habit"]} if "habit" in ref else {})}
        out = sp(kind, params, ref.get("mode", "foreground"))
        result["run_id"] = out["run_id"]
    else:  # FireSpec validates the type; this is belt and braces
        raise Refused(f"Unknown fire type {ftype!r}.")

    def done(c: Card) -> dict[str, Any]:
        _mark(c, "fired", verdict.note, now)
        c.fired = {"at": iso(now), "actor": actor, "verdict": verdict.verdict, **result}
        return c.to_contract()

    contract = store.update_card(card_id, done) or {}

    def labels(st: dict[str, Any]) -> None:
        st["labels"].append({"t": now.timestamp(), "kind": card.kind, "accepted": True, "card": card.id})
        st["suppress"][card.subject] = {"until": now.timestamp() + COOLDOWN_DAYS * 86400, "reason": "fired"}
        if card.kind == "agent_result" and card.subject.startswith("run:"):
            vr = st.setdefault("viewed_runs", [])
            if card.subject[4:] not in vr:
                vr.append(card.subject[4:])

    store.mutate(card.person, labels)
    _audit("briefing_fired", card, "ok")
    return {**result, "status": "fired", "card": contract}


def _mark(c: Card, status: str, note: str, now: datetime) -> Card:
    c.status = status
    c.verify_note = note
    c.updated_at = iso(now)
    return c


def dismiss(card_id: str, *, actor: str, store: BriefingStore, mode: str | None = None, reason: str | None = None,
            now: datetime | None = None) -> dict[str, Any]:
    """The worker said no. A decline is a label (PRO-3). ``mode`` (or the older ``reason``): ``not_now`` snoozes the subject for a
    cooldown; ``never`` is recorded and honoured: the subject, and the card kind with its source, are not proposed again."""
    if actor != "worker":
        raise Refused(f"Only the worker can dismiss a card; the actor {actor[:24]!r} cannot.")
    mode = mode or reason or "not_now"
    if mode not in ("not_now", "never"):
        raise FireError("mode must be not_now or never", code_hint="bad_mode")
    card = store.find(card_id)
    if card is None:
        raise NotFound(f"There is no card {card_id[:40]}.")
    if card.status not in ("ready",):
        raise NotReady(f"Nothing changed: the card is already {card.status}.")
    now = now or datetime.now(timezone.utc)

    def go(c: Card) -> dict[str, Any]:
        c.status = "dismissed"
        c.dismissed = {"at": iso(now), "mode": mode, "reason": mode}
        c.updated_at = iso(now)
        return c.to_contract()

    contract = store.update_card(card_id, go) or {}

    def labels(st: dict[str, Any]) -> None:
        st["labels"].append({"t": now.timestamp(), "kind": card.kind, "accepted": False, "card": card.id})
        until = None if mode == "never" else now.timestamp() + COOLDOWN_DAYS * 86400
        st["suppress"][card.subject] = {"until": until, "reason": mode}
        if mode == "never":
            st["suppress"][f"kind:{card.kind}"] = {"until": None, "reason": "never", "sources": list(card.sources)}
        if card.kind == "agent_result" and card.subject.startswith("run:"):
            vr = st.setdefault("viewed_runs", [])
            if card.subject[4:] not in vr:
                vr.append(card.subject[4:])

    store.mutate(card.person, labels)
    _audit("briefing_dismissed", card, mode)
    return {"status": "dismissed", "mode": mode, "card": contract}
