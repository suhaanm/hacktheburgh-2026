"""Simulated study: language-model participants (NOT people) run the real Understudy pipeline in the sandbox.

Everything produced here is labelled LABEL. It never touches the ``study`` section of the report (that stays
``not_run`` until people do the live study). See PLAN.md (pre-registration) and REPORT.md (after the run).
"""
from __future__ import annotations

LABEL = "simulated participants (language model), not people"


def study_sim_section() -> dict:
    """The report section for engine-eval (see ``section.study_sim_section``). Lazy import keeps ``import evals.study_sim`` light."""
    from .section import study_sim_section as _f

    return _f()


__all__ = ["LABEL", "study_sim_section"]
