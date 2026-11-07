"""`models_status()`: what the model layer would do and how it has been doing, as plain data for GET /models/status.

Pure: no network call, no key (only whether a key is present), no image. The agent server's route is a one-liner:

    @app.get("/models/status")
    def models_status_route(): return models_status()

Health is derived, never assumed: `down` when the provider's breaker is open, `degraded` when at least half of its last 10 metered
calls failed, `ok` when it has calls and fewer failures, `unknown` when it has no metered calls yet (a configured provider that
has not been called has not been shown to work; the boot check says whether its ids exist).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from . import coverage
from .boot import LAST_BOOT
from .config import (GeminiModelIds, ModelIds, gemini_flag_enabled, gemini_ids_from_env_or_none, gemini_key_present,
                     mock_enabled, model_ids_from_env_or_none)
from .errors import ConfigError
from .meter import Meter
from .prices import assumptions
from .routing import ModelRouter, RoutingConfig, peek_router


def _health(provider: str, breaker: dict[str, Any] | None, records: list[dict[str, Any]]) -> str:
    if breaker and breaker.get("state") == "open":
        return "down"
    recent = [r for r in records if r["provider"] == provider][-10:]
    if not recent:
        return "unknown"
    failed = sum(1 for r in recent if not r["ok"])
    return "degraded" if failed * 2 >= len(recent) else "ok"


def models_status(router: ModelRouter | None = None) -> dict[str, Any]:
    router = router or peek_router()
    config_error = None
    if router is not None:
        cfg, meter = router.config, router.meter
    else:
        try:
            cfg = RoutingConfig.from_env()
        except ConfigError as e:
            cfg, config_error = RoutingConfig(), str(e)[:200]
        meter = Meter()
    records = meter.records()
    breakers = {p: b.snapshot() for p, b in router.breakers.items()} if router else {}
    oa: ModelIds | None = model_ids_from_env_or_none()
    gm: GeminiModelIds | None = gemini_ids_from_env_or_none()
    resolved = {
        "openai": {"planner": oa.planner, "fast": oa.fast, "computer_use": oa.computer_use} if oa else None,
        "gemini": gm.as_dict() if gm else None,
    }

    def model_of(provider: str, tier: str) -> str | None:
        if provider == "gemini":
            return getattr(gm, tier, None) if gm else None
        return oa.fast if oa else None   # the OpenAI fallback always uses the fast model

    roles = {
        name: {
            "steps": [{"provider": s.provider, "tier": s.tier, "when": s.when, "model": model_of(s.provider, s.tier)}
                      for s in r.steps],
            "escalate": {"not_found": r.escalate_not_found, "confidence_below": r.confidence_below,
                         "schema_failure": r.escalate_schema_failure, "timeout": r.escalate_timeout},
            "call_timeout_s": r.call_timeout_s, "deadline_s": r.deadline_s,
        } for name, r in cfg.roles.items()
    }
    providers = {
        "openai": {"configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()) and oa is not None,
                   "models": resolved["openai"], "breaker": breakers.get("openai"),
                   "health": _health("openai", breakers.get("openai"), records)},
        "gemini": {"configured": gemini_key_present() and gm is not None, "enabled_by_flag": gemini_flag_enabled(),
                   "models": resolved["gemini"], "api": os.environ.get("GEMINI_API", "").strip().lower() or "interactions",
                   "breaker": breakers.get("gemini"), "health": _health("gemini", breakers.get("gemini"), records)},
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mock": mock_enabled(),
        "roles": roles,
        "providers": providers,
        "boot": {k: dict(v) for k, v in LAST_BOOT.items()},
        "last_latencies_ms": meter.last_latencies(),
        "meter": meter.summary(),
        "prices_assumed": assumptions(),
        "ledger_coverage": _ledger_coverage(),
        "config_error": config_error,
    }


def _ledger_coverage() -> dict[str, Any]:
    """Whether every provider call in this process was ledgered, from the providers' own call counters (see coverage.py)."""
    cov = coverage.snapshot()
    try:
        from understudy_engine.privacy import ledger

        summ = ledger.summary()
        rows = {"calls": summ.get("calls"), "worker_requested_calls": summ.get("worker_requested_calls"),
                "mock_calls": summ.get("mock_calls")}
    except Exception:  # noqa: BLE001 - status must never fail because the ledger is unreadable
        rows = None
    return {"all_provider_calls_ledgered": cov["all_ledgered"], "unledgered_calls": cov["unledgered_calls"],
            "providers": cov["providers"], "ledger_rows": rows, "note": cov["note"]}
