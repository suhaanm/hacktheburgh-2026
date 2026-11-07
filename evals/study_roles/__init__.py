"""Simulated study for the PROGRAMMER and DATA-ANALYST roles: language-model participants (NOT people) work in private sandboxes through the real
Understudy pipeline (extension, engine, coach brain). Mirrors ``evals/study_sim`` (benefits). Everything produced here is labelled LABEL and never
touches the live ``study`` section. See PLAN.md (pre-registration) and REPORT.md (after a run).
"""
from __future__ import annotations

LABEL = "simulated participants (language model), not people"
ROLES = ("programmer", "data-analyst")


def study_roles_section() -> dict:
    """The report section for engine-eval (see ``section.evaluate_study_roles``)."""
    from .section import evaluate_study_roles

    return evaluate_study_roles()


__all__ = ["LABEL", "ROLES", "study_roles_section"]
