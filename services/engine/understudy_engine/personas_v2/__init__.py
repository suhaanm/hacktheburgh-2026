"""Realistic synthetic personas (v2): three structurally different generator families, person-level random effects,
published-range timing, capture noise, a progress label that is a separate point process. Always synthetic:
"synthetic, realism-calibrated". v1 (``understudy_engine.personas``) is untouched."""
from .cohort import V2Cohort, generate_cohort
from .families import FAMILY_ORDER
from .roles import ROLES, get_role

__all__ = ["FAMILY_ORDER", "ROLES", "V2Cohort", "generate_cohort", "get_role"]
