"""The briefing: collect, verify what is already on screen, judge what is new, prepare, persist.

``build`` is the whole morning cycle for one person and it only ever *reads and prepares*: it does not enqueue anything,
spawn anything or write to any source (the one side effect is the handoff track's own refresh of its routine registry,
the same call ``GET /routines`` makes). Pressing a card is ``fire.py``.

One briefing is one *generation* of at most ``CAP`` non-stale cards. A generation lasts ``REGEN_H`` hours; after that, or on
``force``, a new one is made and the old cards are archived (cards the worker has edited and that still verify carry over, so an
edit is never lost). Inside a generation the cards on screen are re-verified on every read: one that went stale is dropped
and its slot can be refilled by the next-best candidate, so the briefing never shows a card that stopped being true.

In mock mode (``UNDERSTUDY_MOCK=1``) the clock is the briefing's own generation time once one exists, so the same state gives the
same output and nothing expires by wall clock; the first briefing for a person is made at the real time.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .acceptance import AcceptanceModel, role_prior
from .candidates import Candidate, Ctx, collect
from .cards import Card, iso, new_card, parse_iso
from .judge import CAP, MIN_SCORE, rank
from .paths import is_mock
from .prepare import prepare
from .sources import Readers
from .store import BriefingStore
from .text import clean_prepared
from .verify import verify_all, verify_one

REGEN_H = 12.0
HISTORY_MAX = 60


@dataclass
class Briefing:
    person: str
    generated_at: str | None
    cards: list[Card]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    dropped: list[dict[str, str]] = field(default_factory=list)
    regenerated: bool = False

    def to_contract(self) -> dict[str, Any]:
        return {"cap": CAP, "generated_at": self.generated_at, "cards": [c.to_contract() for c in self.cards],
                # additive
                "person": self.person, "min_score": MIN_SCORE, "regenerated": self.regenerated, "dropped": self.dropped,
                "sources": {k: {"available": v.get("available"), "n": v.get("n")} for k, v in self.diagnostics.items()}}


def person_role(person: str) -> str | None:
    try:
        from .. import routes_handoff as rh

        pd = rh._src().load(person)
        return pd.role if pd else None
    except Exception:
        return None


def _now(now: datetime | None, st: dict[str, Any]) -> datetime:
    if now is not None:
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if is_mock() and st.get("generated_at"):
        return datetime.fromtimestamp(parse_iso(st["generated_at"]), timezone.utc)
    return datetime.now(timezone.utc)


def _refresh(card: Card, fresh: Candidate, reword) -> None:
    """The evidence moved: bring numbers, title and reason up to date; re-prepare unless the worker edited the content."""
    card.title, card.why, card.numbers, card.wording = fresh.title, fresh.why, dict(fresh.numbers), "template"
    card.candidate = fresh.to_dict()
    card.fire = fresh.fire.to_dict()
    if not card.edited:
        card.prepared = prepare(fresh, reword=reword)
    if ("irreversible", "outward", "normal").index(fresh.risk_class) < ("irreversible", "outward", "normal").index(card.risk_class):
        card.risk_class = fresh.risk_class      # a card only ever gets more careful


def build(person: str, *, store: BriefingStore | None = None, readers: Readers | None = None, now: datetime | None = None,
          force: bool = False, reword: Callable[..., Any] | None = None, reword_why: Callable[[Candidate], str | None] | None = None, role: str | None = None, allow_http: bool = False,
          regen_h: float = REGEN_H, origin: str = "synthetic", p_accept: Callable[[str], float] | None = None,
          cap: int = CAP) -> Briefing:
    store = store or BriefingStore()
    readers = readers or Readers()
    st0 = store.person(person)
    t = _now(now, st0)
    role = role or person_role(person)
    ctx = Ctx(person=person, now=t, role=role, allow_http=allow_http, viewed_runs=frozenset(st0.get("viewed_runs", [])))
    now_c = collect(ctx, readers)
    labels = list(st0.get("labels", []))
    accept = AcceptanceModel.from_labels(labels, role_prior(role))
    pa = p_accept or accept.p

    cards = [Card.from_dict(c) for c in st0["cards"]]
    gen_at = st0.get("generated_at")
    age_h = None if not gen_at else (t.timestamp() - parse_iso(gen_at)) / 3600.0
    new_gen = force or gen_at is None or (age_h is not None and age_h > regen_h and not is_mock())
    dropped: list[dict[str, str]] = []
    history: list[dict[str, Any]] = []

    # 1. a new generation archives the old cards; edited, still-ready cards carry over
    current: list[Card] = []
    for c in cards:
        if new_gen and not (c.status == "ready" and c.edited):
            history.append(c.to_dict())
            continue
        current.append(c)

    # 2. re-verify what is on screen against the live world
    for c in current:
        if c.status != "ready":
            continue
        v = verify_one(Candidate.from_dict(c.candidate), now_c, ctx, in_flight=readers.in_flight, card=c)
        if v.verdict == "stale":
            c.status, c.verify_note, c.updated_at = "stale", v.note, iso(t)
            dropped.append({"id": c.id, "reason": v.note})
        else:
            c.verdict, c.verify_note = v.verdict, v.note
            if v.candidate is not None:
                c.sources = list(v.candidate.source_tags)      # e.g. whether digests came from the local model right now
            if v.verdict == "updated" and v.candidate is not None:
                _refresh(c, v.candidate, reword)
                c.updated_at = iso(t)

    # 3. fill free slots with the best new candidates (judge: code ranks and caps)
    live = [c for c in current if c.status != "stale"]
    slots = max(0, cap - len(live))
    have = {c.id for c in live} | {c.id for c in current}
    regenerated = bool(new_gen)
    selected_cards: list[Card] = []
    if slots > 0:
        pool = [c for c in now_c.candidates if c.id not in have]
        res = rank(pool, p_accept=pa, now_ts=t.timestamp(), suppress=st0.get("suppress", {}), cap=slots)
        verdicts = verify_all([r.candidate for r in res.selected], now_c, ctx, in_flight=readers.in_flight)
        for r in res.selected:
            v = verdicts[r.candidate.id]
            if v.verdict == "stale":
                dropped.append({"id": r.candidate.id, "reason": v.note})
                continue
            cand = v.candidate or r.candidate
            card = new_card(cand, prepare(cand, reword=reword), now_ts=t.timestamp(), score=r.score,
                            ranking=r.explain(), verdict=v.verdict, verify_note=v.note, origin=origin)
            if reword_why is not None:        # display-only, through the egress guard; the template is the fallback
                try:
                    alt = reword_why(cand)
                except Exception:
                    alt = None
                if isinstance(alt, str) and alt.strip():
                    card.why, card.wording = alt, "model"
            selected_cards.append(card)
        regenerated = regenerated or bool(selected_cards)

    final = current + selected_cards

    def save(s: dict[str, Any]) -> None:
        s["cards"] = [c.to_dict() for c in final]
        if regenerated or not s.get("generated_at"):
            s["generated_at"] = iso(t)
        s["history"] = (s.get("history", []) + history)[-HISTORY_MAX:]

    store.mutate(person, save)
    shown = sorted((c for c in final if c.status != "stale"), key=lambda c: (-c.score, c.id))
    return Briefing(person, iso(t) if regenerated else (gen_at or iso(t)), shown, now_c.diagnostics, dropped, regenerated)


# --------------------------------------------------------------------------------------------- edits and the spoken summary
class EditError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def edit_prepared(card_id: str, prepared: Any, *, actor: str, store: BriefingStore, now: datetime | None = None) -> dict[str, Any]:
    """The worker edits the content of a ready card. What is stored is what the worker sees back and what will fire."""
    if actor != "worker":
        raise EditError("write_refused", f"Only the worker can edit a card; the actor {actor[:24]!r} cannot.", 403)
    card = store.find(card_id)
    if card is None:
        raise EditError("no_such_card", f"There is no card {card_id[:40]}.", 404)
    if card.status != "ready":
        raise EditError("not_ready", f"The card is already {card.status}, so it can no longer be edited.", 409)
    try:
        clean = clean_prepared(prepared)
    except ValueError as exc:
        raise EditError("invalid_prepared", str(exc)) from exc
    stamp = iso(now or datetime.now(timezone.utc))

    def go(c: Card) -> dict[str, Any]:
        c.prepared, c.edited, c.updated_at = clean, True, stamp
        return c.to_contract()

    return store.update_card(card_id, go) or {}


KIND_PHRASE = {"practice": ("a practice session", "practice sessions"), "automate": ("an automation worth a look", "automations worth a look"),
               "focus_block": ("a calendar change", "calendar changes"), "git_habit": ("a coding habit to look at", "coding habits to look at"),
               "agent_result": ("a finished background run", "finished background runs")}
NUMBER_WORDS = {1: "one", 2: "two", 3: "three"}


def summary_text(cards: list[Card]) -> str:
    """A short plain-language summary that is safe to speak: counts and kinds only. No names, titles, reasons or free text from any
    source, because the voice flow rejects personal data."""
    ready = [c for c in cards if c.status == "ready"]
    if not ready:
        return "Good morning. Nothing needs your attention today."
    counts: dict[str, int] = {}
    for c in ready:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    n = len(ready)
    parts = []
    for kind in ("practice", "automate", "focus_block", "git_habit", "agent_result"):
        k = counts.get(kind, 0)
        if k:
            one, many = KIND_PHRASE[kind]
            parts.append(one if k == 1 else f"{NUMBER_WORDS.get(k, str(k))} {many}")
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    careful = any(c.risk_class != "normal" for c in ready)
    out = f"Good morning. You have {NUMBER_WORDS.get(n, str(n))} suggestion{'s' if n != 1 else ''} ready: {listed}."
    if careful:
        out += " Some of them would ask for your approval before anything leaves your computer."
    return out + " Nothing happens until you press go."


def briefing_text(person: str, *, store: BriefingStore | None = None, readers: Readers | None = None, now: datetime | None = None) -> str:
    """The spoken morning briefing (ElevenLabs flag): counts and kinds only. See ``summary_text``."""
    b = build(person, store=store, readers=readers, now=now)
    return summary_text(b.cards)
