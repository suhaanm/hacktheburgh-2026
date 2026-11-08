"""RD (7 Nov 2026): the validator's rules for the deeper role packs catch the mistakes they exist to catch, and the real packs satisfy them."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

import validate as V

PACKS = Path(__file__).resolve().parents[1]
ROLES = ["programmer", "data-analyst"]


def clone(tmp_path: Path, pack: str) -> Path:
    dst = tmp_path / pack
    shutil.copytree(PACKS / pack, dst)
    return dst


def edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def errors(dst: Path) -> list[str]:
    return V.validate_pack(dst)


@pytest.mark.parametrize("role", ROLES)
def test_the_real_role_packs_meet_the_standard_floor(role):
    pack = yaml.safe_load((PACKS / role / "pack.yaml").read_text())
    assert pack["depth"] == "standard" and V.validate_pack(PACKS / role) == []
    m = V.STANDARD_MINIMUM
    steps = yaml.safe_load((PACKS / role / "expert_steps.yaml").read_text())
    assert len(pack["cogs"]["extra"]) >= m["cogs"] and len(steps["checks"]) >= m["checks"]
    assert len(pack["onboarding"]["followups"]) >= m["followups"]
    assert "habits" in pack and "suggest_connections" in pack


def test_the_schema_allows_up_to_24_cogs_and_no_more(tmp_path):
    dst = clone(tmp_path, "programmer")
    schema = json.loads((V.SCHEMA_DIR / "pack.schema.json").read_text())
    assert schema["properties"]["cogs"]["properties"]["extra"]["maxItems"] == 24
    assert set(schema["properties"]["depth"]["enum"]) == {"deep", "standard", "thin"}
    edit(dst / "pack.yaml", lambda d: d["cogs"]["extra"].extend(f"EXTRA_COG_{i}" for i in range(3)))
    assert any("extra" in e for e in errors(dst))                 # 25 cogs: the schema refuses (the mapping would also disagree)


def test_a_standard_pack_below_the_floor_is_refused(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "routines.yaml", lambda d: d.update(templates=d["templates"][:5]))
    assert any("at least 8 routine templates" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "programmer")
    def fn(d):
        keep = d["onboarding"]["followups"][:2]
        d["onboarding"].update(followups=keep)
        ids = {q["id"] for q in keep} | {"tools", "risky", "tone", "pace", "hours"}
        d["suggest_connections"] = {k: v for k, v in d["suggest_connections"].items() if k.split(":")[0] in ids}
    edit(dst2 / "pack.yaml", fn)
    assert any("at least 4 onboarding followups" in e for e in errors(dst2))
    dst3 = clone(tmp_path / "c", "programmer")
    edit(dst3 / "pack.yaml", lambda d: d.pop("suggest_connections"))
    assert any("needs suggest_connections" in e for e in errors(dst3))


def test_an_extra_cog_nothing_uses_is_refused(tmp_path):
    dst = clone(tmp_path, "programmer")
    # a cog the mapping produces but no check, skill or template mentions
    def fn(d):
        d["curriculum"] = d["curriculum"]
    mapping = yaml.safe_load((dst / "mapping.yaml").read_text())
    mapping["extra_cogs"].append("IDLE_ADMIN")
    mapping["zones"].append("admin_panel")
    mapping["rules"].insert(2, {"match": {"type": "click", "zone": "admin_panel"}, "cog": "IDLE_ADMIN"})
    mapping["capture_sites"][0]["elements"].append({"zone": "admin_panel", "selector": "#admin"})
    (dst / "mapping.yaml").write_text(yaml.safe_dump(mapping, sort_keys=False))
    edit(dst / "pack.yaml", lambda d: d["cogs"]["extra"].append("IDLE_ADMIN"))
    assert any("IDLE_ADMIN is not used by any expert check, curriculum skill or routine template" in e for e in errors(dst))


# ------------------------------------------------------------------------------------------------ expert checks: families and gates
def test_a_family_check_must_be_optional(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "add_logging").update(required=True))
    assert any("add_logging has a family so it must be optional" in e for e in errors(dst))


def test_a_family_check_must_start_with_a_cog_no_frozen_check_uses(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "add_logging").update(cogs=["RUN_TESTS", "ADD_LOGGING"]))
    assert any("add_logging has a family so its first cog RUN_TESTS" in e for e in errors(dst))


def test_a_frozen_check_may_not_wait_for_a_family_check(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "report_answer")["after"].append("trace_source"))
    assert any("report_answer has no family but waits for family check" in e for e in errors(dst))


def test_a_critical_gate_needs_a_check_to_gate(tmp_path):
    dst = clone(tmp_path, "programmer")
    # the gate bisect_change makes reproduce_locally critical; take it away and the critical mark has nothing to do
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "bisect_change").update(after=[]))
    assert any("reproduce_locally is critical but not required, and no check lists it" in e for e in errors(dst))


def test_a_critical_check_that_is_not_required_is_still_refused_when_nothing_follows_it(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "peer_check").update(critical=True))
    assert any("peer_check is critical but not required" in e for e in errors(dst))


def test_a_coach_target_must_be_a_zone_the_mapping_turns_into_the_checks_first_cog(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "open_pr")["coach"]["target"].update(zone="ci_checks"))
    assert any("open_pr: coach.target zone 'ci_checks' is not a zone the mapping turns into OPEN_PR" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "programmer")
    edit(dst2 / "expert_steps.yaml", lambda d: next(c for c in d["checks"] if c["id"] == "open_pr")["coach"]["target"].update(zone="no_such_zone"))
    assert any("open_pr: coach.target zone 'no_such_zone' is not in the pack's zone vocabulary" in e for e in errors(dst2))


# ------------------------------------------------------------------------------------------------ routine templates
def test_a_judgement_share_must_match_the_hit_lists_own_formula(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "routines.yaml", lambda d: next(t for t in d["templates"] if t["id"] == "review-queue-triage").update(judgement_share=0.1))
    assert any("review-queue-triage: judgement_share 0.1 but its cogs give 0.67" in e for e in errors(dst))


def test_a_template_too_short_for_the_finder_is_refused(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "routines.yaml", lambda d: next(t for t in d["templates"] if t["id"] == "reload-and-reprofile").update(
        cogs=["LOAD_DATA", "PROFILE_DATA", "INSPECT_RESULT"], steps=["a step", "another step"]))
    assert any("reload-and-reprofile: 3 steps once repeats are merged, but the routine finder never reports fewer than 4" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "data-analyst")           # repeats merge: five cogs that collapse to three are three
    edit(dst2 / "routines.yaml", lambda d: next(t for t in d["templates"] if t["id"] == "reload-and-reprofile").update(
        cogs=["LOAD_DATA", "LOAD_DATA", "PROFILE_DATA", "PROFILE_DATA", "INSPECT_RESULT"]))
    assert any("reload-and-reprofile: 3 steps once repeats are merged" in e for e in errors(dst2))


def test_an_irreversible_routine_must_not_be_automatable(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "routines.yaml", lambda d: next(t for t in d["templates"] if t["id"] == "rollback-after-alert").update(automatable=True))
    assert any("rollback-after-alert: an irreversible routine must not be automatable" in e for e in errors(dst))


def test_a_tool_must_be_a_plain_preset_id(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "routines.yaml", lambda d: next(t for t in d["templates"] if t["id"] == "reload-and-reprofile").update(tools=["https://example.com/mcp"]))
    assert errors(dst)


# ------------------------------------------------------------------------------------------------ onboarding follow-ups and connection suggestions
def test_a_followup_may_not_reuse_a_fixed_question_id_or_another_followup_id(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "pack.yaml", lambda d: d["onboarding"]["followups"][0].update(id="tone"))
    assert any("followup id 'tone' is one of the five fixed question ids" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "programmer")
    edit(dst2 / "pack.yaml", lambda d: d["onboarding"]["followups"][1].update(id=d["onboarding"]["followups"][0]["id"]))
    assert any("duplicate ids" in e for e in errors(dst2))


def test_a_single_followup_needs_exactly_one_default(tmp_path):
    dst = clone(tmp_path, "programmer")
    def fn(d):
        for o in d["onboarding"]["followups"][0]["options"]:
            o.pop("default", None)
    edit(dst / "pack.yaml", fn)
    assert any("single followup team_size must have exactly one default option" in e for e in errors(dst))


def test_a_followup_cannot_set_a_pace_the_pack_does_not_offer(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "pack.yaml", lambda d: d["onboarding"]["followups"][1]["options"][0].update(sets={"pace": "quick"}))     # the analyst pack's pace question offers gentle, steady, quick
    assert errors(dst) == []
    edit(dst / "pack.yaml", lambda d: d["onboarding"]["questions"][3]["options"].pop())                                  # drop 'quick' from the pace question
    assert any("sets pace='quick', which the pack's pace question does not offer" in e for e in errors(dst))


def test_the_budget_a_followup_sets_stays_inside_its_bounds(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "pack.yaml", lambda d: d["onboarding"]["followups"][4]["options"][0]["sets"].update(cue_daily_budget=500))
    assert errors(dst)


def test_a_risk_class_needs_patterns_and_the_other_way_round(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "pack.yaml", lambda d: d["onboarding"]["followups"][2]["options"][1].pop("patterns"))
    assert errors(dst)


def test_suggest_connections_must_name_a_real_answer(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "pack.yaml", lambda d: d["suggest_connections"].update({"on_call:sometimes": ["slack"]}))
    assert any("question on_call has no option 'sometimes'" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "programmer")
    edit(dst2 / "pack.yaml", lambda d: d["suggest_connections"].update({"nonsense:x": ["slack"]}))
    assert any("no question 'nonsense'" in e for e in errors(dst2))
    dst3 = clone(tmp_path / "c", "programmer")
    edit(dst3 / "pack.yaml", lambda d: d["suggest_connections"].update({"tools:git_host": ["Not A Preset"]}))
    assert errors(dst3)


# ------------------------------------------------------------------------------------------------ habits
def test_a_habit_names_a_known_skill_and_cog(tmp_path):
    dst = clone(tmp_path, "data-analyst")
    edit(dst / "habits.yaml", lambda d: d["habits"][0].update(skill="no-such-skill"))
    assert any("unknown skill no-such-skill" in e for e in errors(dst))
    dst2 = clone(tmp_path / "b", "data-analyst")
    edit(dst2 / "habits.yaml", lambda d: d["habits"][0].update(cogs=["NO_SUCH_COG"]))
    assert any("unknown cog NO_SUCH_COG" in e for e in errors(dst2))
    dst3 = clone(tmp_path / "c", "data-analyst")
    edit(dst3 / "habits.yaml", lambda d: d.update(role="programmer"))
    assert any("role 'programmer' must equal the pack id" in e for e in errors(dst3))


def test_a_habit_cannot_carry_a_price_or_a_prevalence(tmp_path):
    dst = clone(tmp_path, "programmer")
    edit(dst / "habits.yaml", lambda d: d["habits"][0].update(price_s={"mean": 120, "sd": 10}))
    assert errors(dst)                                           # definitions only: nothing planted, nothing measured
