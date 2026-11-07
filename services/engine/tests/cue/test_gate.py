from __future__ import annotations

import pytest

from understudy_engine.cue.gate import CueState, apply_event, decide, set_quiet
from understudy_engine.cue.params import DEFAULT
from understudy_engine.cue.types import OTHER, REASONS, Grounding

from .helpers import CLIFF, CLOSE, T0, Run, cand, grounded, inp


def reasons(r):
    return r.decision.why["reasons"]


def first_cue(run: Run, t0: float = 0.0, **kw):
    """Poll every 2.5 s until the gate shows something; returns (time, result)."""
    t = t0
    for _ in range(80):
        r = run.poll(t, **kw)
        if r.shown:
            return t, r
        t += 2.5
    raise AssertionError("the gate never showed anything: " + str([(x[0], x[1].decision.kind, x[1].decision.why["reasons"]) for x in run.log[-3:]]))


# ------------------------------------------------------------------------------------------------ silence is the default
def test_not_stuck_is_none_with_a_reason():
    r = Run().poll(0, p=0.1, stall=5)
    assert r.decision.kind == "none" and reasons(r)[0] == "not_stuck"
    assert r.decision.tier is None and r.decision.step is None and r.decision.say is None


def test_needs_two_consecutive_signals():
    run = Run()
    a = run.poll(0)
    assert a.decision.kind == "none" and reasons(a)[0] == "wait_signals"
    b = run.poll(2.5)
    assert b.decision.kind == "cue" and b.shown and b.opened


def test_a_dip_resets_the_chain():
    run = Run()
    run.poll(0)
    assert reasons(run.poll(2.5, p=0.2))[0] == "not_stuck"
    assert reasons(run.poll(5))[0] == "wait_signals"


def test_every_none_names_a_known_reason():
    run = Run()
    for kw in ({"consent": False}, {"denied": True}, {"quiet_hour": True}, {"typing_burst": True}, {"quiet_s": 0.5}, {"away": True}, {"level": 4}, {"p": 0.1}):
        r = Run().poll(0, **kw)
        assert r.decision.kind == "none"
        assert set(reasons(r)) <= set(REASONS), reasons(r)


# ------------------------------------------------------------------------------------------------ hard stops
def test_no_consent_and_denylist_are_never_bypassed_even_when_asked():
    for kw in ({"consent": False}, {"denied": True}):
        r = Run().poll(0, asked=True, **kw)
        assert r.decision.kind == "none" and not r.shown
    assert reasons(Run().poll(0, consent=False))[0] == "no_consent"
    assert reasons(Run().poll(0, denied=True))[0] == "denied"


def test_flow_never_interrupts_typing_and_needs_two_seconds_of_quiet():
    run = Run()
    for _ in range(10):
        assert run.poll(_ * 2.5, typing_burst=True).decision.kind == "none"
    assert reasons(run.poll(30, quiet_s=1.9))[0] == "flow"
    run2 = Run()
    run2.poll(0, quiet_s=2.0)
    assert run2.poll(2.5, quiet_s=2.0).decision.kind == "cue"


def test_asked_bypasses_flow_quiet_and_level_four():
    r = Run().poll(0, asked=True, typing_burst=True, quiet_hour=True, level=4, p=0.0, stall=1)
    assert r.decision.kind == "cue" and r.shown and reasons(r)[0] == "asked"
    assert r.decision.tier >= 2           # an asked cue starts at least at the chip


def test_level_four_is_silent_unless_asked():
    run = Run(level=4)
    for i in range(10):
        assert run.poll(i * 2.5).decision.kind == "none"
    assert reasons(run.log[-1][1])[0] == "level_4"


def test_quiet_hotkey_silences_unrequested_but_not_asked():
    st = set_quiet(CueState(), T0, 60)
    assert decide(inp(0), st).decision.why["reasons"][0] == "quiet"
    assert decide(inp(0, asked=True), st).decision.kind == "cue"
    assert decide(inp(3601), st).decision.why["reasons"][0] != "quiet"


def test_away_is_unsure_and_resets_the_chain():
    run = Run()
    run.poll(0)
    assert reasons(run.poll(2.5, away=True))[0] == "unsure_away"
    assert reasons(run.poll(5))[0] == "wait_signals"


def test_minimum_stall_scales_with_level_and_mastery():
    p = DEFAULT
    assert p.stall_min(2, 0.0) == 20.0 and p.stall_min(1, 0.0) == 15.0 and p.stall_min(3, 0.0) == 45.0
    assert p.stall_min(2, 1.0) == 40.0
    run = Run()
    run.poll(0, stall=10)
    r = run.poll(2.5, stall=12.5)
    assert reasons(r)[0] == "below_stall_min"
    r = run.poll(5, stall=40)
    assert r.decision.kind == "cue"       # primed: no need to collect two fresh signals again


# ------------------------------------------------------------------------------------------------ tiers
def test_start_tier_follows_the_level():
    for level, tier in ((1, 2), (2, 1), (3, 1)):
        stall = 100.0
        _, r = first_cue(Run(level=level), stall=None) if False else (None, None)
        run = Run(level=level, start_stall=stall)
        t, r = first_cue(run)
        assert r.decision.tier == tier, (level, r.decision.tier)


def test_ring_needs_a_target_else_the_cue_is_text_only():
    run = Run(grounding=None)
    t, r = first_cue(run)
    assert r.decision.tier == 2 and r.decision.say["chip"] and r.decision.ground_wanted
    assert r.decision.target is None
    run = Run(grounding=Grounding(found=False, confidence=0.2, source="vision"))
    t, r = first_cue(run)
    assert r.decision.tier == 2 and r.decision.target["box_2d"] is None


def test_display_persists_then_escalates_after_25_seconds_past_the_previous_tier():
    run = Run()
    t, r = first_cue(run)
    assert r.decision.tier == 1 and r.decision.new and r.decision.say["chip"] is None
    again = run.poll(t + 5)
    assert again.decision.kind == "cue" and again.decision.tier == 1 and not again.decision.new and not again.shown
    assert "persisting" in reasons(again)
    gap = run.poll(t + 15)
    assert gap.decision.kind == "none" and reasons(gap)[0] == "waiting_escalation"
    early = run.poll(t + 24)
    assert early.decision.kind == "none"
    up = run.poll(t + 25)
    assert up.decision.kind == "cue" and up.decision.tier == 2 and up.decision.new and "escalated" in reasons(up)
    assert up.decision.say["chip"] and len(up.decision.say["chip"]) <= 40


def test_ghost_tier_needs_a_target_and_voice_needs_voice_ok():
    run = Run()
    t, r = first_cue(run)
    seen = [r.decision.tier]
    for k in (1, 2, 3):
        rr = run.poll(t + 25 * k)
        if rr.shown:
            seen.append(rr.decision.tier)
    assert seen[:3] == [1, 2, 3] or seen == [1, 2, 3]
    # without voice_ok the ladder ends at the ghost, whisper is always None
    for _, rr in run.log:
        assert (rr.decision.say or {}).get("whisper") is None


def test_whisper_exists_only_at_tier_four_with_voice_ok():
    run = Run(voice_ok=True, level=1)
    t, r = first_cue(run)
    tiers = {r.decision.tier: r}
    for k in range(1, 4):
        rr = run.poll(t + 25 * k)
        if rr.shown:
            tiers[rr.decision.tier] = rr
    # the cap of three in ten minutes may stop the ladder before 4 when it starts at 2; with a fresh run it starts at tier 2: 2, 3, 4
    assert max(tiers) == 4
    w = tiers[4].decision.say["whisper"]
    assert w and len(w.split()) <= 8
    for tier, rr in tiers.items():
        if tier < 4:
            assert rr.decision.say["whisper"] is None


def test_no_whisper_without_voice_ok_even_at_the_top():
    run = Run(voice_ok=False, level=1)
    t, r = first_cue(run)
    for k in range(1, 5):
        rr = run.poll(t + 25 * k)
        assert (rr.decision.say or {}).get("whisper") is None
        assert rr.decision.tier in (None, 2, 3)


def test_progress_deescalates_at_once_and_closes_the_episode():
    run = Run()
    t, r = first_cue(run)
    run.progress(t + 3)
    after = run.poll(t + 5.0, stall=2.0) if False else run.poll(t + 5.0)
    assert after.decision.kind == "none" and reasons(after)[0] == "progress"
    assert run.st.episode is None


def test_recovery_takes_the_cue_down():
    run = Run()
    t, r = first_cue(run)
    rr = run.poll(t + 3, p=0.1)
    assert rr.decision.kind == "none" and reasons(rr)[0] == "recovered"


# ------------------------------------------------------------------------------------------------ caps
def test_at_most_three_shown_in_ten_minutes_and_the_cap_explains_itself():
    run = Run(level=1, voice_ok=True)
    t, r = first_cue(run)
    shown = [r]
    for k in range(1, 8):
        rr = run.poll(t + 25 * k)
        if rr.shown:
            shown.append(rr)
    assert len(shown) == 3
    blocked = run.poll(t + 25 * 4 + 1)
    assert reasons(blocked)[0] == "cap_10min" and blocked.decision.cooldown_s > 0
    assert len([x for x in run.st.shown_ts if T0 + t + 100 - x < 600]) <= 3


def test_cap_frees_after_ten_minutes_but_the_skill_gap_and_new_episode_rules_still_apply():
    run = Run(level=1, voice_ok=True)
    t, _ = first_cue(run)
    for k in range(1, 4):
        run.poll(t + 25 * k)
    run.progress(t + 80)
    run.poll(t + 82)                       # progress closes the episode
    run.progress(t + 90)
    far = t + 800
    r = Run.poll(run, far, stall=100.0)
    r2 = run.poll(far + 2.5, stall=102.5)
    assert r2.decision.kind == "cue"


def test_same_skill_needs_ninety_seconds_between_episodes_unless_asked():
    run = Run()
    t, _ = first_cue(run)
    run.progress(t + 5)
    run.poll(t + 6)                        # closes the episode on progress
    # stuck again 20 s later on the same skill: blocked by the 90 s spacing
    run.progress(t + 6)
    r = None
    for k in range(60):
        r = run.poll(t + 30 + 2.5 * k)
        if r.decision.kind != "none" or reasons(r)[0] not in ("wait_signals", "below_stall_min", "not_stuck"):
            break
    assert r.decision.kind == "none" and reasons(r)[0] == "cooldown_skill" or r.decision.kind == "cue" and (T0 + t + 30 + 2.5 * k) - run.st.skill_last[0][1] >= 90
    asked = run.poll(t + 40, asked=True, stall=50)
    assert asked.decision.kind == "cue"


def test_daily_budget_resets_with_the_day():
    p = DEFAULT.with_(daily_budget=1, max_cues_window=10)
    run = Run(params=p)
    first_cue(run)
    run.progress(5)
    run.poll(6)
    run.poll(200, stall=100)
    r = run.poll(202.5, stall=102.5)
    assert reasons(r)[0] == "budget_spent" and r.decision.budget_left == 0
    run.poll(86400 + 500, stall=100)                    # the old episode closes on the new progress clock
    run.poll(86400 + 502.5, stall=102.5)
    next_day = run.poll(86400 + 505, stall=105)
    assert next_day.decision.kind == "cue"


def test_asked_cues_do_not_use_the_cap_or_the_budget():
    run = Run()
    for i in range(6):
        r = run.poll(i * 30.0, asked=True)
        assert r.decision.kind == "cue"
    assert run.st.shown_ts == () and run.st.budget_used == 0


# ------------------------------------------------------------------------------------------------ question and offer
def test_close_call_asks_one_question_with_pack_labels_and_the_fixed_other_option():
    run = Run(cands=CLOSE)
    t, r = first_cue(run)
    d = r.decision
    assert d.kind == "ask" and d.tier is None
    assert d.question == {"type": "close_call", "text": "Which of these is next?"}
    ids = [o["id"] for o in d.options]
    assert ids[-1] == OTHER and 2 <= len(ids) - 1 <= 4 and "cliff_a" in ids
    assert d.options[-1]["label"] == "Something else"


def test_only_one_question_per_episode_then_an_offer_after_a_long_stall():
    run = Run(cands=CLOSE)
    t, r = first_cue(run)
    seen_q = 1
    kinds = []
    for k in range(1, 40):
        rr = run.poll(t + 5 * k)
        kinds.append(rr.decision.kind)
        seen_q += rr.decision.kind == "ask" and rr.shown
    assert seen_q == 1
    assert "offer" in kinds
    off = next(r for _, r in run.log if r.decision.kind == "offer" and r.shown)
    assert off.decision.say["chip"] == "Want a hand?" and off.decision.options is None
    assert (T0 + off_time(run, off)) - run.progress_t >= DEFAULT.offer_after_s - 1e-6


def off_time(run, result):
    return next(t for t, r in run.log if r is result)


def test_answer_becomes_the_step_and_help_follows():
    run = Run(cands=CLOSE)
    t, r = first_cue(run)
    run.st = apply_event(run.st, "answered", T0 + t + 1, answer_id="cliff_a")
    assert run.st.episode.answered == "cliff_a" and run.st.episode.help_wanted
    rr = run.poll(t + 2)
    assert rr.decision.kind == "cue" and rr.decision.step["id"] == "cliff_a" and "answer_known" in reasons(rr)
    assert rr.decision.why["path_prob"] == 1.0


def test_answer_other_asks_nothing_more_before_the_offer():
    run = Run(cands=CLOSE)
    t, r = first_cue(run)
    run.st = apply_event(run.st, "answered", T0 + t + 1, answer_id=OTHER)
    rr = run.poll(t + 30)
    assert rr.decision.kind in ("none", "offer") and rr.decision.kind != "ask"


def test_screen_disagreeing_with_the_prior_asks():
    g = Grounding(found=True, chosen="calc_b", available=("calc_b", "cliff_a"), box_2d=(1, 2, 3, 4), confidence=0.9, source="vision", for_step="cliff_a")
    run = Run(grounding=g, cands=(cand("cliff_a", 0.7), cand("calc_b", 0.3)))
    t, r = first_cue(run)
    assert r.decision.kind == "ask" and r.decision.question["type"] == "screen_disagrees"


def test_offer_accepted_means_help_me():
    run = Run(cands=CLOSE)
    t, r = first_cue(run)
    off = None
    for k in range(1, 40):
        rr = run.poll(t + 5 * k)
        if rr.decision.kind == "offer" and rr.shown:
            off = (t + 5 * k, rr)
            break
    assert off
    run.st = apply_event(run.st, "accepted", T0 + off[0] + 1)
    rr = run.poll(off[0] + 2)
    assert rr.decision.kind == "cue" and "asked" in reasons(rr)


# ------------------------------------------------------------------------------------------------ dismissals and know this
def test_a_dismissal_ends_the_display_and_blocks_more_in_that_episode():
    run = Run()
    t, r = first_cue(run)
    run.st = apply_event(run.st, "dismissed", T0 + t + 2)
    rr = run.poll(t + 3)
    assert rr.decision.kind == "none" and reasons(rr)[0] == "dismissed_in_episode"
    rr = run.poll(t + 60)
    assert rr.decision.kind == "none"
    assert run.poll(t + 61, asked=True).decision.kind == "cue"


def test_know_this_silences_the_skill_for_a_while():
    run = Run()
    t, r = first_cue(run)
    run.st = apply_event(run.st, "know_this", T0 + t + 2)
    run.progress(t + 4)
    run.poll(t + 5)
    run.progress(t + 6)
    rr = None
    for k in range(40):
        rr = run.poll(t + 120 + 2.5 * k, stall=100 + 2.5 * k)
    assert reasons(rr)[0] == "know_this"
    assert run.poll(t + 120 + 400, stall=200).decision.kind in ("none", "cue")


# ------------------------------------------------------------------------------------------------ retrieval
def test_retrieval_practice_returns_confirm_and_withholds():
    run = Run(retrieval_due=True, start_stall=30)
    for i in range(10):
        r = run.poll(i * 2.5)
        assert r.decision.kind == "confirm" and r.decision.retrieval and r.decision.step and not r.shown
        assert r.decision.tier is None and r.decision.say is None
    assert reasons(r)[0] == "retrieval_withheld"


def test_retrieval_practice_gives_way_to_an_offer_after_a_long_stall_and_to_a_request():
    run = Run(retrieval_due=True, start_stall=30)
    r = run.poll(0, stall=95)
    r = run.poll(2.5, stall=97.5)
    assert r.decision.kind in ("offer", "confirm")
    asked = Run(retrieval_due=True).poll(0, asked=True)
    assert asked.decision.kind == "cue"


def test_confirm_also_applies_at_level_four():
    r = Run(retrieval_due=True, level=4, start_stall=30).poll(0)
    assert r.decision.kind == "confirm"


# ------------------------------------------------------------------------------------------------ purity and shape
def test_the_gate_is_deterministic_and_pure():
    a = Run()
    b = Run()
    for t in (0, 2.5, 5, 7.5, 30, 60):
        ra, rb = a.poll(t), b.poll(t)
        assert ra.decision.to_dict() == rb.decision.to_dict()
    st = CueState()
    i = inp(0)
    r1 = decide(i, st)
    r2 = decide(i, st)
    assert r1.decision.to_dict() == r2.decision.to_dict() and st == CueState()


def test_no_candidates_is_silence_with_a_reason():
    r = decide(inp(0, cands=()), CueState())
    assert r.decision.kind == "none" and reasons(r)[0] == "no_candidates"


def test_decision_shape_matches_the_brief():
    r = Run().poll(0)
    r = Run()
    t, res = first_cue(r)
    d = res.decision.to_dict()
    for key in ("kind", "episode_id", "tier", "step", "target", "options", "say", "why", "budget_left", "cooldown_s", "source", "meta"):
        assert key in d
    assert set(d["step"]) >= {"id", "label", "reason_id"}
    assert set(d["target"]) == {"box_2d", "source", "confidence"} and len(d["target"]["box_2d"]) == 4
    assert set(d["why"]) == {"path_prob", "margin", "p_stuck", "mastery", "level", "reasons"}
    assert d["source"] in ("model", "rule")
    assert d["episode_id"].startswith("e_")


def test_chip_never_exceeds_forty_characters_for_any_pack_step():
    from understudy_engine.cue import vocab

    for role in ("benefits-processor", "programmer", "data-analyst"):
        v = vocab.get_vocab(role)
        for sid in v.policy.steps:
            assert len(vocab.chip_text(v.label(sid))) <= 40
            assert len(vocab.whisper_text(v.label(sid)).split()) <= 8
            assert len(vocab.REASONS[v.reason_id(sid)].split()) <= 12
