"""The participant's side: what the prompt shows (and never shows), parsing of actions, the scripted participant, the contamination rule, the refusals of the model-driven commands."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
from types import SimpleNamespace

import pytest

from evals.study_roles import __main__ as cli
from evals.study_roles import participant as P
from evals.study_roles.design import build_participants
from evals.study_roles.observe_roles import parse_actions, snapshot_text
from evals.study_roles.runner import contamination, digest_for_note, CaseResult
from evals.study_roles.roles import cfg

OBS = {"url": "http://127.0.0.1:7941/task/p-boundary-1/1", "text": "Wrong number of pages\nThe pager shows the wrong number.", "fields": [{"label": "Editor", "text": "function pageCount(t, s) {\n  return Math.floor(t / s);\n}"}],
       "elements": [{"ref": 0, "tag": "button", "label": "Run tests", "dom_id": "run-tests", "zone": "test_runner"}, {"ref": 1, "tag": "textarea", "label": "Editor", "type": "textarea", "value": "function", "zone": "code_editor"},
                    {"ref": 2, "tag": "select", "label": "Status", "options": [{"value": "a", "text": "A"}], "value": "a", "zone": ""}]}


def run(coro):
    """Run a coroutine in a fresh thread: safe next to the sync Playwright fixtures of the sandbox tests (they keep an event loop running in the main thread)."""
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def ctx(spec, slot, coach=None, note=None, phase_slot=None):
    return P.StepContext(spec=spec, slot=phase_slot or slot, obs=OBS, history=["1. clicked \"Run tests\""], used=3, cap=45, note_to_self=note, coach=coach, ring_found=bool(coach))


def test_prompt_shows_the_editor_text_and_hides_zones_ids_and_the_checks(specs):
    spec = specs[0]
    slot = spec.slots()[1]
    pr = P.build_prompt(ctx(spec, slot))
    assert "return Math.floor(t / s);" in pr and "Run tests" in pr and "42 actions left" in pr
    for hidden in ("data-understudy", "zone", "test_runner", "run-tests", "probe_edges", "boundary", "edge case", "coach is"):
        assert hidden not in pr
    assert "junior" in pr and f"Participant code: {spec.pid}" in pr and "on your own" not in pr


def test_post_test_shows_the_note_only_in_the_post_phase_and_the_coach_note_when_up(specs):
    spec = specs[0]
    pre, prac, post = spec.slots()[:3]
    assert "This one is on your own" in P.build_prompt(ctx(spec, pre, note="remember x")) and "remember x" not in P.build_prompt(ctx(spec, pre, note="remember x"))
    assert "remember x" in P.build_prompt(ctx(spec, post, note="remember x"))
    p = P.build_prompt(ctx(spec, prac, coach={"message": "Try the edges before you commit.", "step": "probe_edges"}))
    assert "Understudy" in p and "orange ring" in p and "Try the edges before you commit." in p
    assert "Understudy" not in P.build_prompt(ctx(spec, prac))


def test_persona_text_is_neutral_and_the_novice_strength_is_a_separate_switch(specs):
    s = specs[0]
    a = P.persona_text(s.role, s.persona)
    assert "first week" in a and "beginner" not in a
    from evals.study_roles.design import Persona
    assert "beginner" in P.persona_text(s.role, Persona("low", "low", "terse", "novice"))


def test_parse_actions_keeps_valid_kinds_and_at_most_four():
    out = parse_actions({"actions": [{"kind": "click", "ref": 3}, {"kind": "replace", "ref": 1, "find": "a", "text": "b"}, {"kind": "teleport"}, "x", {"kind": "fill", "ref": 1, "text": "z"},
                                     {"kind": "wait", "seconds": 2}, {"kind": "select", "ref": 2, "text": "A"}]})
    assert [a.kind for a in out] == ["click", "replace", "fill", "wait"] and out[1].find == "a" and out[1].text == "b"
    assert parse_actions({}) == [] and parse_actions({"actions": "no"}) == []


def test_snapshot_text_includes_the_full_text_boxes():
    t = snapshot_text(OBS)
    assert "Text box \"Editor\" (full content)" in t and "Math.floor" in t


def test_scripted_participant_follows_a_program_and_obeys_the_coach(specs):
    spec = specs[0]
    slot = spec.slots()[1]
    sp = P.ScriptedParticipant(spec, slot, [("click", "run tests"), ("fill", "editor", "x"), ("click", "nowhere"), ("select", "status", "A")], {"probe_edges": [("click", "run tests")]}, obeys=True)

    async def go():
        a1 = await sp.decide(ctx(spec, slot))
        a2 = await sp.decide(ctx(spec, slot, coach={"message": "m", "step": "probe_edges"}))
        a3 = await sp.decide(ctx(spec, slot, coach={"message": "m", "step": "probe_edges"}))
        a4 = await sp.decide(ctx(spec, slot))
        a5 = await sp.decide(ctx(spec, slot))
        return [a1, a2, a3, a4, a5]
    outs = run(go())
    assert [(o[0].kind, o[0].ref) for o in outs] == [("click", 0), ("click", 0), ("fill", 1), ("select", 2), ("finish", None)]       # the obeyed snippet came first; the missing control was skipped


def test_scripted_participant_dismisses_when_told_to(specs):
    spec = specs[0]
    slot = spec.slots()[1]
    sp = P.ScriptedParticipant(spec, slot, [("click", "run tests")], {}, dismisses=True)
    assert run(sp.decide(ctx(spec, slot, coach={"message": "m", "step": "probe_edges"})))[0].kind == "dismiss_coach"


def test_contamination_rule():
    ok = {"epoch": 3, "events": [{}, {}], "counts": {}}
    assert contamination(ok, 3, 2, 5) == ""
    assert "epoch changed" in contamination({**ok, "epoch": 4}, 3, 0, 0) and "shrank" in contamination(ok, 3, 5, 0)
    assert "forbidden" in contamination({**ok, "counts": {"forbidden": 1}}, 3, 0, 0)


def test_digest_for_note_has_the_history_and_the_end():
    res = CaseResult(phase="practice", block=1, reason="done")
    res.history = ["1. clicked \"Run tests\"", "2. filled \"Editor\""]
    d = digest_for_note(res)
    assert "clicked" in d and "ends the case" in d


def test_model_driven_commands_refuse_without_go_and_with_the_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "GO_FILE", tmp_path / "GO")
    a = SimpleNamespace(role="programmer", tier="fast")
    assert cli.cmd_pilot(a) == 2 and cli.cmd_run(SimpleNamespace(role="programmer", tier="fast", units=3, roles_left=2)) == 2
    (tmp_path / "GO").write_text("ok")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    assert cli.cmd_pilot(a) == 2


def test_run_refuses_without_a_usable_pilot_and_when_the_plan_cannot_afford_two_units(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "GO_FILE", tmp_path / "GO")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    (tmp_path / "GO").write_text("ok")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    a = SimpleNamespace(role="programmer", tier="fast", units=3, roles_left=2)
    assert cli.cmd_run(a) == 2                                               # no pilot at all
    d = tmp_path / "results" / "programmer"
    d.mkdir(parents=True)
    (d / "PILOT_fast.json").write_text(json.dumps({"usable": False, "reasons": ["floor"], "mean_cost_per_participant_usd": 0.2}))
    assert cli.cmd_run(a) == 2                                               # a pilot that failed
    (d / "PILOT_fast.json").write_text(json.dumps({"usable": True, "reasons": [], "mean_cost_per_participant_usd": 0.9}))
    assert cli.cmd_run(a) == 2                                               # usable but only one unit affordable


def test_there_is_no_planner_tier_and_the_pilot_stops_at_the_pilot_cap(tmp_path, monkeypatch):
    assert P.TIERS == ("fast", "fast-low") and not hasattr(cli, "planner_allowed")
    from evals.study_roles import budget_roles as B
    assert (B.CAP_USD, B.PILOT_CAP_USD) == (8.0, 2.0)
    monkeypatch.setattr(cli, "GO_FILE", tmp_path / "GO")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    (tmp_path / "GO").write_text("ok")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    d = tmp_path / "results" / "programmer" / "pilot_fast"
    d.mkdir(parents=True)
    (d / "cost.json").write_text(json.dumps({"usd_this_run": 1.99}))
    assert B.pilot_spent_usd(tmp_path / "results") == 1.99
    assert cli.cmd_pilot(SimpleNamespace(role="data-analyst", tier="fast-low", pace=2.0, cap=None, poll=3.0, workers=1)) == 2         # US$2 used: refused, stop and report


def test_the_pilot_hard_stop_is_inside_the_total_cap():
    from evals.study_roles.budget_roles import RolesBudget
    b = RolesBudget(carried=3.0, cap_usd=min(8.0, 3.0 + 2.0))
    assert b.can_start_participant(0)
    b.charge("p", "decide", 0, 0)
    with __import__("pytest").raises(Exception) as ei:
        b.charge("p", "decide", 1_000_000, 1_000_000)          # at the conservative prices this passes US$5
    assert type(ei.value).__name__ == "BudgetExhausted"
