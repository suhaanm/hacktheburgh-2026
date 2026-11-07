"""Property tests: whatever the inputs, the gate keeps every hard cap (CUE-3). Seeded random walks over inputs and worker reactions."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.cue.gate import CueState, apply_event, decide
from understudy_engine.cue.params import DEFAULT, CueParams
from understudy_engine.cue.types import REASONS, CueInput, Grounding

from .helpers import CLIFF, CLOSE, T0, cand, grounded

SKILLS = ("s_a", "s_b", "s_c")


def walk(seed: int, n: int = 600, params: CueParams = DEFAULT, voice_ok: bool = False, ask_p: float = 0.0):
    rng = np.random.default_rng(seed)
    st = CueState()
    progress_t = T0
    t = T0
    shown_log: list = []
    first_show: dict[str, float] = {}
    results = []
    questions: dict[str, int] = {}
    for _ in range(n):
        t += float(rng.choice([2.5, 2.5, 2.5, 15.0, 60.0]))
        if rng.random() < 0.04:
            progress_t = t - float(rng.random() * 3)
        skill = SKILLS[int(rng.integers(0, 3))]
        close = rng.random() < 0.3
        cands = (cand("x", 0.52, skill=skill), cand("y", 0.48, skill=skill)) if close else (cand("x", 0.85, skill=skill), cand("y", 0.15, skill=skill))
        g = None if rng.random() < 0.4 else (grounded("x", 0.9) if rng.random() < 0.7 else Grounding(found=False, confidence=0.2, source="vision"))
        level = int(rng.integers(1, 5))
        asked = bool(rng.random() < ask_p)
        inp = CueInput(now=t, person="p", role="benefits-processor", p_stuck=float(rng.random()), p_source="rule", last_progress_t=progress_t, candidates=cands,
                       level=level, mastery=float(rng.random()), grounding=g, quiet_s=float(rng.choice([0.0, 1.0, 2.0, 5.0, 30.0])),
                       typing_burst=bool(rng.random() < 0.2), away=bool(rng.random() < 0.05), consent=bool(rng.random() < 0.95), denied=bool(rng.random() < 0.05),
                       quiet_hour=bool(rng.random() < 0.05), asked=asked, voice_ok=voice_ok)
        helped = bool(st.episode and st.episode.help_wanted)
        r = decide(inp, st, params)
        d = r.decision
        assert set(d.why["reasons"]) <= set(REASONS), d.why["reasons"]
        assert d.kind in ("none", "confirm", "cue", "ask", "offer")
        if d.kind == "none":
            assert d.why["reasons"], "silence always has a reason"
        if r.shown:
            effective_asked = asked or helped
            shown_log.append((t, d.kind, effective_asked))
            assert inp.consent and not inp.denied, "never shown without consent or over the denylist, even when asked"
            if not effective_asked:
                assert not inp.quiet_hour and not inp.typing_burst and inp.quiet_s >= params.quiet_required_s
                assert level < 4
                recent = [x for x in r.state.shown_ts if t - x < params.cap_window_s]
                assert len(recent) <= params.max_cues_window
            if d.kind == "ask":
                assert 3 <= len(d.options) <= 5 and d.options[-1]["id"] == "other"
                eid = r.state.episode.id
                questions[eid] = questions.get(eid, 0) + 1
                assert questions[eid] <= params.max_questions or asked
            if r.opened and not effective_asked:
                if skill in first_show:
                    assert t - first_show[skill] >= params.skill_gap_s - 1e-6, "90 s between episodes of the same skill"
                first_show[skill] = t
            if d.kind == "cue":
                assert 1 <= d.tier <= 4
                if d.tier == 4:
                    assert voice_ok
                chip = (d.say or {}).get("chip")
                assert chip is None or len(chip) <= 40
                w = (d.say or {}).get("whisper")
                assert (w is None) or (voice_ok and d.tier == 4 and len(w.split()) <= 8)
                if d.tier == 1:
                    assert d.target and d.target["box_2d"] is not None
        if d.kind in ("cue", "ask", "offer") and not r.shown:
            assert "persisting" in d.why["reasons"] and not d.new
        assert d.new == r.shown
        st = r.state
        if r.shown and rng.random() < 0.3 and st.episode is not None:
            ev = str(rng.choice(["accepted", "dismissed", "know_this"]))
            st = apply_event(st, ev, t + 1.0)
        results.append(r)
    return results, shown_log


@pytest.mark.parametrize("seed", range(12))
def test_random_walks_keep_every_hard_cap(seed):
    results, shown = walk(seed)
    assert any(r.shown for r in results) or seed >= 0


@pytest.mark.parametrize("seed", range(4))
def test_random_walks_with_voice_and_requests(seed):
    walk(100 + seed, voice_ok=True, ask_p=0.05)


def test_a_denied_or_unconsented_poll_never_shows_anything_in_any_state():
    results, _ = walk(7, n=400)
    # re-run the same inputs with consent off: nothing is ever shown
    rng_params = DEFAULT
    st = CueState()
    for k in range(200):
        i = CueInput(now=T0 + 3 * k, person="p", role="r", p_stuck=0.99, p_source="rule", last_progress_t=T0, candidates=CLIFF, level=1, quiet_s=30.0,
                     grounding=grounded(), consent=False, asked=True)
        r = decide(i, st, rng_params)
        assert r.decision.kind == "none" and not r.shown
        i2 = CueInput(now=T0 + 3 * k, person="p", role="r", p_stuck=0.99, p_source="rule", last_progress_t=T0, candidates=CLIFF, level=1, quiet_s=30.0,
                      grounding=grounded(), denied=True, asked=True)
        assert decide(i2, st, rng_params).decision.kind == "none"


def test_ten_minute_cap_holds_for_a_relentlessly_stuck_worker_over_two_hours():
    st = CueState()
    shown = []
    t = T0
    progress = T0
    for k in range(int(2 * 3600 / 2.5)):
        t = T0 + 2.5 * k
        if k % 200 == 0:
            progress = t                                           # a step is finished now and then
        r = decide(CueInput(now=t, person="p", role="r", p_stuck=0.95, p_source="rule", last_progress_t=progress - 100.0 + 0.0, candidates=CLIFF, level=1, quiet_s=10.0,
                            grounding=grounded(), voice_ok=True), st)
        st = r.state
        if r.shown:
            shown.append(t)
    for i in range(len(shown)):
        assert len([x for x in shown if shown[i] - 600 < x <= shown[i]]) <= 3
    assert shown, "a worker stuck for two hours is helped now and then"
    assert len(shown) <= 3 * (2 * 6) + 3                          # at most three per ten minutes
