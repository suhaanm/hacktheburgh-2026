"""Closed vocabularies for the evidence layer (REQ-6): habit ids, cog ids, limitation ids, question intents, display text.

Everything the language model may name, and everything the code may say about it, is written here in code. A packet holds
only ids from these sets; the provenance check recognises names through these tables; the templates and the coach menu
take their wording from them. Nothing here is read from data, so a worker's text can never become a name.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

# ------------------------------------------------------------------------------------------------ badge, source, split
Origin = Literal["synthetic", "simulated_participants", "live"]
ORIGINS = ("synthetic", "simulated_participants", "live")
HazardSource = Literal["model", "rule"]
Calibration = Literal["calibrated", "overconfident", "underconfident", "untested"]
NUnit = Literal["people", "cases", "episodes", "households", "personas"]
Split = Literal["descriptive_nearest_expert", "leave_one_person_out", "none"]
ORIGIN_PHRASE = {
    "synthetic": "synthetic data",
    "simulated_participants": "simulated participants",
    "live": "live data",
}
N_UNIT_PHRASE = {"people": "people", "cases": "cases", "episodes": "episodes", "households": "households", "personas": "personas"}

# ------------------------------------------------------------------------------------------------ habits (waterfall bars)
HabitId = Literal["pace", "pauses", "search_loops", "repeated_reads", "missed_check", "wrong_copy", "rework", "step_skips",
                  "other_extra"]
HABITS: tuple[str, ...] = ("pace", "pauses", "search_loops", "repeated_reads", "missed_check", "wrong_copy", "rework",
                           "step_skips", "other_extra")
#: the genome's waterfall label -> habit id (a drift test compares these strings with ``genome.labels``)
LABEL_TO_HABIT = {
    "Slower on shared steps": "pace",
    "Long pauses": "pauses",
    "Search loops": "search_loops",
    "Repeated reads": "repeated_reads",
    "Missed check, redone": "missed_check",
    "Wrong figure, copied again": "wrong_copy",
    "Rework": "rework",
    "Skipped steps": "step_skips",
    "Other extra steps": "other_extra",
}
HABIT_NAME = {
    "pace": "a slower pace on shared steps",
    "pauses": "long pauses",
    "search_loops": "search loops",
    "repeated_reads": "repeated reads",
    "missed_check": "a missed check",
    "wrong_copy": "copying a wrong figure",
    "rework": "rework",
    "step_skips": "skipped steps",
    "other_extra": "other extra steps",
}
#: regex fragments (lower case) by which a sentence is taken to name a habit; checked by ``provenance``
HABIT_PATTERNS = {
    "pace": r"slower pace|slower on (?:the )?shared steps|pace on (?:the )?shared steps|shared steps",
    "pauses": r"long pauses?|pauses?|paused|freez(?:e|es|ing)|frozen|idle time",
    "search_loops": r"search loops?|searching in loops?|searching again and again|repeated(?:ly)? search(?:es|ing)?",
    "repeated_reads": r"repeated reads?|re-?reading|reading (?:the|each) results? (?:again|twice)|reads? the results? again",
    "missed_check": r"missed checks?|skipped checks?|cliff checks?|checks? that was redone|check being redone",
    "wrong_copy": r"wrong figures?|copy errors?|copying (?:a|the) wrong|copied (?:a|the) wrong|figure copied again",
    "rework": r"rework|redoing|redo\b",
    "step_skips": r"skipped steps?|skipping steps?|steps? (?:you|were|was) skipp?ed",
    "other_extra": r"other extra steps?|extra steps?",
}

# ------------------------------------------------------------------------------------------------ cogs
_BASE_COGS = ("READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK")
#: the cog ids the packs declared on 7 Nov 2026 plus the six the STUDY-ROLES track adds; used when the pack files cannot be read
_FALLBACK_COGS = _BASE_COGS + (
    "ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE",                  # benefits-processor
    "LOAD_DATA", "PROFILE_DATA", "WRITE_QUERY", "RUN_QUERY", "INSPECT_RESULT", "PLOT", "EXPORT_RESULT",             # data-analyst
    "CLEAN_DATA", "RECONCILE_CONTROL", "GROUP_AGG",
    "READ_CODE", "EDIT_CODE", "RUN_TESTS", "READ_TRACE", "REVIEW_DIFF", "COMMIT", "SEARCH_DOCS",                    # programmer
    "PROBE_EDGE", "INSPECT_INPUT", "WRITE_TEST", "CODE", "TEST", "REFACTOR",
)
_COG_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")


def _packs_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "packages" / "packs"


def _derive_cog_ids() -> tuple[str, ...]:
    """The closed set of cog ids: the base cogs, the fixed fallback list, and every ``cogs.extra`` entry of
    ``packages/packs/*/pack.yaml`` at import, so a new cog in a pack never breaks validation. The guarantee is unchanged: ids come
    from code and pack files, never from a worker's text; an id that is not a plain upper-case code, or that the privacy backstop
    would refuse as a payload key (it would be blocked at send time), is dropped here."""
    ids: list[str] = list(_FALLBACK_COGS)
    try:
        import yaml

        for f in sorted(_packs_dir().glob("*/pack.yaml")):
            try:
                doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError, yaml.YAMLError):
                continue
            for cid in ((doc.get("cogs") or {}).get("extra") or []):
                if isinstance(cid, str) and cid not in ids:
                    ids.append(cid)
    except ImportError:
        pass
    from ..privacy.patterns import scan_text

    return tuple(c for c in ids if _COG_ID.match(c) and not scan_text(c))


COG_IDS: tuple[str, ...] = _derive_cog_ids()
#: a ``Literal`` built from COG_IDS at import (a Literal must be closed when the packet class is defined)
CogId = Literal[COG_IDS]  # type: ignore[valid-type]
COG_NAME = {
    "ENTER_HOUSEHOLD": "entering the household", "OPEN_CALCULATOR": "opening a calculator", "READ_RESULT": "reading a result",
    "CHECK_CLIFF": "the cliff check", "COPY_TO_NOTE": "copying to the note", "RECONCILE": "reconciling the results",
    "REVERT": "undoing and redoing", "IDLE": "idle time", "READ": "reading", "SEARCH": "searching", "REFORMULATE": "rewording a search",
    "NAVIGATE": "navigating", "ENTER": "entering data", "COPY": "copying", "PASTE": "pasting", "COMPARE": "comparing",
    "CHECK": "checking", "DECIDE": "deciding", "ASK": "asking",
}

# ------------------------------------------------------------------------------------------------ consequences
StepId = Literal["RECONCILE", "CHECK_CLIFF"]
STEP_NAME = {"RECONCILE": "the reconcile step", "CHECK_CLIFF": "the cliff check"}

# ------------------------------------------------------------------------------------------------ coach and trust
CoachAction = Literal["silent", "nudge", "annotate", "takeover_offer"]
CoachTrigger = Literal["expert_policy", "stuck", "ask"]
Level = Literal["L1", "L2", "L3", "L4"]
Rung = Literal["A0", "A1", "A2", "A3"]
RoutineStatus = Literal["proposed", "declined", "never", "shadow", "approval", "unattended"]
REASON_CODES = (
    "policy_violation", "critical_step_missed", "gate_act", "stuck_signal", "asked", "issue_repeated", "worker_asked",
    "on_track", "gate_wait_signals", "gate_cooldown", "gate_unsure", "unsure_away", "already_prompted", "level_3", "level_4",
    "no_active_task", "no_events", "no_pack", "implicit_task", "study_mode", "study_post_test", "study_off", "other",
)
ReasonCode = Literal[
    "policy_violation", "critical_step_missed", "gate_act", "stuck_signal", "asked", "issue_repeated", "worker_asked",
    "on_track", "gate_wait_signals", "gate_cooldown", "gate_unsure", "unsure_away", "already_prompted", "level_3", "level_4",
    "no_active_task", "no_events", "no_pack", "implicit_task", "study_mode", "study_post_test", "study_off", "other",
]
REASON_NAME = {
    "policy_violation": "a step off the expert's path", "critical_step_missed": "a missed critical step", "gate_act": "the gate opened",
    "stuck_signal": "a stuck signal", "asked": "you asked for help", "issue_repeated": "the same issue repeated",
    "worker_asked": "you asked for help", "on_track": "you were on track", "gate_wait_signals": "the gate was still waiting for another signal",
    "gate_cooldown": "the gate was cooling down after a prompt", "gate_unsure": "the gate was not sure enough to speak",
    "unsure_away": "you seemed to be away", "already_prompted": "a prompt had just been shown", "level_3": "your help level is low",
    "level_4": "your help level is off", "no_active_task": "there was no active task", "no_events": "there were no events yet",
    "no_pack": "there was no role pack", "implicit_task": "the task was inferred", "study_mode": "study mode was on",
    "study_post_test": "a study post-test was running", "study_off": "study mode was off", "other": "another rule",
}
ACTION_PHRASE = {"silent": "stayed silent", "nudge": "showed a nudge", "annotate": "pointed at the screen", "takeover_offer": "offered to take over"}

# routine templates in the packs (a drift test checks this list against packages/packs/*/routines.yaml)
RoutineKind = Literal["calc-entry-3x", "case-note-copy", "cliff-recheck", "queue-sweep", "weekly-report", "weekly-metric-refresh",
                      "rerun-failed-ci"]
ROUTINE_KINDS: tuple[str, ...] = ("calc-entry-3x", "case-note-copy", "cliff-recheck", "queue-sweep", "weekly-report",
                                  "weekly-metric-refresh", "rerun-failed-ci")
ROUTINE_NAME = {
    "calc-entry-3x": "entering the household into each calculator", "case-note-copy": "copying results into the case note",
    "cliff-recheck": "re-checking cliff edges", "queue-sweep": "sweeping the case queue", "weekly-report": "the weekly report",
    "weekly-metric-refresh": "refreshing the weekly metrics", "rerun-failed-ci": "re-running a failed test run",
}
STATUS_PHRASE = {"proposed": "proposed", "declined": "declined for now", "never": "turned off", "shadow": "in shadow mode",
                 "approval": "running with your approval", "unattended": "running while you are away"}

# ------------------------------------------------------------------------------------------------ blocks (freshness and source)
BlockId = Literal["genome", "hazard", "coach", "routines", "mlv2"]
BLOCK_IDS: tuple[str, ...] = ("genome", "hazard", "coach", "routines", "mlv2")
BlockStatus = Literal["ok", "absent", "stale"]
BlockSource = Literal["v1", "v2", "rule", "fixture"]
BLOCK_NAME = {"genome": "comparison with the nearest expert", "hazard": "stuck reading", "coach": "coach decision",
              "routines": "list of routine candidates", "mlv2": "improved analysis"}
#: a block older than this (seconds) is reported as stale; None = never judged stale by age (the genome has no clock of its own)
STALE_AFTER_S: dict[str, float | None] = {"genome": None, "hazard": 6 * 3600.0, "coach": 300.0, "routines": 24 * 3600.0, "mlv2": 24 * 3600.0}

# ------------------------------------------------------------------------------------------------ limitations (fixed ids)
LimitId = Literal[
    "synthetic_data", "simulated_participants", "small_n", "single_case", "association_only", "not_expert_claim",
    "hazard_rule_fallback", "hazard_not_diagnosis", "scripted_tasks", "explainer_readability", "counterfactual_model",
    "consequence_rules", "saved_time_by_skips",
    # the ML-V2 table (REQ-6)
    "synthetic_people_only", "generator_planted_structure", "n_four_personas", "shared_steps_mispriced",
    "additive_counterfactual", "interactions_not_modelled", "calibrated_on_synthetic",
    "alarm_budget_is_design_choice", "llm_participants_not_people", "timing_reconstructed",
    "heldout_same_generator", "generator_mismatch_tested", "small_n_simulated_participants", "interval_too_narrow",
    "stale_data",
]
LIMITATIONS: dict[str, str] = {
    "synthetic_data": "These figures come from synthetic data with planted patterns, so they show that the method recovers known structure, not that real people behave this way.",
    "simulated_participants": "These figures come from simulated participants, not real people.",
    "small_n": "The sample is small, so the intervals are wide.",
    "single_case": "A single case has no interval of its own; the intervals shown are for the cohort average.",
    "association_only": "Everything here is an association in recorded traces, not proof of cause.",
    "not_expert_claim": "This does not show that novices become experts; it shows where time differs from the nearest expert and how sure we are.",
    "hazard_rule_fallback": "The stuck reading came from a simple rule because the trained model was not available.",
    "hazard_not_diagnosis": "The stuck reading predicts no progress in the next minute, not that you are confused.",
    "scripted_tasks": "The tasks follow a fixed script, so part of the gain over the baselines is the script.",
    "explainer_readability": "This explanation only rewords the numbers above; a clear sentence can still rest on a wrong number, and the check proves each number traces to the data, not that it is true.",
    "counterfactual_model": "Counterfactual seconds are a model's estimate of what would change, not a measured result.",
    "consequence_rules": "Error rates come from a simplified internal rule set for the calculators, not from the law.",
    "saved_time_by_skips": "Skipped steps show as saved time in the alignment; the consequences row says what skipping can cost.",
    "synthetic_people_only": "Every person in this analysis is synthetic; no real worker is in the data.",
    "generator_planted_structure": "The synthetic data was generated with planted patterns, so the method can only show that it recovers what was planted.",
    "n_four_personas": "The stuck model was checked on only four synthetic personas, so its scores carry wide uncertainty.",
    "shared_steps_mispriced": "Time on steps that both you and the expert do can be priced unevenly between habits, so treat the split between habits as approximate.",
    "additive_counterfactual": "A counterfactual adds up the effect of one habit on its own and assumes everything else stays the same.",
    "interactions_not_modelled": "The analysis does not model how habits interact with each other.",
    "calibrated_on_synthetic": "The probabilities were calibrated on synthetic data, so they may be off on real work.",
    "alarm_budget_is_design_choice": "The number of false alarms allowed per hour is a design choice, not a measured limit of what workers will tolerate.",
    "llm_participants_not_people": "The participants in this check were language-model agents, not people.",
    "timing_reconstructed": "Some timings were reconstructed from the recorded events rather than measured directly.",
    "heldout_same_generator": "The held-out check used fresh draws from the same generator, so it cannot show that the model avoided learning the generator.",
    "generator_mismatch_tested": "The model was also tested on data from a differently built generator, and those results are labelled separately.",
    "small_n_simulated_participants": "Only a few simulated participants finished, so the intervals are wide.",
    "interval_too_narrow": "The interval for this estimate was too narrow in testing and should be read as optimistic.",
    "stale_data": "Some of the readings above are older than they should be, so they may not describe the present.",
}
LIMIT_IDS: tuple[str, ...] = tuple(LIMITATIONS)
#: ids another track may use for the same limitation; the privacy backstop refuses any payload value of 32 or more id characters
#: as secret-like, so the long ML-V2 id has a short form here
LIMIT_ALIASES = {"additive_counterfactual_assumes_rest_unchanged": "additive_counterfactual",
                 "held_out_replicates_same_generator": "heldout_same_generator"}

# ------------------------------------------------------------------------------------------------ question intents
Intent = Literal[
    "where_time_went", "why_slow", "biggest_habit", "compare_expert", "stuck_reading", "how_sure", "routine_worth",
    "trust_level", "what_to_practise", "unsupported",
]
INTENTS: tuple[str, ...] = ("where_time_went", "why_slow", "biggest_habit", "compare_expert", "stuck_reading", "how_sure",
                            "routine_worth", "trust_level", "what_to_practise", "unsupported")
INTENT_HELP = {
    "where_time_went": "where your time went on this case",
    "why_slow": "why a case took as long as it did",
    "biggest_habit": "which habit is the biggest part of the gap",
    "compare_expert": "how this case compares with the nearest expert",
    "stuck_reading": "what the stuck reading says",
    "how_sure": "how sure the numbers are",
    "routine_worth": "whether a suggested routine is worth automating",
    "trust_level": "how far a routine has earned trust",
    "what_to_practise": "what to practise next",
}

# ------------------------------------------------------------------------------------------------ coach menu ids
MenuId = Literal[
    "keep_pace_with_reference", "prepare_before_entering", "search_once_then_stop", "read_each_result_once", "run_cliff_check",
    "compare_copied_figure", "ask_before_redoing", "keep_every_step", "ask_for_next_step", "review_routine", "keep_shadow_going",
    "keep_going",
]
MENU_IDS: tuple[str, ...] = ("keep_pace_with_reference", "prepare_before_entering", "search_once_then_stop", "read_each_result_once",
                             "run_cliff_check", "compare_copied_figure", "ask_before_redoing", "keep_every_step", "ask_for_next_step",
                             "review_routine", "keep_shadow_going", "keep_going")
