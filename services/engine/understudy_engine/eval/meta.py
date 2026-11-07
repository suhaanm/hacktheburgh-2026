"""AnalyticMeta dicts and the three honest non-results a section can be (pending, not_run, failed)."""
from __future__ import annotations

from typing import Any

META_KEYS = ("origin", "n", "n_unit", "split", "interval_level", "note", "generated_at")


def make_meta(origin: str, n: int, n_unit: str, split: str | None, note: str | None = None,
              interval_level: float = 0.95, generated_at: str | None = None) -> dict[str, Any]:
    return {"origin": origin, "n": int(n), "n_unit": n_unit, "split": split, "interval_level": interval_level,
            "note": note, "generated_at": generated_at}


def normalise_meta(meta: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a complete AnalyticMeta. Missing keys come from ``fallback``, then from safe defaults."""
    src = dict(fallback or {})
    src.update({k: v for k, v in (meta or {}).items() if k in META_KEYS and v is not None})
    return {
        "origin": src.get("origin") or "synthetic",
        "n": int(src.get("n") or 0),
        "n_unit": src.get("n_unit") or "people",
        "split": src.get("split"),
        "interval_level": src.get("interval_level") or 0.95,
        "note": src.get("note"),
        "generated_at": src.get("generated_at"),
    }


def stub(status: str, reason: str, meta: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """A section that has no numbers: ``pending`` (owner's code not landed), ``not_run`` or ``failed`` (it raised)."""
    out: dict[str, Any] = {"status": status, "reason": reason, "meta": normalise_meta(meta)}
    out.update(extra)
    return out


def pending(owner: str, detail: str | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    reason = f"{owner} not landed" + (f" ({detail})" if detail else "")
    return stub("pending", reason, meta)
