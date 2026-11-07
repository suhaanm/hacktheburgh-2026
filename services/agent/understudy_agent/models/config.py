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
