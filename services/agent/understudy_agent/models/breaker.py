"""A per-provider circuit breaker: `failures` failures inside `window_s` seconds open it for `open_s` seconds.

After `open_s` it lets one probe through (half open): a success closes it, a failure opens it again for another `open_s`. The clock
is injectable so the tests never sleep. Deterministic code; no model is involved.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Literal

State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(self, *, failures: int = 3, window_s: float = 60.0, open_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.failures, self.window_s, self.open_s, self._clock = failures, window_s, open_s, clock
        self._lock = threading.Lock()
        self._fails: deque[float] = deque()
        self._opened_at: float | None = None
        self._probe_out = False
        self.opened_count = 0

    def _state_locked(self) -> State:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.open_s:
            return "half_open"
        return "open"

    @property
    def state(self) -> State:
        with self._lock:
            return self._state_locked()

    def retry_in_s(self) -> float:
        with self._lock:
            if self._opened_at is None:
                return 0.0
            return max(0.0, self.open_s - (self._clock() - self._opened_at))

    def allow(self) -> bool:
        """May a call go out now? In the half-open state exactly one probe is allowed until its result is recorded."""
        with self._lock:
            s = self._state_locked()
            if s == "closed":
                return True
            if s == "half_open" and not self._probe_out:
                self._probe_out = True
                return True
            return False

    def cancel_probe(self) -> None:
        """A permitted call was never made (for example the egress ledger refused): give the half-open probe back."""
        with self._lock:
            self._probe_out = False

    def record(self, ok: bool) -> None:
        with self._lock:
            now = self._clock()
            s = self._state_locked()
            if ok:
                if s == "half_open":
                    self._opened_at, self._probe_out = None, False
                    self._fails.clear()
                return
            if s == "half_open":
                self._opened_at, self._probe_out = now, False
                self.opened_count += 1
                return
            self._fails.append(now)
            while self._fails and now - self._fails[0] > self.window_s:
                self._fails.popleft()
            if len(self._fails) >= self.failures and self._opened_at is None:
                self._opened_at, self._probe_out = now, False
                self.opened_count += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            now = self._clock()
            recent = sum(1 for t in self._fails if now - t <= self.window_s)
            s = self._state_locked()
            retry = 0.0 if self._opened_at is None else max(0.0, self.open_s - (now - self._opened_at))
            return {"state": s, "recent_failures": recent, "retry_in_s": round(retry, 1), "opened_count": self.opened_count}
