"""Machine-learning layer v2 (REQ-6): better detection, comparison and analysis, plus the numbers an explainer may use.

Additive and off by default. v1 (hazard/, genome/, coach/, policy/) is untouched and stays the default; v2 is selected by an
explicit ``variant="v2"`` argument or by the environment flag ``UNDERSTUDY_X_MLV2`` (or the master ``UNDERSTUDY_X``).

Pre-registration: ``evals/mlv2/PLAN.md``. Nothing here is imported at engine start-up; importing this package is cheap.
"""
from __future__ import annotations

import os

__all__ = ["enabled", "FLAG"]

FLAG = "UNDERSTUDY_X_MLV2"
_TRUE = ("1", "true", "yes", "on")


def enabled() -> bool:
    """True when the v2 layer is switched on (per-layer flag or the master ``UNDERSTUDY_X``)."""
    return any(os.environ.get(k, "").strip().lower() in _TRUE for k in (FLAG, "UNDERSTUDY_X"))
