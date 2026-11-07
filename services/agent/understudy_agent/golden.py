"""Cached golden run for the offline demo (AGT-8, NFR-1).

`save_golden` stores one real mock-mode run (events, result, the queue item's evidence, screenshots) under
data/golden/. `replay` re-plays it with no browser and no network, and enqueues a fresh approval item so the
morning queue screen works exactly as in a live run. A replay is labelled as cached everywhere it is shown.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from .queue import ApprovalQueue
from .supervisor import data_dir

GOLDEN_NAME = "benefits_golden.json"


def golden_dir() -> Path:
    return data_dir() / "golden"


def golden_path() -> Path:
    return golden_dir() / GOLDEN_NAME


def has_golden() -> bool:
    return golden_path().exists()


def load_golden() -> dict[str, Any] | None:
    p = golden_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_golden(result: dict[str, Any], events: list[dict[str, Any]], queue_item: dict[str, Any] | None,
                run_id: str, *, src_root: Path | None = None) -> Path:
    d = golden_dir()
    shots = d / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    src = (src_root or data_dir()) / "runs" / run_id
    saved = []
    for png in sorted(src.glob("s*.png")):
        shutil.copyfile(png, shots / png.name)
        saved.append(png.name)
    t0 = events[0]["t"] if events else 0.0
    slim = [{**e, "t_rel": round(e.get("t", t0) - t0, 3)} for e in events]
    payload = {"version": 1, "recorded_from": run_id, "mock": True, "result": result, "events": slim,
               "queue_item": queue_item, "screenshots": saved}
    d.mkdir(parents=True, exist_ok=True)
    p = golden_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    return p


def replay(gold: dict[str, Any], run_id: str, *, emit: Callable[[dict[str, Any]], None],
           sleep: Callable[[float], bool], queue: ApprovalQueue, max_gap_s: float = 0.06) -> dict[str, Any]:
    """Re-emit the recorded events (compressed timing), copy the screenshots, enqueue a fresh gate item and
    return the result dict with this run's id. `sleep(seconds)` returns False when the run was stopped."""
    prev = 0.0
    for e in gold["events"]:
        gap = min(max(e["t_rel"] - prev, 0.0), max_gap_s)
        prev = e["t_rel"]
        if not sleep(gap):
            return {"state": "stopped", "reason": "stopped during replay"}
        emit({k: v for k, v in e.items() if k != "t_rel"} | {"cached": True})
    res = json.loads(json.dumps(gold["result"]))
    res["run_id"], res["cached"] = run_id, True
    dest = data_dir() / "runs" / run_id
    dest.mkdir(parents=True, exist_ok=True)
    for name in gold.get("screenshots", []):
        s = golden_dir() / "screenshots" / name
        if s.exists():
            shutil.copyfile(s, dest / name)
    qi = gold.get("queue_item")
    if qi:
        ev = dict(qi.get("evidence", {}))
        ev["screenshots"] = [f"data/runs/{run_id}/{n}" for n in gold.get("screenshots", [])]
        item = queue.enqueue(kind=qi["kind"], title=qi["title"], summary=qi["summary"] + " (cached run)",
                             risk_class=qi["risk_class"], run_id=run_id, evidence=ev)
        res["queue_id"], res["awaiting_approval"] = item["id"], True
    (dest / "evidence.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    return res
