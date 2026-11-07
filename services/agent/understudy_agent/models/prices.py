"""Cost estimates from token counters at per-million prices. PRICES ARE ASSUMPTIONS, and every figure carries its label.

Prices are read from the environment so no price is baked into a result:

    UNDERSTUDY_PRICE_<PROVIDER>_<TIER>_IN   US$ per million input tokens   (provider: GEMINI, OPENAI; tier: FAST, ACCURATE)
    UNDERSTUDY_PRICE_<PROVIDER>_<TIER>_OUT  US$ per million output tokens (thinking tokens are billed as output)

When a variable is unset the fallback below applies, keyed by TIER (never by a model id) and labelled `assumed_default`. The Gemini
fallbacks are the paid-tier standard figures on the vendor's public pricing page as read on 7 Nov 2026 for the flash-lite and
flash classes configured then (the flash price is the promotional one through 31 Dec 2026); the OpenAI fast fallback is the
mini-class placeholder already used in `data/eval/agent_live_runs.json`. Change the environment when the configured models change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Price:
    in_per_m: float
    out_per_m: float
    source: str  # "env" or "assumed_default"

    def cost(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if input_tokens is None or output_tokens is None:
            return None
        return (input_tokens * self.in_per_m + output_tokens * self.out_per_m) / 1_000_000

    def as_dict(self) -> dict[str, Any]:
        return {"input_usd_per_million": self.in_per_m, "output_usd_per_million": self.out_per_m, "source": self.source}


# (input, output) US$ per million tokens; assumptions, see the module docstring.
_ASSUMED: dict[tuple[str, str], tuple[float, float]] = {
    ("gemini", "fast"): (0.30, 2.50),
    ("gemini", "accurate"): (0.75, 3.75),
    ("gemini", "live"): (0.75, 3.75),
    ("openai", "fast"): (0.75, 4.50),
    ("openai", "planner"): (5.00, 30.00),
    ("openai", "computer"): (5.00, 30.00),
}


def price_for(provider: str, tier: str) -> Price:
    p, t = provider.upper(), tier.upper()
    try:
        return Price(float(os.environ[f"UNDERSTUDY_PRICE_{p}_{t}_IN"]), float(os.environ[f"UNDERSTUDY_PRICE_{p}_{t}_OUT"]), "env")
    except (KeyError, ValueError):
        pass
    pin, pout = _ASSUMED.get((provider.lower(), tier.lower()), (0.0, 0.0))
    return Price(pin, pout, "assumed_default")


def cost_estimate(provider: str, tier: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """US$ estimate, or None when a token count is unknown."""
    return price_for(provider, tier).cost(input_tokens, output_tokens)


def assumptions() -> dict[str, dict[str, Any]]:
    """Every price in force, for a report's `meta` block."""
    return {f"{prov}.{tier}": price_for(prov, tier).as_dict() for prov, tier in sorted(_ASSUMED)}
