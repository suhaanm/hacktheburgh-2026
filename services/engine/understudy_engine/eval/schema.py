"""JSON Schema for evals/report.json: loading and validation."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("report.schema.json")


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def errors(report: dict[str, Any]) -> list[str]:
    """Every schema violation as ``path: message``, sorted by path. Empty means valid."""
    from jsonschema import Draft202012Validator

    v = Draft202012Validator(load_schema())
    out = []
    for e in v.iter_errors(report):
        path = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{path}: {e.message[:300]}")
    return sorted(out)


def validate(report: dict[str, Any]) -> None:
    errs = errors(report)
    if errs:
        raise ValueError("report does not match report.schema.json:\n  " + "\n  ".join(errs[:40]))
