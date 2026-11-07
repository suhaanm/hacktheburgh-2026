"""The pre-registered design: who is run, in which order, with which sequence, cases and persona.

Pure and deterministic (a fixed seed). Reads ``evals/study/assignments.json`` and ``evals/cases/households_200.json``
read-only. The sequences (S1 to S4, counterbalanced) and the matched households are exactly those of the live study;
with more than one participant per sequence, half of them get the practice and post-test case of each pair swapped,
which the live plan also does between participants (ANALYSIS_PLAN section 2).
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
STUDY = EVALS / "study"
SEED = 20261107
N_COACHED = 16            # 4 per sequence
N_AA = 8                  # 2 per sequence, the coach is silent in every block
SEQUENCES = ("S1", "S2", "S3", "S4")
SKILL_ID = {"cliff": "check-the-cliff", "reconcile": "reconcile-before-noting"}

CARE = ("low", "medium", "high")
READS = ("low", "high")
VERBOSE = ("terse", "normal", "wordy")


@dataclass(frozen=True)
class Persona:
    carefulness: str
    reads_prompts: str
    verbosity: str

    def code(self) -> str:
        return f"care={self.carefulness};reads={self.reads_prompts};verb={self.verbosity}"


@dataclass
class BlockPlan:
    block: int
    skill: str                   # cliff | reconcile
    skill_id: str
    nominal_condition: str       # coached | uncoached, as in the sequence (what analyze.py sees)
    actual_condition: str        # what really happened: A/A participants are uncoached in both blocks
    practice_case: str
    post_case: str
    coach_on: bool


@dataclass
class ParticipantSpec:
    pid: str                     # p_sim01 ...
    index: int                   # position in the run order, 1-based
    arm: str                     # coached | aa
    sequence: str
    within: int                  # 0..3 within (arm, sequence)
    variant: str                 # base | swapped (practice and post case of each pair exchanged)
    persona: Persona
    blocks: list[BlockPlan] = field(default_factory=list)
    worker: str = ""            # which private world ran this participant (set at run time; not a design factor)

    @property
    def person(self) -> str:
        return self.pid


def load_assignments() -> dict:
    return json.loads((STUDY / "assignments.json").read_text())


def load_cases() -> dict[str, dict]:
    doc = json.loads((EVALS / "cases" / "households_200.json").read_text())
    return {c["household"]["id"]: c for c in doc["cases"]}


def _base_rows(assignments: dict) -> dict[str, list[dict]]:
    """sequence -> the two block rows of the live-study participant that has that sequence."""
    out: dict[str, list[dict]] = {}
    for plan in assignments["participants"].values():
        out[plan["sequence"]] = plan["blocks"]
    return out


def run_order() -> list[tuple[str, str, int]]:
    """(arm, sequence, within) in the order the participants are run. Balanced prefixes: after every 4 participants each
    sequence has been used once in the same arm, so a budget stop leaves a balanced set.
    Round 0: 4 coached, 4 A/A. Round 1: 4 coached, 4 A/A. Rounds 2 and 3: 4 coached."""
    order: list[tuple[str, str, int]] = []
    for rnd in range(4):
        order += [("coached", s, rnd) for s in SEQUENCES]
        if rnd < 2:
            order += [("aa", s, rnd) for s in SEQUENCES]
    return order


def _shuffled(vals: list[str], rng: random.Random) -> list[str]:
    v = list(vals)
    rng.shuffle(v)
    return v


def persona_table(seed: int = SEED) -> dict[tuple[str, int], Persona]:
    """(sequence, within) -> Persona for the coached arm. Each sequence cell of four has carefulness low/medium/high/medium,
    on-page prompt reading low/low/high/high and verbosity terse/normal/normal/wordy, each shuffled with the fixed seed."""
    table: dict[tuple[str, int], Persona] = {}
    for si, s in enumerate(SEQUENCES):
        rng = random.Random(seed * 1000 + si)
        care = _shuffled(["low", "medium", "high", "medium"], rng)
        reads = _shuffled(["low", "low", "high", "high"], rng)
        verb = _shuffled(["terse", "normal", "normal", "wordy"], rng)
        for w in range(4):
            table[(s, w)] = Persona(care[w], reads[w], verb[w])
    return table


def build_participants(seed: int = SEED, assignments: dict | None = None, order: list[tuple[str, str, int]] | None = None,
                       id_prefix: str = "p_sim") -> list[ParticipantSpec]:
    """The participants of a run: ``order`` is a list of (arm, sequence, within); the default is run 4's 24. Ids are ``<id_prefix><nn>``."""
    assignments = assignments or load_assignments()
    base = _base_rows(assignments)
    personas = persona_table(seed)
    specs: list[ParticipantSpec] = []
    for i, (arm, seq, within) in enumerate(order if order is not None else run_order(), start=1):
        variant = "base" if within % 2 == 0 else "swapped"
        blocks: list[BlockPlan] = []
        for row in base[seq]:
            practice, post = row["practice_case"], row["post_case"]
            if variant == "swapped":
                practice, post = post, practice
            nominal = row["condition"]
            actual = nominal if arm == "coached" else "uncoached"
            blocks.append(BlockPlan(block=int(row["block"]), skill=row["skill"], skill_id=row["skill_id"], nominal_condition=nominal,
                                    actual_condition=actual, practice_case=practice, post_case=post, coach_on=actual == "coached"))
        specs.append(ParticipantSpec(pid=f"{id_prefix}{i:02d}", index=i, arm=arm, sequence=seq, within=within, variant=variant,
                                     persona=personas[(seq, within)], blocks=blocks))
    return specs


# ---- exploratory run 5 (PLAN_RUN5.md): a stronger participant, same sites and coach, a smaller balanced design
RUN5_N_COACHED = 8        # 2 per sequence
RUN5_N_AA = 4             # 1 per sequence
PILOT_N = 3


def run5_order() -> list[tuple[str, str, int]]:
    """8 coached (two rounds over S1..S4) then 4 A/A. Every prefix of 4 or 8 is balanced over sequences; if the budget stops the run early the
    coached participants come first and the A/A control is what is lost."""
    return [("coached", s, w) for w in (0, 1) for s in SEQUENCES] + [("aa", s, 0) for s in SEQUENCES]


def pilot_order() -> list[tuple[str, str, int]]:
    """Three A/A participants (the coach silent), sequences S1 to S3. Used only to decide whether the stronger participant is off the floor."""
    return [("aa", s, 0) for s in ("S1", "S2", "S3")]


def build_run5_participants() -> list[ParticipantSpec]:
    return build_participants(order=run5_order(), id_prefix="p_ex")


def build_pilot_participants() -> list[ParticipantSpec]:
    return build_participants(order=pilot_order(), id_prefix="p_pil")


def assignments_for_design_check(specs: list[ParticipantSpec]) -> dict:
    """An in-memory dict in the shape of assignments.json, keyed by the silicon ids, so analyze.design_problems checks each
    participant against what the design says they should have done. ``assignments.json`` itself is not touched."""
    return {"participants": {
        s.pid: {"sequence": s.sequence, "blocks": [
            {"block": b.block, "skill": b.skill, "skill_id": b.skill_id, "condition": b.nominal_condition,
             "practice_case": b.practice_case, "post_case": b.post_case} for b in s.blocks]}
        for s in specs}}


def household_card(case: dict) -> str:
    """What the participant has 'on paper': the household as the live-study paper would show it (age, earnings, rent,
    savings and so on), plus the case reference. Nothing from the oracle, the archetype or the planted notes."""
    h = case["household"]
    lines = [f"Case reference: {h['case_ref']}", f"Adults in the household: {len(h['adults'])}"]
    for i, a in enumerate(h["adults"], start=1):
        who = "You (adult 1)" if i == 1 else "Partner (adult 2)"
        lines.append(f"{who}: age {a['age']}, take-home pay GBP {a['earnings_monthly']:.0f} a month")
    kids = h.get("children_ages") or []
    lines.append("Children (ages): " + (", ".join(str(k) for k in kids) if kids else "none"))
    lines.append(f"Health condition limiting work: {'yes' if h.get('limited_capability') else 'no'}")
    lines.append(f"Housing: {'rents' if h['tenure'] == 'rent' else 'owns'}")
    if h["tenure"] == "rent":
        lines.append(f"Rent: GBP {h['rent_monthly']:.0f} a month")
    lines.append(f"Bedrooms needed: {h['bedrooms']}")
    lines.append(f"Savings: GBP {h['savings']:.0f}")
    lines.append(f"Childcare: GBP {h['childcare_monthly']:.0f} a month")
    return "\n".join(lines)


def case_ref(case: dict) -> str:
    return case["household"]["case_ref"]
