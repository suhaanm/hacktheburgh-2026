"""The card: what the worker sees in the morning, and what is stored.

A card is a candidate that survived the judge and verification, plus its prepared (editable) content. The contract view
(``GET /briefing``) is ``{id, kind, title, why, prepared, risk_class, sources, expires_at, status}``; extra fields
(``numbers``, ``score``, ``ranking``, ``verdict``, ``edited``, ``fire_type``, ``prepared_hash``) are additive, so the
dashboard can explain a card without a second call.

Status: ``ready`` (waiting for the worker), ``fired`` (the worker pressed it), ``dismissed`` (the worker said no),
``stale`` (the situation changed or the card timed out; dropped without bothering anyone).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .candidates import Candidate
from .text import prepared_hash

STATUSES = ("ready", "fired", "dismissed", "stale")
VERDICTS = ("confirmed", "updated", "stale")
#: how long a card stays up before it expires on its own (hours), per kind
TTL_H = {"practice": 24, "automate": 72, "focus_block": 48, "git_habit": 72, "agent_result": 24}


def iso(ts: float | datetime) -> str:
    d = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts, timezone.utc)
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


@dataclass
class Card:
    id: str
    person: str
    kind: str
    title: str
    why: str
    prepared: dict[str, Any]
    risk_class: str
    sources: list[str]
    expires_at: str
    status: str = "ready"
    numbers: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    ranking: dict[str, Any] = field(default_factory=dict)
    verdict: str = "confirmed"
    verify_note: str = ""
    fire: dict[str, Any] = field(default_factory=dict)
    subject: str = ""
    created_at: str = ""
    updated_at: str = ""
    edited: bool = False
    origin: str = "synthetic"
    wording: str = "template"      # "template" or "model" (the reason line was reworded through the egress guard)
    fired: dict[str, Any] | None = None
    dismissed: dict[str, Any] | None = None
    candidate: dict[str, Any] = field(default_factory=dict)      # snapshot used to re-verify and to re-rank

    @property
    def prepared_hash(self) -> str:
        return prepared_hash(self.prepared)

    @property
    def fire_type(self) -> str:
        return str(self.fire.get("type", "queue"))

    def to_contract(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "title": self.title, "why": self.why, "prepared": self.prepared,
                "risk_class": self.risk_class, "sources": list(self.sources), "source_tags": list(self.sources), "expires_at": self.expires_at,
                "status": self.status,
                # additive
                "numbers": dict(self.numbers), "score": round(self.score, 3), "verdict": self.verdict, "verify_note": self.verify_note,
                "edited": self.edited, "fire_type": self.fire_type, "prepared_hash": self.prepared_hash, "origin": self.origin,
                "wording": self.wording,
                "ranking": self.ranking, "fired": self.fired, "dismissed": self.dismissed}

    def to_dict(self) -> dict[str, Any]:
        d = self.to_contract()
        d.update({"person": self.person, "fire": self.fire, "subject": self.subject, "created_at": self.created_at,
                  "updated_at": self.updated_at, "candidate": self.candidate})
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Card:
        return cls(id=d["id"], person=d["person"], kind=d["kind"], title=d["title"], why=d["why"], prepared=d.get("prepared", {}),
                   risk_class=d["risk_class"], sources=list(d.get("sources", [])), expires_at=d["expires_at"],
                   status=d.get("status", "ready"), numbers=d.get("numbers", {}), score=float(d.get("score", 0.0)),
                   ranking=d.get("ranking", {}), verdict=d.get("verdict", "confirmed"), verify_note=d.get("verify_note", ""),
                   fire=d.get("fire", {}), subject=d.get("subject", ""), created_at=d.get("created_at", ""),
                   updated_at=d.get("updated_at", ""), edited=bool(d.get("edited", False)), origin=d.get("origin", "synthetic"),
                   wording=d.get("wording", "template"),
                   fired=d.get("fired"), dismissed=d.get("dismissed"), candidate=d.get("candidate", {}))


def new_card(c: Candidate, prepared: dict[str, Any], *, now_ts: float, score: float, ranking: dict[str, Any],
             verdict: str = "confirmed", verify_note: str = "", origin: str = "synthetic") -> Card:
    ttl = TTL_H.get(c.kind, 24)
    return Card(id=c.id, person=c.person, kind=c.kind, title=c.title, why=c.why, prepared=prepared, risk_class=c.risk_class,
                sources=list(c.source_tags), expires_at=iso(datetime.fromtimestamp(now_ts, timezone.utc) + timedelta(hours=ttl)),
                status="ready", numbers=dict(c.numbers), score=score, ranking=ranking, verdict=verdict, verify_note=verify_note,
                fire=c.fire.to_dict(), subject=c.subject, created_at=iso(now_ts), updated_at=iso(now_ts), origin=origin,
                candidate=c.to_dict())
