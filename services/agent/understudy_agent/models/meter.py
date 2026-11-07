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

import contextlib
import contextvars
import json
import math
import os
import re
import threading
from collections import deque
from collections.abc import Callable, Iterator
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
    # --- REQ-8 context engineering: metadata only, never content
    image_tokens: int | None = None          # input tokens spent on the image(s), where the provider reports them (Gemini: yes; OpenAI: no)
    cached_input_tokens: int | None = None   # input tokens served from the provider's prompt cache, where reported
    cache_eligible: bool | None = None       # the stable prefix was long enough to be cacheable (None when no manifest was supplied)
    ctx_sections: dict[str, int] | None = None   # section name -> tokens, from the caller's manifest
    ctx_dropped_items: int | None = None
    ctx_prefix_hash: str | None = None       # 12 hex of the sha256 of the stable prefix (identifies a prefix, reveals nothing)
    ctx_prefix_tokens: int | None = None
    ctx_total_tokens: int | None = None
    ctx_image_frames: int | None = None      # frames the caller kept in the prompt (0, 1 or 2)
    ctx_stale: list[str] | None = None       # names of inputs the caller dropped as too old or missing

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["t"] = d["t"] or now_iso()
        # estimate versus actual: the provider's own input token count minus the caller's estimate of the whole prompt (signed)
        d["ctx_estimate_error"] = (d["input_tokens"] - d["ctx_total_tokens"]
                                   if d["input_tokens"] is not None and d["ctx_total_tokens"] is not None else None)
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


# ------------------------------------------------------------------------------------------------ the caller's context manifest
_SECTION_NAME = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,39}$")
_HASH = re.compile(r"^[0-9a-f]{8,64}$")
_current: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("understudy_call_manifest", default=None)
_suppress: contextvars.ContextVar[bool] = contextvars.ContextVar("understudy_suppress_provider_meter", default=False)
CACHE_MIN_TOKENS_DEFAULT = 1024   # ASSUMPTION: a prefix under this many tokens is not cache-eligible at either vendor (env overrides)


def clean_manifest(m: Any) -> dict[str, Any]:
    """Whitelist a caller's manifest down to metadata: section names (short ids) with integer token counts, a dropped-item count, a
    prefix hash, prefix and total token counts. Anything else (text, paths, nested objects) is dropped, never stored."""
    if not isinstance(m, dict):
        return {}
    out: dict[str, Any] = {}

    def as_int(v: Any) -> int | None:
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 10**9 else None

    secs: dict[str, int] = {}
    raw = m.get("sections")
    items = raw.items() if isinstance(raw, dict) else ((x.get("name"), x.get("tokens")) for x in raw if isinstance(x, dict)) \
        if isinstance(raw, (list, tuple)) else ()
    for name, tokens in list(items)[:40]:
        n = as_int(tokens)
        if isinstance(name, str) and _SECTION_NAME.match(name) and n is not None:
            secs[name] = secs.get(name, 0) + n
    if secs:
        out["sections"] = secs
    for key in ("dropped_items", "prefix_tokens", "total_tokens", "image_frames"):
        v = as_int(m.get(key))
        if v is not None:
            out[key] = v
    stale = m.get("stale")
    if isinstance(stale, (list, tuple)):
        names = [x for x in stale[:20] if isinstance(x, str) and _SECTION_NAME.match(x)]
        if names:
            out["stale"] = names
    h = m.get("prefix_hash")
    if isinstance(h, str) and _HASH.match(h):
        out["prefix_hash"] = h[:12]
    return out


@contextlib.contextmanager
def call_context(manifest: Any) -> Iterator[None]:
    """Attach a context manifest (metadata only; see `clean_manifest`) to every model call made inside the block:

        with call_context({"sections": [{"name": "system", "tokens": 812}], "dropped_items": 3,
                           "prefix_hash": "a1b2c3d4e5f6", "prefix_tokens": 1500, "total_tokens": 3200}):
            port.plan(messages, schema)
    """
    tok = _current.set(clean_manifest(manifest) or None)
    try:
        yield
    finally:
        _current.reset(tok)


def current_manifest() -> dict[str, Any] | None:
    return _current.get()


@contextlib.contextmanager
def suppress_provider_records() -> Iterator[None]:
    """The router records its own (richer) line for a routed call; inside this block the provider does not add a second one."""
    tok = _suppress.set(True)
    try:
        yield
    finally:
        _suppress.reset(tok)


def provider_records_suppressed() -> bool:
    return _suppress.get()


def cache_min_tokens(provider: str) -> int:
    try:
        return int(os.environ[f"UNDERSTUDY_CACHE_MIN_TOKENS_{provider.upper()}"])
    except (KeyError, ValueError):
        return CACHE_MIN_TOKENS_DEFAULT


def context_fields(provider: str) -> dict[str, Any]:
    """The `CallRecord` fields that come from the caller's manifest (empty when none was supplied)."""
    m = current_manifest()
    if not m:
        return {}
    pt = m.get("prefix_tokens")
    return {"ctx_sections": m.get("sections"), "ctx_dropped_items": m.get("dropped_items"), "ctx_prefix_hash": m.get("prefix_hash"),
            "ctx_prefix_tokens": pt, "ctx_total_tokens": m.get("total_tokens"), "ctx_image_frames": m.get("image_frames"),
            "ctx_stale": m.get("stale"),
            "cache_eligible": (pt >= cache_min_tokens(provider)) if pt is not None else None}


class Meter:
    def __init__(self, *, path: Path | None = None, keep: int = 2000, path_fn: Callable[[], Path] | None = None) -> None:
        self.path = path
        self.path_fn = path_fn
        self._lock = threading.Lock()
        self._recent: deque[dict[str, Any]] = deque(maxlen=keep)

    def record(self, rec: CallRecord) -> dict[str, Any]:
        d = rec.as_dict()
        with self._lock:
            self._recent.append(d)
            path = self.path
            if path is None and self.path_fn is not None:
                try:
                    path = self.path_fn()
                except Exception:  # noqa: BLE001 - the meter is advisory
                    path = None
            if path is not None:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    line = json.dumps({k: v for k, v in d.items() if v is not None}, ensure_ascii=True, separators=(",", ":")) + "\n"
                    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
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
                "image_tokens": sum(r.get("image_tokens") or 0 for r in rs),
                "cached_input_tokens": sum(r.get("cached_input_tokens") or 0 for r in rs),
                "cached_share_of_input": (round(sum(r.get("cached_input_tokens") or 0 for r in rs)
                                                / max(1, sum(r["input_tokens"] or 0 for r in rs)), 4)),
                "cache_eligible_calls": sum(1 for r in rs if r.get("cache_eligible")),
                "calls_with_manifest": sum(1 for r in rs if r.get("ctx_sections")),
                "dropped_items": sum(r.get("ctx_dropped_items") or 0 for r in rs),
                "mean_section_tokens": _mean_sections(rs),
                "mean_ctx_estimate_error_tokens": _mean([r["ctx_estimate_error"] for r in rs if r.get("ctx_estimate_error") is not None]),
            })
        return rows

    def total_cost_usd(self) -> float:
        return round(sum(r["cost_usd"] or 0.0 for r in self.records()), 6)


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


def _mean_sections(rs: list[dict[str, Any]]) -> dict[str, float] | None:
    acc: dict[str, list[int]] = {}
    for r in rs:
        for name, n in (r.get("ctx_sections") or {}).items():
            acc.setdefault(name, []).append(n)
    return {k: round(sum(v) / len(v), 1) for k, v in sorted(acc.items())} or None


_default: Meter | None = None
_default_lock = threading.Lock()


def default_meter() -> Meter:
    """The process-wide meter every provider call is recorded in (unless a router records it): memory plus `model_meter.jsonl` next to
    the egress ledger. The path is resolved on every write, so a changed data dir is honoured."""
    global _default
    with _default_lock:
        if _default is None:
            _default = Meter(path_fn=default_meter_path)
        return _default


def reset_default_meter() -> None:
    global _default
    with _default_lock:
        _default = None
