"""Hashes that pin which generator produced a dataset: ``params.py`` (the ranges) and the generator source as a whole."""
from __future__ import annotations

import hashlib
from pathlib import Path

GENERATOR_FILES = ("cited.py", "params.py", "core.py", "roles.py", "people.py", "ctx.py", "families.py", "emit.py", "cohort.py", "workweeks.py")


def generator_sha256() -> str:
    """SHA-256 over the generator files in a fixed order (not the evaluation code, marginals or tests)."""
    h = hashlib.sha256()
    here = Path(__file__).parent
    for name in GENERATOR_FILES:
        h.update(name.encode())
        h.update((here / name).read_bytes())
    return h.hexdigest()
