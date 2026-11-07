"""Spend guard for the bake-off: US$3 across ALL live calls of the MODELS track, resumable across runs.

Cost per call is an ESTIMATE from token counters at assumed per-million prices (`understudy_agent.models.prices`). The guard applies
a safety factor on top because the price table is an assumption. Before each live call the runner asks `allow(est)`; when the cap
would be crossed it stops and records the dropped cell. Cached results cost nothing. The ledger is `cache/spend.jsonl`
(append-only, one line per live call: contender, kind, estimated cost; no content).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

SAFETY_FACTOR = 1.25            # the guard counts spend at 1.25x the estimate
PROBE_SPEND_USD = 0.06          # my hand-run probes and smoke tests before the harness existed (about 35 tiny calls); conservative


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, cap_usd: float, path: Path | None) -> None:
        self.cap = float(cap_usd)
        self.path = path
        self._lock = threading.Lock()
        self.session_spent = 0.0
        self.prior = PROBE_SPEND_USD
        self.dropped: list[dict[str, str]] = []
        if path is not None and path.exists():
            for line in path.read_text().splitlines():
                try:
                    self.prior += float(json.loads(line).get("usd", 0.0))
                except (ValueError, TypeError):
                    continue

    @property
    def spent(self) -> float:
        """Estimated spend so far (prior runs + probes + this run), before the safety factor."""
        return self.prior + self.session_spent

    def guarded_spent(self) -> float:
        return self.spent * SAFETY_FACTOR

    def allow(self, est_next_usd: float) -> bool:
        with self._lock:
            return self.guarded_spent() + est_next_usd * SAFETY_FACTOR <= self.cap

    def add(self, usd: float | None, *, contender: str, kind: str) -> None:
        usd = float(usd or 0.0)
        with self._lock:
            self.session_spent += usd
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as f:
                    f.write(json.dumps({"usd": round(usd, 6), "contender": contender, "kind": kind}) + "\n")

    def drop(self, cell: dict[str, str]) -> None:
        with self._lock:
            self.dropped.append(cell)

    def summary(self) -> dict[str, object]:
        return {"cap_usd": self.cap, "estimated_spend_usd": round(self.spent, 4), "guarded_spend_usd": round(self.guarded_spent(), 4),
                "safety_factor": SAFETY_FACTOR, "probe_spend_usd_included": PROBE_SPEND_USD,
                "dropped_cells": list(self.dropped), "n_dropped": len(self.dropped)}
