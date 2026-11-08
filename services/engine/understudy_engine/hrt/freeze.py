"""Freeze and the held-out log (``evals/hrt/PLAN.md`` section 7), the same discipline as ``evals/mlv2/PLAN.md`` section 5.

``frozen.json`` records the sha256 of the code each part depends on and of the plan. A held-out run refuses without the token, without a freeze,
when the code or the plan has changed since the freeze, or when the part already has a ``start`` line in ``heldout_log.jsonl``. The log is
append-only: ``start`` is written before any held-out seed is touched, ``done`` after.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any

from understudy_engine.store.paths import evals_dir

from .worlds import HELDOUT_ENV

PARTS = ("ledger", "decisions")
PART_FILES = {
    "ledger": ("__init__", "ledger", "scoring", "guard", "worlds", "prospective", "run"),
    "decisions": ("__init__", "scoreboard", "worlds", "run"),
}


def out_dir() -> Path:
    d = evals_dir() / "hrt"
    (d / "results").mkdir(parents=True, exist_ok=True)
    return d


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def code_hashes(part: str | None = None) -> dict[str, str]:
    names = None if part is None else {f"{n}.py" for n in PART_FILES.get(part, ())}
    h = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package_dir().glob("*.py")) if names is None or p.name in names}
    plan = out_dir() / "PLAN.md"
    if plan.exists():
        h["PLAN.md"] = hashlib.sha256(plan.read_bytes()).hexdigest()
    return h


def fingerprint(hashes: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def frozen_path() -> Path:
    return out_dir() / "results" / "frozen.json"


def log_path() -> Path:
    return out_dir() / "heldout_log.jsonl"


def read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _clean(o: Any) -> Any:
    """JSON-safe copy: numpy scalars and arrays to Python, NaN and inf to None."""
    import math

    import numpy as np

    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, np.ndarray):
        o = o.tolist()
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(_clean(obj), indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def read_frozen() -> dict[str, Any] | None:
    p = frozen_path()
    return read_json(p) if p.exists() else None


def freeze(parts: tuple[str, ...] = PARTS) -> dict[str, Any]:
    cur = read_frozen() or {}
    cur["frozen_at"] = now()
    cur.setdefault("parts", {})
    for part in parts:
        hs = code_hashes(part)
        cur["parts"][part] = {"fingerprint": fingerprint(hs), "hashes": hs}
    write_json(frozen_path(), cur)
    return cur


def token_ok() -> bool:
    import os

    return os.environ.get(HELDOUT_ENV, "").strip() == "1"


def log_lines() -> list[dict[str, Any]]:
    p = log_path()
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def part_started(part: str) -> bool:
    return any(x.get("event") == "start" and x.get("part") == part for x in log_lines())


def append_log(row: dict[str, Any]) -> None:
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


class Refused(RuntimeError):
    """The held-out command refused to run; the message says why."""


def check_can_run_heldout(part: str, *, amended: bool = False) -> dict[str, str]:
    """Raise ``Refused`` unless the token is set, the part is frozen, nothing changed since the freeze, and the part has not run. Returns the hashes."""
    if part not in PARTS:
        raise Refused(f"unknown part {part!r}; choose from {PARTS}")
    if not token_ok():
        raise Refused(f"set {HELDOUT_ENV}=1 (single frozen run, evals/hrt/PLAN.md section 7)")
    fz = read_frozen()
    if not fz or part not in fz.get("parts", {}):
        raise Refused("evals/hrt/results/frozen.json has no freeze for this part; run `freeze` first")
    hs = code_hashes(part)
    if fingerprint(hs) != fz["parts"][part]["fingerprint"]:
        changed = sorted(k for k in set(hs) | set(fz["parts"][part]["hashes"]) if hs.get(k) != fz["parts"][part]["hashes"].get(k))
        raise Refused(f"the code or the plan changed since the freeze ({', '.join(changed)}); re-freeze with a dated amendment before the held-out run")
    if part_started(part) and not amended:
        raise Refused(f"part {part} already has a start line in heldout_log.jsonl (a declared amendment is needed to run it again)")
    return hs
