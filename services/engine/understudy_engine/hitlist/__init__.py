"""The repeated-work hit list (docs/DECISIONS.md D44): what the worker has done many times by hand that could be automated.

Pure compute from the routine finder's clusters, ranked by minutes saved a week with an interval. Flag: ``UNDERSTUDY_X_HITLIST=1`` or the
master ``UNDERSTUDY_X=1`` (off by default). ``top_rows`` is the pointer the insights layer reads; it never raises.
"""
from __future__ import annotations

from .service import FLAG, enabled, top_rows

__all__ = ["FLAG", "enabled", "top_rows"]
