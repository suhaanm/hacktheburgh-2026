from __future__ import annotations

import pytest

from understudy_engine.coach import StepPolicy, short_label, target_for
from understudy_engine.core import Cog
from understudy_engine.packs import load_pack


@pytest.fixture(scope="module")
def pack():
    return load_pack("benefits-processor")


@pytest.fixture(scope="module")
def policy(pack):
    return StepPolicy.from_pack(pack)


def seq(*ids, d=10.0):
    return [Cog(i * d, (i + 1) * d, c) for i, c in enumerate(ids)]


CALC = ("OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT")
A = ("READ",) + CALC + ("CHECK_CLIFF",) + CALC + ("CHECK_CLIFF",) + CALC + ("CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE")
B = ("READ",) + CALC + CALC + CALC + ("CHECK_CLIFF",) * 3 + ("RECONCILE", "COPY_TO_NOTE")


def test_policy_loads_from_the_pack(policy):
    assert policy.task == "entitlement-check" and policy.coverage == "full"
    assert len(policy.steps) == 10 and policy.steps["cliff_a"].critical and policy.steps["cliff_a"].after == ("calc_a",)
    assert policy.steps["reconcile"].critical and not policy.steps["calc_a"].critical
    assert policy.pattern_mates("cliff_b") == ["cliff_a", "cliff_b", "cliff_c"]
    assert policy.pattern_mates("reconcile") == ["reconcile"]


@pytest.mark.parametrize("variant", [A, B], ids=["cliff_after_each", "cliff_batched"])
def test_both_expert_orderings_are_clean(policy, variant):
    prog = policy.track(seq(*variant))
    assert not prog.violations and not prog.unresolved()
    assert {"read_case", "calc_a", "calc_b", "calc_c", "cliff_a", "cliff_b", "cliff_c", "reconcile", "write_note"} <= prog.done
    assert set(policy.episode_outcomes(prog).values()) == {"clean"}


def test_calculators_in_any_order_and_k_th_occurrence_fills_the_k_th_step(policy):
    prog = policy.track(seq(*A), ["x", "calc1", "x", "x", "x", "calc2", "x", "x", "x", "x", "calc3", "x", "x", "x", "x", "x", "x"][:len(A)])
    # sites ride on the occurrence of the OPEN_CALCULATOR cog
    sites = {sid: prog.occurrences[sid].site for sid in ("calc_a", "calc_b", "calc_c")}
    assert sites["calc_a"] == "calc1" and sites["calc_b"] == "calc2"


def test_skipped_cliff_is_a_violation_at_reconcile(policy):
    cogs = ("READ",) + CALC + ("CHECK_CLIFF",) + CALC + CALC + ("CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE")     # only 2 cliff probes
    prog = policy.track(seq(*cogs))
    assert [v.step for v in prog.violations] == ["reconcile"] and prog.violations[0].missing == ("cliff_c",)
    assert prog.unresolved()[0].missing == ("cliff_c",)
    out = policy.episode_outcomes(prog)
    assert out["cliff_c"] == "error" and out["cliff_a"] == "clean" and out["reconcile"] == "clean"


def test_late_check_resolves_the_violation_but_still_counts_as_an_error(policy):
    cogs = ("READ",) + CALC + CALC + CALC + ("RECONCILE", "REVERT", "ENTER_HOUSEHOLD", "CHECK_CLIFF", "CHECK_CLIFF", "CHECK_CLIFF", "READ_RESULT", "COPY_TO_NOTE")
    prog = policy.track(seq(*cogs))
    assert prog.violations and not prog.unresolved()                       # done late: nothing missing any more
    out = policy.episode_outcomes(prog)
    assert out["cliff_a"] == out["cliff_b"] == out["cliff_c"] == "error"   # but it was late, and the skill state hears that


def test_signature_case_copy_toward_the_note_after_one_result(policy):
    prog = policy.track(seq("READ", *CALC, "COPY_TO_NOTE"))
    v = prog.violations[-1]
    assert v.step == "write_note"
    assert {"cliff_a", "reconcile", "calc_b", "calc_c"} <= set(v.missing)             # transitive: what the note rests on
    assert policy.pick_missed(v.missing, prog) == "cliff_a"                           # the critical step that can be done right now
    assert policy.pick_missed(v.missing, prog, exclude=("cliff_a", "cliff_b", "cliff_c")) is None   # reconcile cannot be done yet: no prompt
    assert policy.pick_missed(["calc_b"], prog) is None                               # calculators are required but not critical


def test_noise_cogs_are_ignored_and_a_restarted_calculator_abandons_the_half_done_one(policy):
    noisy = ("READ", "SEARCH", "REFORMULATE", "OPEN_CALCULATOR", "IDLE", "ENTER_HOUSEHOLD", "REVERT", "READ_RESULT", "READ_RESULT", "CHECK_CLIFF")
    prog = policy.track(seq(*noisy))
    assert "calc_a" in prog.done and "cliff_a" in prog.done and not prog.violations
    restarted = policy.track(seq("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"))
    assert "calc_a" in restarted.done and "calc_b" not in restarted.done


def test_current_step_is_the_one_in_progress(policy):
    assert policy.track(seq("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD")).current == "calc_a"
    assert policy.track(seq("READ", *CALC, "CHECK_CLIFF")).current == "cliff_a"
    assert policy.next_ready(policy.track(seq("READ", *CALC))) [:1] == ["calc_b"]


def test_target_comes_from_the_packs_own_mapping(pack, policy):
    m = pack.cog_mapping()
    t = target_for(policy.steps["cliff_a"], m, site="calc1")
    assert t == {"zone": "cliff_button", "label_hint": "Check cliff edges", "role_hint": "button", "site": "calc1"}
    from .helpers import reconcile_zone

    assert target_for(policy.steps["reconcile"], m)["zone"] == reconcile_zone()
    assert target_for(policy.steps["write_note"], m)["zone"] == "case_note"
    assert target_for(policy.steps["calc_a"], m)["zone"] == "calc_site"
    assert short_label("Open Check cliff edges on calculator B") == "Check cliff edges"


def test_thin_pack_policy_also_loads():
    p = StepPolicy.from_pack(load_pack("data-analyst"))
    assert p.coverage == "full" and any(s.critical for s in p.steps.values())     # RD (7 Nov 2026): the analyst policy now covers the job (coverage full)


def test_reconcile_target_is_the_case_note_select_with_the_tab_strip_as_fallback(policy):
    from understudy_engine.cogs import load_mapping

    t = target_for(policy.steps["reconcile"], load_mapping(None), site=None)
    assert t == {"zone": "reconcile_control", "label_hint": "How do they compare", "role_hint": "select", "fallback_zones": ["results_tabs"]}
    # a mapping that does not know the control keeps the tab strip (nothing is invented)
    import yaml

    old = load_mapping({"rules": [r for r in yaml.safe_load(open(load_mapping.__globals__["DEFAULT_MAPPING_PATH"]).read())["rules"]
                                  if (r.get("match") or {}).get("zone") != "reconcile_control"]})
    assert target_for(policy.steps["reconcile"], old)["zone"] == "results_tabs" and "fallback_zones" not in target_for(policy.steps["reconcile"], old)
    # the cliff target is unchanged
    assert target_for(policy.steps["cliff_a"], load_mapping(None))["zone"] == "cliff_button"
