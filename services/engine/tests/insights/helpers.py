"""Builders for hand-made ledger rows and people (schema-valid through the real ``cue.ledger.make_row``)."""
from __future__ import annotations

from understudy_engine.cue import ledger as L
from understudy_engine.insights.firm import NOW0
from understudy_engine.insights.types import FirmSnapshot, PersonRecord

DAY = 86400.0
NOW = NOW0
SKILL = "check-the-cliff"
ROLE = "benefits-processor"


def row(person: str, days_ago: float, skill: str = SKILL, outcome: str = "clean", lost: float | None = 0.0, *, role: str = ROLE, stream: str = "assist",
        serial: int = 0, now: float = NOW, ttp: float | None = None, origin: str = "synthetic") -> dict:
    kw = dict(person=person, role=role, skill=skill, step=skill.replace("-", "_"), t=now - days_ago * DAY, outcome=outcome, origin=origin, stream=stream,
              lost_s=lost, serial=serial, accepted=(outcome == "assisted"), seconds_to_progress=ttp)
    if outcome == "assisted":
        kw.update(trigger="auto", tier=1)
    if stream != "assist":
        kw.update(routine="case-note-draft", minutes=8.0, offload_outcome="done", skill=None, step=None, lost_s=None)
    return L.make_row(**kw)


def person(pid: str, rows, *, role: str = ROLE, level: str = "junior", unit: str = "unit_x", tenure: int = 10, role_since: float | None = None, label: str | None = None,
           tz: str = "UTC", joined_t: float | None = None) -> PersonRecord:
    rs = sorted(rows, key=lambda r: r["t_hour"])
    return PersonRecord(id=pid, role=role, level=level, unit=unit, tenure_weeks=tenure, tz=tz, role_since_t=role_since, label=label or pid, joined_t=joined_t,
                        rows=tuple(rs), origin="synthetic")


def snap(people, *, now: float = NOW, routines=(), approvals=(), events=(), feed=None) -> FirmSnapshot:
    return FirmSnapshot(now=now, people=tuple(people), routines=tuple(routines), approvals=tuple(approvals), risk_events=tuple(events),
                        feed_t=feed if feed is not None else {"ledger": now, "risk_feed": now}, origin="synthetic", badge="synthetic firm", source="firm")


def habit_rows(pid: str, *, weeks: int = 3, per_week: int = 4, lost: float = 30.0, outcome: str = "clean", skill: str = SKILL, start_days: float = 1.0,
               serial0: int = 0, jitter: float = 4.0) -> list[dict]:
    """``per_week`` occurrences in each of the last ``weeks`` weeks with ``lost`` seconds lost (a small deterministic wobble)."""
    out = []
    k = serial0
    for w in range(weeks):
        for i in range(per_week):
            d = start_days + w * 7 + i * (6.0 / per_week)
            wob = ((k * 7919) % 11 - 5) / 5.0 * jitter
            out.append(row(pid, d, skill, outcome, lost + wob, serial=k))
            k += 1
    return out
