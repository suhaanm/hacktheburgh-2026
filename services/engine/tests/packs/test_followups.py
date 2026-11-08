"""Deeper onboarding (RD): the follow-up questions of the two role packs and what their answers set, add and suggest."""
from __future__ import annotations

import pytest

from understudy_engine.packs import load_pack
from understudy_engine.packs.followups import (
    BUDGET_BOUNDS,
    QUIET_BOUNDS,
    followup_questions,
    followups_of,
    resolve,
)

ROLES = ("programmer", "data-analyst")
FIXED = ("tools", "risky", "tone", "pace", "hours")


def test_each_role_asks_five_follow_ups_after_the_five_fixed_questions_and_the_benefits_pack_asks_none():
    for role in ROLES:
        qs = followup_questions(role)
        assert len(qs) == 5 and not {q["id"] for q in qs} & set(FIXED), role
        assert [q["id"] for q in load_pack(role).questions()] == list(FIXED)      # the fixed five are untouched
        for q in qs:
            assert q["prompt"] and q["kind"] in ("single", "multi") and len(q["options"]) >= 2
            assert all(set(o) <= {"value", "label", "default"} for o in q["options"])   # the screen shape: no sets, no patterns, no presets
    assert followup_questions("benefits-processor") == []
    assert resolve("benefits-processor").sets == {} and resolve("benefits-processor", {"anything": "x"}).unknown == ["anything"]


def test_the_asked_topics_are_the_requested_ones():
    prog = {q["id"] for q in followup_questions("programmer")}
    ana = {q["id"] for q in followup_questions("data-analyst")}
    assert prog == {"team_size", "review_habit", "on_call", "release_cadence", "interruption"}
    assert ana == {"data_sources", "team_size", "review_habit", "reporting_cadence", "interruption"}


def test_unanswered_questions_take_their_defaults_for_sets_but_suggest_nothing():
    r = resolve("programmer")
    assert r.sets["cue_daily_budget"] == 12 and r.sets["cue_quiet_required_s"] == 2.0       # Cue's own defaults: the default answer changes nothing
    assert r.sets["traits"] == {"team_scale": "small", "review_load": "normal", "on_call": "none", "release_cadence": "weekly", "interruptibility": "normal"}
    assert r.suggestions == [] and r.unknown == [] and r.risk == {"irreversible": [], "outward": []}


def test_a_quiet_answer_lowers_the_budget_and_lengthens_the_wait_and_a_busy_answer_raises_it():
    quiet = resolve("programmer", {"interruption": "rarely"})
    assert quiet.sets["cue_daily_budget"] == 6 and quiet.sets["cue_quiet_required_s"] == 4.0 and quiet.sets["traits"]["interruptibility"] == "low"
    busy = resolve("data-analyst", {"interruption": "often"})
    assert busy.sets["cue_daily_budget"] == 16 and busy.sets["cue_quiet_required_s"] == 1.5


def test_clashes_resolve_to_the_quietest_answer():
    r = resolve("programmer", {"interruption": "often", "on_call": "rota"})      # 16 from one answer, 8 from the other: the smaller wins
    assert r.sets["cue_daily_budget"] == 8 and r.sets["cue_quiet_required_s"] == 1.5
    r = resolve("programmer", {"interruption": "often", "on_call": "always"})
    assert r.sets["cue_daily_budget"] == 6


def test_on_call_adds_irreversible_risk_patterns():
    assert resolve("programmer", {"on_call": "never"}).risk["irreversible"] == []
    assert "roll back" in resolve("programmer", {"on_call": "rota"}).risk["irreversible"]


def test_suggestions_come_from_explicit_answers_in_order_without_repeats():
    r = resolve("programmer", {"tools": ["git_host", "observability", "ci_dashboard"], "on_call": "rota"})
    assert r.suggestions == ["github", "sentry", "slack"]
    r = resolve("data-analyst", {"tools": ["sql_console", "spreadsheet"], "data_sources": ["warehouse", "spreadsheets"]})
    assert r.suggestions == ["postgres", "sheets"]
    assert resolve("programmer", {"tools": "chat"}).suggestions == ["slack"]       # a single value is accepted for a multi question


def test_unknown_questions_and_options_are_listed_and_ignored():
    r = resolve("programmer", {"on_call": "sometimes", "nonsense": "x", "tools": ["git_host", "fax_machine"]})
    assert sorted(r.unknown) == ["nonsense", "on_call:sometimes", "tools:fax_machine"]
    assert r.suggestions == ["github"] and r.sets["traits"]["on_call"] == "none"      # the bad on_call answer fell back to the default


@pytest.mark.parametrize("role", ROLES)
def test_every_option_of_every_follow_up_resolves_inside_the_schema_bounds(role):
    for q in followups_of(load_pack(role)):
        for o in q["options"]:
            r = resolve(role, {q["id"]: o["value"]})
            assert r.unknown == []
            lo, hi = BUDGET_BOUNDS
            assert lo <= r.sets["cue_daily_budget"] <= hi if "cue_daily_budget" in r.sets else True
            lo, hi = QUIET_BOUNDS
            assert lo <= r.sets["cue_quiet_required_s"] <= hi if "cue_quiet_required_s" in r.sets else True
            assert all(isinstance(k, str) and isinstance(v, str) for k, v in r.sets.get("traits", {}).items())


@pytest.mark.parametrize("role", ROLES)
def test_a_quiet_answer_never_asks_for_more_prompts_than_the_default(role):
    default = resolve(role).sets
    for q in followups_of(load_pack(role)):
        for o in q["options"]:
            sets = o.get("sets") or {}
            if o["value"] in ("rarely",) and q["id"] == "interruption":
                assert sets["cue_daily_budget"] < default["cue_daily_budget"] and sets["cue_quiet_required_s"] > default["cue_quiet_required_s"]
            if q["id"] == "on_call":
                assert sets.get("cue_daily_budget", 0) <= default["cue_daily_budget"]


@pytest.mark.parametrize("role", ROLES)
def test_suggested_presets_are_plain_ids_and_nothing_is_connected(role):
    table = load_pack(role).data["suggest_connections"]
    ids = {p for presets in table.values() for p in presets}
    assert ids and all(p.islower() and p.replace("-", "").replace("_", "").isalnum() for p in ids)
    assert {"github", "slack", "postgres", "sheets"} & ids
