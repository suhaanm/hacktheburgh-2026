"""ROL-4: two roles give visibly different memory files, driven by the pack; answers are validated."""
from __future__ import annotations

import pytest

from understudy_engine.memory import MemoryStore, OnboardingError, load_pack, onboard, questions_payload
from understudy_engine.memory.onboarding import checklist_layers


def _new(tmp_path, name):
    return MemoryStore(tmp_path / name)


def test_two_roles_produce_visibly_different_memory_files(tmp_path):
    a = onboard(_new(tmp_path, "a"), "benefits-processor", {"tone": "short"})
    b = onboard(_new(tmp_path, "b"), "data-analyst", {"tone": "detailed"})
    assert a["role"] == "benefits-processor" and b["role"] == "data-analyst"
    ma, mb = a["memory_markdown"], b["memory_markdown"]
    assert "role: benefits-processor" in ma and "role: data-analyst" in mb
    assert ma != mb
    # differences in every seeded section, not just the front matter
    docs = {}
    for k, md in (("a", ma), ("b", mb)):
        from understudy_engine.memory import parse
        d = parse(md)
        docs[k] = {n: [l.text for l in d.section(n).lines()] for n in ("Preferences", "Procedure", "Skill state", "Never")}
    for section in ("Preferences", "Procedure", "Skill state", "Never"):
        assert docs["a"][section] != docs["b"][section], section
    assert a["tone"]["length"] == "short" and b["tone"]["length"] == "detailed"
    assert a["risk_classes"]["irreversible"] != b["risk_classes"]["irreversible"]
    assert a["revision"] == 1 and b["revision"] == 1


def test_questions_come_from_the_pack_and_differ_per_role():
    qa, qb = questions_payload("benefits-processor"), questions_payload("data-analyst")
    assert [q["id"] for q in qa["questions"]] == ["tools", "risky", "tone", "pace", "hours"] == [q["id"] for q in qb["questions"]]
    assert qa["pack"]["name"] != qb["pack"]["name"]
    assert qa["questions"][0]["options"] != qb["questions"][0]["options"]
    assert qa["pack"]["extra_cogs"] != qb["pack"]["extra_cogs"]
    assert qa["questions"][4]["kind"] == "hours" and "default_hours" in qa["questions"][4]


def test_answers_are_reflected_in_the_file(tmp_path):
    s = _new(tmp_path, "x")
    pack = load_pack("benefits-processor")
    first_tool = pack.question("tools")["options"][0]["value"]
    out = onboard(s, "benefits-processor", {"tools": [first_tool], "pace": "quick",
                                            "hours": {"start": "08:00", "end": "16:00", "days": ["mon", "tue", "wed"]}})
    md = out["memory_markdown"]
    assert "Help fades quickly." in md and "08:00 to 16:00, mon to wed" in md
    assert out["pace"] == "quick"
    st = s.load_state()["profile"]
    assert st["hours"]["start"] == "08:00" and st["role"] == "benefits-processor"
    # the expert checklist and the skills come from the pack
    assert "Checklist:" in md and "Never skipped:" in md
    assert "last seen never" in md


def test_bad_answers_and_unknown_roles_are_rejected_without_writing(tmp_path):
    s = _new(tmp_path, "y")
    with pytest.raises(OnboardingError):
        onboard(s, "astronaut", {})
    with pytest.raises(OnboardingError):
        onboard(s, "benefits-processor", {"tone": "poetic"})
    with pytest.raises(OnboardingError):
        onboard(s, "benefits-processor", {"hours": {"start": "25:00", "end": "17:00", "days": ["mon"]}})
    with pytest.raises(OnboardingError):
        onboard(s, "benefits-processor", {"risky": ["not_an_option"]})
    assert not s.path.exists()


def test_reonboarding_same_role_keeps_progress_and_other_roles_reset(tmp_path):
    s = _new(tmp_path, "z")
    onboard(s, "benefits-processor", {})
    skill = s.read().section("Skill state").lines()[0]
    s.update_line(skill.id, actor="worker", text=skill.text.split(":")[0] + ": L3, streak 2, last seen 2026-11-07")
    s.add_line("Routines", "calc-entry-3x | rung A1", actor="worker")
    out = onboard(s, "benefits-processor", {"tone": "detailed"})
    d = s.read()
    assert any("L3" in l.text for l in d.section("Skill state").lines())     # worker progress survives
    assert [l.text for l in d.section("Routines").lines()] == ["calc-entry-3x | rung A1"]
    assert out["revision"] > 2
    onboard(s, "data-analyst", {})                                           # another role starts clean
    d = s.read()
    assert d.role == "data-analyst" and d.section("Routines").lines() == []
    assert all("L1" in l.text for l in d.section("Skill state").lines())


def test_checklist_layers_group_independent_checks():
    checks = [
        {"id": "a", "after": []}, {"id": "b", "after": ["a"]}, {"id": "c", "after": ["a"]}, {"id": "d", "after": ["b", "c"]},
    ]
    assert [[c["id"] for c in layer] for layer in checklist_layers(checks)] == [["a"], ["b", "c"], ["d"]]
    # cyclic pack data must not loop forever
    assert checklist_layers([{"id": "x", "after": ["y"]}, {"id": "y", "after": ["x"]}])
