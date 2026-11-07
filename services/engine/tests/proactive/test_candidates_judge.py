"""Candidates and the judge: shapes, ranges, the cap, 'fewer, even zero', explainability, acceptance learning."""
from __future__ import annotations

import pytest

from understudy_engine.proactive import judge as J
from understudy_engine.proactive.acceptance import AcceptanceModel
from understudy_engine.proactive.candidates import (
    Candidate, Ctx, FireSpec, Reading, automate_candidates, calendar_candidates, card_id, collect, git_candidates, practice_candidates,
    agent_candidates,
)
from understudy_engine.proactive.text import safe_numbers

from .conftest import NOW, P, cal_row, git_row, make_readers, routine_row, run_row, skill_row

CTX = Ctx(person=P, now=NOW)


def test_automate_candidate_from_a_proposed_routine():
    [c] = automate_candidates(CTX, Reading([routine_row()]))
    assert c.kind == "automate" and c.risk_class == "normal" and c.fire.type == "queue"
    assert 0 < c.value <= 1 and 0 <= c.urgency <= 1 and 0 <= c.freshness <= 1
    assert c.numbers["episodes"] == 14 and c.numbers["hours_saved_lo"] == 3.1 and c.numbers["buy_now"] is True
    assert "routines" in c.source_tags
    assert c.subject == "routine:calc-entry-3x" and c.id == card_id(P, "automate", c.subject)


@pytest.mark.parametrize("kw", [{"status": "shadow"}, {"status": "approval"}, {"status": "declined"}, {"status": "never"},
                                {"proposable": False}, {"automatable": False}, {"hours_lo": 0.0, "hours_hi": 0.0}])
def test_automate_skips_what_is_not_on_offer(kw):
    assert automate_candidates(CTX, Reading([routine_row(**kw)])) == []


def test_practice_follows_teaching_order_and_skips_fluent_skills():
    rows = [skill_row(id="a", order=1, level=4, prerequisites=[]),
            skill_row(id="b", order=2, level=1, prerequisites=["a"], label="Second"),
            skill_row(id="c", order=3, level=1, prerequisites=["b"], label="Third")]
    out = practice_candidates(CTX, Reading(rows))
    # a is already level 4; c waits behind b (a prerequisite still at level 1)
    assert [c.subject for c in out] == ["skill:b"]


def test_practice_notes_when_a_skill_unlocks_an_automation():
    routines = Reading([routine_row(proposable=False, skill_gate_ok=False, skill_cogs=["CHECK_CLIFF"])])
    [c] = practice_candidates(CTX, Reading([skill_row()]), routines)
    assert c.numbers["unlocks_automation"] is True and "routines" in c.source_tags
    [plain] = practice_candidates(CTX, Reading([skill_row()]))
    assert c.value > plain.value


def test_calendar_and_git_candidates_use_our_words_not_theirs():
    [c] = calendar_candidates(CTX, Reading([cal_row(text="Meeting with CANARY_NAME about the merger")]))
    assert c.title == "Protect a focus block" and c.kind == "focus_block" and c.fire.type == "draft" and c.risk_class == "outward"
    assert "CANARY" not in c.why and "CANARY" not in repr(c.to_dict())
    [g] = git_candidates(CTX, Reading([git_row(label="fix: CANARY_COMMIT message")]))
    assert g.kind == "git_habit" and g.fire.type == "agent" and g.fire.payload_ref["agent_kind"] == "programming.commit_analyst"
    assert "CANARY" not in repr(g.to_dict())


def test_a_habit_inside_the_noise_is_worth_little():
    [sig] = git_candidates(CTX, Reading([git_row()]))
    [noise] = git_candidates(CTX, Reading([git_row(ci=[-50.0, 90.0])]))
    assert sig.value > 0.5 > noise.value


def test_agent_result_only_for_finished_unviewed_runs():
    out = agent_candidates(CTX, Reading([run_row(), run_row(run_id="r_2", viewed=True), run_row(run_id="r_3", state="running")]))
    assert [c.subject for c in out] == ["run:r_bg_001"]


def test_numbers_keep_only_plain_values():
    n = safe_numbers({"ok": 3, "ratio": 0.12345, "flag": True, "tok": "lt5", "Bad Key": 1, "text": "Meeting with Alice about layoffs",
                      "nested": {"a": 1}, "lst": [1], "nan": float("nan")})
    assert n == {"ok": 3, "ratio": 0.123, "flag": True, "tok": "lt5"}


def test_an_irreversible_card_cannot_start_a_run():
    with pytest.raises(ValueError):
        Candidate(kind="git_habit", title="t", why="w", numbers={}, source_tags=[], risk_class="irreversible", value=1, urgency=1,
                  freshness=1, prepared_template={}, fire=FireSpec("agent", {}), subject="x", person=P)


def test_unknown_kind_and_fire_type_are_refused():
    with pytest.raises(ValueError):
        FireSpec("auto_approve")
    with pytest.raises(ValueError):
        Candidate(kind="spam", title="t", why="w", numbers={}, source_tags=[], risk_class="normal", value=1, urgency=1, freshness=1,
                  prepared_template={}, fire=FireSpec("queue"), subject="x")


def test_collect_survives_missing_and_broken_sources():
    readers = make_readers(routines=[routine_row()], available={"calendar": False, "git": False})

    def boom(ctx):
        raise RuntimeError("source blew up with CANARY_TEXT")

    readers.runs = boom
    got = collect(CTX, readers)
    assert {c.kind for c in got.candidates} == {"automate"}
    assert got.diagnostics["calendar"]["available"] is False and got.diagnostics["runs"]["available"] is False
    assert "CANARY" not in repr(got.diagnostics)


# ----------------------------------------------------------------------------------------------- judge
def _cand(i: int, kind: str = "automate", value: float = 0.8, urgency: float = 0.8, freshness: float = 0.8, effort: float = 0.2) -> Candidate:
    return Candidate(kind=kind, title=f"t{i}", why="w", numbers={"i": i}, source_tags=["routines"], risk_class="normal", value=value,
                     urgency=urgency, freshness=freshness, prepared_template={}, fire=FireSpec("queue"), subject=f"s{i}", person=P, effort=effort)


P40 = lambda kind: 0.4  # noqa: E731


def test_cap_of_three_always_holds_and_the_best_win():
    cands = [_cand(i, kind=k, value=v) for i, (k, v) in enumerate([("automate", .9), ("practice", .8), ("focus_block", .7), ("git_habit", .95),
                                                                     ("agent_result", .85), ("automate", .6), ("practice", .99)])]
    res = J.rank(cands, p_accept=P40, now_ts=NOW.timestamp())
    assert len(res.selected) == 3
    scores = [r.score for r in res.selected]
    assert scores == sorted(scores, reverse=True)
    assert res.counts().get("over_cap", 0) + res.counts().get("kind_limit", 0) == 4


def test_fewer_even_zero_when_nothing_is_worth_it():
    weak = [_cand(i, value=0.1, urgency=0.1, freshness=0.2, effort=0.5) for i in range(5)]
    res = J.rank(weak, p_accept=P40, now_ts=NOW.timestamp())
    assert res.selected == [] and res.counts() == {"below_threshold": 5}
    assert J.rank([], p_accept=P40, now_ts=NOW.timestamp()).selected == []


def test_one_kind_cannot_crowd_the_morning():
    cands = [_cand(i, kind="practice", value=0.9) for i in range(4)]
    res = J.rank(cands, p_accept=P40, now_ts=NOW.timestamp())
    assert len(res.selected) == 1 and res.counts()["kind_limit"] == 3


def test_every_decision_is_explainable_and_the_parts_add_up():
    [r] = J.rank([_cand(1)], p_accept=P40, now_ts=NOW.timestamp()).selected
    e = r.explain()
    assert e["decision"] == "selected" and e["rank"] == 1
    assert abs(sum(p["contribution"] for p in e["parts"].values()) - e["score"]) < 1e-3
    assert set(e["parts"]) == {"value", "urgency", "freshness", "acceptance", "effort"}
    assert abs(sum(J.WEIGHTS.values()) - 1.0) < 1e-9


def test_suppressed_subjects_are_not_raised_again():
    c = _cand(1)
    soon = {"s1": {"until": NOW.timestamp() + 3600, "reason": "not_now"}}
    gone = {"s1": {"until": None, "reason": "never"}}
    past = {"s1": {"until": NOW.timestamp() - 1, "reason": "not_now"}}
    assert J.rank([c], p_accept=P40, now_ts=NOW.timestamp(), suppress=soon).counts() == {"suppressed": 1}
    assert J.rank([c], p_accept=P40, now_ts=NOW.timestamp() + 10 ** 9, suppress=gone).counts() == {"suppressed": 1}
    assert len(J.rank([c], p_accept=P40, now_ts=NOW.timestamp(), suppress=past).selected) == 1


def test_ranking_is_deterministic():
    cands = [_cand(i, value=0.7) for i in range(3)]       # exact ties
    a = [r.candidate.id for r in J.rank(cands, p_accept=P40, now_ts=0).selected]
    b = [r.candidate.id for r in J.rank(list(reversed(cands)), p_accept=P40, now_ts=0).selected]
    assert a == b


def test_pinned_cards_keep_their_slot_even_below_the_threshold():
    weak = _cand(1, value=0.05, urgency=0.05, freshness=0.1, effort=0.6)
    res = J.rank([weak], p_accept=P40, now_ts=0, pinned={weak.id})
    assert len(res.selected) == 1 and res.selected[0].pinned


# ----------------------------------------------------------------------------------------------- acceptance (PRO-3)
def test_declines_are_labels_that_lower_the_estimate_for_that_kind_only():
    m = AcceptanceModel()
    base = m.p("practice")
    assert abs(base - 0.4) < 1e-9                              # the role prior Beta(2, 3)
    for _ in range(4):
        m.observe("practice", False)
    assert m.p("practice") < base - 0.1
    assert m.p("automate") < base and m.p("automate") > m.p("practice")     # shrunk toward the overall rate, not buried
    for _ in range(6):
        m.observe("automate", True)
    assert m.p("automate") > 0.5
    s = m.summary()
    assert s["labels"] == 10 and s["by_kind"]["practice"]["declined"] == 4


def test_learned_acceptance_moves_the_ranking():
    lo = _cand(1, kind="practice", value=0.5, urgency=0.4, freshness=0.5)
    m = AcceptanceModel()
    before = J.score_candidate(lo, m.p("practice"))[0]
    for _ in range(5):
        m.observe("practice", False)
    assert J.score_candidate(lo, m.p("practice"))[0] < before
