"""The prospective prediction ledger: write the prediction first, score it only from the record, later.

An append-only, hash-chained record. A prediction is written with its timestamp, the model that made it and every naive baseline that
predicted the same thing at the same moment, **before** the outcome exists. An outcome is appended once, only for a prediction that exists,
and only after the prediction's horizon has passed. Scoring reads only resolved predictions and reports how many are still pending.

What the code refuses (each rule has a test in ``tests/hrt/test_ledger.py``):

* a prediction older than the newest entry (no backdating);
* an outcome for an unknown prediction, a second outcome for the same prediction, or an outcome earlier than ``made_at + horizon_s``;
* scoring on fewer resolved predictions than ``MIN_RESOLVED``, or on a stream whose sequence has a gap (a prediction that was made and
  dropped would let a model keep only the predictions that looked good);
* any edit of an earlier entry, because every entry carries the hash of the one before it (``verify``).

Nothing here stores text. A stream key is a salted hash; a forecast is a number or a short list of numbers; an outcome is a label. The
chain proves order and integrity; it does not prove that the clock was honest, which is why in use ``made_at`` comes from the engine's own
clock and in the simulations from the simulated clock.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIN_RESOLVED = 200
GENESIS = "0" * 64
KINDS = ("stuck_hazard", "time_to_progress", "error_risk")
ROUND = 6


class LedgerError(ValueError):
    """The ledger refused an entry or a scoring request; the message says which rule."""


def _canon(o: Any) -> Any:
    if isinstance(o, float):
        return round(o, ROUND)
    if isinstance(o, dict):
        return {str(k): _canon(v) for k, v in sorted(o.items())}
    if isinstance(o, (list, tuple)):
        return [_canon(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):          # numpy scalar
        return _canon(o.item())
    return o


def _digest(prev: str, body: dict[str, Any]) -> str:
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((prev + raw).encode("utf-8")).hexdigest()


def stream_key(raw: str, salt: str = "") -> str:
    """A salted hash of a person or case id: the ledger never holds the id itself."""
    return hashlib.sha256((salt + "|" + str(raw)).encode("utf-8")).hexdigest()[:16]


@dataclass
class _Pred:
    pid: int
    kind: str
    stream: str
    stream_seq: int
    made_at: float
    horizon_s: float
    forecasts: dict[str, Any]
    primary: str
    version: str
    unit: str | None = None
    outcome: Any = None
    resolved_at: float | None = None


@dataclass
class Ledger:
    """In-memory ledger, optionally mirrored to a JSONL file (one entry per line). ``Ledger.load(path)`` re-verifies the chain."""

    path: Path | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    _preds: dict[int, _Pred] = field(default_factory=dict)
    _last_hash: str = GENESIS
    _last_made_at: float = float("-inf")
    _stream_seq: dict[tuple[str, str], int] = field(default_factory=dict)
    _res_t: dict[str, list[float]] = field(default_factory=dict)        # per kind: resolved_at, sorted
    _res_y: dict[str, list[float]] = field(default_factory=dict)        # per kind: labels in the same order
    _res_csum: dict[str, list[float]] = field(default_factory=dict)     # per kind: prefix sums of labels
    _dirty: set[str] = field(default_factory=set)                       # kinds whose prefix sums must be rebuilt before use
    _fh: Any = None

    # ------------------------------------------------------------------------------------------ writing
    def _append(self, body: dict[str, Any]) -> dict[str, Any]:
        body = _canon(body)
        entry = {"seq": len(self.entries), "prev": self._last_hash, **body}
        entry["hash"] = _digest(self._last_hash, {k: v for k, v in entry.items() if k not in ("hash", "prev")})
        self.entries.append(entry)
        self._last_hash = entry["hash"]
        if self.path is not None:
            if self._fh is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = self.path.open("a", encoding="utf-8")
            self._fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            self._fh.flush()
        return entry

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def predict(self, *, kind: str, stream: str, made_at: float, horizon_s: float, forecasts: dict[str, Any], primary: str, version: str = "",
                unit: str | None = None) -> int:
        """Record a prediction. ``forecasts`` maps a predictor name (the model and each naive baseline) to its probability (a float) or its
        discrete CDF (a list of floats). Returns the prediction id."""
        if kind not in KINDS:
            raise LedgerError(f"unknown kind {kind!r}; the ledger records {KINDS}")
        if primary not in forecasts:
            raise LedgerError(f"the primary predictor {primary!r} must be among the forecasts {sorted(forecasts)}")
        if made_at < self._last_made_at:
            raise LedgerError(f"a prediction made at {made_at} is older than the newest entry ({self._last_made_at}): no backdating")
        if horizon_s <= 0:
            raise LedgerError("horizon_s must be positive")
        for name, f in forecasts.items():
            vals = [float(v) for v in f] if hasattr(f, "__len__") else [float(f)]
            if any(not (0.0 <= v <= 1.0) for v in vals):
                raise LedgerError(f"forecast {name!r} is not a probability")
        pid = len(self._preds)
        key = (kind, stream)
        seq = self._stream_seq.get(key, 0)
        self._stream_seq[key] = seq + 1
        fc = {k: (list(map(float, v)) if hasattr(v, "__len__") and not isinstance(v, str) else float(v)) for k, v in forecasts.items()}
        self._append({"type": "prediction", "pid": pid, "kind": kind, "stream": stream, "stream_seq": seq, "made_at": float(made_at),
                      "horizon_s": float(horizon_s), "forecasts": fc, "primary": primary, "version": version, "unit": unit})
        self._preds[pid] = _Pred(pid, kind, stream, seq, float(made_at), float(horizon_s), fc, primary, version, unit)
        self._last_made_at = float(made_at)
        return pid

    def resolve(self, pid: int, *, resolved_at: float, outcome: Any) -> None:
        """Record the outcome of a prediction: a label (0 or 1) for a probability, ``{"event_step": int | None, "steps_obs": int}`` for a CDF."""
        p = self._preds.get(pid)
        if p is None:
            raise LedgerError(f"no prediction {pid} in the ledger")
        if p.resolved_at is not None:
            raise LedgerError(f"prediction {pid} already has an outcome: an outcome is written once")
        if p.kind == "time_to_progress":
            if not isinstance(outcome, dict) or "steps_obs" not in outcome:
                raise LedgerError("a time_to_progress outcome is {'event_step': int | None, 'steps_obs': int}")
            # a CDF is scored over the steps that were observed: the outcome may not be written before the end of the observed span
            span = int(outcome["steps_obs"]) * p.horizon_s / len(p.forecasts[p.primary])
            if resolved_at < p.made_at + span - 1e-9:
                raise LedgerError(f"prediction {pid}: an outcome at {resolved_at} comes before the observed span ends ({p.made_at + span})")
        else:
            if resolved_at < p.made_at + p.horizon_s - 1e-9:
                raise LedgerError(f"prediction {pid}: an outcome at {resolved_at} comes before its horizon ends ({p.made_at + p.horizon_s})")
            if outcome not in (0, 1, 0.0, 1.0, True, False):
                raise LedgerError("a probability's outcome is 0 or 1")
        self._append({"type": "outcome", "pid": pid, "resolved_at": float(resolved_at), "outcome": outcome if isinstance(outcome, dict) else int(outcome)})
        p.outcome, p.resolved_at = outcome, float(resolved_at)
        if p.kind != "time_to_progress":
            ts, ys, cs = self._res_t.setdefault(p.kind, []), self._res_y.setdefault(p.kind, []), self._res_csum.setdefault(p.kind, [])
            i = bisect.bisect_right(ts, float(resolved_at))
            ts.insert(i, float(resolved_at))
            ys.insert(i, float(outcome))
            if i == len(ts) - 1 and len(cs) == len(ts) - 1:             # the usual case: outcomes arrive in order, so the prefix sum grows
                cs.append((cs[-1] if cs else 0.0) + float(outcome))
            else:
                self._dirty.add(p.kind)

    # ------------------------------------------------------------------------------------------ reading
    def resolved_before(self, kind: str, t: float) -> tuple[int, float]:
        """(count, number of ones) over the outcomes of ``kind`` with ``resolved_at <= t``. What an online baseline may use at time ``t``."""
        ts = self._res_t.get(kind, [])
        if kind in self._dirty:
            self._res_csum[kind] = _prefix(self._res_y[kind])
            self._dirty.discard(kind)
        i = bisect.bisect_right(ts, t)
        return i, (self._res_csum[kind][i - 1] if i else 0.0)

    def pending(self, kind: str | None = None) -> int:
        return sum(1 for p in self._preds.values() if p.resolved_at is None and (kind is None or p.kind == kind))

    def n_predictions(self, kind: str | None = None) -> int:
        return sum(1 for p in self._preds.values() if kind is None or p.kind == kind)

    def gaps(self, kind: str) -> list[str]:
        """Streams whose recorded ``stream_seq`` is not 0..n-1 in order: a prediction went missing."""
        seen: dict[str, list[int]] = {}
        for e in self.entries:
            if e["type"] == "prediction" and e["kind"] == kind:
                seen.setdefault(e["stream"], []).append(e["stream_seq"])
        return sorted(s for s, v in seen.items() if v != list(range(len(v))))

    def resolved(self, kind: str) -> dict[str, Any]:
        """Arrays of the resolved predictions of ``kind`` in the order they were made: ``stream``, ``made_at``, ``y`` (or ``event_step`` and
        ``steps_obs``), and ``forecasts`` (name -> array). Refuses below ``MIN_RESOLVED`` and when a stream has a gap."""
        import numpy as np

        rows = [p for p in self._preds.values() if p.kind == kind and p.resolved_at is not None]
        if len(rows) < MIN_RESOLVED:
            raise LedgerError(f"only {len(rows)} resolved {kind} predictions ({self.pending(kind)} pending); scoring needs {MIN_RESOLVED}")
        bad = self.gaps(kind)
        if bad:
            raise LedgerError(f"{len(bad)} stream(s) have a gap in their prediction sequence; nothing is scored from a record with missing predictions")
        rows.sort(key=lambda p: p.pid)
        names = sorted(rows[0].forecasts)
        out: dict[str, Any] = {"stream": np.array([p.stream for p in rows], dtype=object), "unit": np.array([p.unit or p.stream for p in rows], dtype=object),
                               "made_at": np.array([p.made_at for p in rows]),
                               "resolved_at": np.array([p.resolved_at for p in rows]), "n_pending": self.pending(kind), "names": names,
                               "primary": rows[0].primary, "version": rows[0].version}
        out["forecasts"] = {n: np.array([p.forecasts[n] for p in rows], dtype=float) for n in names}
        if kind == "time_to_progress":
            out["event_step"] = np.array([(-1 if p.outcome["event_step"] is None else p.outcome["event_step"]) for p in rows], dtype=int)
            out["steps_obs"] = np.array([p.outcome["steps_obs"] for p in rows], dtype=int)
        else:
            out["y"] = np.array([float(p.outcome) for p in rows])
        return out

    # ------------------------------------------------------------------------------------------ integrity
    def verify(self) -> bool:
        """Recompute the chain. Raises ``LedgerError`` naming the first entry that does not match; True when the chain is intact."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.get("seq") != i or e.get("prev") != prev:
                raise LedgerError(f"entry {i}: the chain is broken (an entry was removed, reordered or inserted)")
            if _digest(prev, {k: v for k, v in e.items() if k not in ("hash", "prev")}) != e.get("hash"):
                raise LedgerError(f"entry {i}: its content does not match its hash (it was edited)")
            prev = e["hash"]
        return True

    def head(self) -> str:
        return self._last_hash

    @classmethod
    def load(cls, path: Path | str) -> "Ledger":
        """Read a JSONL ledger, rebuild its state and verify the chain."""
        p = Path(path)
        led = cls(path=None)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    led.entries.append(json.loads(line))
        led.verify()
        for e in led.entries:
            if e["type"] == "prediction":
                pr = _Pred(e["pid"], e["kind"], e["stream"], e["stream_seq"], e["made_at"], e["horizon_s"], e["forecasts"], e["primary"], e.get("version", ""), e.get("unit"))
                led._preds[pr.pid] = pr
                led._stream_seq[(pr.kind, pr.stream)] = pr.stream_seq + 1
                led._last_made_at = max(led._last_made_at, pr.made_at)
            else:
                pr = led._preds[e["pid"]]
                pr.outcome, pr.resolved_at = e["outcome"], e["resolved_at"]
                if pr.kind != "time_to_progress":
                    ts, ys = led._res_t.setdefault(pr.kind, []), led._res_y.setdefault(pr.kind, [])
                    i = bisect.bisect_right(ts, pr.resolved_at)
                    ts.insert(i, pr.resolved_at)
                    ys.insert(i, float(pr.outcome))
        for k in led._res_y:
            led._res_csum[k] = _prefix(led._res_y[k])
        led._last_hash = led.entries[-1]["hash"] if led.entries else GENESIS
        led.path = p
        return led

    def summary(self) -> dict[str, Any]:
        """Counts per kind and the head hash: safe to show anywhere (no ids, no text)."""
        out: dict[str, Any] = {"entries": len(self.entries), "head": self._last_hash[:16], "kinds": {}}
        for k in KINDS:
            n = self.n_predictions(k)
            if n:
                out["kinds"][k] = {"predictions": n, "resolved": n - self.pending(k), "pending": self.pending(k)}
        return out


def _prefix(ys: list[float]) -> list[float]:
    out, s = [], 0.0
    for v in ys:
        s += v
        out.append(s)
    return out
