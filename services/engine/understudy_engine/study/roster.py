"""``data/real/roster.json``: who is an expert and who is a novice in the real cohort (the genome needs it)."""
from __future__ import annotations

import json
import re

from ..store.paths import data_dir
from .state import StudyError, atomic_write

_PERSON = re.compile(r"^p_[a-z0-9]{2,16}$")
LEVELS = ("expert", "novice")


def roster_path():
    return data_dir() / "real" / "roster.json"


def load() -> dict[str, str]:
    p = roster_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def add(person: str, level: str) -> dict[str, str]:
    if not _PERSON.match(person):
        raise StudyError("person must look like p_ab12 (lowercase letters and digits after p_).")
    if level not in LEVELS:
        raise StudyError("level must be expert or novice.")
    r = load()
    r[person] = level
    atomic_write(roster_path(), json.dumps(dict(sorted(r.items())), indent=2) + "\n")
    return r


def remove(person: str) -> dict[str, str]:
    r = load()
    r.pop(person, None)
    atomic_write(roster_path(), json.dumps(dict(sorted(r.items())), indent=2) + "\n")
    return r
