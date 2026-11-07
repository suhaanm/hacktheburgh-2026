"""Cost and latency meter: one record per model call, metadata only.

A record holds: time, role, provider, model, tier, method, latency (ms), input and output tokens (thinking tokens listed
separately and billed as output), a cost estimate at the configured per-million prices (an ASSUMPTION; see `prices.py`), ok or
failed (with a closed error kind), the image hash prefix when an image was sent, and which step of the route it was.
Never image bytes, never text from a screen, never a key.

`Meter` keeps the last 2000 records in memory and, when `path` is set, appends each one to a JSONL file. The router's default path
is `model_meter.jsonl` next to the egress ledger (`<data dir>`), because a ledger line is written BEFORE a send and cannot hold
the latency and token counts that are only known afterwards.
"""
from __future__ import annotations

import json
import math
import os
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class CallRecord:
    role: str
    provider: str
    model: str
    tier: str
    method: str
    ok: bool
    latency_ms: int | None
    input_tokens: int | None = None
    output_tokens: int | None = None   # visible output
    thought_tokens: int | None = None  # billed as output
    cost_usd: float | None = None      # estimate at assumed prices
    error_kind: str | None = None
    image_sha: str | None = None
    step: int = 0                       # 0 primary, 1 first escalation or fallback, ...
    api: str | None = None
    t: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["t"] = d["t"] or now_iso()
        return d


def percentile(sorted_vals: list[float], q: float) -> float | None:
    """Nearest-rank percentile of an already sorted list (q in 0..100)."""
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, math.ceil(q / 100.0 * len(sorted_vals)) - 1))
    return sorted_vals[k]


def default_meter_path() -> Path:
    from understudy_engine.privacy import ledger

    return ledger.ledger_path().with_name("model_meter.jsonl")


class Meter:
    def __init__(self, *, path: Path | None = None, keep: int = 2000) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._recent: deque[dict[str, Any]] = deque(maxlen=keep)

    def record(self, rec: CallRecord) -> dict[str, Any]:
        d = rec.as_dict()
        with self._lock:
            self._recent.append(d)
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    line = json.dumps(d, ensure_ascii=True, separators=(",", ":")) + "\n"
                    fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                    try:
                        os.write(fd, line.encode("ascii"))
                    finally:
                        os.close(fd)
                except OSError:
                    pass  # the meter is advisory: losing a line must never fail a call
        return d

    def records(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._recent)
        return rows if limit is None else rows[-limit:]

    def last_latencies(self, per_key: int = 5) -> dict[str, list[int]]:
        """{'provider:model': [latest latencies, newest last]} of successful calls."""
        out: dict[str, list[int]] = {}
        for r in self.records():
            if r["ok"] and r["latency_ms"] is not None:
                out.setdefault(f"{r['provider']}:{r['model']}", []).append(int(r["latency_ms"]))
        return {k: v[-per_key:] for k, v in out.items()}

    def summary(self) -> list[dict[str, Any]]:
        """One row per (role, provider, model): counts, p50 and p95 latency of ok calls, tokens, cost estimate."""
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in self.records():
            groups.setdefault((r["role"], r["provider"], r["model"]), []).append(r)
        rows = []
        for (role, prov, model), rs in sorted(groups.items()):
            lat = sorted(float(r["latency_ms"]) for r in rs if r["ok"] and r["latency_ms"] is not None)
            costs = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
            rows.append({
                "role": role, "provider": prov, "model": model, "n": len(rs), "ok": sum(1 for r in rs if r["ok"]),
                "failed": sum(1 for r in rs if not r["ok"]),
                "p50_ms": percentile(lat, 50), "p95_ms": percentile(lat, 95),
                "input_tokens": sum(r["input_tokens"] or 0 for r in rs),
                "output_tokens": sum((r["output_tokens"] or 0) + (r["thought_tokens"] or 0) for r in rs),
                "cost_usd_est": round(sum(costs), 6) if costs else None,
            })
        return rows

    def total_cost_usd(self) -> float:
        return round(sum(r["cost_usd"] or 0.0 for r in self.records()), 6)
