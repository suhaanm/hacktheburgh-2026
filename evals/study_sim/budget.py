"""Spend guard and ledger. Cap US$8 (PLAN section 9). Token counts come from the model port's own usage stats when it has them
(the OpenAI provider does), else from a character estimate; prices come from the environment so no price is baked into a result
and the estimate is labelled an estimate. Cache hits cost nothing and are counted separately."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

CAP_USD = 8.0
STOP_FRACTION = 0.95                    # no new participant is started above this share of the cap; no new call above 100%
# conservative defaults (US$ per million tokens) used only when STUDY_SIM_PRICE_IN / _OUT are not set; the report says which was used
DEFAULT_PRICE_IN = 2.50
DEFAULT_PRICE_OUT = 15.00


class BudgetExhausted(RuntimeError):
    pass


def prices() -> tuple[float, float, bool]:
    """(in, out, from_env)"""
    try:
        pin, pout = float(os.environ["STUDY_SIM_PRICE_IN"]), float(os.environ["STUDY_SIM_PRICE_OUT"])
        return pin, pout, True
    except (KeyError, ValueError):
        return DEFAULT_PRICE_IN, DEFAULT_PRICE_OUT, False


@dataclass
class Budget:
    cap_usd: float = CAP_USD
    ledger_path: Path | None = None
    calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    by_role: dict = field(default_factory=dict)
    per_participant: dict = field(default_factory=dict)
    token_source: str = "provider_usage"
    finished: set = field(default_factory=set)
    _seen_in: int = 0
    _seen_out: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def usd(self) -> float:
        pin, pout, _ = prices()
        return (self.tokens_in * pin + self.tokens_out * pout) / 1e6

    def charge(self, participant: str, role: str, tin: int, tout: int, estimated: bool = False) -> None:
        with self._lock:
            self._charge(participant, role, tin, tout, estimated)

    def charge_from_stats(self, participant: str, role: str, stats: dict) -> None:
        """Workers run in parallel and share one model port, so a per-call delta of the port's cumulative usage could include another worker's call.
        The TOTAL is exact (every delta is charged once, to whoever finishes next); the split by participant is approximate."""
        with self._lock:
            tin, tout = int(stats["input_tokens"]) - self._seen_in, int(stats["output_tokens"]) - self._seen_out
            self._seen_in, self._seen_out = int(stats["input_tokens"]), int(stats["output_tokens"])
            self._charge(participant, role, max(tin, 0), max(tout, 0), False)

    def _charge(self, participant: str, role: str, tin: int, tout: int, estimated: bool) -> None:
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        if estimated:
            self.token_source = "character_estimate"
        r = self.by_role.setdefault(role, {"calls": 0, "in": 0, "out": 0})
        r["calls"] += 1
        r["in"] += tin
        r["out"] += tout
        p = self.per_participant.setdefault(participant, {"calls": 0, "usd": 0.0})
        pin, pout, _ = prices()
        p["calls"] += 1
        p["usd"] += (tin * pin + tout * pout) / 1e6
        self._log({"t": time.time(), "participant": participant, "role": role, "in": tin, "out": tout, "usd_total": round(self.usd, 4), "calls": self.calls})
        if self.usd >= self.cap_usd:
            raise BudgetExhausted(f"estimated spend ${self.usd:.2f} reached the cap ${self.cap_usd:.2f}")

    def hit(self, participant: str) -> None:
        self.cache_hits += 1

    def can_start_participant(self, in_flight: int = 0) -> bool:
        """Start a new participant only if the estimate leaves room for it and every participant already running, at 1.5 x the average cost
        of the participants finished so far (workers run in parallel, so the spend of those in flight is not in the ledger yet)."""
        done = [v["usd"] for k, v in self.per_participant.items() if k in self.finished]
        avg = sum(done) / len(done) if done else 0.0
        return self.usd + 1.5 * avg * (in_flight + 1) < self.cap_usd * STOP_FRACTION and self.usd < self.cap_usd * STOP_FRACTION

    def _log(self, row: dict) -> None:
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")

    def summary(self) -> dict:
        pin, pout, from_env = prices()
        return {"usd_est": round(self.usd, 3), "cap_usd": self.cap_usd, "calls": self.calls, "cache_hits": self.cache_hits,
                "tokens": {"in": self.tokens_in, "out": self.tokens_out}, "price_in_per_mtok": pin, "price_out_per_mtok": pout,
                "prices_from_env": from_env, "token_source": self.token_source, "by_role": self.by_role}
