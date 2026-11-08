"""RD (7 Nov 2026): the worker's memory file after onboarding with a deeper role pack. The Procedure section lists the pack's main task, names the other
task families on a line of their own, and "Never skipped" lists only checks that are required (an optional critical gate is not a rule for every task)."""
from __future__ import annotations

import pytest

from understudy_engine.memory import MemoryStore, load_pack, onboard, parse


def lines(md: str, section: str) -> list[str]:
    return [ln.text for ln in parse(md).section(section).lines()]


def test_the_procedure_of_each_role_is_the_main_task_with_the_families_on_their_own_line(tmp_path):
    prog = lines(onboard(MemoryStore(tmp_path / "p"), "programmer", {})["memory_markdown"], "Procedure")
    assert prog[0] == "Checklist: read_trace_first or inspect_inputs or write_failing_test, then edit_and_commit, then rerun_and_confirm or probe_edges or review_diff, then commit_fix."
    assert prog[1] == "Never skipped: read_trace_first, inspect_inputs, write_failing_test, rerun_and_confirm, probe_edges, review_diff."
    assert prog[2].startswith("Also, when the task needs them: ") and "ship-a-change" in prog[2] and "release-and-watch" in prog[2]
    ana = lines(onboard(MemoryStore(tmp_path / "a"), "data-analyst", {})["memory_markdown"], "Procedure")
    assert ana[0] == "Checklist: profile_inputs, then clean_data or run_and_inspect or reconcile_to_control or segment_breakdown, then sanity_check or report_answer."
    assert ana[1] == "Never skipped: profile_inputs, reconcile_to_control, segment_breakdown, sanity_check."
    assert ana[2].startswith("Also, when the task needs them: ") and "report-a-finding" in ana[2]


def test_the_benefits_procedure_is_unchanged(tmp_path):
    ben = lines(onboard(MemoryStore(tmp_path / "b"), "benefits-processor", {})["memory_markdown"], "Procedure")
    assert ben == ["Checklist: read_case, then calc_a or calc_b or calc_c, then cliff_a or cliff_b or cliff_c, then reconcile, then write_note, then verify_note.",
                   "Never skipped: cliff_a, cliff_b, cliff_c, reconcile."]


def test_a_family_check_is_never_listed_as_never_skipped(tmp_path):
    for role in ("programmer", "data-analyst"):
        pack = load_pack(role)
        optional_gates = {c["id"] for c in pack.expert_checks if c.get("critical") and not c.get("required", True)}
        assert optional_gates, role
        md = onboard(MemoryStore(tmp_path / role), role, {})["memory_markdown"]
        never_skipped = next(t for t in lines(md, "Procedure") if t.startswith("Never skipped"))
        assert not any(g in never_skipped for g in optional_gates)


def test_the_deeper_tool_and_risk_options_are_accepted_and_reach_the_never_section(tmp_path):
    r = onboard(MemoryStore(tmp_path / "p"), "programmer", {"tools": ["git_host", "observability", "release_console"], "risky": ["rollback_prod", "run_migration", "submit_review"]})
    irr, out = r["risk_classes"]["irreversible"], r["risk_classes"]["outward"]
    assert "roll back" in irr and "run migration" in irr and "submit review" in out
    never = lines(r["memory_markdown"], "Never")
    assert any("Roll back a release" in t for t in never) and any("Run a migration on a real database" in t for t in never)
    a = onboard(MemoryStore(tmp_path / "a"), "data-analyst", {"tools": ["sql_console", "data_catalog", "writeup_tool"], "risky": ["alter_schema", "share_outside"]})
    assert "alter table" in a["risk_classes"]["irreversible"] and "share externally" in a["risk_classes"]["outward"]


@pytest.mark.parametrize("role,n_skills", [("programmer", 18), ("data-analyst", 16)])
def test_every_curriculum_skill_starts_in_the_skill_state_section(tmp_path, role, n_skills):
    md = onboard(MemoryStore(tmp_path / role), role, {})["memory_markdown"]
    state = lines(md, "Skill state")
    assert len(state) == n_skills and all(t.endswith("L1, streak 0, last seen never") for t in state)
