"""Per-layer switches for the red-team ablation (SEC-12). Production runs everything on."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

LAYERS = ("sanitize", "reader", "actions", "gates", "dataflow", "detector", "drift", "settings")
LAYER_NAMES = {
    "sanitize": "L1 instructions apart from data",
    "reader": "L2 quarantined reader",
    "actions": "L3 typed actions",
    "gates": "L4 action-class gate",
    "dataflow": "L5 data-flow rules",
    "detector": "L6 injection detector",
    "drift": "L7 goal-drift and stuck loop",
    "settings": "L8 protected settings",
}


@dataclass(frozen=True)
class SecurityConfig:
    sanitize: bool = True
    reader: bool = True
    actions: bool = True
    gates: bool = True
    dataflow: bool = True
    detector: bool = True
    drift: bool = True
    settings: bool = True
    # budgets used by layer 3
    max_steps: int = 20
    deadline_s: float = 600.0
    max_observation_age_s: float = 30.0

    @classmethod
    def all_on(cls) -> "SecurityConfig":
        return cls()

    @classmethod
    def all_off(cls) -> "SecurityConfig":
        return cls(**{name: False for name in LAYERS})

    def without(self, *names: str) -> "SecurityConfig":
        for n in names:
            if n not in LAYERS:
                raise KeyError(f"unknown layer {n!r}; layers are {LAYERS}")
        return replace(self, **{n: False for n in names})

    def enabled_layers(self) -> list[str]:
        return [n for n in LAYERS if getattr(self, n)]

    def as_dict(self) -> dict[str, bool]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name in LAYERS}
