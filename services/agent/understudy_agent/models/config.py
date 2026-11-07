"""Model configuration read from the environment. No model id is ever hard-coded (NFR-3)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import ConfigError

ENV_PLANNER = "OPENAI_MODEL_PLANNER"
ENV_FAST = "OPENAI_MODEL_FAST"
ENV_COMPUTER = "OPENAI_MODEL_COMPUTER_USE"

# Optional per-role reasoning effort (values are the provider's own: none, low, medium, high, ...).
ENV_EFFORT = {
    "planner": "OPENAI_EFFORT_PLANNER",
    "fast": "OPENAI_EFFORT_FAST",
    "reader": "OPENAI_EFFORT_READER",
    "vision": "OPENAI_EFFORT_VISION",
    "computer": "OPENAI_EFFORT_COMPUTER_USE",
}
# Defaults are effort levels, not model names. The computer tool at its default effort took ~45 s a step in the
# 7 Nov probe; at "low" it took ~2 s.
DEFAULT_EFFORT = {"planner": "low", "fast": "none", "reader": "low", "vision": "low", "computer": "low"}


# --- Gemini (REQ-5 phase C). Ids come only from the environment, never from code. GEMINI_API_KEY is read by the
# HTTP client alone and never appears in a log, an error, a fixture or a URL.
ENV_GEMINI_KEY = "GEMINI_API_KEY"
ENV_GEMINI_FAST = "GEMINI_MODEL_FAST"          # flash-lite class: pointing and glances, first try
ENV_GEMINI_ACCURATE = "GEMINI_MODEL_ACCURATE"  # flash class: escalation, verifier fallback
ENV_GEMINI_LIVE = "GEMINI_MODEL_LIVE"          # live voice (phase D); only checked at boot, not called here
ENV_GEMINI_COMPUTER = "GEMINI_MODEL_COMPUTER_USE"  # optional: computer-use dry runs; unset = the accurate model

_TRUE = ("1", "true", "yes", "on")


def gemini_flag_enabled() -> bool:
    """`UNDERSTUDY_X_GEMINI=1` (or the master `UNDERSTUDY_X=1`). Off by default; the P0 path never depends on it."""
    e = os.environ
    return any(e.get(k, "").strip().lower() in _TRUE for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_GEMINI"))


@dataclass(frozen=True)
class GeminiModelIds:
    fast: str
    accurate: str
    live: str | None = None
    computer_use: str | None = None

    @classmethod
    def from_env(cls) -> "GeminiModelIds":
        missing = [k for k in (ENV_GEMINI_FAST, ENV_GEMINI_ACCURATE) if not os.environ.get(k, "").strip()]
        if missing:
            raise ConfigError(
                "Gemini model ids are not configured: set " + ", ".join(missing) + " in .env. "
                "Run `uv run --env-file .env python -m understudy_agent.models.boot` to list the models "
                "your key can use, then pick from that list. Model ids are never guessed."
            )
        live = os.environ.get(ENV_GEMINI_LIVE, "").strip() or None
        cu = os.environ.get(ENV_GEMINI_COMPUTER, "").strip() or None
        return cls(fast=os.environ[ENV_GEMINI_FAST].strip(), accurate=os.environ[ENV_GEMINI_ACCURATE].strip(), live=live,
                   computer_use=cu)

    def as_dict(self) -> dict[str, str]:
        d = {"fast": self.fast, "accurate": self.accurate}
        if self.live:
            d["live"] = self.live
        if self.computer_use:
            d["computer_use"] = self.computer_use
        return d

    def env_name(self, role: str) -> str:
        return {"fast": ENV_GEMINI_FAST, "accurate": ENV_GEMINI_ACCURATE, "live": ENV_GEMINI_LIVE,
                "computer_use": ENV_GEMINI_COMPUTER}[role]


def gemini_ids_from_env_or_none() -> GeminiModelIds | None:
    try:
        return GeminiModelIds.from_env()
    except ConfigError:
        return None


def gemini_key_present() -> bool:
    return bool(os.environ.get(ENV_GEMINI_KEY, "").strip())


@dataclass(frozen=True)
class ModelIds:
    planner: str
    fast: str
    computer_use: str

    @classmethod
    def from_env(cls) -> "ModelIds":
        missing = [k for k in (ENV_PLANNER, ENV_FAST, ENV_COMPUTER) if not os.environ.get(k, "").strip()]
        if missing:
            raise ConfigError(
                "Model ids are not configured: set " + ", ".join(missing) + " in .env. "
                "Run `uv run --env-file .env python -m understudy_agent.models.boot` to list the models "
                "your key can use, then pick from that list. Model ids are never guessed."
            )
        return cls(
            planner=os.environ[ENV_PLANNER].strip(),
            fast=os.environ[ENV_FAST].strip(),
            computer_use=os.environ[ENV_COMPUTER].strip(),
        )

    def as_dict(self) -> dict[str, str]:
        return {"planner": self.planner, "fast": self.fast, "computer_use": self.computer_use}


def model_ids_from_env_or_none() -> ModelIds | None:
    try:
        return ModelIds.from_env()
    except ConfigError:
        return None


def effort_for(role: str) -> str | None:
    """Reasoning effort for a role: env override, else the default. 'unset' disables the parameter."""
    v = os.environ.get(ENV_EFFORT[role], "").strip() or DEFAULT_EFFORT[role]
    return None if v.lower() == "unset" else v


def mock_enabled() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes", "on")
