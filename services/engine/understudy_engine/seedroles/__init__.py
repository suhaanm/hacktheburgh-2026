"""A twelve-week working history for the worker, per role, written into the data directory as a top-up (``python -m understudy_engine.demo seed-growth --role ...``).

When the worker switches their profile to another role (Account menu, Change profile; ``POST /profile``), the worker screens must have something real to show for that role: Growth
(progress, the week and the hours, the steps against one experienced worker, the routines map, commits for programmers), the pointers on Home, the coach and Cue labels, and the proposals
in Needs you. Each role's history is kept apart, under the role's own name, for the SAME worker id, and is readable again when the worker returns to the role.

Two writers, one marker file each, both idempotent and both only ever writing into the demo data directory (``demo.is_demo_data_dir``):

* ``ledger``: the worker's assist ledger rows for the role (``<data>/assist/ledger.jsonl``; skills, outcomes, help given, hard skills that stay hard, plateaus, a regression, bad weeks),
  and the role's briefing cards.
* ``events``: the worker's captured events for the role (``<data>/real/<person>/<day>.jsonl``; the work ribbon, hours, the routines the finder reads, the steps the genome compares with
  the experienced worker's, and for programmers the commit history).

``seed_role`` runs both for one role, ``seed_roles`` for a list. Nothing here reads a clock but the ``now`` it is given, calls a model, or reaches the network. Every row keeps the data
enum ``origin: synthetic``; no text a person reads says how the data was made.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

#: the roles that have a deepened pack and no history of their own in the base demo seed (benefits processor has the demo's own Growth seed)
ROLES: tuple[str, ...] = ("programmer", "data-analyst")
#: the worker the history is written for (the demo person; the same id under every role)
PERSON = "p_learn01"


def seed_role(dd: Path, role: str, now: datetime, out: Callable[[str], None] = print) -> dict[str, Any]:
    """Seed one role's history: ledger and briefing first, then events. Returns what each writer reports. Idempotent (each writer keeps its own marker)."""
    if role not in ROLES:
        raise ValueError(f"no history to seed for {role!r}; choose one of {', '.join(ROLES)}")
    from . import events, ledger

    res: dict[str, Any] = {"role": role}
    res["ledger"] = ledger.seed(dd, role, now, out)
    res["events"] = events.seed(dd, role, now, out)
    return res


def seed_roles(dd: Path, roles: list[str] | tuple[str, ...], now: datetime, out: Callable[[str], None] = print) -> list[dict[str, Any]]:
    return [seed_role(dd, r, now, out) for r in roles]
