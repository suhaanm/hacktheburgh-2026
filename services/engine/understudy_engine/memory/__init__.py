"""Worker-owned memory (MEM-1 to MEM-5), onboarding writer (ROL-4) and rule engine.

Public surface::

    MemoryStore(home)               one memory.md, atomic writes, worker-only writers
    RuleEngine(store, policy=...)   corrections -> precedents -> proposals -> approved, versioned rules
    onboard(store, role, answers)   pack-driven starting memory file
"""
from .doc import SECTIONS, Line, MemoryDoc, clean_text, parse, render, skill_levels
from .onboarding import OnboardingError, load_profile, onboard, questions_payload
from .packinfo import PackView, list_pack_ids, load_pack
from .rules import RUNGS, RuleEngine, RuleError, clamp_rung, decay_weight
from .shadow import ExpertPolicy, ShadowResult
from .store import WORKER_ACTORS, MemoryStore, StaleRevision, WriteRefused

__all__ = [
    "SECTIONS", "Line", "MemoryDoc", "clean_text", "parse", "render", "skill_levels",
    "OnboardingError", "load_profile", "onboard", "questions_payload",
    "PackView", "list_pack_ids", "load_pack",
    "RUNGS", "RuleEngine", "RuleError", "clamp_rung", "decay_weight",
    "ExpertPolicy", "ShadowResult",
    "WORKER_ACTORS", "MemoryStore", "StaleRevision", "WriteRefused",
]
