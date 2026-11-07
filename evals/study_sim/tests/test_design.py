"""The pre-registered design: counts, balance, determinism, case roles. Made-up data only."""
from __future__ import annotations

import sys
from collections import Counter

from evals.study_sim import design
from evals.study_sim.design import SEQUENCES, assignments_for_design_check, build_participants, household_card, load_cases

sys.path.insert(0, str(design.STUDY))
import analyze as A  # noqa: E402

from .conftest import made_up_rows  # noqa: E402


def test_counts_and_arms(specs):
    assert len(specs) == 24
    assert Counter(s.arm for s in specs) == {"coached": 16, "aa": 8}
    for arm, n in (("coached", 4), ("aa", 2)):
        assert Counter(s.sequence for s in specs if s.arm == arm) == {q: n for q in SEQUENCES}
    assert [s.pid for s in specs] == [f"p_sim{i:02d}" for i in range(1, 25)]


def test_run_order_prefixes_are_balanced(specs):
    for k in (4, 8, 12, 16, 20, 24):                      # a budget stop at a round boundary leaves each sequence equally used per arm
        first = specs[:k]
        for arm in ("coached", "aa"):
            c = Counter(s.sequence for s in first if s.arm == arm)
            assert max(c.values(), default=0) - min((c.get(q, 0) for q in SEQUENCES), default=0) <= 1


def test_deterministic():
    a, b = build_participants(), build_participants()
    assert [(s.pid, s.sequence, s.variant, s.persona) for s in a] == [(s.pid, s.sequence, s.variant, s.persona) for s in b]
    c = build_participants(seed=1)
    assert [s.persona for s in a] != [s.persona for s in c]


def test_blocks_follow_assignments_and_aa_is_silent(specs):
    base = design.load_assignments()["participants"]
    seq_rows = {p["sequence"]: p["blocks"] for p in base.values()}
    for s in specs:
        for b, row in zip(s.blocks, seq_rows[s.sequence]):
            assert (b.skill, b.skill_id, b.nominal_condition) == (row["skill"], row["skill_id"], row["condition"])
            pair = {row["practice_case"], row["post_case"]}
            assert {b.practice_case, b.post_case} == pair and b.practice_case != b.post_case
            if s.variant == "base":
                assert (b.practice_case, b.post_case) == (row["practice_case"], row["post_case"])
            else:
                assert (b.practice_case, b.post_case) == (row["post_case"], row["practice_case"])
            assert b.coach_on == (s.arm == "coached" and row["condition"] == "coached")
            if s.arm == "aa":
                assert b.actual_condition == "uncoached" and not b.coach_on


def test_each_coached_person_has_exactly_one_coached_block(specs):
    for s in specs:
        n = sum(b.coach_on for b in s.blocks)
        assert n == (1 if s.arm == "coached" else 0)


def test_case_roles_are_balanced_within_each_cell(specs):
    for arm in ("coached", "aa"):
        for q in SEQUENCES:
            cell = [s for s in specs if s.arm == arm and s.sequence == q]
            assert Counter(s.variant for s in cell) == ({"base": 2, "swapped": 2} if arm == "coached" else {"base": 1, "swapped": 1})


def test_persona_balance_and_matched_aa(specs):
    table = design.persona_table()
    for q in SEQUENCES:
        cell = [table[(q, w)] for w in range(4)]
        assert Counter(p.carefulness for p in cell) == {"low": 1, "medium": 2, "high": 1}
        assert Counter(p.reads_prompts for p in cell) == {"low": 2, "high": 2}
        assert Counter(p.verbosity for p in cell) == {"terse": 1, "normal": 2, "wordy": 1}
    for s in specs:
        assert s.persona == table[(s.sequence, s.within)]
    aa = {(s.sequence, s.within): s.persona for s in specs if s.arm == "aa"}
    co = {(s.sequence, s.within): s.persona for s in specs if s.arm == "coached"}
    assert all(co[k] == v for k, v in aa.items())          # the sham arm repeats the personas of the first coached participants


def test_the_design_check_passes_on_complete_rows(specs):
    rows = made_up_rows(specs, lambda s, b: 1)
    problems = A.design_problems([r for r in rows if r["arm"] == "coached"], assignments_for_design_check(specs))
    assert problems == []
    problems = A.design_problems([r for r in rows if r["arm"] == "aa"], assignments_for_design_check(specs))
    assert problems == []


def test_household_card_has_no_planted_hints():
    cases = load_cases()
    for hid in ("hh_0005", "hh_0041", "hh_0004", "hh_0028"):
        card = household_card(cases[hid])
        low = card.lower()
        assert cases[hid]["household"]["case_ref"] in card and "savings" in low
        for banned in ("archetype", "cliff", "capital", "16,000", "tariff", "oracle", "discrepancy", "notes"):
            assert banned not in low
