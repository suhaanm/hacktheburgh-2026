"""A built firm on disk: the people the Admin screens show, kept in the data directory so every screen reads the same people.

Layout (``<data>/firm/``):

* ``roster.json``: the commit point. Version, the plan that made it, its seed and clock, then per person the id, label, display name, role, level,
  unit (team), tenure, join and role-change times, and the row count and SHA-1 of the person's ledger file; then the routines, the open approvals
  (ages only), the risk events and the feed times. Written last, by rename, so a reader never sees a half-written firm.
* ``ledger/<person>.jsonl``: that person's assist-ledger-shaped rows (the same shape as ``<data>/assist/ledger.jsonl``; ``origin`` stays the data enum
  ``synthetic``). They are NOT the worker's own ledger and never mixed into it: the Worker view never reads this directory, and the worker's own
  export and delete never touch it.

``load_firm`` refuses a firm whose version, row counts or hashes do not match (it answers None, as if there were no firm) rather than serve part of one.
``signature`` is a cheap stat of the roster so a running engine notices a firm that was added, refreshed or removed without a restart.
Nothing here reads a clock or the network; ``write_firm`` is given the firm to write.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .names import assign_names
from .types import FirmSnapshot, PersonRecord

VERSION = 1
DIRNAME = "firm"
ROSTER = "roster.json"
LEDGER_DIR = "ledger"
#: the neutral value of ``meta.badge`` for a built firm: the screens print it as a plain word, never as a tag about how the data was made
BADGE = "firm"


def firm_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / DIRNAME


def roster_path(data_dir: Path | str) -> Path:
    return firm_dir(data_dir) / ROSTER


def signature(data_dir: Path | str) -> tuple[int, int] | None:
    """``(mtime_ns, size)`` of the roster, or None when there is no built firm. One stat; safe to call on every request."""
    try:
        st = roster_path(data_dir).stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def has_firm(data_dir: Path | str) -> bool:
    return signature(data_dir) is not None


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _jsonl(rows: tuple[dict[str, Any], ...]) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows).encode()


def write_firm(data_dir: Path | str, snap: FirmSnapshot, *, plan: str, seed: int, names: dict[str, str] | None = None) -> dict[str, Any]:
    """Write ``snap`` (people, routines, approvals, risk events) under ``<data>/firm/``. Ledger files first, the roster last. Returns a summary of what was written.

    ``names`` is ``label -> display name``; by default each person gets one from ``names.assign_names`` over the firm's labels (a fixed rule: the same labels give
    the same names). Idempotent: the same snapshot gives byte-identical files.
    """
    d = firm_dir(data_dir)
    by_label = names if names is not None else assign_names((p.label or p.id) for p in snap.people)
    people: list[dict[str, Any]] = []
    total = 0
    for p in sorted(snap.people, key=lambda x: x.id):
        blob = _jsonl(p.rows)
        _atomic(d / LEDGER_DIR / f"{p.id}.jsonl", blob)
        total += len(p.rows)
        people.append({"id": p.id, "label": p.label or p.id, "name": p.name or by_label.get(p.label or p.id, ""), "role": p.role, "level": p.level, "unit": p.unit,
                       "tenure_weeks": int(p.tenure_weeks), "tz": p.tz, "role_since_t": p.role_since_t, "joined_t": p.joined_t, "pack_rev": p.pack_rev, "origin": p.origin,
                       "rows": len(p.rows), "sha1": hashlib.sha1(blob).hexdigest()})
    roster = {"version": VERSION, "plan": plan, "seed": int(seed), "now": snap.now, "origin": snap.origin, "people": people, "routines": list(snap.routines),
              "approvals": list(snap.approvals), "risk_events": list(snap.risk_events), "feed_t": dict(snap.feed_t)}
    _atomic(d / ROSTER, (json.dumps(roster, sort_keys=True, indent=1) + "\n").encode())
    return {"people": len(people), "rows": total, "plan": plan, "now": snap.now, "path": str(d)}


def load_firm(data_dir: Path | str) -> FirmSnapshot | None:
    """The built firm as a snapshot (source ``firm``, badge ``firm``), or None when there is none or it does not check out."""
    d = firm_dir(data_dir)
    try:
        roster = json.loads((d / ROSTER).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(roster, dict) or roster.get("version") != VERSION or not isinstance(roster.get("people"), list):
        return None
    people: list[PersonRecord] = []
    try:
        for e in roster["people"]:
            blob = (d / LEDGER_DIR / f"{e['id']}.jsonl").read_bytes()
            if hashlib.sha1(blob).hexdigest() != e["sha1"]:
                return None
            rows = tuple(json.loads(line) for line in blob.decode().splitlines() if line.strip())
            if len(rows) != e["rows"]:
                return None
            people.append(PersonRecord(id=e["id"], role=e["role"], level=e["level"], unit=e["unit"], tenure_weeks=int(e["tenure_weeks"]), tz=e.get("tz", "UTC"),
                                       role_since_t=e.get("role_since_t"), pack_rev=e.get("pack_rev", "1"), joined_t=e.get("joined_t"), label=e["label"],
                                       origin=e.get("origin", "synthetic"), rows=rows, name=e.get("name", "")))
        return FirmSnapshot(now=float(roster["now"]), people=tuple(people), routines=tuple(roster.get("routines", ())), approvals=tuple(roster.get("approvals", ())),
                            risk_events=tuple(roster.get("risk_events", ())), feed_t={k: float(v) for k, v in (roster.get("feed_t") or {}).items()},
                            origin=roster.get("origin", "synthetic"), badge=BADGE, source="firm")
    except (OSError, ValueError, KeyError, TypeError):
        return None


_cache: dict[str, Any] = {"key": None, "snap": None}


def load_cached(data_dir: Path | str) -> FirmSnapshot | None:
    """``load_firm`` remembered by the roster's signature (one entry), so every screen's request reads the same people without re-reading 24 files each time."""
    d = str(Path(data_dir))
    sig = signature(d)
    key = (d, sig)
    if sig is None:
        _cache.update(key=key, snap=None)
        return None
    if _cache["key"] != key:
        _cache.update(key=key, snap=load_firm(d))
    return _cache["snap"]


def describe(data_dir: Path | str) -> dict[str, Any] | None:
    """What the roster says it holds, without reading any ledger file: for the seed's report and the tests."""
    try:
        r = json.loads(roster_path(data_dir).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict) or not isinstance(r.get("people"), list):
        return None
    roles: dict[str, int] = {}
    for e in r["people"]:
        roles[e["role"]] = roles.get(e["role"], 0) + 1
    return {"version": r.get("version"), "plan": r.get("plan"), "seed": r.get("seed"), "now": r.get("now"), "people": len(r["people"]), "roles": roles,
            "units": sorted({e["unit"] for e in r["people"]}), "rows": sum(int(e["rows"]) for e in r["people"])}
