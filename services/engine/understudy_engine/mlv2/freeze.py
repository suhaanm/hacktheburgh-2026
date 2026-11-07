"""Frozen choices and the held-out log (PLAN.md section 5).

``frozen.json`` records what DEV decided (the primary candidate of each family, A7's base) and the hashes of the code and the plan at that
moment. ``heldout_log.jsonl`` is append-only: every held-out part writes a ``start`` line (timestamp, part, code hash, plan hash, frozen choices)
before it touches held-out data, and a ``done`` line after; a part that already has a ``start`` line is refused.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

from understudy_engine.store.paths import evals_dir

HELDOUT_TOKEN_ENV = "UNDERSTUDY_MLV2_HELDOUT"
PARTS = ("hazard", "genome", "mismatch")


def out_dir() -> Path:
    d = evals_dir() / "mlv2"
    (d / "results").mkdir(parents=True, exist_ok=True)
    return d


def package_dir() -> Path:
    return Path(__file__).resolve().parent


# the modules each held-out part depends on (a change to any other file does not change that part's fingerprint)
PART_FILES = {
    "hazard": ("__init__", "ablation", "ablation_awareness", "alarms", "conformal", "controls", "family_a", "family_c", "hazard_part", "models",
               "protocol", "splits", "stats", "tte"),
    "genome": ("__init__", "splits", "stats", "genome_part", "envelope", "counterfactual", "apprentice_pool", "genome_stats"),
    "mismatch": ("__init__", "alarms", "conformal", "family_a", "family_c", "models", "protocol", "stats", "mismatch"),
}


def code_hashes(part: str | None = None) -> dict[str, str]:
    names = None if part is None else {f"{n}.py" for n in PART_FILES.get(part, ())}
    h = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package_dir().glob("*.py")) if names is None or p.name in names}
    plan = out_dir() / "PLAN.md"
    if plan.exists():
        h["PLAN.md"] = hashlib.sha256(plan.read_bytes()).hexdigest()
    return h


def code_fingerprint(hashes: dict[str, str] | None = None) -> str:
    hs = hashes or code_hashes()
    return hashlib.sha256(json.dumps(hs, sort_keys=True).encode()).hexdigest()


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(o: Any) -> Any:
    """JSON-safe copy: numpy to Python, NaN and inf to None, tuples to lists."""
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, Path):
        return str(o)
    return o


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean(obj), indent=1, sort_keys=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_path() -> Path:
    return out_dir() / "results" / "frozen.json"


def log_path() -> Path:
    return out_dir() / "heldout_log.jsonl"


def read_frozen() -> dict | None:
    p = frozen_path()
    return read_json(p) if p.exists() else None


def log_lines() -> list[dict]:
    p = log_path()
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def part_started(part: str) -> bool:
    return any(x.get("part") == part and x.get("event") == "start" for x in log_lines())


def append_log(entry: dict) -> None:
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(clean(entry)) + "\n")


def token_ok() -> bool:
    return os.environ.get(HELDOUT_TOKEN_ENV, "").strip() == "1"
