"""Assemble evals/report.json (ANA-15, EVL-1, SEC-12, VIS-6).

``build_report`` calls each owning track's code through ``adapters``. A section whose owner has not landed is
``{status: "pending", reason: "<owner> not landed", meta}``; one that raises is ``{status: "failed", ...}`` (the traceback
goes to stderr and the CLI exits 2); the live study with no results is ``{status: "not_run", n: 4, rows: []}``.
Nothing here computes a number except the two sections in ``deficit.py``; the rest is reshaping.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..store.paths import repo_root
from .adapters import SECTION_NAMES, SECTIONS, Ctx, NotLanded, Skipped
from .data import ensure_synthetic, evals_out_dir
from .limitations import assemble as assemble_limitations
from .meta import stub


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_mock() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes")


def clean(o: Any) -> Any:
    """JSON-safe copy: numpy scalars and arrays to Python, tuples to lists, NaN and inf to None, paths and datetimes to text."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        np = None
    if np is not None:
        if isinstance(o, np.generic):
            o = o.item()
        elif isinstance(o, np.ndarray):
            o = o.tolist()
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in (sorted(o, key=str) if isinstance(o, set) else o)]
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    return o


def _stamp_meta(o: Any, generated_at: str) -> None:
    """Every ``meta`` in the report carries the report's own timestamp (owners stamp their own, which is not deterministic)."""
    if isinstance(o, dict):
        m = o.get("meta")
        if isinstance(m, dict) and "origin" in m and "n_unit" in m:
            m["generated_at"] = generated_at
        for v in o.values():
            _stamp_meta(v, generated_at)
    elif isinstance(o, list):
        for v in o:
            _stamp_meta(v, generated_at)


def git_rev() -> str | None:
    root = repo_root()
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        rev = out.stdout.strip()
        return rev or None
    except (OSError, subprocess.SubprocessError):
        return None


def run_section(spec, ctx: Ctx, log: Callable[[str], None]) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    try:
        sec = spec.fn(ctx)
    except NotLanded as e:
        sec = stub("pending", f"{e.owner} not landed ({e.detail})" if e.detail else f"{e.owner} not landed")
    except Skipped as e:
        sec = stub("pending", str(e))
    except FileNotFoundError as e:
        sec = stub("pending", f"data missing: {e}")
    except Exception as e:  # a bug in an owner's code must not take the whole report down; it is shown, loudly
        log(f"eval: section {spec.name} FAILED: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        sec = stub("failed", f"{type(e).__name__}: {e}")
    dt = time.perf_counter() - t0
    return sec, dt


def build_report(*, fast: bool = False, sections: list[str] | None = None, root: Path | str | None = None, now: str | None = None,
                 seed: int = 0, allow_live: bool | None = None, regenerate: bool = True,
                 log: Callable[[str], None] | None = None) -> dict[str, Any]:
    log = log or (lambda m: print(m, file=sys.stderr))
    wanted = list(SECTION_NAMES) if not sections else [s for s in sections if s != "limitations"]
    unknown = [s for s in wanted if s not in SECTION_NAMES]
    if unknown:
        raise ValueError(f"unknown section(s): {', '.join(unknown)}; choose from {', '.join(SECTION_NAMES)}, limitations")
    specs = [s for s in SECTIONS if s.name in wanted]
    t_start = time.perf_counter()
    if regenerate and any(s.needs_synthetic for s in specs):
        try:
            ensure_synthetic(root, log)
        except Exception as e:  # pragma: no cover
            log(f"eval: could not generate synthetic data: {type(e).__name__}: {e}")
    ctx = Ctx(fast=fast, root=Path(root) if root else None, seed=seed,
              allow_live=(os.environ.get("UNDERSTUDY_EVAL_LIVE") == "1" and not is_mock()) if allow_live is None else allow_live)
    out: dict[str, Any] = {}
    secs: dict[str, float] = {}
    for spec in specs:
        log(f"eval: {spec.name} ...")
        sec, dt = run_section(spec, ctx, log)
        out[spec.name] = clean(sec)
        secs[spec.name] = round(dt, 2)
        log(f"eval: {spec.name} {sec.get('status', 'ok')} in {dt:.1f}s")
    out["limitations"] = clean(assemble_limitations(out))
    generated_at = now or _now()
    report: dict[str, Any] = {"generated_at": generated_at, "mock": is_mock()}
    rev = git_rev()
    if rev:
        report["git_rev"] = rev
    report["run"] = {"fast": fast, "seed": seed, "seconds_total": round(time.perf_counter() - t_start, 1), "seconds_by_section": secs,
                     "note": "timing only; excluded from the determinism check"}
    report["sections"] = out
    _stamp_meta(report["sections"], generated_at)
    return report


def deterministic_view(report: dict[str, Any]) -> dict[str, Any]:
    """The report without the fields that legitimately change between two runs (timestamps, timing, git revision)."""
    r = json.loads(json.dumps(report))
    for k in ("generated_at", "git_rev", "run"):
        r.pop(k, None)
    _stamp_meta(r.get("sections", {}), "")
    return r


def dumps(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def default_out() -> Path:
    return evals_out_dir() / "report.json"
