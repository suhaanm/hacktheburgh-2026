"""The design is a pure function of the seed: sequences, balance, matched cases, personas, run order, pilot."""
from __future__ import annotations

import re
from collections import Counter

from evals.study_roles import design as D
from evals.study_roles.roles import cfg


def test_twelve_sequences_each_skill_coached_equally_within_each_pair(role):
    seqs = D.sequences(role)
    assert len(seqs) == 12 and [s[0] for s in seqs] == [f"R{i:02d}" for i in range(1, 13)]
    skills = cfg(role).skills
    for pi in range(3):
        group = seqs[pi * 4:(pi + 1) * 4]
        x, y = group[0][1]
        assert {g[1] for g in group} == {(x, y)} and {x, y} <= set(skills) and x != y
        coached_first = [g[2][0] for g in group if g[2][0][1] == "coached"] + [g[2][1] for g in group if g[2][1][1] == "coached"]
        assert Counter(s for s, _ in coached_first) == {x: 2, y: 2}                       # each skill is coached in 2 of the 4 sequences of its pair
        assert sorted(g[2][0][1] for g in group) == ["coached", "coached", "uncoached", "uncoached"]    # and each order appears twice
        for g in group:
            assert sorted(c for _, c in g[2]) == ["coached", "uncoached"] and g[2][0][0] != g[2][1][0]
    pairs = Counter(tuple(sorted(s[1])) for s in seqs)
    assert len(pairs) == 3 and all(v == 4 for v in pairs.values())


def test_run_order_units_and_ids(specs, role):
    assert len(specs) == 24 and [s.index for s in specs] == list(range(1, 25))
    for s in specs:
        assert re.fullmatch(r"p_[a-z0-9]{2,16}", s.pid)
    for u in range(3):
        unit = specs[u * 8:(u + 1) * 8]
        assert [s.arm for s in unit] == ["coached"] * 4 + ["aa"] * 4 and {s.unit for s in unit} == {u + 1}
        assert [s.sequence for s in unit[:4]] == [s.sequence for s in unit[4:]] == [f"R{u * 4 + k + 1:02d}" for k in range(4)]
        assert len({s.pair for s in unit}) == 1                                          # a unit is complete within one pair: a budget stop at a unit boundary stays balanced
    assert len({s.pid for s in specs}) == 24


def test_aa_participants_repeat_the_cases_and_personas_of_their_coached_twin(specs):
    for u in range(3):
        for k in range(4):
            c, a = specs[u * 8 + k], specs[u * 8 + 4 + k]
            assert c.persona == a.persona and c.bits == a.bits
            for bc, ba in zip(c.blocks, a.blocks):
                assert (bc.skill, bc.nominal_condition, bc.pre, bc.practice, bc.post) == (ba.skill, ba.nominal_condition, ba.pre, ba.practice, ba.post)
                assert ba.actual_condition == "uncoached" and not ba.coach_on and bc.actual_condition == bc.nominal_condition


def test_pre_and_post_are_matched_variants_of_one_task_and_practice_is_the_other(specs, role):
    for s in specs:
        for b in s.blocks:
            (tp, vp), (tr, vr), (tq, vq) = b.pre, b.practice, b.post
            assert tp == tq and vp != vq and {vp, vq} == {1, 2}
            assert tr != tp and {tp, tr} == set(cfg(role).sandbox.SKILLS[b.skill]["task_ids"])
    # the two bits are spread over the 12 sequences
    bits = Counter(specs[i].bits for i in range(12))
    assert set(bits) == {(0, 0), (0, 1), (1, 0), (1, 1)} and all(v == 3 for v in bits.values())
    tasks_as_pre = Counter(b.pre[0] for s in specs[:12] for b in s.blocks)
    assert all(v >= 2 for v in tasks_as_pre.values()) and len(tasks_as_pre) == 6


def test_slots_modes_and_steps_off(specs):
    for s in specs:
        slots = s.slots()
        assert [x.phase for x in slots] == ["pre", "practice", "post"] * 2 and [x.block for x in slots] == [1, 1, 1, 2, 2, 2]
        for x in slots:
            if x.phase == "practice":
                assert x.mode == ("train" if x.coach_on else "off")
            else:
                assert x.mode == "post_test" and not x.coach_on
            assert isinstance(x.steps_off, list)
        assert sum(x.coach_on for x in slots) == (1 if s.arm == "coached" else 0)


def test_personas_balanced_within_each_pair_and_deterministic(role):
    t = D.persona_table(role)
    assert t == D.persona_table(role) and t != D.persona_table(role, seed=1)
    for rnd in range(2):
        for pi in range(3):
            ps = [t[(rnd, pi * 4 + w)] for w in range(4)]
            assert sorted(p.carefulness for p in ps) == ["high", "low", "medium", "medium"]
            assert sorted(p.reads_prompts for p in ps) == ["high", "high", "low", "low"]
            assert sorted(p.verbosity for p in ps) == ["normal", "normal", "terse", "wordy"]
    assert D.build_participants(role) == D.build_participants(role) or [s.pid for s in D.build_participants(role)] == [s.pid for s in D.build_participants(role)]


def test_pilot_is_aa_only_three_participants_one_per_pair(role):
    pilot = D.build_pilot(role)
    assert len(pilot) == 3 and {s.arm for s in pilot} == {"pilot"} and len({s.pair for s in pilot}) == 3
    assert all(not b.coach_on and b.actual_condition == "uncoached" for s in pilot for b in s.blocks)
    assert all(not x.coach_on and x.mode in ("off", "post_test") for s in pilot for x in s.slots())
    main_ids = {s.pid for s in D.build_participants(role)}
    assert not (main_ids & {s.pid for s in pilot})
