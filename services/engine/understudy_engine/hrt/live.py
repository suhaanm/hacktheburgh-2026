"""The live ledger: where the running product writes a forecast before its outcome exists, and where it is scored from.

One hash-chained ledger per origin (``real`` for forecasts about real work, ``synthetic`` for the example data and tests), each its own file under the
worker's data directory, so a real record is never scored together with a seeded one. The engine's clock stamps ``made_at`` and ``resolved_at``: a caller
cannot send a time, so a caller cannot backdate. A subject (a person, a case) is hashed with a per-install salt before it is stored; the files hold no
text. Nothing here calls a model.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import LEDGER_FILE
from .ledger import KINDS, Ledger, LedgerError, stream_key

ORIGINS = ("real", "synthetic")


class LiveLedgers:
    def __init__(self, root: Path | str, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root)
        self.clock = clock
        self._lock = threading.Lock()
        self._ledgers: dict[str, Ledger] = {}
        self._salt: str | None = None

    # -------------------------------------------------------------------------------------------- storage
    def _path(self, origin: str) -> Path:
        return self.root / origin / LEDGER_FILE

    def salt(self) -> str:
        if self._salt is None:
            p = self.root / "salt"
            self.root.mkdir(parents=True, exist_ok=True)
            if p.exists():
                self._salt = p.read_text(encoding="utf-8").strip()
            else:
                self._salt = secrets.token_hex(16)
                p.write_text(self._salt, encoding="utf-8")
        return self._salt

    def ledger(self, origin: str) -> Ledger:
        if origin not in ORIGINS:
            raise LedgerError(f"origin must be one of {ORIGINS}")
        if origin not in self._ledgers:
            p = self._path(origin)
            self._ledgers[origin] = Ledger.load(p) if p.exists() else Ledger(path=p)
        return self._ledgers[origin]

    # -------------------------------------------------------------------------------------------- writing
    def predict(self, origin: str, *, kind: str, subject: str, horizon_s: float, forecasts: dict[str, Any], primary: str, version: str = "", unit: str | None = None) -> dict[str, Any]:
        with self._lock:
            led = self.ledger(origin)
            now = float(self.clock())
            pid = led.predict(kind=kind, stream=stream_key(subject, self.salt()), unit=(stream_key(unit, self.salt()) if unit else None), made_at=now,
                              horizon_s=horizon_s, forecasts=forecasts, primary=primary, version=version)
            return {"pid": pid, "made_at": now, "origin": origin}

    def resolve(self, origin: str, pid: int, outcome: Any) -> dict[str, Any]:
        with self._lock:
            led = self.ledger(origin)
            now = float(self.clock())
            led.resolve(pid, resolved_at=now, outcome=outcome)
            return {"pid": pid, "resolved_at": now, "origin": origin}

    # -------------------------------------------------------------------------------------------- reading
    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"origins": {}, "kinds": list(KINDS)}
        with self._lock:
            for origin in ORIGINS:
                led = self.ledger(origin)
                try:
                    verified = led.verify()
                    why = None
                except LedgerError as e:
                    verified, why = False, str(e)
                out["origins"][origin] = {**led.summary(), "verified": verified, "verify_error": why}
        return out

    def score(self, origin: str, kind: str, *, B: int = 500, seed: int = 0) -> dict[str, Any]:
        """Score the resolved predictions of ``kind`` in this origin's ledger, or refuse and say why (too few resolved, a gap, a broken chain)."""
        from . import scoring as sc

        with self._lock:
            led = self.ledger(origin)
            try:
                led.verify()
                arr = led.resolved(kind)
            except LedgerError as e:
                return {"status": "refused", "reason": str(e), "origin": origin, "kind": kind, "n_resolved": led.n_predictions(kind) - led.pending(kind), "n_pending": led.pending(kind)}
        if kind == "time_to_progress":
            return {"status": "refused", "reason": "scoring a distribution from the live route is not built; use the held-out replay's truncated CRPS", "origin": origin, "kind": kind}
        res = sc.score_binary(arr["y"], arr["forecasts"], arr["stream"], primary=arr["primary"], B=B, seed=seed, calibration_draws=min(200, B))
        return {"status": "ok", "origin": origin, "kind": kind, "n_pending": arr["n_pending"], "split": "scored from the ledger only: every forecast was written before its outcome",
                "interval_note": "intervals resample subjects (people or case blocks), B draws, paired across predictors", **res}


_instances: dict[str, LiveLedgers] = {}


def live_ledgers(root: Path | str | None = None) -> LiveLedgers:
    """The process-wide live ledgers for a data directory (``<data dir>/ledger``)."""
    from understudy_engine.store.paths import data_dir

    r = str(Path(root) if root else data_dir() / "ledger")
    if r not in _instances:
        _instances[r] = LiveLedgers(r)
    return _instances[r]
