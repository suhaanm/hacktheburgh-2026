"""The pre-registered design of the role studies: who is run, in which order, with which sequence, cases and persona. Pure and deterministic (a fixed seed).

Per role: 3 skills, a participant does TWO of them (a pair), each as a BLOCK of three cases of that skill:

    pre-test (unassisted)  ->  practice (coached or not)  ->  post-test (unassisted, a held-out variant of the pre-test's task)

Pairs cycle (s0,s1), (s1,s2), (s2,s0). For each pair (X, Y) there are 4 sequences (which skill is coached x which comes first):
    X coached then Y uncoached | Y coached then X uncoached | X uncoached then Y coached | Y uncoached then X coached     -> 12 sequences per role.
Each skill has two tasks (T1, T2) and two variants (1, 2). Pre-test and post-test are the SAME task, variants 1 and 2 (matched); the practice case is the OTHER task.
Two bits per participant balance which task is the practice task and which variant is the pre-test (``cell_bits``).

Run order: three UNITS (one per pair); each unit = 4 coached participants (the 4 sequences of the pair) then 4 A/A participants (the same 4 sequences, same personas
and cases, coach silent in every block). A budget stop leaves complete units, which are balanced within each pair. Participants 1-8 = unit 1, 9-16 = unit 2, 17-24 = unit 3.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .roles import SLUG, cfg, role_tasks, skill_pack_id, steps_off

SEED = 20261107
N_UNITS = 3
CARE = ("low", "medium", "high")
READS = ("low", "high")
VERBOSE = ("terse", "normal", "wordy")
PHASES = ("pre", "practice", "post")


@dataclass(frozen=True)
class Persona:
    carefulness: str
    reads_prompts: str
    verbosity: str
    strength: str = "default"       # default | novice (the weaker "novice" prompt of the sensitivity check; not funded, not run)

    def code(self) -> str:
        return f"care={self.carefulness};reads={self.reads_prompts};verb={self.verbosity};prompt={self.strength}"


@dataclass
class Slot:
    """One case a participant works: block, phase, skill, task, variant, and the study mode the engine is put in."""
    block: int
    phase: str                    # pre | practice | post
    skill: str                    # skill key
    skill_id: str                 # pack skill id
    task: str
    variant: int
    mode: str                     # train | off | post_test
    coach_on: bool
    steps_off: list[str] = field(default_factory=list)


@dataclass
class BlockPlan:
    block: int
    skill: str
    skill_id: str
    nominal_condition: str        # coached | uncoached (what the sequence says)
    actual_condition: str         # what happened: A/A participants are uncoached in both blocks
    pre: tuple[str, int]
    practice: tuple[str, int]
    post: tuple[str, int]
    coach_on: bool


@dataclass
class ParticipantSpec:
    pid: str
    index: int                    # position in the run order, 1-based
    role: str
    arm: str                      # coached | aa | pilot
    sequence: str                 # R01..R12
    pair: tuple[str, str]
    unit: int                     # 1..3
    bits: tuple[int, int]         # (task swap, variant swap)
    persona: Persona
    blocks: list[BlockPlan] = field(default_factory=list)
    worker: str = ""
    tier: str = ""

    @property
    def person(self) -> str:
        return self.pid

    def slots(self) -> list[Slot]:
        out: list[Slot] = []
        for b in self.blocks:
            for phase, (task, variant) in (("pre", b.pre), ("practice", b.practice), ("post", b.post)):
                mode = ("train" if b.coach_on else "off") if phase == "practice" else "post_test"
                out.append(Slot(block=b.block, phase=phase, skill=b.skill, skill_id=b.skill_id, task=task, variant=variant, mode=mode,
                                coach_on=(phase == "practice" and b.coach_on), steps_off=steps_off(self.role, task)))
        return out


def sequences(role: str) -> list[tuple[str, tuple[str, str], list[tuple[str, str]]]]:
    """[(sequence id, pair, [(skill, nominal condition) for block 1, block 2])] for the 12 sequences of a role."""
    s = cfg(role).skills
    pairs = [(s[0], s[1]), (s[1], s[2]), (s[2], s[0])]
    out = []
    for pi, (x, y) in enumerate(pairs):
        for k, blocks in enumerate([[(x, "coached"), (y, "uncoached")], [(y, "coached"), (x, "uncoached")], [(x, "uncoached"), (y, "coached")], [(y, "uncoached"), (x, "coached")]]):
            out.append((f"R{pi * 4 + k + 1:02d}", (x, y), blocks))
    return out


def cell_bits(seq_idx: int, rnd: int = 0) -> tuple[int, int]:
    """(task swap, variant swap), spread over the 12 sequences and flipped in a second round."""
    return ((seq_idx + rnd) % 2, (seq_idx // 2 + rnd) % 2)


def block_cases(role: str, skill: str, bits: tuple[int, int]) -> tuple[tuple[str, int], tuple[str, int], tuple[str, int]]:
    """(pre, practice, post) = ((task, variant), ...). Pre and post: the same task, variants matched; practice: the other task."""
    t1, t2 = role_tasks(role, skill)
    tpp, tprac = (t1, t2) if bits[0] == 0 else (t2, t1)
    pre_v, post_v = (1, 2) if bits[1] == 0 else (2, 1)
    return (tpp, pre_v), (tprac, 1 if bits[0] == 0 else 2), (tpp, post_v)


def _shuffled(vals: list[str], rng: random.Random) -> list[str]:
    v = list(vals)
    rng.shuffle(v)
    return v


def persona_table(role: str, seed: int = SEED) -> dict[tuple[int, int], Persona]:
    """(round, seq_idx) -> Persona. Within each pair of the design the four sequences get carefulness low/medium/high/medium, prompt reading low/low/high/high and
    verbosity terse/normal/normal/wordy, each shuffled with the fixed seed (a different shuffle in round 1)."""
    table: dict[tuple[int, int], Persona] = {}
    for rnd in range(2):
        for pi in range(3):
            rng = random.Random(seed * 1000 + (1 if role == "programmer" else 2) * 100 + rnd * 10 + pi)
            care = _shuffled(["low", "medium", "high", "medium"], rng)
            reads = _shuffled(["low", "low", "high", "high"], rng)
            verb = _shuffled(["terse", "normal", "normal", "wordy"], rng)
            for w in range(4):
                table[(rnd, pi * 4 + w)] = Persona(care[w], reads[w], verb[w])
    return table


def run_order() -> list[tuple[str, int, int]]:
    """(arm, seq_idx, unit) in the order the participants are run: unit 1 coached x4, unit 1 A/A x4, unit 2 ..."""
    out: list[tuple[str, int, int]] = []
    for u in range(N_UNITS):
        out += [("coached", u * 4 + w, u + 1) for w in range(4)]
        out += [("aa", u * 4 + w, u + 1) for w in range(4)]
    return out


def build_participants(role: str, seed: int = SEED) -> list[ParticipantSpec]:
    seqs = sequences(role)
    personas = persona_table(role, seed)
    specs: list[ParticipantSpec] = []
    for i, (arm, si, unit) in enumerate(run_order(), start=1):
        sid, pair, blocks_def = seqs[si]
        bits = cell_bits(si)
        blocks: list[BlockPlan] = []
        for bi, (skill, nominal) in enumerate(blocks_def, start=1):
            actual = nominal if arm == "coached" else "uncoached"
            pre, prac, post = block_cases(role, skill, bits)
            blocks.append(BlockPlan(block=bi, skill=skill, skill_id=skill_pack_id(role, skill), nominal_condition=nominal, actual_condition=actual,
                                    pre=pre, practice=prac, post=post, coach_on=actual == "coached"))
        specs.append(ParticipantSpec(pid=f"p_{SLUG[role]}{i:02d}", index=i, role=role, arm=arm, sequence=sid, pair=pair, unit=unit, bits=bits,
                                     persona=personas[(0, si)], blocks=blocks))
    return specs


PILOT_SEQUENCES = (0, 4, 8)          # one per pair: R01, R05, R09


def build_pilot(role: str, seed: int = SEED) -> list[ParticipantSpec]:
    """Three feasibility-pilot participants (A/A arm only: the coach is silent in every block), one per pair. Discarded from every analysis."""
    seqs = sequences(role)
    personas = persona_table(role, seed)
    out: list[ParticipantSpec] = []
    for n, si in enumerate(PILOT_SEQUENCES, start=1):
        sid, pair, blocks_def = seqs[si]
        bits = cell_bits(si)
        blocks = []
        for bi, (skill, nominal) in enumerate(blocks_def, start=1):
            pre, prac, post = block_cases(role, skill, bits)
            blocks.append(BlockPlan(block=bi, skill=skill, skill_id=skill_pack_id(role, skill), nominal_condition=nominal, actual_condition="uncoached", pre=pre, practice=prac, post=post, coach_on=False))
        out.append(ParticipantSpec(pid=f"p_p{SLUG[role]}{n}", index=n, role=role, arm="pilot", sequence=sid, pair=pair, unit=0, bits=bits, persona=personas[(0, si)], blocks=blocks))
    return out


def assignments_for_design_check(specs: list[ParticipantSpec]) -> dict[str, dict]:
    """participant -> the design the CSV rows must match (used by the design check of the analysis)."""
    return {s.pid: {"sequence": s.sequence, "blocks": {b.block: {"skill": b.skill, "condition": b.nominal_condition, "pre": b.pre, "practice": b.practice, "post": b.post} for b in s.blocks}} for s in specs}
